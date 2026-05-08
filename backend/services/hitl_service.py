import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

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
                .in_("status", ["open", "assigned"]) \
                .execute()
            return len(response.data or []) > 0
        except Exception as exc:
            logger.error(f"❌ Failed to check escalation status | {exc}")
            return False

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
        Returns all tickets in 'open' status for the queue.
        """
        try:
            # Join via users table to get profile info, and conversations to get AI summary
            query = self._supabase.table("hitl_tickets").select(
                "*, "
                "conversations!hitl_tickets_conversation_id_fkey(conversation_summary), "
                "users!hitl_tickets_user_id_fkey("
                "  email, "
                "  user_profiles(display_name, phone_number)"
                ")"
            ).eq("status", "open")
            
            response = query.order("created_at", desc=False).execute()
            data = response.data or []
            
            # Flatten
            for ticket in data:
                # Extract conversation summary
                conv_data = ticket.pop("conversations", {}) or {}
                ticket["conversation_summary"] = conv_data.get("conversation_summary")

                # Extract user details
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
        """
        try:
            now = datetime.utcnow().isoformat()
            self._supabase.table("hitl_tickets").update({
                "assigned_lawyer_id": lawyer_id,
                "status": "assigned",
                "assigned_at": now,
            }).eq("ticket_id", ticket_id).eq("status", "open").execute()
            
            logger.info(f"🎫 Ticket assigned | ticket={ticket_id} | lawyer={lawyer_id}")
            return True
        except Exception as exc:
            logger.error(f"❌ Failed to assign ticket {ticket_id} | {exc}")
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
