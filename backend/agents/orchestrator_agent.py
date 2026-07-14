
import logging
from typing import Dict, List

from agents.intent_agent import IntentAgent
from agents.memory_agent import MemoryAgent
from agents.generator_agent import GeneratorAgent

logger = logging.getLogger(__name__)


class OrchestratorAgent:
    
    def __init__(
        self,
        intent_agent: IntentAgent,
        memory_agent: MemoryAgent,
        generator_agent: GeneratorAgent,
    ) -> None:
        self._intent = intent_agent
        self._memory = memory_agent
        self._generator = generator_agent
        logger.info(" OrchestratorAgent initialized")

    async def classify(
        self,
        query: str,
        conversation_id: str,
    ) -> Dict[str, str]:
       
        # Build a short context string so IntentAgent handles follow-ups correctly
        intent_input = self._memory.build_intent_context(
            conversation_id=conversation_id,
            current_query=query,
            n_messages=2,
        )
        result = await self._intent.run(intent_input)
        logger.info(
            f" OrchestratorAgent: intent={result['intent']}, language={result['language']}"
        )
        return result

    def load_history(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        
        return self._memory.run(conversation_id, limit=limit)