import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

# Ticket statuses in lifecycle order
# open → assigned → booked → resolved → closed
TICKET_STATUSES = ("open", "assigned", "booked", "resolved", "closed")

class HitlService:
    """
    HitlService — handles Human-In-The-Loop (HITL) escalation tickets.
    """

    def __init__(self, supabase_client: SupabaseClient) -> None:
        self._supabase = supabase_client
        logger.info("✅ HitlService initialized")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # USER ACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def create_ticket(
        self,
        conversation_id: str,
        user_id: str,
        trigger_message_id: str,
        user_note: Optional[str] = None,   # kept in signature for API compat; not stored yet
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Creates a new escalation ticket. Called when a user is unsatisfied.
        """
        try:
            ticket_id = str(uuid4())
            # NOTE: only columns that exist in the real hitl_tickets schema.
            # tenant_id is deferred to a future phase — column will be made nullable via migration.
            # user_note is not yet in the schema — add via migration when needed.
            ticket_data = {
                "ticket_id": ticket_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "trigger_message_id": trigger_message_id,
                "status": "open",
                "created_at": datetime.utcnow().isoformat(),
            }

            response = self._supabase.table("hitl_tickets").insert(ticket_data).execute()
            logger.info(f"🎫 Ticket created | id={ticket_id} | user={user_id}")
            return response.data[0] if response.data else ticket_data
            
        except Exception as exc:
            logger.error(f"❌ Failed to create HITL ticket | {exc}", exc_info=True)
            raise ValueError(f"Failed to create ticket: {exc}")

    def is_conversation_escalated(self, conversation_id: str) -> bool:
        """
        Checks if a conversation already has an active (open or assigned) ticket.
        """
        try:
            response = self._supabase.table("hitl_tickets").select("ticket_id") \
                .eq("conversation_id", conversation_id) \
                .in_("status", ["open", "assigned", "booked"]) \
                .execute()
            return len(response.data or []) > 0
        except Exception as exc:
            logger.error(f"❌ Failed to check escalation status | {exc}")
            return False

    def get_ticket_by_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns the most recent active ticket for a conversation with full user and lawyer details.
        """
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
                    ")"
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
                
            return ticket
        except Exception as exc:
            logger.error(f"❌ Failed to fetch ticket by conversation | {exc}")
            return None

    def get_escalated_conversation_ids(self, conversation_ids: List[str]) -> set:
        """
        Given a list of conversation IDs, returns a set of those that are currently escalated.
        """
        if not conversation_ids:
            return set()
        try:
            response = self._supabase.table("hitl_tickets").select("conversation_id") \
                .in_("conversation_id", conversation_ids) \
                .in_("status", ["open", "assigned"]) \
                .execute()
            return {row["conversation_id"] for row in (response.data or [])}
        except Exception as exc:
            logger.error(f"❌ Failed to fetch escalated IDs | {exc}")
            return set()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LAWYER ACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_open_tickets(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns all tickets in 'open' status visible on the lawyer dashboard queue.
        Includes the DB summary from the conversations table and user profile info.
        """
        try:
            query = self._supabase.table("hitl_tickets").select(
                "ticket_id, conversation_id, user_id, status, created_at, "
                "conversations!hitl_tickets_conversation_id_fkey(conversation_summary), "
                "users!hitl_tickets_user_id_fkey("
                "  email, "
                "  user_profiles(display_name, phone_number)"
                ")"
            ).eq("status", "open")

            response = query.order("created_at", desc=False).execute()
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

            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch open tickets | {exc}")
            return []

    def assign_ticket(self, ticket_id: str, lawyer_id: str) -> bool:
        """
        Self-assigns an open ticket to a specific lawyer.

        Race-condition guard: uses .eq("status", "open") so that if two lawyers
        click "Claim" simultaneously, only the first one succeeds.
        Returns False (rather than raising) if the ticket was already claimed.
        """
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
            return True
        except Exception as exc:
            logger.error(f"❌ Failed to assign ticket {ticket_id} | {exc}")
            return False

    def admin_assign_ticket(self, ticket_id: str, lawyer_id: str) -> bool:
        """
        Admin force-assigns a ticket to a lawyer regardless of current status.
        Works on any status: open, assigned, booked.
        Used by admin for overrides and reassignments at any time.
        """
        try:
            now = datetime.utcnow().isoformat()
            resp = self._supabase.table("hitl_tickets").update({
                "assigned_lawyer_id": lawyer_id,
                "status": "assigned",
                "assigned_at": now,
                # Reset booking fields if admin is reassigning
                "booking_cal_booking_id": None,
                "booking_url": None,
                "booking_confirmed_at": None,
            }).eq("ticket_id", ticket_id).execute()

            if not resp.data:
                logger.warning(f"⚠️ admin_assign_ticket: ticket {ticket_id} not found")
                return False

            logger.info(f"🎫 Admin assigned ticket | ticket={ticket_id} | lawyer={lawyer_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ admin_assign_ticket failed | {ticket_id} | {exc}")
            return False

    def admin_unassign_ticket(self, ticket_id: str) -> bool:
        """
        Admin removes the lawyer assignment from a ticket, resetting it to 'open'.
        """
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

    def get_ticket_with_user_details(self, ticket_id: str, lawyer_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches full ticket details including the user's profile info.
        Enforces that ONLY the assigned lawyer can see this.

        Returns the ticket with a 'user_info' key containing:
          - email, user_name (from users table)
          - display_name, phone_number (from user_profiles)
        """
        try:
            # hitl_tickets has two FKs to users (user_id and assigned_lawyer_id)
            # We must use the explicit FK hint for the user join to avoid ambiguity
            response = (
                self._supabase.table("hitl_tickets")
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  user_id, email, user_name, "
                    "  user_profiles(display_name, phone_number)"
                    ")"
                )
                .eq("ticket_id", ticket_id)
                .execute()
            )

            if not response.data:
                return None

            ticket = response.data[0]

            # Security check: only the assigned lawyer can view details
            if ticket.get("assigned_lawyer_id") != lawyer_id:
                logger.warning(
                    f"Unauthorized access to ticket details | "
                    f"lawyer={lawyer_id} | ticket={ticket_id}"
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

            return ticket

        except Exception as exc:
            logger.error(f"Failed to fetch ticket details {ticket_id} | {exc}")
            return None

    def get_lawyer_resolved_history(self, lawyer_id: str) -> List[Dict[str, Any]]:
        """
        Returns all tickets resolved by a specific lawyer.
        """
        try:
            response = self._supabase.table("hitl_tickets") \
                .select(
                    "*, "
                    "users!hitl_tickets_user_id_fkey("
                    "  user_profiles(display_name)"
                    ")"
                ) \
                .eq("assigned_lawyer_id", lawyer_id) \
                .eq("status", "resolved") \
                .order("resolved_at", desc=True) \
                .execute()
            
            data = response.data or []
            # Flatten for cleaner consumption
            for ticket in data:
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = raw_user.get("user_profiles", {}) or {}
                ticket["user_display_name"] = raw_profile.get("display_name")
                
            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch lawyer history | {exc}")
            return []

    def get_lawyer_active_tickets(self, lawyer_id: str) -> List[Dict[str, Any]]:
        """
        Returns tickets assigned to a specific lawyer that are NOT resolved or closed.
        Includes user and conversation details.
        """
        try:
            response = self._supabase.table("hitl_tickets") \
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
                .order("assigned_at", desc=True) \
                .execute()
            
            data = response.data or []
            # Flatten for cleaner consumption
            for ticket in data:
                raw_user = ticket.pop("users", {}) or {}
                raw_profile = raw_user.get("user_profiles", {}) or {}
                ticket["user_email"] = raw_user.get("email")
                ticket["user_display_name"] = raw_profile.get("display_name")
                ticket["user_phone_number"] = raw_profile.get("phone_number")
                
                conv_data = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv_data.get("conversation_summary")
                
            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch lawyer active tickets | {exc}")
            return []

    def get_user_tickets(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Returns all tickets created by a specific user.
        Includes the assigned lawyer's name if the ticket is claimed.
        """
        try:
            response = self._supabase.table("hitl_tickets") \
                .select(
                    "*, "
                    "lawyer:users!hitl_tickets_assigned_lawyer_id_fkey("
                    "  user_name, "
                    "  user_profiles(display_name)"
                    ")"
                ) \
                .eq("user_id", user_id) \
                .order("created_at", desc=True) \
                .execute()
            
            # Clean up the lawyer name for easier frontend consumption
            data = response.data or []
            for ticket in data:
                lawyer = ticket.pop("lawyer", {}) or {}
                if lawyer:
                    profile = lawyer.get("user_profiles", {}) or {}
                    ticket["assigned_lawyer_name"] = profile.get("display_name") or lawyer.get("user_name")
                else:
                    ticket["assigned_lawyer_name"] = None
                    
            return data
        except Exception as exc:
            logger.error(f"❌ Failed to fetch user tickets | {exc}")
            return []

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SINGLE TICKET LOOKUP (used by Cal routes + webhook)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_ticket_by_id(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetches a single ticket by ID with flattened user info and assigned lawyer info.
        Used internally by cal.py routes and cal_webhooks.py.
        Returns None if not found.
        """
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # BOOKING UPDATE (called by Cal.com webhook)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def update_booking(
        self,
        ticket_id: str,
        cal_booking_id: str,
        booking_url: Optional[str],
        meeting_time: Optional[str] = None,
    ) -> bool:
        """
        Updates the ticket with booking details.
        Repurposes booking_confirmed_at to store the actual meeting start time.
        """
        try:
            now = datetime.utcnow().isoformat()
            update_data: Dict[str, Any] = {
                "booking_cal_booking_id": cal_booking_id,
                "booking_confirmed_at": meeting_time or now,
                "status": "booked",
            }
            if booking_url:
                update_data["booking_url"] = booking_url

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
            return True
        except Exception as exc:
            logger.error(f"❌ update_booking failed | {ticket_id} | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # ADMIN FULL QUEUE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_all_tickets_for_admin(self) -> List[Dict[str, Any]]:
        """
        Returns ALL tickets across all statuses for the admin case queue.
        Includes user info, assigned lawyer info, booking URL, and outcome notes.

        Statuses returned: open, assigned, booked, resolved, closed
        """
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OUTCOME NOTES + CLOSE
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def resolve_ticket_with_notes(
        self,
        ticket_id: str,
        lawyer_id: str,
        content: str,
        outcome_notes: Optional[str] = None,
    ) -> bool:
        """
        Lawyer resolves a ticket with a response + optional outcome notes.
        Saves the response in hitl_responses and updates the ticket.
        """
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
            return True
        except Exception as exc:
            logger.error(f"❌ resolve_ticket_with_notes failed | {ticket_id} | {exc}")
            return False

    def close_ticket_admin(
        self,
        ticket_id: str,
        outcome_notes: Optional[str] = None,
    ) -> bool:
        """
        Admin closes a ticket with optional billing/outcome notes.
        Can close from any status.
        """
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
            return True
        except Exception as exc:
            logger.error(f"❌ close_ticket_admin failed | {ticket_id} | {exc}")
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 30-MINUTE ALERT SUPPORT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_unassigned_tickets_older_than_minutes(
        self,
        minutes: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Returns open tickets that have been unassigned for more than `minutes`
        AND for which no alert has been sent yet (alert_sent_at IS NULL).

        Called by the asyncio background task in main.py every 30 minutes.
        """
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
                .lt("created_at", cutoff)         # older than cutoff
                .is_("alert_sent_at", "null")     # alert not yet sent
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
        """
        Marks alert_sent_at = NOW() for a list of ticket IDs so the background
        task doesn't fire duplicate alerts for the same ticket.
        """
        if not ticket_ids:
            return
        try:
            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update(
                {"alert_sent_at": now}
            ).in_("ticket_id", ticket_ids).execute()
            logger.info(f"✅ Alert marked sent for {len(ticket_ids)} tickets")
        except Exception as exc:
            logger.warning(f"⚠️ mark_alert_sent failed | {exc}")
