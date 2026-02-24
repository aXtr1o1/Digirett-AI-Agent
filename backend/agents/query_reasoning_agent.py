"""
agents/query_reasoning_agent.py

Query Reasoning Summary Agent
==============================
Inserted between MemoryAgent (Step 4) and IntentAgent (Step 5) in the LEGAL pipeline.

Responsibilities:
  - Receives the current user query + short conversation context window.
  - Applies the reasoning patterns extracted from the golden dataset to produce
    a structured reasoning summary.
  - Returns a single enriched string that replaces the raw query for:
      * Embedding generation (RetrieverAgent)
    CASUAL queries are never passed through this agent.

How to plug in your reasoning patterns
---------------------------------------
  Find the block labelled  ── PASTE REASONING PATTERNS HERE ──  below.
  Replace the placeholder text with the patterns your team extracted from
  the golden dataset.  The patterns should be a plain string that is injected
  into the system prompt verbatim, so format them however you like
  (numbered list, JSON, markdown table, etc.).

  Example placeholder format (replace with real patterns):
  ─────────────────────────────────────────────────────────
  PATTERN 1 – AS vs ASA distinction
    Trigger: query mentions "aksjeselskap", "selskap", or ownership structure
    Reasoning: Identify whether the question concerns AS (aksjeloven 1997-06-13-44)
               or ASA (allmennaksjeloven 1997-06-13-45) before retrieving.
    Expansion: Append the correct law identifier to the search query.

  PATTERN 2 – Paragraph attribution
    Trigger: query references a specific § (paragraph) number
    Reasoning: Confirm which law the paragraph belongs to before embedding.
    Expansion: Prepend "§ <number> [law name]" to the search query.
  ─────────────────────────────────────────────────────────
"""

import logging
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ── PASTE REASONING PATTERNS HERE ────────────────────────────────────
# Replace this entire string with the patterns your team extracted from
# the golden dataset.  Keep the surrounding triple-quotes.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REASONING_PATTERNS: str = """
STRUCTURED LEGAL QUERY DECOMPOSITION FRAMEWORK

STEP 1 — Identify Legal Subject
Extract the legal entity explicitly mentioned in the query.
Examples:
  - AS → aksjeselskap
  - ASA → allmennaksjeselskap
  - styret
  - daglig leder
  - aksjonær
  - selskap

STEP 2 — Identify Legal Action or Competence
Extract the legal function or authority being asked about.
Examples:
  - binde selskapet
  - representere utad
  - myndighet
  - kompetanse
  - vedtak
  - signatur

STEP 3 — Identify Explicit Law Mention
Only if explicitly written in the query.
If no law name appears → Law Identifier must be "unknown".

STEP 4 — Identify Authority Actors Mentioned
Extract all actors explicitly referenced:
  - styret
  - daglig leder
  - generalforsamling
  - prokurist
  - fullmektig

STEP 5 — Identify Limitation Mechanisms
Extract explicit mechanisms:
  - signaturregler
  - prokura
  - fullmakt
  - vedtektsbegrensning
  - registrering

STEP 6 — Strengthen Retrieval Using Statute-Native Terminology

When the query concerns corporate authority or representation,
you may lexically expand using known statute-native terms:

- representerer selskapet
- tegne selskapets firma
- representasjonsrett
- signaturrett
- daglig ledelse
- registrering i foretaksregisteret
- styrets kompetanse

These are neutral legal synonyms.
They are allowed because they are lexical expansions,
not new legal assumptions.

Do NOT:
  - Add § numbers
  - Add law names
  - Add legal consequences

The enriched query MUST:
  - Be ONE single sentence
  - Be keyword-dense
  - Contain only terms already present in the query
  - Add only lexical clarifications (e.g., AS → aksjeselskap)
  - Not add new § numbers
  - Not add new law names
"""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class QueryReasoningAgent:
    """
    Generates a structured reasoning summary for a legal query.

    The summary is richer and more precise than the raw user query —
    it disambiguates law type (AS vs ASA), anchors paragraph references,
    and surfaces the exact legal concept being asked about.

    Usage (called inside RAGService._handle_legal, before embedding):

        reasoning_agent = QueryReasoningAgent()
        enriched_query  = await reasoning_agent.run(
            query=raw_query,
            context_window=recent_history,      # last 2–4 messages
        )
        # Pass `enriched_query` to RetrieverAgent instead of `raw_query`
    """

    # ── System prompt ────────────────────────────────────────────────────
    # The reasoning patterns from the golden dataset are injected at the end.

    _SYSTEM_PROMPT_TEMPLATE = """You are a legal query reasoning specialist for Norwegian law (Lovdata).

Your task is to analyse a legal query and produce a structured reasoning summary that will
be used INSTEAD of the raw query for vector-search retrieval in Milvus.

OUTPUT FORMAT (plain text, no JSON):
  Legal Topic      : <one-line description of the core legal topic>
  Law Identifier   : <primary law(s) that govern this topic, e.g. aksjeloven, arbeidsmiljøloven>
  Key Concepts     : <comma-separated list of the most precise legal terms>
  Disambiguation   : <any AS vs ASA, § number, or law-type clarifications needed>
  Enriched Query   : <a single precise search-optimised sentence combining all of the above>

RULES:
  1. Output ONLY the five labelled lines above — no preamble, no explanation.
  2. The "Enriched Query" must be a keyword-dense restatement of the user query without introducing new legal assumptions.
  3. If the conversation context shows prior legal discussion, incorporate it.
  4. You are STRICTLY FORBIDDEN from:
    - Adding law names not explicitly mentioned
    - Adding § numbers not explicitly mentioned
    - Inferring governing statutes from entity types
    - Expanding beyond lexical clarification

    5. If a law is not explicitly written in the query,
    Law Identifier MUST be set to "unknown".

    6. The Enriched Query must only restate and lexically expand
    terms already present in the query.
    7. Always respond in the same language as the user query (Norwegian or English).

REASONING PATTERNS FROM GOLDEN DATASET:
{reasoning_patterns}
"""

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.1,   # Low temperature — we want deterministic enrichment
            streaming=False,
        )
        logger.info("✅ QueryReasoningAgent initialized")

    # ── Public interface ──────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        context_window: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Produce an enriched query string from the raw user query.

        Args:
            query:          The raw user query (unchanged).
            context_window: Last 2–4 {role, content} dicts from MemoryAgent.

        Returns:
            The "Enriched Query" line extracted from the reasoning summary.
            Falls back to the original query on any error so the pipeline
            never breaks.
        """
        logger.info(f"🧠 QueryReasoningAgent: reasoning on '{query[:70]}'")

        try:
            system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(
                reasoning_patterns=REASONING_PATTERNS.strip()
            )

            # Build conversation context string
            context_str = self._build_context_str(context_window)

            user_content = (
                f"CONVERSATION CONTEXT (last messages):\n{context_str}\n\n"
                f"CURRENT QUERY:\n{query}"
                if context_str
                else f"CURRENT QUERY:\n{query}"
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]

            response = await self._llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()

            logger.debug(f"🧠 QueryReasoningAgent raw output:\n{raw_output}")

            # Extract the "Enriched Query" line — that is what goes to embedding
            enriched_query = self._extract_enriched_query(raw_output, fallback=query)

            logger.info(
                f"🧠 QueryReasoningAgent: enriched='{enriched_query}'"
            )
            return enriched_query

        except Exception as exc:
            # Never break the pipeline — fall back to original query
            logger.warning(
                f"⚠️  QueryReasoningAgent failed, using raw query | {exc}"
            )
            return query

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_context_str(
        context_window: Optional[List[Dict[str, str]]]
    ) -> str:
        """Convert a list of {role, content} dicts into a readable string."""
        if not context_window:
            return ""
        parts = []
        for msg in context_window:
            role = msg.get("role", "").capitalize()
            content = msg.get("content", "")
            if role and content:
                parts.append(f"{role}: {content}")
        return "\n".join(parts)

    @staticmethod
    def _extract_enriched_query(raw_output: str, fallback: str) -> str:
        """
        Pull the value of the 'Enriched Query :' line from the LLM output.
        If extraction fails, return the fallback (original raw query).
        """
        for line in raw_output.splitlines():
            # Accept variations like "Enriched Query:", "Enriched Query :", etc.
            stripped = line.strip()
            if stripped.lower().startswith("enriched query"):
                # Everything after the first colon
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value:
                        return value

        # If the model produced freeform text instead of the structured format,
        # use the whole output as the enriched query (still better than raw query).
        if raw_output and len(raw_output) < 500:
            return raw_output

        return fallback