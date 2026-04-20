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

Company law (corporate governance, capital, board duties, daglig leder, styret)

Commercial agency law (prokura, fullmakt, representasjonsrett, signaturrett)

Business registration law (Foretaksregisteret, registerplikt, meldeplikt)

Insolvency law (bankruptcy, reconstruction, insolvency tests)

Creditor protection law (omstøtelse, dekningsloven, avoidance)

Security rights (pledge, collateral, mortgage, pant)

Contract law (agreement validity, breach, formation)

Employment law

Administrative law

Tax law

Criminal law

Property law

Procedural law

IMPORTANT: "Company law" does NOT cover prokura, signaturregistrering, or pant.
These belong to "Commercial agency law", "Business registration law", and "Security rights".
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
MULTI-MECHANISM DETECTION RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If the query:

• compares two or more legal concepts
• contains phrases like:
  "forskjellen mellom"
  "sammenlign"
  "kontra"
  "versus"
  "hva er forskjellen på"
• or clearly regulates more than one legal mechanism

THEN:

→ Treat the query as MULTI-MECHANISM.
→ Identify each mechanism independently.
→ Determine statute family for each mechanism.
→ Select:

   PRIMARY = statute governing the main comparative axis
   SECONDARY = additional structurally relevant statute(s)

Do NOT collapse multiple mechanisms into a single statute
unless one statute clearly governs all mechanisms.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 3 — MAP MECHANISM TO STATUTE FAMILY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Based on the legal mechanism and domain,
identify the primary Norwegian statute family that governs it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRIORITY ROUTING TABLE — apply these BEFORE general rules.
These override the general rules below when the mechanism matches.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MECHANISM: prokura, prokurist, særfullmakt for driftshandlinger
→ PRIMARY: prokuraloven
→ NOT aksjeloven (even if the entity is an AS/ASA)
→ SECONDARY: foretaksregisterloven (for registration duty)

MECHANISM: registrering av rettigheter/opplysninger i Foretaksregisteret,
           registreringsplikt, meldeplikt til Foretaksregisteret,
           registrerbare opplysninger, firmaattest
→ PRIMARY: foretaksregisterloven
→ NOT aksjeloven unless the question is specifically about
  internal capital changes (kapitalforhøyelse, fusjon, fisjon)

MECHANISM: signaturrett (who signs on behalf of the company),
           tegningsrett, hvem binder selskapet utad,
           representasjonsrett utad, fullmakt til å tegne firma
→ PRIMARY: foretaksregisterloven (registration of signature rights)
→ SECONDARY: aksjeloven (internal rules on who may be given signature)
→ If question is ONLY about internal limits (not registration) → aksjeloven primary

MECHANISM: daglig leders kompetanse og myndighetsgrenser,
           hva faller innenfor/utenfor daglig ledelse,
           daglig leders representasjon utad
→ PRIMARY: aksjeloven (for AS), allmennaksjeloven (for ASA)
→ NOT selskapsloven, NOT helseforetaksloven, NOT IKS-loven

MECHANISM: styrets kompetanse, styrevedtak, styrebehandling,
           generalforsamlingens myndighet, aksjeeiernes rettigheter
→ PRIMARY: aksjeloven (for AS), allmennaksjeloven (for ASA)
→ NOT selskapsloven unless entity is explicitly ANS/KS/DA

MECHANISM: pantsettelse, sikkerhetsstillelse, pant i løsøre/fast eiendom,
           avtalepant, utleggspant, rettsvern for pant
→ PRIMARY: panteloven
→ SECONDARY: finansavtaleloven (for financial collateral)

MECHANISM: konkurs, gjeldsforhandling, insolvens, betalingsudyktighet,
           oppbud, bobehandling
→ PRIMARY: konkursloven
→ SECONDARY: dekningsloven (for omstøtelse/avoidance)

MECHANISM: omstøtelse av transaksjoner, kreditorskadelige disposisjoner,
           omstøtelsesregler
→ PRIMARY: dekningsloven

MECHANISM: arbeidsforhold, arbeidsavtale, oppsigelse, avskjed,
           arbeidstakers rettigheter, arbeidsgivers plikter
→ PRIMARY: arbeidsmiljøloven
→ SECONDARY: ferieloven, tjenestemannsloven (for state employees)

MECHANISM: skatt, skatteberegning, fradrag, skattesubjekt, skatteplikt
→ PRIMARY: skatteloven

MECHANISM: regnskap, bokføring, årsregnskap, revisjonsplikt
→ PRIMARY: regnskapsloven, bokføringsloven

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERAL RULES — apply only when no PRIORITY ROUTING matches:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• If the mechanism concerns corporate internal governance of an AS/ASA
→ aksjeloven / allmennaksjeloven

• If the mechanism concerns insolvency or bankruptcy procedure
→ konkursloven

• If the mechanism concerns avoidance of pre-bankruptcy transactions
→ dekningsloven

• If the mechanism concerns security rights in assets
→ panteloven

• If the mechanism concerns registration and legal protection
→ foretaksregisterloven

• If multiple mechanisms exist, identify all relevant statute families.

You ARE allowed to infer statute names based on legal classification.

If uncertainty exists, list primary and secondary statutes.

CRITICAL: Never default to aksjeloven for questions about prokura,
signaturregistrering, foretaksregistrering, or pant.
These have their own dedicated primary statutes listed above.

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
STEP 4 — DERIVE THE OFFICIAL LOVDATA FILE IDENTIFIER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Using your knowledge of Norwegian law and web search of Lovdata website, derive the official Lovdata
statute identifier for the governing law.

The Lovdata format is: LOV-YYYY-MM-DD-NNN
  YYYY = year the law was enacted
  MM   = month enacted
  DD   = day enacted
  NNN  = sequential number of the law that year

Derivation process — reason through what you know:

  From Steps you know the statute family name (e.g. "aksjeloven").
  From your legal knowledge, recall the enactment date and number.
  Construct the identifier from: enactment date + sequential number.

  Widely used Norwegian statutes and their identifiers
  (use as reference points for reasoning — do not treat as exhaustive):

    avtaleloven           → LOV-1918-05-31-4
    aksjeloven            → LOV-1997-06-13-44
    allmennaksjeloven     → LOV-1997-06-13-45
    foretaksregisterloven → LOV-1985-06-21-78
    prokuraloven          → LOV-1985-06-21-80
    selskapsloven         → LOV-1985-06-21-83
    panteloven            → LOV-1980-02-08-2
    konkursloven          → LOV-1984-06-08-58
    dekningsloven         → LOV-1984-06-08-59
    arbeidsmiljøloven     → LOV-2005-06-17-62
    ferieloven            → LOV-1988-04-29-21
    skatteloven           → LOV-1999-03-26-14
    regnskapsloven        → LOV-1998-07-17-56
    bokføringsloven       → LOV-2004-11-19-73
    revisorloven          → LOV-2020-11-20-128
    finansavtaleloven     → LOV-2020-11-26-129
    verdipapirhandelloven → LOV-2007-06-29-75
    tvisteloven           → LOV-2005-06-17-90
    straffeloven          → LOV-2005-05-20-28
    forvaltningsloven     → LOV-1967-02-10-0
    plan- og bygningsloven → LOV-2008-06-27-71
    kommuneloven          → LOV-2018-06-22-83
    tinglysingsloven      → LOV-1935-03-07-2
    husleieloven          → LOV-1999-03-26-17
    kjøpsloven            → LOV-1988-05-13-27
    forbrukerkjøpsloven   → LOV-2002-06-21-34

  For SECONDARY statutes: apply the same derivation reasoning.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 6 — OUTPUT STRUCTURE
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
Legal Domain              : <must be EXACTLY one of the 12 allowed domain values listed below>
Jurisdiction              : <NO / EU-EEA / both>
Source Type               : <lov / forskrift / both>
Primary Statute Name      : <most likely governing Norwegian law>
Primary Statute ID        : <official Lovdata statute id OR full Lovdata URL if known>
Secondary Statute Name    : <if relevant, else "none">
Secondary Statute ID      : <official Lovdata statute id or full Lovdata URL or "none">
Key Mechanism             : <core legal mechanism being regulated>
Key Concepts              : <comma-separated statute-native terms>
Enriched Query            : <single dense statute-anchored sentence>
Response Style            : <one plain-English instruction for the generator, e.g. "Brief overview requested. Keep under 150 words and avoid subheadings." or "Standard structured response." — derive from the user's phrasing>

Do not output anything outside this structure.
Do not explain your reasoning.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALLOWED LEGAL DOMAIN VALUES (Legal Domain field)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You MUST set Legal Domain to EXACTLY one of these 12 values — no variations, no translations:

  Arbeidsrett
  Arsregnskap_og_selskapsrapportering_dataset
  Avtalerett
  Inkasso_og_tvangsfullbyrdelse_dataset
  Konkursrett_og_insolvens_dataset
  MandA_Fusjon_Fisjon
  Obligasjonrett
  Panterett_og_sikkerhetsrett_dataset
  Pengekravsrett_fordringer_dataset
  Personvern_GDPR_business_compliance_dataset
  Selskapsrett
  Tvistelosning_SMB_dataset

Mapping guidance (use mechanism, not entity type):
  - Employment contracts, dismissal, working conditions, worker rights → Arbeidsrett
  - Annual accounts, bookkeeping, audit, financial reporting → Arsregnskap_og_selskapsrapportering_dataset
  - Contract formation, validity, breach, general obligations → Avtalerett
  - Debt collection, enforcement, attachment, forced sale → Inkasso_og_tvangsfullbyrdelse_dataset
  - Bankruptcy, insolvency, reconstruction, creditor protection → Konkursrett_og_insolvens_dataset
  - Mergers, demergers, acquisitions, M&A process → MandA_Fusjon_Fisjon
  - Obligations, claims, creditor/debtor relationship → Obligasjonrett
  - Pledge, mortgage, collateral, security interests → Panterett_og_sikkerhetsrett_dataset
  - Receivables, claims assignment, negotiable instruments → Pengekravsrett_fordringer_dataset
  - GDPR, data protection, processor agreements, privacy → Personvern_GDPR_business_compliance_dataset
  - Company governance, board, shareholders, corporate structure → Selskapsrett
  - Dispute resolution, arbitration, litigation, SMB conflicts → Tvistelosning_SMB_dataset

JURISDICTION values: NO / EU-EEA / both
SOURCE TYPE values: lov / forskrift / both

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUTE ROUTING PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Mechanism overrides entity type.
• Select the statute that structurally governs the legal power, obligation, restriction, or consequence described.
• If multiple mechanisms exist:
    1. You MUST identify each mechanism explicitly in "Key Mechanism"
       using semicolon separation.
       Example: "representation authority; registration requirement"
    2. You MUST populate Secondary Statute Name and Secondary Statute ID.
    3. The Enriched Query MUST reference both statute families.
    4. Do NOT collapse multiple mechanisms into a single abstract formulation.
• If ambiguity exists, choose the most structurally governing statute.
• Never invent statute IDs.
• Always output Primary Statute ID.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT CONTINUITY RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If PREVIOUS_STATUTE_ID is provided in the conversation context:

STEP A — ALWAYS determine the correct statute for the CURRENT query independently
using the STATUTE ROUTING PRINCIPLES above. Do NOT default to the previous statute.

STEP B — After determining the correct statute for the current query, apply these rules:

• If the current query introduces a NEW legal mechanism or references a different
  law/topic area → use the newly determined statute. Ignore PREVIOUS_STATUTE_ID.
  Examples of domain switches that MUST produce a new statute:
  - Previous: aksjeloven (company governance) → Current: prokura, prokuraloven
  - Previous: aksjeloven → Current: foretaksregisterloven (registration rules)
  - Previous: any statute → Current: a question that explicitly names a different law

• If the current query is clearly a follow-up or rephrasing of the previous question
  (e.g. "explain more briefly", "give an overview", "what about that", "forklar mer",
  "kan du utdype", "summarise") AND the same legal mechanism still governs
  → keep PREVIOUS_STATUTE_ID.

• If uncertain whether it is a follow-up or a new topic → treat it as a NEW topic
  and determine the statute independently. Do NOT default to the previous statute.

• Distinguish between:
  - Mechanism change → new statute required
  - Analytical dimension change (structure, scope, overview of the SAME topic) → keep same statute

• If only the analytical dimension changes (e.g. "explain more briefly",
  "give an overview", "summarise"):
  - Keep the same statute.
  - Abstract to statute level if structural/systematic explanation is requested.
  - Do NOT carry forward previously extracted subtopics.
  - Reformulate the enriched query to reflect the new analytical focus only.
• If the current query introduces additional legal mechanisms
  beyond the previous query (even if partially overlapping),
  re-run full statute classification.
  Do NOT preserve statute continuity in multi-mechanism queries.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENRICHED QUERY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The Enriched Query must:

• Be 15–22 words.
• Contain at least TWO statute-native legal terms.
• Explicitly reference the identified statute family name.
• Avoid repeating the user’s wording without legal enrichment.
• Avoid generic phrases like "i henhold til loven".
• Avoid listing concepts without syntactic integration.
• If multi-mechanism: reference BOTH statute families naturally.
• Be ONE dense statutory-style sentence.
• Expand terminology, not legal interpretation.

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
            domain         = QueryReasoningAgent._extract_domain(raw_output)
            jurisdiction   = QueryReasoningAgent._extract_jurisdiction(raw_output)
            source_type    = QueryReasoningAgent._extract_source_type(raw_output)

            # Pad short enriched queries using natural sentence (not keyword dump)
            if len(enriched_query.split()) < 15:
                key_concepts = QueryReasoningAgent._extract_key_concepts(raw_output)
                if key_concepts:
                    concepts_clean = key_concepts.strip()
                    enriched_query = f"{enriched_query} Dette gjelder særlig {concepts_clean}."
                    logger.info("🧠 QueryReasoningAgent: padded short query structurally")

            secondary_statute_id = QueryReasoningAgent._extract_secondary_statute_id(raw_output)

            # Only anchor statute prefix if single-mechanism case
            # (i.e., no secondary statute present)

            if statute_id and not secondary_statute_id:
                enriched_query = f"{statute_name} ({statute_id}): {enriched_query}"

            elif statute_id and secondary_statute_id:
                enriched_query = f"{statute_name} ({statute_id}) og sekundær lov: {secondary_statute_id}: {enriched_query}"

            logger.info(
                f"🧠 QueryReasoningAgent: enriched='{enriched_query[:80]}' | "
                f"statute_id={statute_id} | domain={domain} | "
                f"jurisdiction={jurisdiction} | source_type={source_type} | "
                f"style='{response_style}'"
            )
            return {
                "enriched_query": enriched_query,
                "primary_statute_id": statute_id,
                "response_style": response_style,
                "domain": domain,
                "jurisdiction": jurisdiction,
                "source_type": source_type,
            }

        except Exception as exc:
            logger.warning(
                f"⚠️  QueryReasoningAgent failed, using raw query | {exc}"
            )
            return {
                "enriched_query": query,
                "primary_statute_id": None,
                "response_style": "",
                "domain": None,
                "jurisdiction": None,
                "source_type": None,
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
    def _extract_secondary_statute_id(raw_output: str) -> Optional[str]:
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("secondary statute id"):
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

    # ── Allowed domain values — must match Milvus metadata exactly ───────
    _ALLOWED_DOMAINS = frozenset({
        "Arbeidsrett",
        "Arsregnskap_og_selskapsrapportering_dataset",
        "Avtalerett",
        "Inkasso_og_tvangsfullbyrdelse_dataset",
        "Konkursrett_og_insolvens_dataset",
        "MandA_Fusjon_Fisjon",
        "Obligasjonrett",
        "Panterett_og_sikkerhetsrett_dataset",
        "Pengekravsrett_fordringer_dataset",
        "Personvern_GDPR_business_compliance_dataset",
        "Selskapsrett",
        "Tvistelosning_SMB_dataset",
    })

    @staticmethod
    def _extract_domain(raw_output: str) -> Optional[str]:
        """
        Extract the Legal Domain line and validate it against the 12 allowed values.
        Returns None if the value is not in the allowed set — prevents bad Milvus filters.
        """
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("legal domain"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value in QueryReasoningAgent._ALLOWED_DOMAINS:
                        return value
                    logger.warning(
                        f"⚠️  QueryReasoningAgent: domain '{value}' not in allowed set — "
                        "dropping domain filter"
                    )
                    return None
        return None

    @staticmethod
    def _extract_jurisdiction(raw_output: str) -> Optional[str]:
        """Extract Jurisdiction field. Returns 'NO', 'EU-EEA', 'both', or None."""
        allowed = {"NO", "EU-EEA", "both"}
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("jurisdiction"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip()
                    if value in allowed:
                        return value
        return None

    @staticmethod
    def _extract_source_type(raw_output: str) -> Optional[str]:
        """Extract Source Type field. Returns 'lov', 'forskrift', 'both', or None."""
        allowed = {"lov", "forskrift", "both"}
        for line in raw_output.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("source type"):
                colon_idx = stripped.find(":")
                if colon_idx != -1:
                    value = stripped[colon_idx + 1:].strip().lower()
                    if value in allowed:
                        return value
        return None

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