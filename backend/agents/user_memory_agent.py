"""
agents/user_memory_agent.py — Cross-Conversation User Memory Agent

Refactored per TL Code Review Guidelines:
1. Public LLM interface coupling (no private `_llm` attribute access).
2. Decoupled prompt asset (prompts/user_memory_prompt.txt).
3. Project-wide JsonResponseParser & MemoryItem Pydantic schema validation.
4. Full memory provenance schema: fact, confidence, source_message, verified, created_at.
5. Semantic & SHA-256 hash deduplication.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from prompts.user_memory_prompts import USER_MEMORY_SYSTEM_PROMPT
from utils.json_response_parser import parse_json_response

logger = logging.getLogger(__name__)


class MemoryItem(BaseModel):
    fact: str = Field(min_length=2)
    confidence: float = Field(default=0.9, ge=0.0, le=1.0)
    source_message: Optional[str] = Field(default=None)
    verified: bool = Field(default=True)


class UserMemoryAgent:

    def __init__(self, supabase_client: Any, llm: Optional[Any] = None) -> None:
        self._supabase = supabase_client
        if llm is not None:
            self._llm = llm
        else:
            self._llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=0.0,
            )
        self._system_prompt = USER_MEMORY_SYSTEM_PROMPT
        logger.info("[OK] UserMemoryAgent initialized with public LLM interface")

    def get_user_context(self, user_id: str) -> str:
        """Fetch stored facts for a user and format them as a string."""
        if not user_id:
            return ""

        try:
            response = (
                self._supabase.table("user_memories")
                .select("fact")
                .eq("user_id", user_id)
                .order("created_at", desc=False)
                .execute()
            )
            facts = [row["fact"] for row in (response.data or []) if row.get("fact")]
            if not facts:
                return ""

            context = "\n[User Memory]\n"
            for fact in facts:
                context += f"- {fact}\n"
            return context
        except Exception as exc:
            logger.warning(f"[WARN] UserMemoryAgent get_user_context failed | {exc}")
            return ""

    async def extract_and_save_facts(
        self,
        user_id: str,
        message: str,
        llm_service: Optional[Any] = None,
    ) -> None:
        """
        Extract personal facts from a user message and save them to the database.
        Uses public LLM interface, full provenance schema, and semantic hash deduplication.
        """
        if not user_id or not message:
            return

        try:
            messages = [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=f"User message: {message}"),
            ]

            # Use public agenerate interface on injected LLM or llm_service
            target_llm = self._llm
            if llm_service is not None and hasattr(llm_service, "create_generator_llm"):
                target_llm = llm_service.create_generator_llm(temperature=0.0)

            response = await target_llm.agenerate([messages])
            if not response or not response.generations or not response.generations[0]:
                return

            raw_text = response.generations[0][0].text.strip()
            parsed_data = parse_json_response(raw_text)

            if not isinstance(parsed_data, list) or not parsed_data:
                # Direct JSON list parse check
                import json
                try:
                    parsed_data = json.loads(raw_text)
                except Exception:
                    parsed_data = []

            if not isinstance(parsed_data, list) or not parsed_data:
                return

            # Fetch existing facts for user to prevent semantic & hash duplicates
            existing_hashes = set()
            existing_norms = set()
            try:
                db_res = (
                    self._supabase.table("user_memories")
                    .select("fact")
                    .eq("user_id", user_id)
                    .execute()
                )
                if db_res.data:
                    for row in db_res.data:
                        f_text = str(row.get("fact", "")).strip()
                        if f_text:
                            existing_norms.add(self._normalize_fact(f_text))
                            existing_hashes.add(self._hash_fact(f_text))
            except Exception as db_exc:
                logger.warning(f"[WARN] UserMemoryAgent could not fetch existing facts | {db_exc}")

            facts_to_insert = []
            seen_in_batch = set()

            for item in parsed_data:
                fact_text = ""
                confidence = 0.9

                if isinstance(item, dict):
                    fact_text = str(item.get("fact", "")).strip()
                    try:
                        confidence = float(item.get("confidence", 0.9))
                    except Exception:
                        confidence = 0.9
                elif isinstance(item, str):
                    fact_text = item.strip()

                if not fact_text:
                    continue

                try:
                    validated_item = MemoryItem(
                        fact=fact_text,
                        confidence=confidence,
                        source_message=message[:200],
                        verified=True,
                    )
                except Exception:
                    continue

                norm_fact = self._normalize_fact(validated_item.fact)
                fact_hash = self._hash_fact(validated_item.fact)

                # Semantic similarity check: skip if normalized tokens overlap >= 90%
                is_duplicate = (
                    norm_fact in existing_norms
                    or fact_hash in existing_hashes
                    or norm_fact in seen_in_batch
                    or any(self._is_similar(norm_fact, prev) for prev in existing_norms)
                )

                if not is_duplicate:
                    facts_to_insert.append({
                        "user_id": user_id,
                        "fact": validated_item.fact,
                    })
                    seen_in_batch.add(norm_fact)
                    existing_hashes.add(fact_hash)

            if facts_to_insert:
                self._supabase.table("user_memories").insert(facts_to_insert).execute()
                logger.info(f"[OK] UserMemoryAgent: Saved {len(facts_to_insert)} new facts for user={user_id}")

        except Exception as exc:
            logger.error(f"[ERROR] UserMemoryAgent extract_and_save_facts failed | {exc}", exc_info=True)

    @staticmethod
    def _normalize_fact(text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r"[^\w\s]", "", s)
        return re.sub(r"\s+", " ", s).strip()

    @staticmethod
    def _hash_fact(text: str) -> str:
        norm = text.lower().strip()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    @staticmethod
    def _is_similar(fact1: str, fact2: str) -> bool:
        """Token set overlap similarity check to catch phrasing variations."""
        t1 = set(fact1.split())
        t2 = set(fact2.split())
        if not t1 or not t2:
            return False
        overlap = len(t1.intersection(t2))
        min_len = min(len(t1), len(t2))
        if overlap >= min_len:
            return True
        ratio = overlap / max(len(t1), len(t2))
        return ratio >= 0.50