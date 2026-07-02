import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings
from config_domains import DOMAINS_CANONICAL, normalize_domain

logger = logging.getLogger(__name__)


_TAXONOMY_TEXT = """
DOMAIN: Avtalerett
SUBDOMAINS (use EXACTLY these labels):
  - Contract Formation & Interpretation
  - Standard Terms (B2B / B2C)
  - Specific Contract Types
  - Perfection & Registration
  - Electronic Contracting / eCom
KEYWORDS: inngå avtale, avtaleinngåelse, tilbud og aksept, tolkning av avtale, urimelig avtalevilkår,
  ugyldig avtale, avtaleloven § 36, standardvilkår, angrerett, e-signatur, netthandel, fullmakt,
  signaturrett, prokura, stillingsfullmakt

DOMAIN: Arbeidsrett
SUBDOMAINS (use EXACTLY these labels):
  - Hiring & Employment Contracts
  - Labour Court & Dispute Resolution
  - Working Time, Leave & Furlough
  - Business Transfers (Virksomhetsoverdragelse)
  - Termination & Dismissal Procedure
KEYWORDS: ansette, arbeidsavtale, oppsigelse av ansatt, arbeidstid, overtid, ferie, sykmelding,
  permittering, virksomhetsoverdragelse, drøftelsesmøte, usaklig oppsigelse, prøvetid,
  diskriminering, likestilling, pensjon, tariffavtale, allmenngjøring, sjøfolk, skip

DOMAIN: Arsregnskap_og_selskapsrapportering
SUBDOMAINS (use EXACTLY these labels):
  - Annual Accounts & Notes
  - Audit: Duty / Opting Out
  - Accounting Duty & Reporting
  - Distributions
KEYWORDS: årsregnskap, årsberetning, noter, bokføring, revisjon, revisor, revisjonsplikt,
  regnskapsplikt, regnskap, utbytte, konsernregnskap, IFRS, god regnskapsskikk

DOMAIN: Inkasso_og_tvangsfullbyrdelse
SUBDOMAINS (use EXACTLY these labels):
  - Pre-Collection (Reminders & Notices)
  - Collection (Inkasso Steps & Fees)
  - Enforcement (Attachments & Forced Sale)
  - Insolvency Thresholds & Filing
KEYWORDS: inkasso, purring, betalingspåminnelse, tvangsfullbyrdelse, utlegg, tvangsdekning,
  namsmann, tvangssalg, gjeldsordning, innkreving, pengekrav, tvangsbøter

DOMAIN: Konkursrett_og_insolvens
SUBDOMAINS (use EXACTLY these labels):
  - Insolvency Thresholds & Filing
  - Estate Process & Creditor Actions
  - Avoidance / Priority / Dividends
KEYWORDS: konkurs, gjeldsforhandling, insolvens, betalingsudyktighet, oppbud, bobehandling,
  bobestyrer, omstøtelse, dekningsloven, kreditorer, dividende, rekonstruksjon

DOMAIN: Manda_fusjon_fisjon
SUBDOMAINS (use EXACTLY these labels):
  - Competition Notifications
KEYWORDS: fusjon, fisjon, M&A, virksomhetsoverdragelse, aksjesalg, selskapssammenslåing,
  konkurransemelding, due diligence, transaksjoner

DOMAIN: Obligasjonsrett
SUBDOMAINS (use EXACTLY these labels):
  - Remedies: Performance, Price Reduction, Termination, Damages
KEYWORDS: mislighold, heving, prisavslag, erstatning, reklamasjon, force majeure,
  kreditorrettigheter, ytelse, kontraktsbrudd, direkte krav

DOMAIN: Panterett_og_sikkerhetsrett
SUBDOMAINS (use EXACTLY these labels):
  - Creating Security (Pledge Types)
  - Perfection & Registration
  - Payment Disputes
KEYWORDS: pant, pantsettelse, sikkerhetsstillelse, pant i løsøre, fast eiendom,
  avtalepant, utleggspant, rettsvern, finansiell sikkerhet, tinglysing, mortifikasjon

DOMAIN: Pengekravsrett_fordringer
SUBDOMAINS (use EXACTLY these labels):
  - Payment Disputes
  - Interest & Late Interest
  - Assignment / Cessio & Debtor Change
KEYWORDS: pengekrav, fordring, gjeldsbrev, rente, forsinkelsesrente, cesjon,
  gjeldsoverføring, kausjon, regresskrav, motregning

DOMAIN: Personvern_gdpr_business_compliance
SUBDOMAINS (use EXACTLY these labels):
  - Lawful Basis & Internal Control
  - Data Subject Rights
  - Processor Agreements (DPA)
  - Security Measures (TOMs)
  - Cookies & eCom Overlay
  - Formation & Registration
  - Standard Terms (B2B / B2C)
KEYWORDS: GDPR, personopplysninger, personvern, databehandler, behandlingsgrunnlag,
  samtykke, registerføring, innsyn, sletting, databehandleravtale, cookies, informasjonsplikt

DOMAIN: Selskapsrett
SUBDOMAINS (use EXACTLY these labels):
  - Formation & Registration
  - Shareholder Rights & Records
  - Share Capital & Equity Changes
  - Board Liability & Loss of Equity
  - Distributions
KEYWORDS: aksjeselskap, ASA, styret, generalforsamling, aksjonærrettigheter, aksjekapital,
  vedtekter, daglig leder, foretaksregisteret, fisjon, kapitalforhøyelse, utbytte

DOMAIN: Tvistelosning_smb
SUBDOMAINS (use EXACTLY these labels):
  - Conciliation Board (Forliksråd)
  - Small Claims / Simplified Procedure
  - Arbitration & Agreed Venue
KEYWORDS: forliksråd, tvistelosning, mekling, voldgift, søksmål, rettslig tvist,
  forlik, stevning, konfliktråd, husleietvistutvalget, domstol
"""


class RouterAgent:

    _SYSTEM_PROMPT = (
        "You are a Legal Query Routing Engine for Norwegian law.\n"
        "Your job is NOT to answer the legal question.\n"
        "Your job is to classify the query into structured retrieval filters "
        "using the provided taxonomy.\n\n"
        "If the query fits one of the 12 canonical domains in the taxonomy, you MUST use that domain key.\n"
        "If the query does NOT fit any of the 12 canonical domains (e.g., it is about criminal law, family law, tax law, traffic law, etc.), you should classify it into an appropriate custom domain key (e.g. 'criminal_law', 'family_law', 'tax_law') and leave the subdomain_candidates list empty.\n\n"
        "You MUST use the taxonomy domain keys and subdomain labels below for canonical domains.\n"
        "DO NOT invent subdomains.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TAXONOMY\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + _TAXONOMY_TEXT
        + "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "CANONICAL DOMAIN KEYS — you MUST output one of these EXACTLY:\n"
        "  arbeidsrett\n"
        "  arsregnskap_og_selskapsrapportering\n"
        "  avtalerett\n"
        "  inkasso_og_tvangsfullbyrdelse\n"
        "  konkursrett_og_insolvens\n"
        "  manda_fusjon_fisjon\n"
        "  obligasjonsrett\n"
        "  panterett_og_sikkerhetsrett\n"
        "  pengekravsrett_fordringer\n"
        "  personvern_gdpr_business_compliance\n"
        "  selskapsrett\n"
        "  tvistelosning_smb\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "YOUR STEPS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Step 1 — Accept DOMAIN HINT as primary anchor. Only override with clear evidence.\n"
        "Step 2 — Match USER QUERY and ENRICHED QUERY against taxonomy keywords.\n"
        "Step 3 — Select the matching canonical domain key (lowercase, underscore).\n"
        "Step 4 — Select TOP 1-2 subdomains from that domain's list. Use exact subdomain labels.\n"
        "Step 5 — Detect B2B/B2C: 'forbruker'/'privatperson' → B2C; unclear → BOTH; else → B2B.\n"
        "Step 6 — Set jurisdiction from taxonomy (NO / EU-EEA / BOTH).\n"
        "Step 7 — Score confidence 0.0–1.0.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "OUTPUT — respond with ONLY this JSON, no extra text:\n"
        "{\n"
        '  "domain": "<canonical_domain_key>",\n'
        '  "subdomain_candidates": ["<subdomain1>", "<subdomain2>"],\n'
        '  "b2b_b2c": "B2B|B2C|BOTH",\n'
        '  "relationship_type": "commercial|consumer|employment",\n'
        '  "jurisdiction": "NO|EU-EEA|BOTH",\n'
        '  "matched_keywords": ["<kw1>", "<kw2>"],\n'
        '  "conflict_detected": false,\n'
        '  "confidence": 0.85\n'
        "}\n"
    )

    # Complete canonical subdomain list — ALL 12 domains
    _VALID_SUBDOMAINS: Dict[str, List[str]] = {
        "avtalerett": [
            "Contract Formation & Interpretation",
            "Standard Terms (B2B / B2C)",
            "Specific Contract Types",
            "Perfection & Registration",
            "Electronic Contracting / eCom",
        ],
        "arbeidsrett": [
            "Hiring & Employment Contracts",
            "Labour Court & Dispute Resolution",
            "Working Time, Leave & Furlough",
            "Business Transfers (Virksomhetsoverdragelse)",
            "Termination & Dismissal Procedure",
        ],
        "arsregnskap_og_selskapsrapportering": [
            "Annual Accounts & Notes",
            "Audit: Duty / Opting Out",
            "Accounting Duty & Reporting",
            "Distributions",
        ],
        "inkasso_og_tvangsfullbyrdelse": [
            "Pre-Collection (Reminders & Notices)",
            "Collection (Inkasso Steps & Fees)",
            "Enforcement (Attachments & Forced Sale)",
            "Insolvency Thresholds & Filing",
        ],
        "konkursrett_og_insolvens": [
            "Insolvency Thresholds & Filing",
            "Estate Process & Creditor Actions",
            "Avoidance / Priority / Dividends",
        ],
        "manda_fusjon_fisjon": [
            "Competition Notifications",
        ],
        "obligasjonsrett": [
            "Remedies: Performance, Price Reduction, Termination, Damages",
        ],
        "panterett_og_sikkerhetsrett": [
            "Creating Security (Pledge Types)",
            "Perfection & Registration",
            "Payment Disputes",
        ],
        "pengekravsrett_fordringer": [
            "Payment Disputes",
            "Interest & Late Interest",
            "Assignment / Cessio & Debtor Change",
        ],
        "personvern_gdpr_business_compliance": [
            "Lawful Basis & Internal Control",
            "Data Subject Rights",
            "Processor Agreements (DPA)",
            "Security Measures (TOMs)",
            "Cookies & eCom Overlay",
            "Formation & Registration",
            "Standard Terms (B2B / B2C)",
        ],
        "selskapsrett": [
            "Formation & Registration",
            "Shareholder Rights & Records",
            "Share Capital & Equity Changes",
            "Board Liability & Loss of Equity",
            "Distributions",
        ],
        "tvistelosning_smb": [
            "Conciliation Board (Forliksråd)",
            "Small Claims / Simplified Procedure",
            "Arbitration & Agreed Venue",
        ],
    }

    _VALID_DOMAINS = frozenset(DOMAINS_CANONICAL)
    _VALID_B2B_B2C = {"B2B", "B2C", "BOTH"}
    _VALID_REL_TYPES = {"commercial", "consumer", "employment"}
    _VALID_JURISDICTIONS = {"NO", "EU-EEA", "BOTH"}

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.0,
            streaming=False,
        )
        logger.info("✅ RouterAgent initialized (v2 — full subdomain list)")

    async def run(
        self,
        raw_query: str,
        enriched_query: str,
        domain_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger.info(
            f"🔀 RouterAgent: classifying | domain_hint={domain_hint!r} | "
            f"enriched='{enriched_query[:60]}'"
        )

        try:
            user_content = (
                f"DOMAIN HINT (from reasoning agent — HIGH PRIORITY): {domain_hint or 'none'}\n\n"
                f"USER QUERY:\n{raw_query}\n\n"
                f"ENRICHED QUERY:\n{enriched_query}"
            )

            messages = [
                SystemMessage(content=self._SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]

            response = await self._llm.agenerate([messages])
            raw_output = response.generations[0][0].text.strip()

            logger.debug(f"🔀 RouterAgent raw output: {raw_output}")

            result = self._parse_and_validate(raw_output, domain_hint)

            logger.info(
                f"🔀 RouterAgent: domain={result['domain']} | "
                f"subdomains={result['subdomain_candidates']} | "
                f"b2b_b2c={result['b2b_b2c']} | "
                f"jurisdiction={result['jurisdiction']} | "
                f"confidence={result['confidence']}"
            )
            return result

        except Exception as exc:
            logger.warning(f"⚠️  RouterAgent failed | {exc}")
            return self._fallback(domain_hint)

    def _parse_and_validate(
        self,
        raw_output: str,
        domain_hint: Optional[str],
    ) -> Dict[str, Any]:

        cleaned = re.sub(r"```(?:json)?\s*", "", raw_output)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.warning("🔀 RouterAgent: no JSON found")
            return self._fallback(domain_hint)

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning(f"🔀 RouterAgent: JSON parse error | {exc}")
            return self._fallback(domain_hint)

        # ── Domain: normalize to canonical lowercase ───────────────────────
        raw_domain = data.get("domain", "")
        domain = normalize_domain(raw_domain)
        if not domain:
            # If not in the 12 canonical domains, keep it as a custom lowercase string
            domain = raw_domain.strip().lower() if raw_domain else ""
        if not domain:
            # Try hint
            hint = normalize_domain(domain_hint)
            domain = hint if hint else (domain_hint.strip().lower() if domain_hint else "")

        # ── Subdomains: validate against the domain's list ────────────────
        valid_subs = self._VALID_SUBDOMAINS.get(domain, [])
        raw_subs = data.get("subdomain_candidates", [])
        if isinstance(raw_subs, list):
            subdomain_candidates = [s for s in raw_subs if s in valid_subs][:2]
        else:
            subdomain_candidates = []

        # If LLM returned no valid subdomains, try to infer from first valid
        if not subdomain_candidates and valid_subs:
            logger.debug(
                f"🔀 RouterAgent: no valid subdomains from LLM for domain={domain}, "
                f"valid={valid_subs}"
            )

        b2b_b2c = data.get("b2b_b2c", "BOTH")
        if b2b_b2c not in self._VALID_B2B_B2C:
            b2b_b2c = "BOTH"

        relationship_type = data.get("relationship_type", "commercial")
        if relationship_type not in self._VALID_REL_TYPES:
            relationship_type = "commercial"
        if domain == "arbeidsrett":
            relationship_type = "employment"

        jurisdiction = data.get("jurisdiction", "NO")
        if jurisdiction not in self._VALID_JURISDICTIONS:
            jurisdiction = "NO"

        matched_keywords = data.get("matched_keywords", [])
        if not isinstance(matched_keywords, list):
            matched_keywords = []

        conflict_detected = bool(data.get("conflict_detected", False))
        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        return {
            "domain": domain,
            "subdomain_candidates": subdomain_candidates,
            "matched_keywords": matched_keywords,
            "conflict_detected": conflict_detected,
            "b2b_b2c": b2b_b2c,
            "relationship_type": relationship_type,
            "jurisdiction": jurisdiction,
            "confidence": confidence,
        }

    def _fallback(self, domain_hint: Optional[str]) -> Dict[str, Any]:
        domain = normalize_domain(domain_hint)
        domain = domain if domain in self._VALID_DOMAINS else ""
        return {
            "domain": domain,
            "subdomain_candidates": [],
            "matched_keywords": [],
            "conflict_detected": False,
            "b2b_b2c": "BOTH",
            "relationship_type": "commercial",
            "jurisdiction": "NO",
            "confidence": 0.0,
        }