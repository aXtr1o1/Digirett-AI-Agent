"""
agents/orchestrator_agent.py — Workflow Orchestrator Agent

Refactored per TL Code Review Guidelines:
1. Orchestrates intent classification, history loading, and casual generation workflow.
2. Utilizes injected GeneratorAgent dependency.
3. Returns typed IntentResult Pydantic model from classification.
4. Uses named constants (INTENT_CONTEXT_MESSAGES = 2).
"""

import logging
from typing import AsyncIterator, Dict, List, Optional

from agents.generator_agent import GeneratorAgent
from agents.intent_agent import IntentAgent, IntentResult
from services.memory_service import ConversationMemoryService

logger = logging.getLogger(__name__)

# ── NAMED CONSTANTS ──────────────────────────────────────────────────
INTENT_CONTEXT_MESSAGES = 2


class OrchestratorAgent:
    
    def __init__(
        self,
        intent_agent: IntentAgent,
        memory_agent: ConversationMemoryService,
        generator_agent: GeneratorAgent,
    ) -> None:
        self._intent = intent_agent
        self._memory = memory_agent
        self._generator = generator_agent
        logger.info("[OK] OrchestratorAgent initialized")

    async def classify(
        self,
        query: str,
        conversation_id: str,
    ) -> IntentResult:
        """
        Builds intent context and delegates to IntentAgent.
        Returns typed IntentResult Pydantic model.
        """
        intent_input = self._memory.build_intent_context(
            conversation_id=conversation_id,
            current_query=query,
            n_messages=INTENT_CONTEXT_MESSAGES,
        )
        res_dict = await self._intent.run(intent_input)
        
        result = IntentResult(
            intent=res_dict.get("intent", "CASUAL"),
            language=res_dict.get("language", "english"),
        )
        logger.info(f"OrchestratorAgent: intent={result.intent}, language={result.language}")
        return result

    def load_history(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """Delegates history retrieval to ConversationMemoryService."""
        return self._memory.run(conversation_id, limit=limit)

    async def generate_casual(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        language: Optional[str] = None,
        user_memory: str = "",
    ) -> AsyncIterator[str]:
        """Orchestrates casual response streaming via injected GeneratorAgent."""
        logger.info("OrchestratorAgent: delegating to GeneratorAgent.stream_casual()")
        async for chunk in self._generator.stream_casual(
            query=query,
            conversation_history=conversation_history,
            language=language,
            user_memory=user_memory,
        ):
            yield chunk