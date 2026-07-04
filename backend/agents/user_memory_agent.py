import logging
from typing import Any
import json
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

class UserMemoryAgent:
    def __init__(self, supabase_client: Any):
        self._supabase = supabase_client
        logger.info("✅ UserMemoryAgent initialized")

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
            facts = [row["fact"] for row in (response.data or [])]
            if not facts:
                return ""
            
            context = "\n[User Memory]\n"
            for fact in facts:
                context += f"- {fact}\n"
            return context
        except Exception as exc:
            logger.warning(f"⚠️ UserMemoryAgent get_user_context failed | {exc}")
            return ""

    async def extract_and_save_facts(self, user_id: str, message: str, llm_service: Any) -> None:
        """
        Extract personal facts from a user message and save them to the database.
        Designed to be run asynchronously in the background.
        """
        if not user_id or not message:
            return

        try:
            system_prompt = (
                "You are a memory extraction assistant. "
                "Analyze the user's message to find explicit, permanent personal details (e.g., name, profession, location, ongoing preferences). "
                "Ignore temporary states, conversational pleasantries, or questions. "
                "Return ONLY a JSON array of strings representing the individual facts extracted (e.g., [\"User lives in Oslo\", \"User is a lawyer\"]). "
                "If no facts are found, return exactly []. "
                "Output nothing but the JSON array."
            )
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"User message: {message}")
            ]
            
            # Using the fast underlying LLM directly
            response = await llm_service._llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()
            
            if not raw_output or raw_output == "[]":
                return
            
            # Clean up potential markdown formatting if the model disobeys
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:-3].strip()
            elif raw_output.startswith("```"):
                raw_output = raw_output[3:-3].strip()
                
            try:
                new_facts = json.loads(raw_output)
            except json.JSONDecodeError:
                logger.warning(f"⚠️ Failed to parse JSON from memory extraction: {raw_output}")
                return
                
            if not isinstance(new_facts, list) or not new_facts:
                return
                
            for fact in new_facts:
                if isinstance(fact, str) and fact.strip():
                    self._supabase.table("user_memories").insert({
                        "user_id": user_id,
                        "fact": fact.strip()
                    }).execute()
                    
            logger.info(f"🧠✅ UserMemoryAgent: Extracted and saved {len(new_facts)} new facts for user={user_id}")
            
        except Exception as exc:
            logger.error(f"❌ UserMemoryAgent extract_and_save_facts failed | {exc}", exc_info=True)
