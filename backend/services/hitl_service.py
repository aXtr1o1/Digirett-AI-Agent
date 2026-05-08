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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # LAWYER ACTIONS
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_open_tickets(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Returns all tickets in 'open' status for the queue.
        """
        try:
            query = self._supabase.table("hitl_tickets").select("*, user_profiles(display_name)").eq("status", "open")
            # Placeholder tenant guard: if we eventually require multi-tenancy, uncomment below:
            # if tenant_id:
            #     query = query.eq("tenant_id", tenant_id)
            
            response = query.order("created_at", desc=False).execute()
            return response.data or []
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
