
import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import AzureChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TAXONOMY — extracted from DigiRett AI Legal Taxonomy v1.0.1 PDF
# Used as context in the LLM prompt for keyword matching.
# Keep in sync with digirett_taxonomy_v101.json.
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_TAXONOMY_TEXT = """
DOMAIN: Avtalerett
SUBDOMAIN: Contract Formation & Interpretation (CL-01)
  b2b_b2c: BOTH | jurisdiction: BOTH | relationship_type: commercial/consumer
  KEYWORDS: inngå avtale, avtaleinngåelse, tilbud og aksept, er vi bundet av avtalen,
    muntlig avtale, skriftlig krav til avtale, tolkning av avtale, avtaletolkning,
    hva betyr denne klausulen, uklarhetsregelen, avtalens innhold, forutsetningslæren,
    lojalitetsplikt i kontraktsforhold, avtalefrihet, bindende tilbud, akseptfrist,
    konkludent atferd, stilltiende aksept, si opp avtalen, oppsigelsestid i kontrakt,
    oppsigelsesklausul, automatisk fornyelse av avtale, culpa in contrahendo
  CONFUSERS (do NOT route here): mislighold→Obligasjonsrett, heving av avtale→Obligasjonsrett,
    erstatning→Obligasjonsrett, reklamasjon→Obligasjonsrett, force majeure→Obligasjonsrett,
    oppsigelse av ansatt→Arbeidsrett

SUBDOMAIN: Authority & Representation (CL-02)
  b2b_b2c: B2B | jurisdiction: NO | relationship_type: commercial
  KEYWORDS: fullmakt, hvem kan binde selskapet, signaturrett, prokura, daglig leders myndighet,
    styrets myndighet, stillingsfullmakt, tilsynelatende fullmakt, legitimasjon, fullmektig,
    hvem signerer kontrakten, kan daglig leder inngå avtale, krav til to signaturer,
    fullmaktens grenser, overskridelse av fullmakt, tilbakekall av fullmakt,
    generalfullmakt, spesialfullmakt
  CONFUSERS: styrevedtak→Selskapsrett, generalforsamling→Selskapsrett, revisor→Arsregnskap

SUBDOMAIN: Invalidity & Unfair Terms (CL-03)
  b2b_b2c: BOTH | jurisdiction: BOTH | relationship_type: commercial/consumer
  KEYWORDS: ugyldig avtale, ugyldighet, urimelig avtalevilkår, avtaleloven § 36,
    lemping av avtale, revisjon av avtale, tvang, trusler ved avtaleinngåelse,
    svik, villfarelse, forutsetningssvikt, åger, misbruk av stilling, utnyttelse,
    kan vi komme oss ut av avtalen, er klausulen gyldig,
    urimelig konkurranseklausul, urimelig ansvarsbegrensning
  CONFUSERS: heving→Obligasjonsrett, mislighold→Obligasjonsrett,
    prisavslag→Obligasjonsrett, oppsigelse av ansatt→Arbeidsrett

SUBDOMAIN: Standard Terms B2B/B2C (CL-04)
  b2b_b2c: BOTH | jurisdiction: BOTH | relationship_type: commercial/consumer
  KEYWORDS: standardvilkår, alminnelige vilkår, standard salgsvilkår, standardkontrakt,
    NS-kontrakt, NS 8405, NF 15, NTK 15, ORGALIME, innarbeidelse av standardvilkår,
    battle of the forms, motstridende standardvilkår, forbrukeravtale,
    kan ikke fravikes til ugunst for forbruker, digitale standardvilkår, click-wrap avtale
  CONFUSERS: individuell forhandling→CL-01, angrerett→CL-05, arbeidsavtale→Arbeidsrett

SUBDOMAIN: Electronic Contracting/eCom (CL-05)
  b2b_b2c: BOTH (angrerett is B2C only) | jurisdiction: BOTH | relationship_type: commercial/consumer
  KEYWORDS: angrerett, angrefrist, 14 dagers angrerett, netthandel, elektronisk avtale,
    e-signatur, BankID, kvalifisert elektronisk signatur, eIDAS, opplysningsplikt ved netthandel,
    avtaleinngåelse på nett, abonnement på nett, automatisk fornyelse av abonnement, ehandelsloven
  CONFUSERS: informasjonskapsler/cookies→Personvern_GDPR, personopplysninger→Personvern_GDPR,
    GDPR samtykke→Personvern_GDPR

---

DOMAIN: Arbeidsrett
SUBDOMAIN: Hiring & Employment Contracts (EL-01)
  b2b_b2c: B2B | jurisdiction: BOTH | relationship_type: employment
  KEYWORDS: ansette ny medarbeider, arbeidsavtale, hva skal stå i arbeidsavtalen,
    krav til arbeidsavtale, skriftlig arbeidsavtale, prøvetid, prøvetidsoppsigelse,
    fast ansettelse, midlertidig ansettelse, når kan jeg ansette midlertidig, vikariat,
    sesongarbeid, innleie fra bemanningsbyrå, likebehandling ved innleie,
    arbeidsgivers styringsrett, stillingsbeskrivelse, konkurranseklausul i arbeidsavtale,
    kundeklausul, diskriminering ved ansettelse
  CONFUSERS: oppsigelse→EL-02, permittering→EL-03, virksomhetsoverdragelse→EL-04,
    konsulentavtale→Avtalerett, standardvilkår i arbeidsavtale→Avtalerett

SUBDOMAIN: Termination & Dismissal Procedure (EL-02)
  b2b_b2c: B2B | jurisdiction: NO | relationship_type: employment
  KEYWORDS: si opp ansatt, oppsigelse av ansatt, saklig grunn til oppsigelse,
    oppsigelse begrunnet i virksomheten, oppsigelse begrunnet i arbeidstaker,
    drøftelsesmøte, krav til drøftelsesmøte, oppsigelsestid for ansatt,
    oppsigelsesfrister, avskjed, grovt pliktbrudd, usaklig oppsigelse,
    ugyldig oppsigelse, fortrinnsrett til ny stilling, vern mot oppsigelse under sykdom,
    vern mot oppsigelse under svangerskap, sluttattest, fratredelsesavtale, sluttpakke
  CONFUSERS: permittering→EL-03, virksomhetsoverdragelse→EL-04, konkurs→Konkursrett,
    lønnsgaranti→Konkursrett, si opp avtalen→Avtalerett, oppsigelse av leieavtale→Avtalerett

SUBDOMAIN: Working Time Leave & Furlough (EL-03)
  b2b_b2c: B2B | jurisdiction: BOTH | relationship_type: employment
  KEYWORDS: arbeidstid, maksimal arbeidstid, overtid, overtidsbetaling,
    gjennomsnittsberegning av arbeidstid, hviletid, nattarbeid, ferie, feriepenger,
    ferieloven, foreldrepermisjon, svangerskapspermisjon, fedrekvote, sykemelding,
    sykepenger, arbeidsgiverperioden, permittering, permitteringsvarsel,
    permitteringsperiode, arbeidsgivers lønnsplikt ved permittering
  CONFUSERS: oppsigelse av ansatt→EL-02, sluttpakke→EL-02, lønnsgaranti ved konkurs→Konkursrett,
    ferie (leie)→Avtalerett

SUBDOMAIN: Business Transfers (EL-04)
  b2b_b2c: B2B | jurisdiction: BOTH | relationship_type: employment
  KEYWORDS: virksomhetsoverdragelse, overdragelse av virksomhet,
    ansattes rettigheter ved salg av bedrift, hva skjer med de ansatte ved fusjon,
    informasjon og drøftelse ved overdragelse, rett til å motsette seg overdragelse,
    reservasjonsrett, fortrinnsrett etter reservasjon, tariffavtale ved overdragelse,
    pensjonsrettigheter ved overdragelse, identitetstest, outsourcing og VO,
    virksomhetsoverdragelse ved konkurs
  CONFUSERS: fusjon→MandA_Fusjon_Fisjon, fisjon→MandA_Fusjon_Fisjon,
    aksjesalg→MandA_Fusjon_Fisjon, oppsigelse ved nedleggelse→EL-02, konkurs→Konkursrett

SUBDOMAIN: Labour Court & Dispute Resolution (EL-05)
  b2b_b2c: B2B | jurisdiction: NO | relationship_type: employment
  KEYWORDS: tvist om oppsigelse, ugyldig oppsigelse søksmål,
    midlertidig forføyning mot oppsigelse, stå i stilling, rett til å stå i stilling,
    Arbeidsretten, prosessvarsel, søksmålsfrist, 8-ukersfrist,
    erstatning ved usaklig oppsigelse, gjeninnsettelsesskrav, saksomkostninger i arbeidsrett
  CONFUSERS: forliksråd (general)→Tvistelosning_SMB_dataset,
    midlertidig forføyning (general)→Tvistelosning_SMB_dataset,
    søksmål om kontrakt→Avtalerett

---
TERMINATION DECISION RULE (deterministic — apply before keyword scoring):
  "oppsigelse av ansatt" / "si opp ansatt" / "drøftelsesmøte"  →  Arbeidsrett / EL-02
  "si opp avtalen" / "oppsigelsestid i kontrakt" / "oppsigelsesklausul" (no employment context)  →  Avtalerett / CL-01
  "heving" / "mislighold" / "erstatning" / "prisavslag" / "force majeure"  →  Obligasjonsrett
"""


class RouterAgent:

    _SYSTEM_PROMPT = (
        "You are a Legal Query Routing Engine for Norwegian law.\n"
        "Your job is NOT to answer the legal question.\n"
        "Your job is to classify the query into structured retrieval filters "
        "using the provided taxonomy.\n\n"
        "You MUST use ONLY the taxonomy values below. "
        "DO NOT invent domains or subdomains.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "TAXONOMY\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + _TAXONOMY_TEXT
        + "\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "YOUR STEPS\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Step 1 — Accept DOMAIN HINT as primary anchor. "
        "Only override it when keyword evidence is clearly stronger.\n"
        "Step 2 — Match both USER QUERY and ENRICHED QUERY against taxonomy keywords "
        "(semantic match, not exact string match).\n"
        "Step 3 — Apply TERMINATION DECISION RULE first — it overrides keyword scoring.\n"
        "Step 4 — Apply CONFUSER rules — confusers override keyword matches.\n"
        "Step 5 — Select TOP 1–2 most relevant subdomains.\n"
        "Step 6 — Detect B2B/B2C: 'forbruker'/'privatperson'/'privatkunde' → B2C; "
        "unclear → BOTH; else → B2B.\n"
        "Step 7 — Set relationship_type: employment if Arbeidsrett; "
        "consumer if B2C; commercial otherwise.\n"
        "Step 8 — Set jurisdiction from taxonomy subdomain (NO / EU-EEA / BOTH).\n"
        "Step 9 — Score confidence: 0.8–1.0 strong match, 0.5–0.79 partial, 0.0–0.49 weak.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "OUTPUT — respond with ONLY valid JSON, no markdown fences, no explanation:\n"
        "{\n"
        '  "domain": "",\n'
        '  "subdomain_candidates": ["", ""],\n'
        '  "matched_keywords": ["", ""],\n'
        '  "conflict_detected": false,\n'
        '  "b2b_b2c": "B2B",\n'
        '  "relationship_type": "commercial",\n'
        '  "jurisdiction": "NO",\n'
        '  "confidence": 0.0\n'
        "}\n\n"
        "IMPORTANT: subdomain_candidates must use EXACTLY these names from the taxonomy:\n"
        "  Avtalerett subdomains: 'Contract Formation & Interpretation', "
        "'Authority & Representation', 'Invalidity & Unfair Terms', "
        "'Standard Terms (B2B / B2C)', 'Electronic Contracting / eCom'\n"
        "  Arbeidsrett subdomains: 'Hiring & Employment Contracts', "
        "'Termination & Dismissal Procedure', 'Working Time, Leave & Furlough', "
        "'Business Transfers (Virksomhetsoverdragelse)', 'Labour Court & Dispute Resolution'\n"
        "  For other domains: leave subdomain_candidates as [].\n"
        "  If no match: return empty subdomain_candidates and confidence=0.1."
    )

    # Valid subdomain names per domain — used to validate LLM output
    _VALID_SUBDOMAINS: Dict[str, List[str]] = {
        "Avtalerett": [
            "Contract Formation & Interpretation",
            "Authority & Representation",
            "Invalidity & Unfair Terms",
            "Standard Terms (B2B / B2C)",
            "Electronic Contracting / eCom",
        ],
        "Arbeidsrett": [
            "Hiring & Employment Contracts",
            "Termination & Dismissal Procedure",
            "Working Time, Leave & Furlough",
            "Business Transfers (Virksomhetsoverdragelse)",
            "Labour Court & Dispute Resolution",
        ],
    }

    _VALID_DOMAINS = frozenset({
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

    _VALID_B2B_B2C    = {"B2B", "B2C", "BOTH"}
    _VALID_REL_TYPES  = {"commercial", "consumer", "employment"}
    _VALID_JURISDICTIONS = {"NO", "EU-EEA", "BOTH"}

    def __init__(self) -> None:
        self._llm = AzureChatOpenAI(
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=0.0,   # deterministic — routing must be consistent
            streaming=False,
        )
        logger.info("✅ RouterAgent initialized")

    # ── Public interface ──────────────────────────────────────────────────

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
                f"rel={result['relationship_type']} | "
                f"jurisdiction={result['jurisdiction']} | "
                f"confidence={result['confidence']}"
            )
            return result

        except Exception as exc:
            logger.warning(f"⚠️  RouterAgent failed, returning domain_hint only | {exc}")
            return self._fallback(domain_hint)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _parse_and_validate(
        self,
        raw_output: str,
        domain_hint: Optional[str],
    ) -> Dict[str, Any]:
        """Parse JSON output and validate all enum fields."""

        # Strip markdown fences if present
        cleaned = re.sub(r"```(?:json)?\s*", "", raw_output)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()

        # Extract JSON object
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            logger.warning("🔀 RouterAgent: no JSON found in output")
            return self._fallback(domain_hint)

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            logger.warning(f"🔀 RouterAgent: JSON parse error | {exc}")
            return self._fallback(domain_hint)

        # Validate and sanitise each field
        domain = data.get("domain", "")
        if domain not in self._VALID_DOMAINS:
            # Fall back to domain_hint if LLM returned an invalid domain
            domain = domain_hint if domain_hint in self._VALID_DOMAINS else ""

        # Validate subdomains — only keep names that exist in the taxonomy
        valid_subs_for_domain = self._VALID_SUBDOMAINS.get(domain, [])
        raw_subs = data.get("subdomain_candidates", [])
        if isinstance(raw_subs, list):
            subdomain_candidates = [
                s for s in raw_subs if s in valid_subs_for_domain
            ][:2]
        else:
            subdomain_candidates = []

        b2b_b2c = data.get("b2b_b2c", "BOTH")
        if b2b_b2c not in self._VALID_B2B_B2C:
            b2b_b2c = "BOTH"

        relationship_type = data.get("relationship_type", "commercial")
        if relationship_type not in self._VALID_REL_TYPES:
            relationship_type = "commercial"

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
            "domain":               domain,
            "subdomain_candidates": subdomain_candidates,
            "matched_keywords":     matched_keywords,
            "conflict_detected":    conflict_detected,
            "b2b_b2c":              b2b_b2c,
            "relationship_type":    relationship_type,
            "jurisdiction":         jurisdiction,
            "confidence":           confidence,
        }

    def _fallback(self, domain_hint: Optional[str]) -> Dict[str, Any]:
        """Safe fallback — returns domain_hint with empty subdomains."""
        domain = domain_hint if domain_hint in self._VALID_DOMAINS else ""
        return {
            "domain":               domain,
            "subdomain_candidates": [],
            "matched_keywords":     [],
            "conflict_detected":    False,
            "b2b_b2c":              "BOTH",
            "relationship_type":    "commercial",
            "jurisdiction":         "NO",
            "confidence":           0.0,
        }