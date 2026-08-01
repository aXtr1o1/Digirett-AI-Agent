"""
services/brief_service.py — Case Brief Generation Service
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from db.supabase_client import SupabaseClient
from services.llm_service import LLMService
from utils.json_response_parser import parse_json_response

logger = logging.getLogger(__name__)

_PROMPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "prompts",
    "case_brief.txt",
)


class CaseBrief(BaseModel):
    matter_type: str = Field(description="Short title specifying legal matter type")
    key_issues: List[str] = Field(default_factory=list, description="2-4 key issues identified")
    relevant_laws: List[str] = Field(default_factory=list, description="Relevant statutes mentioned or applicable")
    risk_level: str = Field(default="Low", description="Risk level string: Low, Moderate, or High")


class ConversationFormatter:
    @staticmethod
    def format_messages(messages: List[Dict[str, Any]]) -> str:
        convo_lines = []
        for msg in messages:
            role = str(msg.get("role", "user")).upper()
            content = str(msg.get("content", ""))
            convo_lines.append(f"{role}: {content}")
        return "\n".join(convo_lines)


class BriefService:
    def __init__(self, supabase_client: SupabaseClient, llm_service: Optional[LLMService] = None) -> None:
        self._supabase = supabase_client
        self._llm_service = llm_service or LLMService()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4), reraise=True)
    async def _generate_llm_response(self, prompt: str) -> str:
        return await self._llm_service.agenerate(prompt)

    async def generate_case_brief(self, ticket_id: str, conversation_id: Optional[str] = None) -> CaseBrief:
        """
        Fetches conversation messages, calls LLM, and saves the CaseBrief model into Supabase.
        """
        try:
            logger.info(f"📋 Generating case brief for ticket={ticket_id}...")

            if not conversation_id:
                ticket_res = self._supabase.execute_query(
                    self._supabase.table("hitl_tickets").select("conversation_id").eq("ticket_id", ticket_id)
                )
                if ticket_res.data:
                    conversation_id = ticket_res.data[0].get("conversation_id")

            if not conversation_id:
                logger.warning(f"⚠️ No conversation_id found for ticket {ticket_id}")
                return CaseBrief(matter_type="General Inquiry", key_issues=[], relevant_laws=[], risk_level="Low")

            resp = self._supabase.execute_query(
                self._supabase.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=False)
            )

            messages = resp.data or []
            if not messages:
                logger.warning(f"⚠️ No messages found for conversation {conversation_id}")
                return CaseBrief(matter_type="General Inquiry", key_issues=[], relevant_laws=[], risk_level="Low")

            convo_text = ConversationFormatter.format_messages(messages)

            prompt_template = ""
            if os.path.exists(_PROMPT_PATH):
                with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
                    prompt_template = f.read()
            else:
                prompt_template = "Analyze the conversation and return JSON case brief:\n{convo_text}"

            prompt = prompt_template.format(convo_text=convo_text)
            raw_response = await self._generate_llm_response(prompt)
            brief_dict = parse_json_response(raw_response)

            brief = CaseBrief(**brief_dict) if brief_dict else CaseBrief(matter_type="General Inquiry", key_issues=[], relevant_laws=[], risk_level="Low")
            self._supabase.save_case_brief(ticket_id, brief.model_dump())

            logger.info(f"[OK] Successfully generated and stored brief for ticket {ticket_id}")
            return brief

        except Exception as exc:
            logger.error(f"[ERROR] Failed to generate case brief for ticket {ticket_id} | {exc}", exc_info=True)
            return CaseBrief(matter_type="General Inquiry", key_issues=[], relevant_laws=[], risk_level="Low")
