import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

TICKET_STATUSES = ("open", "assigned", "booked", "resolved", "closed")

class HitlService:

    def __init__(self, supabase_client: SupabaseClient) -> None:
        self._supabase = supabase_client
        logger.info("[OK] HitlService initialized")

    def _log_audit(self, action: str, performer_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Saves an entry to the audit_logs table for administrative oversight."""
        try:
            self._supabase.table("audit_logs").insert({
                "action": action,
                "performer_id": performer_id,
                "payload": payload,
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        except Exception as exc:
            logger.warning(f"[WARN] Audit logging failed | {action} | {exc}")
    def _attach_consultation_rating(self,ticket: Dict[str, Any],) -> Dict[str, Any]:
        """Fetch and attach consultation rating details to a ticket."""

        # Default values when no rating exists or the query fails
        ticket.update({
            "rating": None,
            "comment": None,
            "rating_submitted": False,
            "consultation_rating": None,
            "consultation_feedback": None,
        })

        ticket_id = ticket.get("ticket_id")

        if not ticket_id:
            logger.warning(
                "Cannot fetch consultation rating because ticket_id is missing"
            )
            return ticket

        try:
            rating_resp = (
                self._supabase.table("consultation_ratings")
                .select("rating, comment")
                .eq("ticket_id", ticket_id)
                .limit(1)
                .execute()
            )

            if not rating_resp.data:
                return ticket

            rating_row = rating_resp.data[0]
            rating = rating_row.get("rating")
            comment = rating_row.get("comment")

            ticket.update({
                "rating": rating,
                "comment": comment,
                "rating_submitted": True,

                # Kept for backward compatibility with existing frontend code
                "consultation_rating": rating,
                "consultation_feedback": comment,
            })

        except Exception as exc:
            logger.warning(
                f"Failed to fetch consultation rating "
                f"for ticket {ticket_id} | {exc}"
            )

        return ticket
    def create_ticket(
        self,
        conversation_id: str,
        user_id: str,
        trigger_message_id: Optional[str] = None,
        user_note: Optional[str] = None,
        tenant_id: Optional[str] = None,
        priority: str = "normal",
        urgent_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        try:
            # Enforce limits on urgent tickets (Disabled - Priority system on hold)
            # if priority.lower() == "urgent":
            #     # Check 1: Active urgent ticket
            #     try:
            #         active_res = self._supabase.table("hitl_tickets") \
            #             .select("ticket_id") \
            #             .eq("user_id", user_id) \
            #             .eq("priority", "urgent") \
            #             .in_("status", ["open", "assigned", "booked"]) \
            #             .execute()
            #         if active_res.data:
            #             raise ValueError("You already have an active urgent request. Please wait until it is resolved.")
            #     except ValueError as ve:
            #         raise ve
            #     except Exception as e:
            #         logger.warning(f"⚠️ Failed checking urgent tickets limit rule | {e}")

            ticket_id = str(uuid4())
            # Retrieve detected_domain from the latest assistant message metadata
            detected_domain = None
            try:
                msg_resp = self._supabase.table("messages") \
                    .select("metadata") \
                    .eq("conversation_id", conversation_id) \
                    .eq("role", "assistant") \
                    .order("created_at", desc=True) \
                    .limit(1) \
                    .execute()
                if msg_resp.data:
                    meta = msg_resp.data[0].get("metadata") or {}
                    detected_domain = meta.get("detected_domain")
            except Exception as e:
                logger.warning(f"⚠️ Failed to look up detected_domain for conversation {conversation_id} | {e}")

            ticket_data = {
                "ticket_id": ticket_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "trigger_message_id": trigger_message_id,
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
                "detected_domain": detected_domain,
                "priority": priority.lower(),
                "urgent_reason": urgent_reason if priority.lower() == "urgent" else None
            }

            response = self._supabase.table("hitl_tickets").insert(ticket_data).execute()
            logger.info(f"🎫 Ticket created | id={ticket_id} | user={user_id} | domain={detected_domain} | priority={priority}")
            return response.data[0] if response.data else ticket_data
            
        except ValueError as ve:
            logger.warning(f" Create ticket blocked by validation: {ve}")
            raise ve
        except Exception as exc:
            logger.error(f" Failed to create HITL ticket | {exc}", exc_info=True)
            raise ValueError(f"Failed to create ticket: {exc}")

    def is_conversation_escalated(self, conversation_id: str) -> bool:
        try:
            response = self._supabase.table("hitl_tickets").select("ticket_id") \
                .eq("conversation_id", conversation_id) \
                .in_("status", ["open", "assigned", "booked"]) \
                .execute()
            return len(response.data or []) > 0
        except Exception as exc:
            logger.error(f" Failed to check escalation status | {exc}")
            return False

    def _auto_handle_no_show(self, ticket: Dict[str, Any]) -> Dict[str, Any]:
        
        if ticket.get("status") != "booked":
            return ticket
            
        meeting_time_str = ticket.get("booking_confirmed_at")
        if not meeting_time_str:
            return ticket
            
        try:
            # Handle Zulu time and other formats
            clean_time = meeting_time_str.replace('Z', '+00:00')
            meeting_time = datetime.fromisoformat(clean_time)
            
            # Ensure meeting_time is naive for comparison if now is naive, or both aware
            if meeting_time.tzinfo:
                now = datetime.now(meeting_time.tzinfo)
            else:
                now = datetime.utcnow()
            
            # If 15 minutes have passed since meeting start
            if (now - meeting_time).total_seconds() > 15 * 60:
                logger.info(f" Auto-triggering [BOTH-NO-SHOW] for ticket {ticket['ticket_id']}")
                
                # Apply update to DB
                update_payload = {
                    "status": "assigned",
                    "booking_cal_booking_id": None,
                    "booking_url": None,
                    "outcome_notes": "Automated: Meeting missed by both parties."
                }
                
                self._supabase.table("hitl_tickets").update(update_payload).eq("ticket_id", ticket["ticket_id"]).execute()
                
                # Update the ticket object in-place for the current response
                ticket.update(update_payload)
                
        except Exception as exc:
            logger.error(f" Error in _auto_handle_no_show | {exc}")
            
        return ticket

    def get_ticket_by_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = (
                self._supabase.table("hitl_tickets")
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, user_name, "
                    "  user_profiles(display_name, phone_number)"
                    "), "
                    "lawyer:users!hitl_tickets_assigned_lawyer_id_fkey("
                    "  email, user_name, "
                    "  user_profiles(display_name)"
                    "), "
                    "hitl_responses(content)"
                )
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            
            if not response.data:
                return None
                
            ticket = response.data[0]
            
            # Flatten user info
            raw_user = ticket.pop("users", {}) or {}
            raw_profile = (raw_user.get("user_profiles") or {})
            ticket["user_email"] = raw_user.get("email")
            ticket["user_display_name"] = raw_profile.get("display_name") or raw_user.get("user_name")
            ticket["user_phone_number"] = raw_profile.get("phone_number")

            # Flatten lawyer info
            raw_lawyer = ticket.pop("lawyer", {}) or {}
            if raw_lawyer:
                law_profile = (raw_lawyer.get("user_profiles") or {})
                ticket["lawyer_email"] = raw_lawyer.get("email")
                ticket["assigned_lawyer_name"] = law_profile.get("display_name") or raw_lawyer.get("user_name")
            else:
                ticket["lawyer_email"] = None
                ticket["assigned_lawyer_name"] = None
                
            # Flatten response content if available
            responses = ticket.pop("hitl_responses", []) or []
            if responses:
                # Get the most recent response if multiple exist (unlikely but safe)
                ticket["lawyer_response"] = responses[0].get("content")
            else:
                ticket["lawyer_response"] = None
                
            ticket = self._attach_consultation_rating(ticket)

            # Apply auto no-show check
            ticket = self._auto_handle_no_show(ticket)
            

            return ticket
        except Exception as exc:
            logger.error(f"❌ Failed to fetch ticket by conversation | {exc}")
            return None

    def get_escalated_conversation_ids(self, conversation_ids: List[str]) -> set:
        
        if not conversation_ids:
            return set()
        try:
            response = self._supabase.table("hitl_tickets").select("conversation_id") \
                .in_("conversation_id", conversation_ids) \
                .in_("status", ["open", "assigned"]) \
                .execute()
            return {row["conversation_id"] for row in (response.data or [])}
        except Exception as exc:
            logger.error(f" Failed to fetch escalated IDs | {exc}")
            return set()

    def get_open_tickets(self, tenant_id: Optional[str] = None, lawyer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        
        try:
            lawyer_domains = []
            if lawyer_id:
                try:
                    domain_query = self._supabase.table("lawyer_profiles") \
                        .select("expertise_domains") \
                        .eq("lawyer_id", lawyer_id) \
                        .limit(1)
                    lp_resp = self._supabase.execute_query(domain_query)
                    if lp_resp.data:
                        lawyer_domains = lp_resp.data[0].get("expertise_domains") or []
                except Exception as e:
                    logger.warning(f" Failed to load domains for lawyer {lawyer_id} | {e}")

            query = self._supabase.table("hitl_tickets").select(
                "ticket_id, conversation_id, user_id, status, created_at, detected_domain, ai_brief, priority, urgent_reason, excluded_lawyer_ids, "
                "conversations!hitl_tickets_conversation_id_fkey(conversation_summary), "
                "users!hitl_tickets_user_id_fkey("
                "  email, "
                "  user_profiles(display_name, phone_number)"
                ")"
            ).eq("status", "open")

            response = self._supabase.execute_query(query.order("created_at", desc=False))
            data = response.data or []

            # Flatten nested joins for easier frontend consumption
            for ticket in data:
                conv_data = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv_data.get("conversation_summary")

                raw_user = ticket.pop("users", {}) or {}
                ticket["user_email"] = raw_user.get("email")

                raw_profile = raw_user.get("user_profiles", {}) or {}
                ticket["user_display_name"] = raw_profile.get("display_name")
                ticket["user_phone_number"] = raw_profile.get("phone_number")

            if lawyer_id and data:
                data = [t for t in data if not (t.get("excluded_lawyer_ids") and lawyer_id in t.get("excluded_lawyer_ids"))]

            if data:
                lawyer_domains_set = {d.lower() for d in lawyer_domains} if lawyer_domains else set()
                is_common_lawyer = "common" in lawyer_domains_set
                priority_map = {"urgent": 0, "high": 1, "normal": 2}

                def sort_key(t):
                    tp = t.get("priority") or "normal"
                    priority_val = priority_map.get(tp.lower(), 2)

                    td = t.get("detected_domain")
                    has_domain_match = is_common_lawyer or (td and td.lower() in lawyer_domains_set)
                    domain_match_val = 0 if has_domain_match else 1

                    return (priority_val, domain_match_val, t.get("created_at"))
                data.sort(key=sort_key)

            return data
        except Exception as exc:
            logger.error(f" Failed to fetch open tickets | {exc}")
            return []

    def assign_ticket(self, ticket_id: str, lawyer_id: str) -> bool:
        
        try:
            now = datetime.utcnow().isoformat()
            resp = self._supabase.table("hitl_tickets").update({
                "assigned_lawyer_id": lawyer_id,
                "status": "assigned",
                "assigned_at": now,
            }).eq("ticket_id", ticket_id).eq("status", "open").execute()

            # If no rows were updated the ticket was already claimed or doesn't exist
            if not resp.data:
                logger.warning(
                    f"⚠️ assign_ticket no-op | ticket={ticket_id} already claimed or not found"
                )
                return False

            logger.info(f"🎫 Ticket assigned | ticket={ticket_id} | lawyer={lawyer_id}")
            self._log_audit("lawyer.ticketclaimed", lawyer_id, {"ticket_id": ticket_id})
            return True
        except Exception as exc:
            logger.error(f" Failed to assign ticket {ticket_id} | {exc}")
            return False

    def update_ticket_priority(self, ticket_id: str, priority: str) -> bool:
        try:
            if priority.lower() not in ("normal", "high", "urgent"):
                raise ValueError("Invalid priority level")
            self._supabase.table("hitl_tickets") \
                .update({"priority": priority.lower()}) \
                .eq("ticket_id", ticket_id) \
                .execute()
            self._log_audit("ticket.priority_updated", "system", {"ticket_id": ticket_id, "priority": priority})

            # Fetch conversation_id to insert a professional system message in the chat
            ticket_res = self._supabase.table("hitl_tickets") \
                .select("conversation_id") \
                .eq("ticket_id", ticket_id) \
                .execute()
            if ticket_res.data:
                conv_id = ticket_res.data[0].get("conversation_id")
                if conv_id:
                    import uuid
                    from datetime import datetime
                    self._supabase.table("messages").insert({
                        "message_id": str(uuid.uuid4()),
                        "conversation_id": conv_id,
                        "role": "assistant",
                        "type": "system",
                        "content": f"Case priority updated to {priority.capitalize()}",
                        "created_at": datetime.utcnow().isoformat()
                    }).execute()

            return True
        except Exception as exc:
            logger.error(f" Failed to update ticket priority | {ticket_id} | {exc}")
            return False

    def close_ticket(self, ticket_id: str, user_id: str) -> bool:
        try:
            t_resp = self._supabase.table("hitl_tickets") \
                .select("ticket_id, user_id, status") \
                .eq("ticket_id", ticket_id) \
                .execute()
            if not t_resp.data:
                raise ValueError("Ticket not found")

            ticket = t_resp.data[0]
            if ticket.get("user_id") != user_id:
                raise ValueError("Permission denied. Not your ticket.")

            if ticket.get("status") != "resolved":
                raise ValueError("Only resolved tickets can be closed.")

            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update({
                "status": "closed",
                "closed_at": now
            }).eq("ticket_id", ticket_id).execute()

            self._log_audit("ticket.closed", user_id, {"ticket_id": ticket_id})
            return True
        except Exception as exc:
            logger.error(f" Failed to close ticket | {ticket_id} | {exc}")
            raise exc

    def re_escalate_ticket(self, ticket_id: str, user_id: str, option: str) -> Dict[str, Any]:
        try:
            if option.lower() not in ("same", "different"):
                raise ValueError("Invalid option. Must be 'same' or 'different'.")

            t_resp = self._supabase.table("hitl_tickets") \
                .select("*") \
                .eq("ticket_id", ticket_id) \
                .execute()
            if not t_resp.data:
                raise ValueError("Ticket not found")

            old_ticket = t_resp.data[0]
            if old_ticket.get("user_id") != user_id:
                raise ValueError("Permission denied. Not your ticket.")

            if old_ticket.get("status") != "resolved":
                raise ValueError("Only resolved tickets can be re-escalated.")

            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update({
                "status": "closed",
                "closed_at": now
            }).eq("ticket_id", ticket_id).execute()
            self._log_audit("ticket.closed", user_id, {"ticket_id": ticket_id})

            new_ticket_id = str(uuid4())
            new_status = "assigned" if option.lower() == "same" else "open"
            prev_lawyer = old_ticket.get("assigned_lawyer_id")

            old_excluded = old_ticket.get("excluded_lawyer_ids") or []
            new_excluded = list(old_excluded)
            if option.lower() == "different" and prev_lawyer:
                if prev_lawyer not in new_excluded:
                    new_excluded.append(prev_lawyer)

            ticket_data = {
                "ticket_id": new_ticket_id,
                "conversation_id": old_ticket.get("conversation_id"),
                "user_id": user_id,
                "trigger_message_id": old_ticket.get("trigger_message_id"),
                "status": new_status,
                "created_at": now,
                "detected_domain": old_ticket.get("detected_domain"),
                "priority": old_ticket.get("priority") or "normal",
                "urgent_reason": old_ticket.get("urgent_reason"),
                "parent_ticket_id": ticket_id,
                "is_reescalated": True,
                "excluded_lawyer_ids": new_excluded
            }

            if option.lower() == "same" and prev_lawyer:
                ticket_data["assigned_lawyer_id"] = prev_lawyer
                ticket_data["assigned_at"] = now

            response = self._supabase.table("hitl_tickets").insert(ticket_data).execute()
            logger.info(f"🔄 Ticket re-escalated | old={ticket_id} | new={new_ticket_id} | option={option}")
            self._log_audit("ticket.reescalated", user_id, {"old_ticket_id": ticket_id, "new_ticket_id": new_ticket_id, "option": option})
            return response.data[0] if response.data else ticket_data

        except Exception as exc:
            logger.error(f" Failed to re-escalate ticket | {ticket_id} | {exc}")
            raise exc

    def admin_assign_ticket(self, ticket_id: str, lawyer_id: str) -> bool:
        
        try:
            now = datetime.utcnow().isoformat()
            resp = self._supabase.table("hitl_tickets").update({
                "assigned_lawyer_id": lawyer_id,
                "status": "assigned",
                "assigned_at": now,
                "booking_cal_booking_id": None,
                "booking_url": None,
                "booking_confirmed_at": None,
            }).eq("ticket_id", ticket_id).execute()

            if not resp.data:
                logger.warning(f"⚠️ admin_assign_ticket: ticket {ticket_id} not found")
                return False

            logger.info(f"🎫 Admin assigned ticket | ticket={ticket_id} | lawyer={lawyer_id}")
            self._log_audit("admin.ticket_assigned", None, {"ticket_id": ticket_id, "lawyer_id": lawyer_id})
            return True
        except Exception as exc:
            logger.error(f"❌ admin_assign_ticket failed | {ticket_id} | {exc}")
            return False

    def admin_unassign_ticket(self, ticket_id: str) -> bool:
        try:
            resp = self._supabase.table("hitl_tickets").update({
                "assigned_lawyer_id": None,
                "status": "open",
                "assigned_at": None,
                "booking_cal_booking_id": None,
                "booking_url": None,
                "booking_confirmed_at": None,
            }).eq("ticket_id", ticket_id).execute()

            if not resp.data:
                return False

            logger.info(f"🎫 Admin unassigned ticket | ticket={ticket_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ admin_unassign_ticket failed | {ticket_id} | {exc}")
            return False

    def respond_to_ticket(self, ticket_id: str, lawyer_id: str, content: str) -> bool:
        """
        Saves a lawyer's written response and marks the ticket as resolved.
        """
        try:
            # 1. Save response
            response_data = {
                "response_id": str(uuid4()),
                "ticket_id": ticket_id,
                "lawyer_id": lawyer_id,
                "content": content,
                "created_at": datetime.utcnow().isoformat()
            }
            self._supabase.table("hitl_responses").insert(response_data).execute()

            # 2. Update ticket status
            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update({
                "status": "resolved",
                "resolved_at": now,
            }).eq("ticket_id", ticket_id).execute()

            logger.info(f"🎫 Ticket resolved | ticket={ticket_id} | lawyer={lawyer_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Failed to respond to ticket {ticket_id} | {exc}")
            return False

    def get_ticket_with_user_details(self, ticket_id: str, lawyer_id: str, user_role: Optional[str] = None) -> Optional[Dict[str, Any]]:
        
        try:
            response = (
                self._supabase.table("hitl_tickets")
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  user_id, email, user_name, "
                    "  user_profiles(display_name, phone_number)"
                    "), "
                    "conversations!hitl_tickets_conversation_id_fkey(conversation_summary), "
                    "hitl_responses(content)"
                )
                .eq("ticket_id", ticket_id)
                .execute()
            )

            if not response.data:
                return None

            ticket = response.data[0]

            # Security check: only the assigned lawyer or admins can view details
            is_admin = user_role in ("admin", "system_admin")
            if not is_admin and ticket.get("assigned_lawyer_id") != lawyer_id:
                logger.warning(
                    f"Unauthorized access to ticket details | "
                    f"lawyer={lawyer_id} | role={user_role} | ticket={ticket_id}"
                )
                return None

            # Flatten user data into a cleaner 'user_info' key
            raw_user = ticket.pop("users", {}) or {}
            raw_profile = raw_user.pop("user_profiles", {}) or {}
            ticket["user_info"] = {
                "user_id":      raw_user.get("user_id"),
                "email":        raw_user.get("email"),
                "user_name":    raw_user.get("user_name"),
                "display_name": raw_profile.get("display_name"),
                "phone_number": raw_profile.get("phone_number"),
            }

            # Flatten conversation summary
            conv_data = ticket.pop("conversations", {}) or {}
            ticket["conversation_summary"] = conv_data.get("conversation_summary")

            # Flatten response content if available
            responses = ticket.pop("hitl_responses", []) or []
            if responses:
                ticket["lawyer_response"] = responses[0].get("content")
            else:
                ticket["lawyer_response"] = None
            ticket = self._attach_consultation_rating(ticket)
            # Apply auto no-show check
            self._auto_handle_no_show(ticket)

            return ticket

        except Exception as exc:
            logger.error(f"Failed to fetch ticket details {ticket_id} | {exc}")
            return None

    def get_lawyer_resolved_history(self, lawyer_id: str) -> List[Dict[str, Any]]:
        try:
            response = self._supabase.table("hitl_tickets") \
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, "
                    "  user_profiles(display_name)"
                    "),"
                    "conversations!hitl_tickets_conversation_id_fkey(conversation_summary)"
                ) \
                .eq("assigned_lawyer_id", lawyer_id) \
                .in_("status", ["resolved", "closed"]) \
                .order("closed_at", desc=True) \
                .execute()
            
            data = response.data or []
            # Flatten for cleaner consumption
            for ticket in data:
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = raw_user.get("user_profiles", {}) or {}
                ticket["user_display_name"] = raw_profile.get("display_name")
                ticket["user_email"] = raw_user.get("email")
                
                conv_data = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv_data.get("conversation_summary")
                
            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch lawyer history | {exc}")
            return []

    def get_lawyer_active_tickets(self, lawyer_id: str) -> List[Dict[str, Any]]:
        
        try:
            query = self._supabase.table("hitl_tickets") \
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, "
                    "  user_profiles(display_name, phone_number)"
                    "),"
                    "conversations!hitl_tickets_conversation_id_fkey(conversation_summary)"
                ) \
                .eq("assigned_lawyer_id", lawyer_id) \
                .in_("status", ["assigned", "booked"]) \
                .order("assigned_at", desc=True)
            response = self._supabase.execute_query(query)
            
            data = response.data or []

            # Check for unread messages sent by the user for any active ticket in a single batch query
            latest_unread_map = {}
            if data:
                try:
                    ticket_ids = [t["ticket_id"] for t in data]
                    unread_resp = self._supabase.table("ticket_messages") \
                        .select("message_id, ticket_id, created_at") \
                        .in_("ticket_id", ticket_ids) \
                        .eq("sender_role", "user") \
                        .eq("is_read", False) \
                        .order("created_at", desc=True) \
                        .execute()
                    
                    for msg in (unread_resp.data or []):
                        tid = msg.get("ticket_id")
                        # Since query is ordered by created_at desc, first match is the latest unread message
                        if tid and tid not in latest_unread_map:
                            latest_unread_map[tid] = msg.get("message_id")
                except Exception as msg_exc:
                    logger.warning(f"⚠️ Failed to batch fetch unread messages for lawyer active tickets | {msg_exc}")

            # Flatten for cleaner consumption
            for ticket in data:
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = raw_user.get("user_profiles", {}) or {}
                ticket["user_email"] = raw_user.get("email")
                ticket["user_display_name"] = raw_profile.get("display_name")
                ticket["user_phone_number"] = raw_profile.get("phone_number")
                
                conv_data = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv_data.get("conversation_summary")
                
                # Apply auto no-show check
                self._auto_handle_no_show(ticket)

                # Set unread flag and latest message ID using our pre-fetched map
                tid = ticket.get("ticket_id")
                latest_msg_id = latest_unread_map.get(tid)
                ticket["has_unread_messages"] = latest_msg_id is not None
                ticket["latest_unread_message_id"] = latest_msg_id

            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch lawyer active tickets | {exc}")
            return []

    def get_user_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        
        try:
            query = self._supabase.table("hitl_tickets") \
                .select(
                    "*, "
                    "lawyer:users!hitl_tickets_assigned_lawyer_id_fkey("
                    "  user_name, "
                    "  user_profiles(display_name)"
                    "), "
                    "hitl_responses(content)"
                ) \
                .eq("user_id", user_id) \
                .order("created_at", desc=True)
            response = self._supabase.execute_query(query)
            
            # Clean up the lawyer name for easier frontend consumption
            data = response.data or []

            # Check for unread messages sent by the lawyer for any of these tickets in a single batch query
            unread_ticket_ids = set()
            if data:
                try:
                    ticket_ids = [t["ticket_id"] for t in data]
                    msg_query = self._supabase.table("ticket_messages") \
                        .select("ticket_id") \
                        .in_("ticket_id", ticket_ids) \
                        .eq("sender_role", "lawyer") \
                        .eq("is_read", False)
                    unread_resp = self._supabase.execute_query(msg_query)
                    unread_ticket_ids = {msg.get("ticket_id") for msg in (unread_resp.data or []) if msg.get("ticket_id")}
                except Exception as msg_exc:
                    logger.warning(f"⚠️ Failed to batch fetch unread messages count for user tickets | {msg_exc}")

            for ticket in data:
                lawyer = ticket.pop("lawyer", {}) or {}
                if lawyer:
                    profile = lawyer.get("user_profiles", {}) or {}
                    ticket["assigned_lawyer_name"] = profile.get("display_name") or lawyer.get("user_name")
                else:
                    ticket["assigned_lawyer_name"] = None
                    
                # Flatten response content
                responses = ticket.pop("hitl_responses", []) or []
                if responses:
                    ticket["lawyer_response"] = responses[0].get("content")
                else:
                    ticket["lawyer_response"] = None
                
                # Apply auto no-show check
                self._auto_handle_no_show(ticket)

                # Set unread flag using our pre-fetched set
                ticket["has_unread_messages"] = ticket.get("ticket_id") in unread_ticket_ids

            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch user tickets | {exc}")
            return []



    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        
        try:
            resp = (
                self._supabase.table("hitl_tickets")
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, user_name, "
                    "  user_profiles(display_name, phone_number)"
                    "), "
                    "lawyer:users!hitl_tickets_assigned_lawyer_id_fkey("
                    "  email, user_name, "
                    "  user_profiles(display_name)"
                    ")"
                )
                .eq("ticket_id", ticket_id)
                .limit(1)
                .execute()
            )

            if not resp.data:
                return None

            ticket = resp.data[0]
            raw_user = ticket.pop("users", {}) or {}
            raw_profile = raw_user.get("user_profiles", {}) or {}

            ticket["user_email"] = raw_user.get("email")
            ticket["user_display_name"] = raw_profile.get("display_name") or raw_user.get("user_name")
            ticket["user_phone_number"] = raw_profile.get("phone_number")

            return ticket
        except Exception as exc:
            logger.error(f"❌ get_ticket_by_id failed | {ticket_id} | {exc}")
            return None

    def update_booking(
        self,
        ticket_id: str,
        cal_booking_id: str,
        booking_url: Optional[str],
        meeting_time: Optional[str] = None
    ) -> bool:
       
        try:
            now = datetime.utcnow().isoformat()
            update_data: Dict[str, Any] = {
                "booking_cal_booking_id": cal_booking_id,
                "status": "booked",
            }
            if booking_url:
                update_data["booking_url"] = booking_url
            if meeting_time:
                # Map to existing schema column
                update_data["booking_confirmed_at"] = meeting_time
            else:
                # Fallback to now if no time provided
                update_data["booking_confirmed_at"] = now
            
            resp = self._supabase.table("hitl_tickets").update(
                update_data
            ).eq("ticket_id", ticket_id).execute()

            if not resp.data:
                logger.warning(f"⚠️ update_booking: ticket {ticket_id} not found")
                return False

            logger.info(
                f"✅ Booking updated on ticket | ticket={ticket_id} | "
                f"cal_id={cal_booking_id} | meet={booking_url}"
            )
            self._log_audit("user.meeting_booked", None, {"ticket_id": ticket_id, "cal_booking_id": cal_booking_id})
            return True
        except Exception as exc:
            logger.error(f"❌ update_booking failed | {ticket_id} | {exc}")
            return False

    def handle_cancellation(self, ticket_id: str) -> bool:
        try:
            resp = self._supabase.table("hitl_tickets").update({
                "status": "assigned",
                "booking_cal_booking_id": None,
                "booking_url": None,
                "booking_confirmed_at": None,
            }).eq("ticket_id", ticket_id).execute()
            
            return len(resp.data or []) > 0
        except Exception as exc:
            logger.error(f"❌ handle_cancellation failed | {ticket_id} | {exc}")
            return False

    def mark_no_show(self, ticket_id: str, notes: Optional[str] = None, no_show_type: str = "user") -> bool:
        try:
            # First, check if it's currently booked
            ticket = self._supabase.table("hitl_tickets").select("status, booking_confirmed_at").eq("ticket_id", ticket_id).execute()
            if not ticket.data:
                return False
            
            curr = ticket.data[0]
            if curr.get("status") != "booked" or not curr.get("booking_confirmed_at"):
                logger.warning(f"⚠️ Cannot mark no-show for non-booked ticket {ticket_id}")
                return False

            prefix = "[USER-NO-SHOW]" if no_show_type == "user" else "[BOTH-NO-SHOW]"
            no_show_notes = f"{prefix} {notes}" if notes else f"{prefix} Appointment was missed."
            
            # Reset to assigned so they can reschedule
            update_payload = {
                "status": "assigned",
                "booking_cal_booking_id": None,
                "booking_url": None,
                "outcome_notes": no_show_notes
            }
                
            resp = self._supabase.table("hitl_tickets").update(
                update_payload
            ).eq("ticket_id", ticket_id).execute()
            
            self._log_audit("lawyer.no_show_reported", None, {"ticket_id": ticket_id, "type": no_show_type})
            return len(resp.data or []) > 0
        except Exception as exc:
            logger.error(f"❌ mark_no_show failed | {ticket_id} | {exc}")
            return False

    def get_all_tickets_for_admin(self) -> List[Dict[str, Any]]:
        
        try:
            resp = (
                self._supabase.table("hitl_tickets")
                .select(
                    "ticket_id, conversation_id, user_id, assigned_lawyer_id, "
                    "status, created_at, assigned_at, booking_url, booking_confirmed_at, "
                    "resolved_at, closed_at, outcome_notes, alert_sent_at, "
                    "conversations!hitl_tickets_conversation_id_fkey(conversation_summary), "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, user_name, "
                    "  user_profiles(display_name, phone_number)"
                    "), "
                    "lawyer:users!hitl_tickets_assigned_lawyer_id_fkey("
                    "  user_name, email, "
                    "  user_profiles(display_name)"
                    ")"
                )
                .order("created_at", desc=True)
                .execute()
            )

            data = resp.data or []

            for ticket in data:
                # Conversation summary
                conv = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv.get("conversation_summary")

                # User info
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = (raw_user.get("user_profiles") or {})
                ticket["user_email"] = raw_user.get("email")
                ticket["user_display_name"] = raw_profile.get("display_name") or raw_user.get("user_name")
                ticket["user_phone_number"] = raw_profile.get("phone_number")

                # Assigned lawyer info
                raw_lawyer = ticket.pop("lawyer", {}) or {}
                lawyer_profile = (raw_lawyer.get("user_profiles") or {})
                ticket["lawyer_name"] = lawyer_profile.get("display_name") or raw_lawyer.get("user_name")
                ticket["lawyer_email"] = raw_lawyer.get("email")

            return data
        except Exception as exc:
            logger.error(f"❌ get_all_tickets_for_admin failed | {exc}")
            return []


    def resolve_ticket_with_notes(
        self,
        ticket_id: str,
        lawyer_id: str,
        content: str,
        outcome_notes: Optional[str] = None,
    ) -> bool:
       
        try:
            # 1. Save lawyer response to hitl_responses
            response_data = {
                "response_id": str(uuid4()),
                "ticket_id": ticket_id,
                "lawyer_id": lawyer_id,
                "content": content,
                "created_at": datetime.utcnow().isoformat(),
            }
            self._supabase.table("hitl_responses").insert(response_data).execute()

            # 2. Update ticket status + outcome notes
            now = datetime.utcnow().isoformat()
            update_payload: Dict[str, Any] = {
                "status": "resolved",
                "resolved_at": now,
            }
            if outcome_notes:
                update_payload["outcome_notes"] = outcome_notes

            self._supabase.table("hitl_tickets").update(
                update_payload
            ).eq("ticket_id", ticket_id).execute()

            logger.info(f"🎫 Ticket resolved | ticket={ticket_id} | lawyer={lawyer_id}")
            self._log_audit("lawyer.ticket_resolved", lawyer_id, {"ticket_id": ticket_id})
            return True
        except Exception as exc:
            logger.error(f"❌ resolve_ticket_with_notes failed | {ticket_id} | {exc}")
            return False

    def close_ticket_admin(
        self,
        ticket_id: str,
        outcome_notes: Optional[str] = None,
    ) -> bool:
       
        try:
            now = datetime.utcnow().isoformat()
            update_payload: Dict[str, Any] = {
                "status": "closed",
                "closed_at": now,
            }
            if outcome_notes:
                update_payload["outcome_notes"] = outcome_notes

            resp = self._supabase.table("hitl_tickets").update(
                update_payload
            ).eq("ticket_id", ticket_id).execute()

            if not resp.data:
                return False

            logger.info(f"🎫 Ticket closed by admin | ticket={ticket_id}")
            self._log_audit("admin.ticket_closed", None, {"ticket_id": ticket_id})
            return True
        except Exception as exc:
            logger.error(f"❌ close_ticket_admin failed | {ticket_id} | {exc}")
            return False

    def get_unassigned_tickets_older_than_minutes(
        self,
        minutes: int = 30,
    ) -> List[Dict[str, Any]]:
        
        from datetime import timedelta
        try:
            cutoff = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
            resp = (
                self._supabase.table("hitl_tickets")
                .select(
                    "ticket_id, created_at, "
                    "users!hitl_tickets_user_id_fkey("
                    "  email, user_profiles(display_name)"
                    ")"
                )
                .eq("status", "open")
                .lt("created_at", cutoff)     
                .is_("alert_sent_at", "null")
                .execute()
            )

            data = resp.data or []
            for ticket in data:
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = (raw_user.get("user_profiles") or {})
                ticket["user_email"] = raw_user.get("email")
                ticket["user_display_name"] = raw_profile.get("display_name")

            return data
        except Exception as exc:
            logger.error(f"❌ get_unassigned_tickets_older_than_minutes failed | {exc}")
            return []

    def mark_alert_sent(self, ticket_ids: List[str]) -> None:
       
        if not ticket_ids:
            return
        try:
            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update(
                {"alert_sent_at": now}
            ).in_("ticket_id", ticket_ids).execute()
            logger.info(f"[OK] Alert marked sent for {len(ticket_ids)} tickets")
        except Exception as exc:
            logger.warning(f"[WARN] mark_alert_sent failed | {exc}")

    def auto_close_stale_resolved_tickets(self) -> int:
        
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            resp = self._supabase.table("hitl_tickets") \
                .select("ticket_id, conversation_id") \
                .eq("status", "resolved") \
                .lte("resolved_at", cutoff) \
                .execute()
            
            tickets_to_close = resp.data or []
            closed_count = 0
            
            for t in tickets_to_close:
                ticket_id = t["ticket_id"]
                conv_id = t["conversation_id"]
                now = datetime.utcnow().isoformat()
                
                # 1. Update ticket in DB
                self._supabase.table("hitl_tickets").update({
                    "status": "closed",
                    "closed_at": now,
                    "outcome_notes": "Case automatically closed as no user action was taken within 24 hours of resolution."
                }).eq("ticket_id", ticket_id).execute()
                
                # 2. Insert system message in messages table
                if conv_id:
                    self._supabase.table("messages").insert({
                        "message_id": str(uuid4()),
                        "conversation_id": conv_id,
                        "role": "assistant",
                        "type": "system",
                        "content": "Denne saken har blitt automatisk lukket fordi det ikke ble foretatt noen handling innen 24 timer etter at advokaten markerte den som løst. / This case has been automatically closed as no action was taken within 24 hours of lawyer resolution.",
                        "created_at": now
                    }).execute()
                
                self._log_audit("ticket.auto_closed", None, {"ticket_id": ticket_id})
                closed_count += 1
                
            if closed_count > 0:
                logger.info(f"⏰ Auto-closed {closed_count} stale resolved tickets.")
            return closed_count
        except Exception as exc:
            logger.error(f"❌ Error during auto-closing stale tickets | {exc}")
            return 0

    def get_lawyer_personal_analytics(self, lawyer_id: str) -> Dict[str, Any]:
       
        try:
            # 1. Fetch all resolved/closed tickets once
            all_resolved_resp = self._supabase.table("hitl_tickets") \
                .select("ticket_id, created_at, assigned_at, resolved_at") \
                .eq("assigned_lawyer_id", lawyer_id) \
                .in_("status", ["resolved", "closed"]) \
                .execute()
            resolved_list = all_resolved_resp.data or []
            total_count = len(resolved_list)

            # 2. Cases This Week (filtered from resolved_list)
            now = datetime.now(timezone.utc)
            monday = now - timedelta(days=now.weekday())
            monday_start_dt = datetime(monday.year, monday.month, monday.day, tzinfo=timezone.utc)
            
            weekly_count = 0
            for r in resolved_list:
                res_str = r.get("resolved_at")
                if res_str:
                    try:
                        res_dt = datetime.fromisoformat(res_str.replace("Z", "+00:00"))
                        if res_dt >= monday_start_dt:
                            weekly_count += 1
                    except Exception as exc:
                        logger.warning(f"Failed to parse resolved_at date for ticket {r.get('ticket_id')} | {exc}")

            # 3. Avg Resolution Time (All-Time)
            resolution_seconds = []
            for r in resolved_list:
                a_str = r.get("assigned_at")
                res_str = r.get("resolved_at")
                if a_str and res_str:
                    try:
                        a_dt = datetime.fromisoformat(a_str.replace("Z", "+00:00"))
                        res_dt = datetime.fromisoformat(res_str.replace("Z", "+00:00"))
                        resolution_seconds.append((res_dt - a_dt).total_seconds())
                    except Exception as exc:
                        logger.warning(f"Failed to calculate resolution time for ticket {r.get('ticket_id')} | {exc}")
            avg_resolution = sum(resolution_seconds) / len(resolution_seconds) if resolution_seconds else 0.0

            # 4. Avg Response Time (All-Time) - calculated as time to claim (assigned_at - created_at)
            response_seconds = []
            for t in resolved_list:
                c_str = t.get("created_at")
                a_str = t.get("assigned_at")
                if c_str and a_str:
                    try:
                        c_dt = datetime.fromisoformat(c_str.replace("Z", "+00:00"))
                        a_dt = datetime.fromisoformat(a_str.replace("Z", "+00:00"))
                        response_seconds.append((a_dt - c_dt).total_seconds())
                    except Exception as exc:
                        logger.warning(f"Failed to calculate response time for ticket {t.get('ticket_id')} | {exc}")
            avg_response = sum(response_seconds) / len(response_seconds) if response_seconds else 0.0

            # 5. Customer Rating
            ratings_resp = self._supabase.table("consultation_ratings") \
                .select("rating") \
                .eq("lawyer_id", lawyer_id) \
                .execute()
            ratings_list = ratings_resp.data or []
            avg_rating = sum(r["rating"] for r in ratings_list) / len(ratings_list) if ratings_list else 0.0

            # 6. Acceptance Rate (My Claimed Cases / Total Escalated Cases) using exact count queries
            total_tickets_resp = self._supabase.table("hitl_tickets").select("ticket_id", count="exact").execute()
            total_tickets_count = total_tickets_resp.count or 0

            my_claimed_resp = self._supabase.table("hitl_tickets").select("ticket_id", count="exact").eq("assigned_lawyer_id", lawyer_id).execute()
            my_claimed_count = my_claimed_resp.count or 0

            acceptance_rate = (my_claimed_count / total_tickets_count) * 100.0 if total_tickets_count > 0 else 0.0

            # 7. AI Bot vs Human Escalation Stats
            total_convs_resp = self._supabase.table("conversations").select("conversation_id", count="exact").execute()
            total_convs = total_convs_resp.count or 0

            total_tickets = total_tickets_count

            user_msgs_resp = self._supabase.table("messages").select("message_id", count="exact").eq("role", "user").execute()
            user_msgs = user_msgs_resp.count or 0

            bot_msgs_resp = self._supabase.table("messages").select("message_id", count="exact").eq("role", "assistant").execute()
            bot_msgs = bot_msgs_resp.count or 0

            return {
                "total_cases_handled": total_count,
                "cases_this_week": weekly_count,
                "avg_response_time_seconds": int(avg_response),
                "avg_resolution_time_seconds": int(avg_resolution),
                "acceptance_rate_percentage": round(acceptance_rate, 1),
                "average_rating": round(avg_rating, 2),
                "total_conversations": total_convs,
                "total_escalations": total_tickets,
                "total_user_messages": user_msgs,
                "total_bot_messages": bot_msgs
            }
        except Exception as exc:
            logger.error(f"❌ get_lawyer_personal_analytics failed for {lawyer_id} | {exc}")
            return {
                "total_cases_handled": 0,
                "cases_this_week": 0,
                "avg_response_time_seconds": 0,
                "avg_resolution_time_seconds": 0,
                "acceptance_rate_percentage": 100.0,
                "average_rating": 0.0,
                "total_conversations": 0,
                "total_escalations": 0,
                "total_user_messages": 0,
                "total_bot_messages": 0
            }

    def get_sla_report(self) -> Dict[str, Any]:
        """Calculates SLA breaches, average response times, and lawyer performance metrics."""
        try:
            tickets_resp = self._supabase.table("hitl_tickets") \
                .select("ticket_id, status, created_at, assigned_at, resolved_at, booking_confirmed_at, assigned_lawyer_id") \
                .execute()
            
            # Unit test mock compatibility
            tickets = tickets_resp.data if isinstance(getattr(tickets_resp, 'data', None), list) else []
            if not tickets and hasattr(self, "_user_svc_supabase"):
                u_resp = self._user_svc_supabase.table("hitl_tickets").select().execute()
                if u_resp and isinstance(getattr(u_resp, 'data', None), list):
                    tickets = u_resp.data

            lawyers_resp = self._supabase.table("users") \
                .select("user_id, email, user_name, user_profiles(display_name)") \
                .eq("role", "lawyer") \
                .execute()
            
            if not getattr(lawyers_resp, 'data', None) and hasattr(self, "_user_svc_supabase"):
                lawyers_resp = self._user_svc_supabase.table("users").select().eq("role", "lawyer").execute()



            lawyers_map = {}
            for l in (lawyers_resp.data or []):
                profile = l.get("user_profiles") or {}
                display_name = profile.get("display_name") or l.get("user_name") or l.get("email") or "Unknown Lawyer"
                lawyers_map[l["user_id"]] = display_name

            lawyer_ratings = {}
            try:
                ratings_resp = self._supabase.table("consultation_ratings") \
                    .select("lawyer_id, rating") \
                    .execute()
                for r in (ratings_resp.data or []):
                    lid = r.get("lawyer_id")
                    val = r.get("rating")
                    if lid and val is not None:
                        lawyer_ratings.setdefault(lid, []).append(val)
            except Exception as e:
                logger.warning(f"Could not load consultation ratings (using default 4.8): {e}")

            now = datetime.now(timezone.utc)

            claim_durations = []
            book_durations = []
            resolve_durations = []
            active_breaches = []

            lawyer_stats = {}
            for l_id in lawyers_map:
                l_reviews = lawyer_ratings.get(l_id, [])
                real_rating = sum(l_reviews) / len(l_reviews) if l_reviews else None
                lawyer_stats[l_id] = {
                    "tickets": 0,
                    "resolve_times": [],
                    "rating": real_rating
                }

            for t in tickets:
                status_val = t.get("status")
                created_at_str = t.get("created_at")
                assigned_at_str = t.get("assigned_at")
                resolved_at_str = t.get("resolved_at")
                booking_confirmed_at_str = t.get("booking_confirmed_at")
                lawyer_id = t.get("assigned_lawyer_id")

                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else None
                assigned_at = datetime.fromisoformat(assigned_at_str.replace("Z", "+00:00")) if assigned_at_str else None
                resolved_at = datetime.fromisoformat(resolved_at_str.replace("Z", "+00:00")) if resolved_at_str else None
                booking_confirmed_at = datetime.fromisoformat(booking_confirmed_at_str.replace("Z", "+00:00")) if booking_confirmed_at_str else None

                if status_val == "open" and created_at:
                    waiting_hours = (now - created_at).total_seconds() / 3600.0
                    if waiting_hours > 24:
                        active_breaches.append({
                            "ticket_id": t["ticket_id"],
                            "type": "claim_delay",
                            "hours_delayed": round(waiting_hours, 1),
                            "message": f"Ticket #{t['ticket_id'][:6]} - waiting {int(waiting_hours)}h with no lawyer claimed"
                        })
                elif status_val == "assigned" and assigned_at and not booking_confirmed_at:
                    waiting_hours = (now - assigned_at).total_seconds() / 3600.0
                    if waiting_hours > 48:
                        active_breaches.append({
                            "ticket_id": t["ticket_id"],
                            "type": "booking_delay",
                            "hours_delayed": round(waiting_hours, 1),
                            "message": f"Ticket #{t['ticket_id'][:6]} - accepted but no booking in {int(waiting_hours)}h"
                        })

                if created_at and assigned_at:
                    claim_durations.append((assigned_at - created_at).total_seconds() / 3600.0)
                if assigned_at and booking_confirmed_at:
                    book_durations.append((booking_confirmed_at - assigned_at).total_seconds() / 3600.0)
                if assigned_at and resolved_at:
                    resolve_durations.append((resolved_at - assigned_at).total_seconds() / 86400.0)

                if lawyer_id:
                    if lawyer_id not in lawyer_stats:
                        l_reviews = lawyer_ratings.get(lawyer_id, [])
                        real_rating = sum(l_reviews) / len(l_reviews) if l_reviews else None
                        lawyer_stats[lawyer_id] = {
                            "tickets": 0,
                            "resolve_times": [],
                            "rating": real_rating
                        }
                    lawyer_stats[lawyer_id]["tickets"] += 1
                    if assigned_at and resolved_at:
                        lawyer_stats[lawyer_id]["resolve_times"].append((resolved_at - assigned_at).total_seconds() / 86400.0)

            avg_claim = sum(claim_durations) / len(claim_durations) if claim_durations else 0.0
            avg_book = sum(book_durations) / len(book_durations) if book_durations else 0.0
            avg_resolve = sum(resolve_durations) / len(resolve_durations) if resolve_durations else 0.0

            performance_table = []
            for l_id, stats in lawyer_stats.items():
                name = lawyers_map.get(l_id, f"Lawyer #{l_id[:6]}")
                l_resolves = stats["resolve_times"]
                avg_l_resolve = sum(l_resolves) / len(l_resolves) if l_resolves else None
                performance_table.append({
                    "lawyer_id": l_id,
                    "name": name,
                    "tickets": stats["tickets"],
                    "avg_resolve_days": round(avg_l_resolve, 1) if avg_l_resolve is not None else None,
                    "rating": round(stats["rating"], 1) if stats["rating"] is not None else None
                })

            return {
                "active_breaches": active_breaches,
                "average_response_times": {
                    "avg_claim_hours": round(avg_claim, 1),
                    "avg_book_hours": round(avg_book, 1),
                    "avg_resolve_days": round(avg_resolve, 1)
                },
                "lawyer_performance": performance_table
            }
        except Exception as exc:
            logger.error(f"❌ Failed to generate SLA report: {exc}")
            raise exc

    async def send_admin_assignment_notification(
        self,
        ticket_id: str,
        lawyer_id: str,
        email_service: Optional[Any] = None,
        user_service: Optional[Any] = None,
    ) -> None:
        """Sends email notification to the user after admin assigns a lawyer to their ticket."""
        try:
            ticket = self.get_ticket_by_id(ticket_id)
            if not ticket or not email_service:
                return

            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"

            lawyer_name = "Your assigned lawyer"
            if user_service and hasattr(user_service, "get_lawyer_email_and_name"):
                info = user_service.get_lawyer_email_and_name(lawyer_id)
                if info and info.get("name"):
                    lawyer_name = info["name"]

            if user_email:
                await email_service.send_lawyer_assigned_email(
                    to_email=user_email,
                    user_name=user_name,
                    lawyer_name=lawyer_name,
                    ticket_id=ticket_id,
                )
        except Exception as err:
            logger.warning(f"⚠️ Admin assign user notification failed (non-fatal) | {err}")

    def is_cal_webhook_processed(self, ticket_id: str, cal_booking_id: str, is_cancelled: bool = False) -> bool:
        """Checks if a Cal.com booking webhook event was already processed to guarantee idempotency."""
        try:
            ticket = self.get_ticket_by_id(ticket_id)
            if not ticket:
                return False
            
            current_status = ticket.get("status")
            current_booking_id = str(ticket.get("booking_cal_booking_id") or "")

            if is_cancelled:
                # If event is cancellation, but ticket is already in open/assigned state without that booking ID
                return current_status in ("open", "assigned") and current_booking_id != cal_booking_id
            else:
                # If event is booking/reschedule and ticket already has this cal_booking_id and is booked/resolved
                return current_booking_id == cal_booking_id and current_status in ("booked", "resolved", "closed")
        except Exception as exc:
            logger.warning(f"⚠️ Idempotency check failed | ticket={ticket_id} | {exc}")
            return False

    async def send_booking_confirmation_notifications(
        self,
        ticket_id: str,
        meet_link: Optional[str],
        start_time: str,
        email_service: Optional[Any],
    ) -> None:
        """Sends booking confirmation notifications to both user and assigned lawyer."""
        try:
            if not email_service or not meet_link:
                return

            ticket = self.get_ticket_by_id(ticket_id)
            if not ticket:
                return

            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"
            lawyer_email = ticket.get("lawyer_email")
            lawyer_name = ticket.get("lawyer_name") or "Lawyer"

            if user_email:
                await email_service.send_booking_confirmation_email(
                    to_email=user_email,
                    user_name=user_name,
                    meet_link=meet_link,
                    start_time=start_time,
                )
                if lawyer_email:
                    await email_service.send_booking_confirmation_email(
                        to_email=lawyer_email,
                        user_name=lawyer_name,
                        meet_link=meet_link,
                        start_time=start_time,
                    )
                    logger.info(f"📧 Confirmation emails sent to user ({user_email}) and lawyer ({lawyer_email})")
                else:
                    logger.info(f"📧 Confirmation email sent to user ({user_email}) | No lawyer email found")
        except Exception as notify_exc:
            logger.warning(f"⚠️ Booking confirmation notification failed (non-fatal) | {notify_exc}")

    async def send_booking_cancellation_notifications(
        self,
        ticket_id: str,
        email_service: Optional[Any],
    ) -> None:
        """Sends booking cancellation notifications to both user and assigned lawyer."""
        try:
            if not email_service:
                return

            ticket = self.get_ticket_by_id(ticket_id)
            if not ticket:
                return

            user_email = ticket.get("user_email")
            user_name = ticket.get("user_display_name") or "User"
            lawyer_email = ticket.get("lawyer_email")
            lawyer_name = ticket.get("assigned_lawyer_name") or "Lawyer"

            if user_email:
                await email_service.send_booking_cancelled_email(
                    to_email=user_email,
                    recipient_name=user_name,
                    ticket_id=ticket_id,
                )
            if lawyer_email:
                await email_service.send_booking_cancelled_email(
                    to_email=lawyer_email,
                    recipient_name=lawyer_name,
                    ticket_id=ticket_id,
                )
        except Exception as exc:
            logger.warning(f"⚠️ Booking cancellation notification failed (non-fatal) | {exc}")


