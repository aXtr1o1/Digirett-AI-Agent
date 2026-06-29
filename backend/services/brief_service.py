import json
import logging
from typing import Any, Dict, Optional
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage
from config import settings
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)

class BriefService:
    def __init__(self, supabase_client: SupabaseClient) -> None:
        self._supabase = supabase_client
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.3,
        )

    async def generate_case_brief(self, ticket_id: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches conversation messages, calls the LLM with a structured prompt,
        and saves the generated JSON brief in hitl_tickets.ai_brief.
        """
        try:
            logger.info(f"📋 Generating case brief for ticket={ticket_id}...")
            
            if not conversation_id:
                ticket_res = self._supabase.table("hitl_tickets").select("conversation_id").eq("ticket_id", ticket_id).execute()
                if ticket_res.data:
                    conversation_id = ticket_res.data[0].get("conversation_id")
            
            if not conversation_id:
                logger.warning(f"⚠️ No conversation_id found for ticket {ticket_id}")
                return {}

            logger.info(f"📋 Generating case brief for ticket={ticket_id} conversation={conversation_id}...")
            # Fetch all non-deleted messages
            resp = self._supabase.table("messages")\
                .select("role, content")\
                .eq("conversation_id", conversation_id)\
                .or_("is_deleted.is.null,is_deleted.eq.false")\
                .order("created_at", desc=False)\
                .execute()

            messages = resp.data or []
            if not messages:
                logger.warning(f"⚠️ No messages found for conversation {conversation_id}")
                return {}

            convo_text = ""
            for msg in messages:
                role = msg.get("role", "user").upper()
                content = msg.get("content", "")
                convo_text += f"{role}: {content}\n"

            prompt = f"""You are an expert legal assistant. Analyze the following conversation between a user and a legal AI assistant.
Generate a structured case brief for the lawyer who will consult the user.

Return ONLY a raw JSON object with the following keys, without any markdown formatting or backticks:
- matter_type: A short string specifying the type of legal matter (e.g. "Company Formation", "Employment Dispute", "Rental Contract Issue").
- key_issues: A list of 2-4 key issues identified in the conversation (bullet points as strings).
- relevant_laws: A list of relevant statutes, acts, or regulations mentioned or applicable (e.g. "Aksjeloven", "Arbeidsmiljøloven").
- risk_level: A single string, either "Low", "Moderate", or "High", assessing the urgency and risk.

CONVERSATION:
{convo_text}

JSON response:"""

            response = await self._llm.agenerate([[HumanMessage(content=prompt)]])
            raw_json = response.generations[0][0].text.strip()

            # Clean markdown code block markers if present
            if raw_json.startswith("```"):
                lines = raw_json.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines[-1].startswith("```"):
                    lines = lines[:-1]
                raw_json = "\n".join(lines).strip()

            brief_data = json.loads(raw_json)

            # Save to database
            self._supabase.table("hitl_tickets")\
                .update({"ai_brief": brief_data})\
                .eq("ticket_id", ticket_id)\
                .execute()

            logger.info(f"✅ Successfully generated and stored brief for ticket {ticket_id}")
            return brief_data

        except Exception as exc:
            logger.error(f"❌ Failed to generate case brief for ticket {ticket_id} | {exc}", exc_info=True)
            return {}
