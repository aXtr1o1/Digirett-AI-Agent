
import logging
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)



REASONING_PATTERNS: str = """
STRUCTURAL STATUTE DETECTION FRAMEWORK FOR NORWEGIAN LAW

Goal:
The purpose of this reasoning stage is NOT simple lexical expansion.
It is to assist retrieval by aligning the query with statutory vocabulary,
without adding legal conclusions or new legal conditions.


The model must perform structural legal classification.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 1 — IDENTIFY LEGAL DOMAIN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Classify the query into a Norwegian legal domain based on
the legal mechanism being regulated — not just keywords.

Examples of domains (non-exhaustive, do not treat as fixed list):

Company law (corporate governance, capital, board duties)

Insolvency law (bankruptcy, reconstruction, insolvency tests)

Security rights (pledge, collateral, mortgage, pant)

Contract law (agreement validity, breach, formation)

Employment law

Administrative law

Tax law

Criminal law

Property law

Procedural law

You must determine domain dynamically from the mechanism described.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 2 — IDENTIFY LEGAL MECHANISM
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Extract the core legal mechanism:

Ask:
What legal power, obligation, restriction, or consequence
is being regulated?

Examples of mechanism types:

Representation authority

Capital maintenance

Avoidance of transactions

Insolvency obligation

Registration requirement

Security interest creation

Liability

Competence of an organ

Validity conditions

Form requirements

Mechanism is more important than entity type.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — MAP MECHANISM TO STATUTE FAMILY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on the legal mechanism and domain,
identify the primary Norwegian statute family that governs it.

Rules:

• If the mechanism concerns corporate internal governance
→ Company law statute

• If the mechanism concerns insolvency or bankruptcy procedure
→ Insolvency statute

• If the mechanism concerns avoidance of pre-bankruptcy transactions
→ Creditor protection statute

• If the mechanism concerns security rights in assets
→ Security rights statute

• If the mechanism concerns registration and legal protection
→ Registration statute

• If multiple mechanisms exist, identify all relevant statute families.

You ARE allowed to infer statute names based on legal classification.

If uncertainty exists, list primary and secondary statutes.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — DERIVE STATUTE-NATIVE TERMINOLOGY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

From the mechanism and statute family,
derive precise terminology that would appear in statute text.

Prefer:

kompetanse

handleplikt

rettsvern

omstøtelse

insolvens

kapitaltap

sikkerhetsstillelse

representasjonsrett

registreringsplikt

vilkår

ugyldighet

ansvar

Use only terms logically connected to the query.

Do not invent unrelated concepts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 5 — OUTPUT STRUCTURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output:

Legal Topic :
Legal Domain :
Primary Statute :
Secondary Statute:
Key Mechanism :
Key Concepts :
Enriched Query :

The Enriched Query must include statute-native vocabulary
and reference the identified statute family.
"""


class QueryReasoningAgent:
    """
    Generates a structured reasoning summary for a legal query.

    Follow-up awareness: RAGService passes previous_statute_id (from Redis),
    previous_enriched_query, and the last assistant summary so the agent
    can honour statute continuity for vague follow-ups like
    "can you explain it more briefly".
    """

   
    _SYSTEM_PROMPT_TEMPLATE = """You are a Norwegian Legal Statute Routing and Query Enrichment Specialist.

Your task is NOT to answer the legal question.

Your task is to:

1. Identify the governing legal mechanism.
2. Determine the most structurally governing Norwegian statute family.
3. Preserve statute continuity when applicable.
4. Produce a statute-anchored enriched query optimized for vector retrieval.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT – NO EXTRA TEXT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Legal Topic               : <short description>
Legal Domain              : <broad legal field>
Primary Statute Name      : <most likely governing Norwegian law>
Primary Statute ID        : <official Lovdata statute id>
Secondary Statute Name    : <if relevant, else "none">
Secondary Statute ID      : <official Lovdata statute id or "none">
Key Mechanism             : <core legal mechanism being regulated>
Key Concepts              : <comma-separated statute-native terms>
Enriched Query            : <single dense statute-anchored sentence>
Response Style            : <one plain-English instruction for the generator, e.g. "Brief overview requested. Keep under 150 words and avoid subheadings." or "Standard structured response." — derive from the user's phrasing>

Do not output anything outside this structure.
Do not explain your reasoning.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUTE ROUTING PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Mechanism overrides entity type.
• Select the statute that structurally governs the legal power, obligation, restriction, or consequence described.
• If multiple mechanisms exist, identify primary and secondary statutes.
• If ambiguity exists, choose the most structurally governing statute.
• Never invent statute IDs.
• Always output Primary Statute ID.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT CONTINUITY RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If PREVIOUS_STATUTE_ID is provided in the conversation context:

• Presume the same statute continues to govern
  unless a clearly different legal mechanism is introduced.

• Distinguish between:
  - Mechanism change (requires new statute), and
  - Analytical dimension change (structure, scope, systematics, overview).

• If only the analytical dimension changes (e.g. "explain more briefly",
  "give an overview", "summarise"):
  - Keep the same statute.
  - Abstract to statute level if structural/systematic explanation is requested.
  - Do NOT carry forward previously extracted subtopics.
  - Reformulate the enriched query to reflect the new analytical focus only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENRICHED QUERY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The Enriched Query must:

• Be 10–25 words.
• Use statute-native terminology.
• Align lexically with statutory phrasing.
• Avoid introducing new legal elements.
• Avoid factual assumptions.
• Expand terminology, not legal interpretation.
• Reflect statute-level abstraction if structural explanation is requested.

Do not cite § numbers unless present in the query.
Respond in the same language as the user query.
REASONING PATTERNS FROM GOLDEN DATASET:
{reasoning_patterns}
"""

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.1,
            streaming=False,
        )
        logger.info("✅ QueryReasoningAgent initialized")

    # ── Public interface ──────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        context_window: Optional[List[Dict[str, str]]] = None,
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
    ) -> Dict[str, str]:
        
        logger.info(f"🧠 QueryReasoningAgent: reasoning on '{query[:70]}'")

        try:
            system_prompt = self._SYSTEM_PROMPT_TEMPLATE.format(
                reasoning_patterns=REASONING_PATTERNS.strip()
            )

            context_str = self._build_context_str(
                context_window=context_window,
                previous_statute_id=previous_statute_id,
                previous_enriched_query=previous_enriched_query,
            )

            if context_str:
                user_content = (
                    f"{context_str}\n\n"
                    f"CURRENT QUERY:\n{query}"
                )
            else:
                user_content = f"CURRENT QUERY:\n{query}"

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]

            response = await self._llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()

            logger.debug(f"🧠 QueryReasoningAgent raw output:\n{raw_output}")

            enriched_query = self._extract_enriched_query(raw_output, fallback=query)
            statute_id     = self._extract_statute_id(raw_output)
            statute_name   = QueryReasoningAgent._extract_statute_name(raw_output)
            response_style = QueryReasoningAgent._extract_response_style(raw_output)

            # Pad short enriched queries using natural sentence (not keyword dump)
            if len(enriched_query.split()) < 15:
                key_concepts = QueryReasoningAgent._extract_key_concepts(raw_output)
                if key_concepts:
                    concepts_clean = key_concepts.replace(",", " og").strip()
                    enriched_query = f"{enriched_query} Relevante begreper: {concepts_clean}."
                    logger.info("🧠 QueryReasoningAgent: padded short query naturally")

            if statute_name and statute_id:
                enriched_query = f"{statute_name} ({statute_id}): {enriched_query}"
            elif statute_name:
                enriched_query = f"{statute_name}: {enriched_query}"
            elif statute_id:
                enriched_query = f"{statute_id}: {enriched_query}"

            logger.info(
                f"🧠 QueryReasoningAgent: enriched='{enriched_query[:80]}' | "
                f"statute_id={statute_id} | style='{response_style}'"
            )
            return {
                "enriched_query": enriched_query,
                "primary_statute_id": statute_id,
                "response_style": response_style,
            }

        except Exception as exc:
            logger.warning(
                f"⚠️  QueryReasoningAgent failed, using raw query | {exc}"
            )
            return {
                "enriched_query": query,
                "primary_statute_id": None,
                "response_style": "",   
            }

    # ── Internal helpers ──────────────────────────────────────────────────

    @staticmethod
    def _build_context_str(
        context_window: Optional[List[Dict[str, str]]],
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
    ) -> str:
        
        parts = []

        # Signal 1 — statute ID from Redis (most important for continuity)
        if previous_statute_id:
            parts.append(
                f"PREVIOUS_STATUTE_ID: {previous_statute_id}"
            )

        # Signal 2 — what the reasoning agent produced last turn
        if previous_enriched_query:
            parts.append(
                f"PREVIOUS_ENRICHED_QUERY: {previous_enriched_query}"
            )

        # Signal 3 — extract from context_window:
        #   (a) last user message  → shows what was asked before
        #   (b) last assistant message → shows what topic was covered
        if context_window:
            last_user = None
            last_assistant = None

            for msg in reversed(context_window):
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "assistant" and last_assistant is None:
                    # Truncate to 400 chars — enough for topic signal, not noisy
                    last_assistant = content[:400].strip()
                if role == "user" and last_user is None:
                    last_user = content.strip()
                if last_user and last_assistant:
                    break

            if last_user:
                parts.append(f"PREVIOUS_USER_QUERY: {last_user}")

            if last_assistant:
                parts.append(
                    f"PREVIOUS_ASSISTANT_ANSWER (first 400 chars):\n{last_assistant}"
                )

        return "\n\n".join(parts)

    @staticmethod
    def _extract_key_concepts(raw_output: str) -> str:
        """Extract Key Concepts line — used to pad short enriched queries."""
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("key concepts"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value:
                        return value
        return ""

    @staticmethod
    def _extract_statute_name(raw_output: str) -> str:
        """Extract Primary Statute Name — used to anchor the enriched query."""
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("primary statute name"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value and value.lower() not in ("none", ""):
                        return value
        return ""

    @staticmethod
    def _extract_statute_id(raw_output: str) -> Optional[str]:
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("primary statute id"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value and value.lower() != "none":
                        return value
        return None

    @staticmethod
    def _extract_response_style(raw_output: str) -> str:
        """
        Pull the value of the 'Response Style :' line from the LLM output.
        Returns a plain-English generation instruction.
        Falls back to empty string (= standard response) if not found.
        """
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("response style"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value:
                        return value
        return ""   # empty = standard response, no override

    @staticmethod
    def _extract_enriched_query(raw_output: str, fallback: str) -> str:
        """
        Pull the value of the 'Enriched Query :' line from the LLM output.
        Falls back to the original raw query on extraction failure.
        """
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("enriched query"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value:
                        return value

        # Model produced freeform text — use it if it's short enough
        if raw_output and len(raw_output) < 500:
            return raw_output

        return fallback