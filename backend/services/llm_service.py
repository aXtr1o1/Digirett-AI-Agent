

import logging
import re
import json
from typing import Dict, AsyncIterator, Optional, List, Any

from ..config import settings
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ① INTENT AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IntentAgent:
    

    INTENT_SYSTEM_PROMPT = """You are a binary classifier. Classify the user's query as either CASUAL or LEGAL and Find user 's query language.


OUTPUT FORMAT (JSON only):
{"intent": "CASUAL", "language": "english"}
OR
{"intent": "LEGAL", "language": "norwegian"}

Respond ONLY with valid JSON. No other text."""

    def __init__(self):
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.1,
        )
        logger.info("✅ IntentAgent initialized")

    async def run(self, query: str) -> Dict[str, str]:
        """
        Detect intent and language.

        Args:
            query: Raw user query (may include context prefix from MemoryAgent)

        Returns:
            {"intent": "CASUAL|LEGAL", "language": "norwegian|english"}
        """
        logger.info(f"🔍 IntentAgent.run: '{query[:60]}...'")

        # ── PRIMARY: LLM ──────────────────────────────────────
        try:
            messages = [
                SystemMessage(content=self.INTENT_SYSTEM_PROMPT),
                HumanMessage(content=query),
            ]
            response = await self._llm.agenerate([messages])
            content = response.generations[0][0].text.strip()
            content = re.sub(r"```json\s*", "", content)
            content = re.sub(r"```\s*", "", content).strip()

            m = re.search(r"\{[^}]+\}", content)
            if m:
                result = json.loads(m.group(0))
                intent = result.get("intent", "CASUAL").upper()
                language = result.get("language", "english").lower()
                logger.info(f"✅ IntentAgent (LLM): intent={intent}, language={language}")
                return {"intent": intent, "language": language}

        except Exception as e:
            logger.warning(f"⚠️  IntentAgent LLM failed, falling back to keywords | {e}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ② MEMORY AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class MemoryAgent:

    def __init__(self, redis_client: Any, supabase_client: Any):
        self.redis = redis_client
        self.supabase = supabase_client
        logger.info("✅ MemoryAgent initialized")

    def run(self, conversation_id: str, limit: int = 10) -> List[Dict[str, str]]:
        
        logger.info(f"🧠 MemoryAgent.run: conversation_id={conversation_id}")

        # ── Redis fast path ────────────────────────────────────
        try:
            cached = self.redis.get_context(conversation_id)
            if cached:
                messages = self._normalize(cached[-limit:])
                logger.info(f"✅ MemoryAgent (Redis): {len(messages)} messages")
                return messages
        except Exception as e:
            logger.warning(f"⚠️  MemoryAgent Redis error: {e}")

        # ── Supabase slow path ─────────────────────────────────
        try:
            response = (
                self.supabase.table("messages")
                .select("role, content, created_at")
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            messages = self._normalize(response.data or [])
            logger.info(f"✅ MemoryAgent (Supabase): {len(messages)} messages")
            return messages
        except Exception as e:
            logger.error(f"❌ MemoryAgent Supabase error: {e}", exc_info=True)
            return []

    def build_intent_context(
        self,
        conversation_id: str,
        current_query: str,
        n_messages: int = 2,
    ) -> str:
        """
        Build a context-aware string for IntentAgent so follow-up
        questions are classified correctly.

        Returns:
            "User: prev_q\\nAssistant: prev_a\\nUser: current_query"
        """
        history = self.run(conversation_id, limit=n_messages)
        if not history:
            return current_query
        parts = [f"{m['role'].capitalize()}: {m['content']}" for m in history]
        parts.append(f"User: {current_query}")
        return "\n".join(parts)

    @staticmethod
    def _normalize(raw: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        result = []
        for msg in raw:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                result.append({"role": role, "content": content})
        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ③ GENERATOR AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GeneratorAgent:
    

    # ── CASUAL (unchanged) ────────────────────────────────────
    CASUAL_SYSTEM_PROMPT = """You are a friendly, helpful AI assistant.

Your personality:
- Warm and conversational
- Natural and human-like
- Match the user's language (Norwegian ↔ English)
- Keep responses brief and friendly
- Use emojis sparingly (1-2 per message if appropriate)

Response style:
- For greetings: Greet back warmly and ask how you can help
- For emotional support: Be empathetic and kind
- For general help: Be friendly and offer assistance

IMPORTANT RULES:
- NO formal legal language unless asked
- Be natural and human
- Match their energy and tone
- Keep it conversational"""


    LEGAL_UNIFIED_PROMPT = """You are a professional AI Legal Assistant specialized in Norwegian law from Lovdata.

CRITICAL RULES:
1. ONLY use information from the provided KILDER (sources) below
2. NEVER use your general knowledge about Norwegian law
3. NEVER invent, assume, or hallucinate legal information
4. If sources don't contain the answer, say: "I cannot find relevant legal excerpts in the available Lovdata database."

RESPONSE STRUCTURE:
- Write in a clear, structured ChatGPT-style format using subheadings (###)
- Use short sections with descriptive headings
- Keep explanations brief and easy to understand
- Summarize the legal meaning instead of copying statutory wording
- Keep the total answer brief (maximum 250 words unless absolutely required by the sources)
- Be professional but approachable — NO unnecessary jargon

LANGUAGE RULE:
- ALWAYS respond in the SAME language as the user's question
- If user asks in English → Answer in English (even if sources are Norwegian)
- If user asks in Norwegian → Answer in Norwegian (even if sources are English)

SCORING RULES — append on the very last line, after your answer:
- [SCORE:0.9] to [SCORE:1.0] → Sources fully answer the query with clear, direct information
- [SCORE:0.5] to [SCORE:0.8] → Sources partially answer the query or answer is somewhat relevant
- [SCORE:0.1] to [SCORE:0.4] → Sources are vague, barely relevant, or don't answer the query

IMPORTANT: After your complete answer, append EXACTLY this on its own line (no spaces, no extra text):
[SCORE:0.9]
Replace 0.9 with the actual score based on source relevance. This line must always be present."""

    def __init__(self, temperature: float = 0.7):
        self._temperature = temperature
        logger.info("✅ GeneratorAgent initialized")

    def _make_llm(self, temperature: float, streaming: bool = False) -> AzureChatOpenAI:
        return AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=temperature,
            streaming=streaming,
        )

    # ── CASUAL streaming ───────────────────────────────────────
    async def stream_casual(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Yield raw casual response tokens. No scoring."""
        logger.info("💬 GeneratorAgent: casual stream")
        messages = [SystemMessage(content=self.CASUAL_SYSTEM_PROMPT)]

        if conversation_history:
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        messages.append(HumanMessage(content=query))
        llm = self._make_llm(temperature=temperature or 0.7, streaming=True)

        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

        logger.info("✅ GeneratorAgent: casual stream complete")

    # ── LEGAL unified streaming ────────────────────────────────
    async def stream_legal(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """
        Yield every token INCLUDING the trailing [SCORE:x.x] line.
        Callers that show text to users must strip it (done in LLMService).
        Callers that need the score collect the full stream then parse it.
        """
        logger.info("⚖️  GeneratorAgent: legal stream (unified prompt)")

        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts from my knowledge"
            )
            for char in error_msg:
                yield char
            yield "\n[SCORE:0.1]"
            return

        messages = [SystemMessage(content=self.LEGAL_UNIFIED_PROMPT)]

        if conversation_history:
            logger.info(
                f"🧠 GeneratorAgent: injecting {len(conversation_history)} history msgs"
            )
            for msg in conversation_history:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        user_prompt = (
            f"CRITICAL: Answer ONLY from sources below.\n\n"
            f"KILDER (Sources):\n{rag_context}\n\n"
            f"SPØRSMÅL (Question):\n{query}\n\n"
            f"Respond in {language}. Be direct and cite sources.\n"
            f"Append [SCORE:x.x] on the very last line."
        )
        messages.append(HumanMessage(content=user_prompt))

        llm = self._make_llm(temperature=temperature or 0.2, streaming=True)

        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

        logger.info("✅ GeneratorAgent: legal stream complete")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ④ ORCHESTRATOR AGENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OrchestratorAgent:
    

    def __init__(
        self,
        intent_agent: "IntentAgent",
        memory_agent: "MemoryAgent",
        generator_agent: "GeneratorAgent",
    ):
        self.intent_agent = intent_agent
        self.memory_agent = memory_agent
        self.generator_agent = generator_agent
        logger.info("✅ OrchestratorAgent initialized")

    async def classify(
        self,
        query: str,
        conversation_id: str,
    ) -> Dict[str, str]:
        
        intent_input = self.memory_agent.build_intent_context(
            conversation_id=conversation_id,
            current_query=query,
            n_messages=2,
        )
        result = await self.intent_agent.run(intent_input)
        logger.info(
            f"🎯 OrchestratorAgent.classify: intent={result['intent']}, "
            f"language={result['language']}"
        )
        return result

    def load_history(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        
        return self.memory_agent.run(conversation_id, limit=limit)




class LLMService:
    """
    LLM service using LangChain + Azure OpenAI.
    Handles intent detection, language detection, and message generation with scoring.

    Public interface is 100% unchanged.
    Internal implementation delegates to agent classes.
    """

    # ── Backward-compatible prompt constants ──────────────────
    INTENT_SYSTEM_PROMPT = IntentAgent.INTENT_SYSTEM_PROMPT
    CASUAL_SYSTEM_PROMPT = GeneratorAgent.CASUAL_SYSTEM_PROMPT
    # Both names now point to the unified prompt
    LEGAL_SYSTEM_PROMPT  = GeneratorAgent.LEGAL_UNIFIED_PROMPT
    LEGAL_STREAM_PROMPT  = GeneratorAgent.LEGAL_UNIFIED_PROMPT

    def __init__(self, temperature: float = 0.7):
        try:
            # Keep self.llm for check_connection (unchanged usage)
            self.llm = AzureChatOpenAI(
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
                temperature=temperature,
            )

            # ── Instantiate agents ─────────────────────────────
            self._intent_agent    = IntentAgent()
            self._generator_agent = GeneratorAgent(temperature=temperature)


            logger.info(
                "✅ Azure OpenAI LLM initialized | "
                f"Deployment: {settings.AZURE_OPENAI_DEPLOYMENT}"
            )

        except Exception as e:
            logger.error(
                f"❌ Failed to initialize Azure OpenAI LLM | "
                f"{type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise

    # ── Factory methods (used by rag_service.py) ──────────────

    def get_intent_agent(self) -> IntentAgent:
        return self._intent_agent

    def get_generator_agent(self) -> GeneratorAgent:
        return self._generator_agent

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # check_connection  ── UNCHANGED
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def check_connection(self) -> bool:
        """Test Azure OpenAI connection"""
        try:
            messages = [HumanMessage(content="test")]
            await self.llm.agenerate([messages])
            return True
        except Exception as e:
            logger.error(
                f"❌ Azure OpenAI connection check failed | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # detect_intent  ── UNCHANGED signature
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def detect_intent(self, query: str) -> Dict[str, str]:
        """
        Detect intent and language.
        PRIMARY: LLM-based detection (intent + language together)
        FALLBACK: Keyword-based detection

        Returns:
            {"intent": "CASUAL|LEGAL", "language": "norwegian|english"}
        """
        return await self._intent_agent.run(query)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # generate_casual_stream  ── UNCHANGED signature
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def generate_casual_stream(
        self,
        query: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """
        Generate casual conversation response (streaming).

        Yields:
            Response tokens
        """
        try:
            logger.info("💬 Generating casual response (streaming)")
            async for token in self._generator_agent.stream_casual(
                query=query,
                conversation_history=conversation_history,
                temperature=temperature,
            ):
                yield token
            logger.info("✅ Casual response streaming complete")
        except Exception as e:
            logger.error(
                f"❌ Casual response generation failed | "
                f"Query: {query[:50]} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise



    async def generate_legal_answer(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        
        logger.info("⚖️  Generating legal response with score (streaming internally)")

        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts in the available Lovdata database."
            )
            return {
                "answer": error_msg,
                "score": 0.1,
                "confidence": "No sources available",
                "tokens_used": 0,
            }

        # Collect full stream to parse [SCORE:x.x]
        full_text = ""
        try:
            async for token in self._generator_agent.stream_legal(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=conversation_history,
                temperature=temperature,
            ):
                full_text += token
        except Exception as e:
            logger.error(
                f"❌ generate_legal_answer failed | {type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

        answer, score = _extract_score(full_text)
        confidence = _score_to_confidence(score)

        logger.info(f"✅ Legal answer generated — Score: {score}, Confidence: {confidence}")

        return {
            "answer": answer,
            "score": score,
            "confidence": confidence,
            "tokens_used": 0,
        }



    async def generate_legal_stream(
        self,
        query: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        
        logger.info("⚖️  Generating legal response (streaming)")

        if not rag_context or not rag_context.strip():
            error_msg = (
                "Jeg finner ingen relevante lovutdrag i den tilgjengelige Lovdata-databasen."
                if language == "norwegian"
                else "I cannot find any relevant legal excerpts in the available Lovdata database."
            )
            for char in error_msg:
                yield char
            return

        score_pattern = re.compile(r"\[SCORE:[0-9.]+\]")

        buffer = ""

        try:
            async for token in self._generator_agent.stream_legal(
                query=query,
                rag_context=rag_context,
                language=language,
                conversation_history=conversation_history,
                temperature=temperature,
            ):
                buffer += token

                # Full score tag arrived — flush clean text and stop
                if score_pattern.search(buffer):
                    clean = score_pattern.split(buffer)[0].rstrip("\n")
                    if clean:
                        yield clean
                    logger.info("✅ Legal streaming complete (score tag detected)")
                    return

                # Safe to yield everything except the tail guard
                if len(buffer) > 15:
                    yield buffer[:-15]
                    buffer = buffer[-15:]

            # Flush remaining buffer (model may not have appended the tag)
            if buffer:
                clean = score_pattern.sub("", buffer).rstrip("\n")
                if clean:
                    yield clean

        except Exception as e:
            logger.error(
                f"❌ Legal response generation failed | "
                f"Query: {query[:50]} | "
                f"Error: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise

        logger.info("✅ Legal response streaming complete")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MODULE-LEVEL HELPERS (used by LLMService methods above)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _extract_score(full_text: str):
    """
    Parse [SCORE:x.x] from the end of a legal stream response.

    Returns:
        (answer_without_score_line: str, score: float)
    """
    score_pattern = re.compile(r"\[SCORE:([0-9.]+)\]")
    m = score_pattern.search(full_text)

    if m:
        score = min(max(float(m.group(1)), 0.0), 1.0)   # clamp to [0, 1]
        answer = score_pattern.sub("", full_text).rstrip("\n").strip()
    else:
        logger.warning("⚠️  No [SCORE:x.x] in legal response, defaulting to 0.5")
        score = 0.5
        answer = full_text.strip()

    return answer, score


def _score_to_confidence(score: float) -> str:
    if score >= 0.9:
        return "Fully supported by sources"
    elif score >= 0.5:
        return "Partially supported by sources"
    else:
        return "Weakly supported or not found in sources"