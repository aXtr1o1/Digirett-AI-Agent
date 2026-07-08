import logging
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from agents.statute_registry import get_registry

logger = logging.getLogger(__name__)

_registry = get_registry()


# ── Allowed domains (must match Milvus `domain` field values) ──────────────
_ALLOWED_DOMAINS = frozenset({
    "arbeidsrett",
    "arsregnskap_og_selskapsrapportering",
    "avtalerett",
    "inkasso_og_tvangsfullbyrdelse",
    "konkursrett_og_insolvens",
    "manda_fusjon_fisjon",
    "obligasjonsrett",
    "panterett_og_sikkerhetsrett",
    "pengekravsrett_fordringer",
    "personvern_gdpr_business_compliance",
    "selskapsrett",
    "tvistelosning_smb",
})


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

Ask: What legal power, obligation, restriction, or consequence is being regulated?

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
• contains phrases like "forskjellen mellom", "sammenlign", "kontra",
  "versus", "hva er forskjellen på"
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

PRIORITY ROUTING TABLE — apply BEFORE general rules:

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

MECHANISM: omstøtelse av transaksjoner, kreditorskadelige disposisjoner
→ PRIMARY: dekningsloven

MECHANISM: arbeidsforhold, arbeidsavtale, oppsigelse, avskjed
→ PRIMARY: arbeidsmiljøloven
→ SECONDARY: ferieloven, tjenestemannsloven (for state employees)

MECHANISM: skatt, skatteberegning, fradrag, skattesubjekt, skatteplikt
→ PRIMARY: skatteloven

MECHANISM: regnskap, bokføring, årsregnskap, revisjonsplikt
→ PRIMARY: regnskapsloven, bokføringsloven

GENERAL RULES — apply only when no PRIORITY ROUTING matches:
• Corporate internal governance of AS/ASA → aksjeloven / allmennaksjeloven
• Insolvency or bankruptcy procedure → konkursloven
• Avoidance of pre-bankruptcy transactions → dekningsloven
• Security rights in assets → panteloven
• Registration and legal protection → foretaksregisterloven

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STEP 4 — DERIVE THE OFFICIAL LOVDATA FILE IDENTIFIER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANT: The statute ID may have already been determined by the
deterministic registry lookup (shown in the REGISTRY HINT below, if present).
If a REGISTRY HINT is provided, use that statute ID — do not override it.

Using your knowledge of Norwegian law, derive the official Lovdata
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
    husleieloven          → LOV-1999-03-26-17
    kjøpsloven            → LOV-1988-05-13-27
    forbrukerkjøpsloven   → LOV-2002-06-21-34

CRITICAL: Never default to aksjeloven for questions about prokura,
signaturregistrering, foretaksregistrering, or pant.
"""


_SYSTEM_PROMPT_TEMPLATE = """You are a Norwegian Legal Statute Routing and Query Enrichment Specialist.

Your task is NOT to answer the legal question.

Your task is to:
1. Identify the governing legal mechanism.
2. Determine the most structurally governing Norwegian statute family.
3. Preserve statute continuity when applicable.
4. Produce a statute-anchored enriched query optimized for vector retrieval.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (STRICT – NO EXTRA TEXT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Legal Topic               : <short description>
Legal Domain              : <one of the allowed domain keys below, or a custom key if outside the 12 default domains>
Primary Statute Name      : <most likely governing Norwegian law>
Primary Statute ID        : <official Lovdata statute id OR full Lovdata URL if known>
Secondary Statute Name    : <if relevant, else "none">
Secondary Statute ID      : <official Lovdata statute id or full Lovdata URL or "none">
Key Mechanism             : <core legal mechanism being regulated>
Key Concepts              : <comma-separated statute-native terms>
Enriched Query            : <single dense statute-anchored sentence>
Response Style            : <one plain-English instruction for the generator>
Legal Domain              : <canonical domain key or custom key>
Jurisdiction              : <NO / EU-EEA / both>
Source Type               : <lov / forskrift / both>

Do not output anything outside this structure.
Do not explain your reasoning.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ALLOWED LEGAL DOMAIN VALUES (use EXACTLY these keys for canonical domains, or custom keys for other domains)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{domain_list}

Mapping guidance (use mechanism, not entity type) for reference:
  - Employment contracts, dismissal, working conditions → arbeidsrett
  - Annual accounts, bookkeeping, audit, financial reporting → arsregnskap_og_selskapsrapportering
  - Contract formation, validity, breach, general obligations → avtalerett
  - Debt collection, enforcement, attachment, forced sale → inkasso_og_tvangsfullbyrdelse
  - Bankruptcy, insolvency, reconstruction, creditor protection → konkursrett_og_insolvens
  - Mergers, demergers, acquisitions, M&A process → manda_fusjon_fisjon
  - Obligations, claims, creditor/debtor relationship → obligasjonsrett
  - Pledge, mortgage, collateral, security interests → panterett_og_sikkerhetsrett
  - Receivables, claims assignment, negotiable instruments → pengekravsrett_fordringer
  - GDPR, data protection, processor agreements, privacy → personvern_gdpr_business_compliance
  - Company governance, board, shareholders, corporate structure → selskapsrett
  - Dispute resolution, arbitration, litigation, SMB conflicts → tvistelosning_smb

JURISDICTION values: NO / EU-EEA / both
SOURCE TYPE values: lov / forskrift / both

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STATUTE ROUTING PRINCIPLES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• Mechanism overrides entity type.
• Select the statute that structurally governs the legal power, obligation,
  restriction, or consequence described.
• If multiple mechanisms exist:
    1. Identify each mechanism explicitly in "Key Mechanism" using semicolon separation.
    2. Populate Secondary Statute Name and Secondary Statute ID.
    3. The Enriched Query MUST reference both statute families.
• Never invent statute IDs.
• Always output Primary Statute ID.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXT CONTINUITY RULE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

If PREVIOUS_STATUTE_ID is provided:

STEP A — ALWAYS determine the correct statute for the CURRENT query independently
using the STATUTE ROUTING PRINCIPLES above. Do NOT default to the previous statute.
STEP B — After determining the correct statute for the current query, apply these rules:

• If the current query introduces a NEW legal mechanism or references a different
  law/topic area → use the newly determined statute. Ignore PREVIOUS_STATUTE_ID.

• If the current query is clearly a follow-up or rephrasing of the previous question
  AND the same legal mechanism still governs → keep PREVIOUS_STATUTE_ID.

• If uncertain whether it is a follow-up or a new topic → treat it as a NEW topic.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ENRICHED QUERY RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The Enriched Query must:
• Be 15–22 words.
• Contain at least TWO statute-native legal terms.
• Explicitly reference the identified statute family name.
• Avoid repeating the user's wording without legal enrichment.
• Avoid generic phrases like "i henhold til loven".
• If multi-mechanism: reference BOTH statute families naturally.
• Be ONE dense statutory-style sentence.
• Expand terminology, not legal interpretation.

Respond in the same language as the user query.

REASONING PATTERNS:
{reasoning_patterns}
"""



class QueryReasoningAgent:

    _ALLOWED_DOMAINS = _ALLOWED_DOMAINS

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.1,
            streaming=False,
        )
        logger.info("[OK] QueryReasoningAgent initialised (v4 — deterministic statute routing)")

    # ── Public API ────────────────────────────────────────────────────────

    async def run(
        self,
        query: str,
        context_window: Optional[List[Dict[str, str]]] = None,
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
    ) -> Dict:
        
        logger.debug(f"QueryReasoningAgent: reasoning on '{query[:70]}'")

        # ── STEP 0: Deterministic registry lookup (before LLM) ────────────
        registry_result = _registry.lookup(query)
        registry_statute_id = None
        registry_domain = None
        statute_from_registry = False

        if registry_result:
            registry_statute_id = registry_result["id"]
            registry_domain = registry_result.get("domain")
            statute_from_registry = True
            logger.info(
                f"Registry hit: id={registry_statute_id} | domain={registry_domain}"
            )
        else:
            logger.info("Registry: no match — LLM will infer statute")

        try:
            domain_list = "\n".join(
                f"  {d}" for d in sorted(self._ALLOWED_DOMAINS)
            )

            # Inject registry hint into prompt when available
            registry_hint = ""
            if registry_statute_id:
                registry_hint = (
                    f"\n\n⚠️  REGISTRY HINT (AUTHORITATIVE — DO NOT OVERRIDE):\n"
                    f"  The statute for this query has been deterministically identified as:\n"
                    f"  Primary Statute ID: {registry_statute_id}\n"
                    f"  Domain: {registry_domain}\n"
                    f"  Use EXACTLY this statute ID in your output. Do not change it.\n"
                )

            system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
                domain_list=domain_list,
                reasoning_patterns=REASONING_PATTERNS.strip(),
            )

            context_str = self._build_context_str(
                context_window=context_window,
                previous_statute_id=previous_statute_id,
                previous_enriched_query=previous_enriched_query,
            )

            user_content = (
                f"{context_str}\n\nCURRENT QUERY:\n{query}{registry_hint}"
                if context_str
                else f"CURRENT QUERY:\n{query}{registry_hint}"
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_content),
            ]

            response = await self._llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()

            # logger.debug(f"Raw output:\n{raw_output}")

            enriched_query = self._extract_enriched_query(raw_output, fallback=query)
            llm_statute_id = self._extract_statute_id(raw_output)
            statute_name = self._extract_statute_name(raw_output)
            secondary_statute_id = self._extract_secondary_statute_id(raw_output)
            response_style = self._extract_response_style(raw_output)
            llm_domain = self._extract_domain(raw_output)
            jurisdiction = self._extract_jurisdiction(raw_output)
            source_type = self._extract_source_type(raw_output)

            # ── PRECEDENCE RULES ──────────────────────────────────────────
            # Registry result beats LLM for statute ID and domain
            final_statute_id = registry_statute_id or llm_statute_id
            final_domain = registry_domain or llm_domain

            # ── Enrich the query string ───────────────────────────────────
            if len(enriched_query.split()) < 15:
                key_concepts = self._extract_key_concepts(raw_output)
                if key_concepts:
                    enriched_query = (
                        f"{enriched_query} Dette gjelder særlig {key_concepts.strip()}."
                    )

            if final_statute_id and not secondary_statute_id:
                enriched_query = f"{statute_name} ({final_statute_id}): {enriched_query}"
            elif final_statute_id and secondary_statute_id:
                enriched_query = (
                    f"{statute_name} ({final_statute_id}) og sekundær lov "
                    f"({secondary_statute_id}): {enriched_query}"
                )

            logger.debug(
                f"enriched='{enriched_query[:80]}' | statute={final_statute_id} "
                f"({'registry' if statute_from_registry else 'LLM'}) | "
                f"domain={final_domain} | jurisdiction={jurisdiction}"
            )

            return {
                "enriched_query": enriched_query,
                "primary_statute_id": final_statute_id,
                "secondary_statute_id": secondary_statute_id,
                "statute_from_registry": statute_from_registry,
                "response_style": response_style,
                "domain": final_domain,
                "jurisdiction": jurisdiction,
                "source_type": source_type,
            }

        except Exception as exc:
            logger.warning(
                f"[WARN] QueryReasoningAgent LLM failed — using registry result if available: {exc}"
            )
            # Even if LLM fails, return registry result if we have one
            return {
                "enriched_query": query,
                "primary_statute_id": registry_statute_id,
                "secondary_statute_id": None,
                "statute_from_registry": statute_from_registry,
                "response_style": "",
                "domain": registry_domain,
                "jurisdiction": None,
                "source_type": None,
            }

    @staticmethod
    def _build_context_str(
        context_window: Optional[List[Dict[str, str]]],
        previous_statute_id: Optional[str] = None,
        previous_enriched_query: Optional[str] = None,
    ) -> str:
        parts = []
        if previous_statute_id:
            parts.append(f"PREVIOUS_STATUTE_ID: {previous_statute_id}")
        if previous_enriched_query:
            parts.append(f"PREVIOUS_ENRICHED_QUERY: {previous_enriched_query}")
        if context_window:
            last_user = last_assistant = None
            for msg in reversed(context_window):
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "assistant" and last_assistant is None:
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

    # ── Field extractors ──────────────────────────────────────────────────

    @staticmethod
    def _extract_field(raw: str, prefix: str) -> Optional[str]:
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith(prefix.lower()):
                idx = stripped.find(":")
                if idx != -1:
                    val = stripped[idx + 1:].strip()
                    if val and val.lower() not in ("none", ""):
                        return val
        return None

    @staticmethod
    def _extract_enriched_query(raw: str, fallback: str) -> str:
        for line in raw.splitlines():
            if line.strip().lower().startswith("enriched query"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val:
                        return val
        if raw and len(raw) < 500:
            return raw
        return fallback

    @staticmethod
    def _extract_statute_id(raw: str) -> Optional[str]:
        for line in raw.splitlines():
            if line.strip().lower().startswith("primary statute id"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val and val.lower() != "none":
                        return val
        return None

    @staticmethod
    def _extract_secondary_statute_id(raw: str) -> Optional[str]:
        for line in raw.splitlines():
            if line.strip().lower().startswith("secondary statute id"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val and val.lower() != "none":
                        return val
        return None

    @staticmethod
    def _extract_statute_name(raw: str) -> str:
        for line in raw.splitlines():
            if line.strip().lower().startswith("primary statute name"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val and val.lower() not in ("none", ""):
                        return val
        return ""

    @staticmethod
    def _extract_response_style(raw: str) -> str:
        for line in raw.splitlines():
            if line.strip().lower().startswith("response style"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val:
                        return val
        return ""

    @staticmethod
    def _extract_key_concepts(raw: str) -> str:
        for line in raw.splitlines():
            if line.strip().lower().startswith("key concepts"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val:
                        return val
        return ""

    def _extract_domain(self, raw: str) -> Optional[str]:
        # Check both "Legal Domain" occurrences (prompt has it twice)
        found = []
        for line in raw.splitlines():
            if line.strip().lower().startswith("legal domain"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val and val.lower() not in ("none", ""):
                        found.append(val.lower())
        return found[-1] if found else None

    @staticmethod
    def _extract_jurisdiction(raw: str) -> Optional[str]:
        allowed = {"NO", "EU-EEA", "BOTH", "both"}
        for line in raw.splitlines():
            if line.strip().lower().startswith("jurisdiction"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip()
                    if val in allowed:
                        return "BOTH" if val.lower() == "both" else val
        return None

    @staticmethod
    def _extract_source_type(raw: str) -> Optional[str]:
        allowed = {"lov", "forskrift", "both"}
        for line in raw.splitlines():
            if line.strip().lower().startswith("source type"):
                idx = line.find(":")
                if idx != -1:
                    val = line[idx + 1:].strip().lower()
                    if val in allowed:
                        return "BOTH" if val.lower() == "both" else val
        return None