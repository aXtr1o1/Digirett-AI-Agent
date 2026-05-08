import logging
from typing import AsyncIterator, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)

class DocumentQAAgent:

    # ── DocQA system prompt ────────────────────────────────────────────
    _DOCQA_SYSTEM_PROMPT = """You are a document analysis assistant.

You may be provided with multiple documents, separated by '==='.
Your ONLY source of information is the DOCUMENT TEXT provided below.

RULES:
1. Analyze the user's question to determine WHICH document(s) they are asking about.
2. If the user asks about "the document", "it", "this", or similar vague terms, assume they mean the MOST RECENT document (the one with the highest Document number).
3. Do NOT summarize or explain all documents unless explicitly asked to do so. Focus your answer ONLY on the relevant document(s).
4. Answer ONLY from the document text — never use external knowledge to answer factual questions. However, you MAY translate, summarize, or explain the document if requested.
5. If the user asks a factual question and the answer is not in the document, say so clearly. Do not use this rule to refuse requests to summarize, explain, or translate the document.
6. Cite the relevant part of the document (and the document name) when answering
7. Respond in the requested language (specified below). If the user explicitly asks to use a different language in their query, honor the user's request over the default.
8. Be precise — quote specific clauses, sections, or passages when relevant
9. Append [SCORE:x.x] on the very last line (0.0-1.0, how well the doc answers the query)

SCORING:
0.9-1.0: Document clearly and directly answers the query
0.5-0.8: Document partially answers or is somewhat relevant
0.1-0.4: Document does not contain relevant information"""

    # ── Hybrid system prompt ───────────────────────────────────────────
    _HYBRID_SYSTEM_PROMPT = """You are a legal document compliance assistant.

You have access to TWO sources:
  1. DOCUMENT TEXT — the user's uploaded document(s) (contract, agreement, etc.)
  2. LEGAL SOURCES — retrieved excerpts from Norwegian law (Lovdata)

RULES:
1. Analyze the user's question to determine WHICH uploaded document(s) they are asking about. If vague, assume the MOST RECENT document (highest Document number).
2. Use BOTH sources to answer — cross-reference them
3. State what the relevant document says, then what the law requires, then your assessment
4. Never invent legal conclusions not supported by the legal sources
5. Never invent document contents not present in the document text. However, you MAY translate, summarize, or explain the text if requested.
6. Respond in the requested language (specified below). If the user explicitly asks to use a different language in their query, honor the user's request.
7. Use this structure:
   ### Document says
   ### Law requires  
   ### Assessment
   ### Conclusion
8. Append [SCORE:x.x] on the very last line (0.0-1.0)

SCORING:
0.9-1.0: Both sources fully support a clear answer
0.5-0.8: Partial match — answer is directional but incomplete
0.1-0.4: Sources don't adequately address the question"""

    def __init__(self, temperature: float = 0.2) -> None:
        self._temperature = temperature
        logger.info("✅ DocumentQAAgent initialized")

    def _make_llm(self, streaming: bool = True) -> AzureChatOpenAI:
        return AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=self._temperature,
            streaming=streaming,
        )

    async def stream_docqa(
        self,
        query: str,
        doc_text: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        
        logger.info("📄 DocumentQAAgent: DOCQA stream starting (document only)")
        logger.debug(f"   Query: '{query[:80]}'")
        logger.debug(f"   Language: {language}")
        logger.debug(f"   Document size: {len(doc_text)} characters")
        logger.debug(f"   History context: {len(conversation_history or [])} messages")

        messages = [SystemMessage(content=self._DOCQA_SYSTEM_PROMPT)]

        # Inject conversation history for follow-up awareness
        if conversation_history:
            logger.debug(f"   📚 Injecting {min(len(conversation_history), 6)} history messages")
            for msg in conversation_history[-6:]:  # last 3 turns
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Truncate doc text to avoid token overflow (~60k chars ≈ 15k tokens)
        truncated_doc = doc_text[:60_000]
        truncated_flag = ""
        if len(doc_text) > 60_000:
            truncated_flag = " (truncated)"
            truncated_doc += "\n\n[... document truncated for length ...]"
        
        logger.debug(f"   📄 Document prepared: {len(truncated_doc)} chars{truncated_flag}")

        user_prompt = (
            f"DOCUMENT TEXT:\n{truncated_doc}\n\n"
            f"QUESTION: {query}\n\n"
            f"Respond in {language} UNLESS the user explicitly requests a different language in their QUESTION.\n"
            f"Append [SCORE:x.x] on the very last line."
        )
        messages.append(HumanMessage(content=user_prompt))

        llm = self._make_llm(streaming=True)
        logger.debug(f"   🤖 LLM initialized for streaming")
        logger.debug(f"   ▶️  Starting token stream...")
        
        token_count = 0
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                token_count += 1
                yield chunk.content

        logger.info(f"✅ DOCQA stream complete | {token_count} tokens generated")

    async def stream_hybrid(
        self,
        query: str,
        doc_text: str,
        rag_context: str,
        language: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        logger.info("� DocumentQAAgent: HYBRID stream starting (document + VDB)")
        logger.debug(f"   Query: '{query[:80]}'")
        logger.debug(f"   Language: {language}")
        logger.debug(f"   Document size: {len(doc_text)} characters")
        logger.debug(f"   RAG context size: {len(rag_context)} characters")
        logger.debug(f"   History context: {len(conversation_history or [])} messages")

        messages = [SystemMessage(content=self._HYBRID_SYSTEM_PROMPT)]

        if conversation_history:
            for msg in conversation_history[-6:]:
                if msg["role"] == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        truncated_doc = doc_text[:40_000]  # leave room for RAG context
        if len(doc_text) > 40_000:
            truncated_doc += "\n\n[... document truncated ...]"

        user_prompt = (
            f"DOCUMENT TEXT:\n{truncated_doc}\n\n"
            f"---\n\n"
            f"LEGAL SOURCES (from Lovdata):\n{rag_context}\n\n"
            f"---\n\n"
            f"QUESTION: {query}\n\n"
            f"Respond in {language} UNLESS the user explicitly requests a different language in their QUESTION.\n"
            f"Cross-reference both sources.\n"
            f"Append [SCORE:x.x] on the very last line."
        )
        messages.append(HumanMessage(content=user_prompt))

        llm = self._make_llm(streaming=True)
        async for chunk in llm.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield chunk.content

        logger.info("✅ DocumentQAAgent: stream_hybrid complete")