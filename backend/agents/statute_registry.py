"""
statute_registry.py

Deterministic Norwegian statute name → LOV/FORSKRIFT ID lookup.

Built from all 358 laws in the DigiRett VDB (eval dataset).
Used by QueryReasoningAgent BEFORE any LLM call to pin the exact statute.

Usage:
    from statute_registry import StatuteRegistry
    registry = StatuteRegistry()
    result = registry.lookup("skipssikkerhetsloven")
    # → {"id": "LOV-2007-02-16-9", "url": "https://lovdata.no/dokument/NL/lov/2007-02-16-9", "domain": "arbeidsrett"}
"""

import re
import unicodedata
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MASTER STATUTE TABLE
# Keys: lowercase Norwegian law names (popular + full forms)
# Values: {id, url, domain}
#
# Covers all 358 laws in the VDB (2000–2026).
# Each law has BOTH its popular short name (e.g. "skipssikkerhetsloven")
# AND its full "Lov om X" name (e.g. "lov om skipssikkerhet").
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_STATUTE_TABLE: Dict[str, Dict] = {

    # ── ARBEIDSRETT ──────────────────────────────────────────────────

    "likestillings- og diskrimineringsloven": {"id": "LOV-2017-06-16-51", "domain": "arbeidsrett"},
    "lov om likestilling og forbud mot diskriminering": {"id": "LOV-2017-06-16-51", "domain": "arbeidsrett"},

    "åpenhetsloven": {"id": "LOV-2021-06-18-99", "domain": "arbeidsrett"},
    "lov om virksomheters åpenhet og arbeid med grunnleggende menneskerettigheter og anstendige arbeidsforhold": {"id": "LOV-2021-06-18-99", "domain": "arbeidsrett"},

    "ela-lova": {"id": "LOV-2025-04-10-8", "domain": "arbeidsrett"},
    "lov om den europeiske arbeidsmarknadsstyresmakta": {"id": "LOV-2025-04-10-8", "domain": "arbeidsrett"},

    "lov om endringer i arbeidsmiljøloven lovens anvendelse for fornybar energiproduksjon til havs": {"id": "LOV-2025-06-20-45", "domain": "arbeidsrett"},
    "lovens anvendelse for fornybar energiproduksjon til havs": {"id": "LOV-2025-06-20-45", "domain": "arbeidsrett"},

    "arbeidsmarkedsloven": {"id": "LOV-2004-12-10-76", "domain": "arbeidsrett"},
    "lov om arbeidsmarkedstjenester": {"id": "LOV-2004-12-10-76", "domain": "arbeidsrett"},

    "arbeidsmiljøloven": {"id": "LOV-2005-06-17-62", "domain": "arbeidsrett"},
    "lov om arbeidsmiljø, arbeidstid og stillingsvern mv.": {"id": "LOV-2005-06-17-62", "domain": "arbeidsrett"},
    "lov om arbeidsmiljø": {"id": "LOV-2005-06-17-62", "domain": "arbeidsrett"},

    "lønnsnemndloven": {"id": "LOV-2012-01-27-10", "domain": "arbeidsrett"},
    "lov om lønnsnemnd i arbeidstvister": {"id": "LOV-2012-01-27-10", "domain": "arbeidsrett"},

    "arbeidstvistloven": {"id": "LOV-2012-01-27-9", "domain": "arbeidsrett"},
    "lov om arbeidstvister": {"id": "LOV-2012-01-27-9", "domain": "arbeidsrett"},

    "skipsarbeidsloven": {"id": "LOV-2013-06-21-102", "domain": "arbeidsrett"},
    "lov om stillingsvern mv. for arbeidstakere på skip": {"id": "LOV-2013-06-21-102", "domain": "arbeidsrett"},
    "lov om stillingsvern mv.": {"id": "LOV-2013-06-21-102", "domain": "arbeidsrett"},

    "lov om obligatorisk tjenestepensjon": {"id": "LOV-2005-12-21-124", "domain": "arbeidsrett"},
    "otp-loven": {"id": "LOV-2005-12-21-124", "domain": "arbeidsrett"},

    "arbeids- og velferdsforvaltningsloven": {"id": "LOV-2006-06-16-20", "domain": "arbeidsrett"},
    "lov om arbeids- og velferdsforvaltningen": {"id": "LOV-2006-06-16-20", "domain": "arbeidsrett"},
    "nav-loven": {"id": "LOV-2006-06-16-20", "domain": "arbeidsrett"},

    "skipssikkerhetsloven": {"id": "LOV-2007-02-16-9", "domain": "arbeidsrett"},
    "lov om skipssikkerhet": {"id": "LOV-2007-02-16-9", "domain": "arbeidsrett"},

    "sosialtjenesteloven": {"id": "LOV-2009-12-18-131", "domain": "arbeidsrett"},
    "lov om sosiale tjenester i arbeids- og velferdsforvaltningen": {"id": "LOV-2009-12-18-131", "domain": "arbeidsrett"},

    "afp-tilskottsloven": {"id": "LOV-2010-02-19-5", "domain": "arbeidsrett"},
    "lov om statstilskott til arbeidstakere": {"id": "LOV-2010-02-19-5", "domain": "arbeidsrett"},
    "lov om statstilskott til ordninger for avtalefestet pensjon": {"id": "LOV-2010-02-19-5", "domain": "arbeidsrett"},

    "a-opplysningsloven": {"id": "LOV-2012-06-22-43", "domain": "arbeidsrett"},
    "lov om arbeidsgivers innrapportering av ansettelses- og inntektsforhold mv.": {"id": "LOV-2012-06-22-43", "domain": "arbeidsrett"},

    "statsansatteloven": {"id": "LOV-2017-06-16-67", "domain": "arbeidsrett"},
    "lov om statens ansatte mv.": {"id": "LOV-2017-06-16-67", "domain": "arbeidsrett"},

    "yrkeskvalifikasjonsloven": {"id": "LOV-2017-06-16-69", "domain": "arbeidsrett"},
    "lov om godkjenning av yrkeskvalifikasjoner": {"id": "LOV-2017-06-16-69", "domain": "arbeidsrett"},

    "diskrimineringsombudsloven": {"id": "LOV-2017-06-16-50", "domain": "arbeidsrett"},
    "lov om likestillings- og diskrimineringsombudet og diskrimineringsnemnda": {"id": "LOV-2017-06-16-50", "domain": "arbeidsrett"},

    "lov om endringer i arbeidsmiljøloven og sosialtjenesteloven": {"id": "LOV-2015-04-24-20", "domain": "arbeidsrett"},

    "se-loven": {"id": "LOV-2005-04-01-14", "domain": "arbeidsrett"},
    "lov om europeiske selskaper": {"id": "LOV-2005-04-01-14", "domain": "arbeidsrett"},

    "sce-loven": {"id": "LOV-2006-06-30-50", "domain": "arbeidsrett"},
    "lov om europeiske samvirkeforetak": {"id": "LOV-2006-06-30-50", "domain": "arbeidsrett"},

    "lov om endringer i arbeidsmiljøloven": {"id": "LOV-2025-06-20-37", "domain": "arbeidsrett"},
    "lov om endringer i statsansatteloven": {"id": "LOV-2025-06-20-43", "domain": "arbeidsrett"},

    "lov om endringer i allmenngjøringsloven": {"id": "LOV-2025-03-28-4", "domain": "arbeidsrett"},

    # ARBEIDSRETT — forskrifter
    "forskrift om europeiske samarbeidsutvalg mv.": {"id": "FORSKRIFT-2000-07-28-797", "domain": "arbeidsrett"},
    "forskrift om ansattes rett til representasjon": {"id": "FORSKRIFT-2002-03-01-213", "domain": "arbeidsrett"},
    "forskrift om arbeid og utplassering av ungdom": {"id": "FORSKRIFT-2002-04-25-423", "domain": "arbeidsrett"},
    "forskrift om hms-kort på bygge- og anleggsplasser": {"id": "FORSKRIFT-2007-03-30-366", "domain": "arbeidsrett"},
    "forskrift om lønns- og arbeidsvilkår i offentlige kontrakter mv.": {"id": "FORSKRIFT-2008-02-08-112", "domain": "arbeidsrett"},
    "forskrift om informasjons- og påseplikt og innsynsrett": {"id": "FORSKRIFT-2008-02-22-166", "domain": "arbeidsrett"},
    "forskrift om offentlig godkjenning av bemanningsforetak": {"id": "FORSKRIFT-2008-06-04-541", "domain": "arbeidsrett"},
    "forskrift om arbeidsgiver- og arbeidstakerregisteret": {"id": "FORSKRIFT-2008-08-18-942", "domain": "arbeidsrett"},
    "bemanningsforskriften": {"id": "FORSKRIFT-2009-06-18-666", "domain": "arbeidsrett"},
    "forskrift om bemanning av norske skip": {"id": "FORSKRIFT-2009-06-18-666", "domain": "arbeidsrett"},
    "forskrift om unntak fra arbeidsmiljølovens arbeidstidsbestemmelser": {"id": "FORSKRIFT-2009-06-26-873", "domain": "arbeidsrett"},
    "forskrift om offentlig godkjenning av renholdsvirksomheter": {"id": "FORSKRIFT-2012-05-08-408", "domain": "arbeidsrett"},
    "forskrift om innleie fra bemanningsforetak": {"id": "FORSKRIFT-2013-01-11-33", "domain": "arbeidsrett"},
    "forskrift om skipsarbeidslovens virkeområde": {"id": "FORSKRIFT-2013-08-19-990", "domain": "arbeidsrett"},
    "forskrift om klagerett": {"id": "FORSKRIFT-2013-08-19-998", "domain": "arbeidsrett"},
    "forskrift om bruk av arbeidsformidlingsvirksomhet på skip": {"id": "FORSKRIFT-2013-08-19-999", "domain": "arbeidsrett"},
    "a-opplysningsforskriften": {"id": "FORSKRIFT-2014-06-24-857", "domain": "arbeidsrett"},
    "forskrift om arbeidsgivers innrapportering av ansettelses- og inntektsforhold mv.": {"id": "FORSKRIFT-2014-06-24-857", "domain": "arbeidsrett"},
    "tilleggsstønadsforskriften": {"id": "FORSKRIFT-2015-07-02-867", "domain": "arbeidsrett"},
    "forskrift om stønader til dekning av utgifter knyttet til å komme i eller beholde arbeid": {"id": "FORSKRIFT-2015-07-02-867", "domain": "arbeidsrett"},
    "forskrift om tilskudd til sysselsetting av arbeidstakere til sjøs": {"id": "FORSKRIFT-2016-02-26-204", "domain": "arbeidsrett"},
    "forskrift om lønnsplikt under permittering": {"id": "FORSKRIFT-2016-06-21-764", "domain": "arbeidsrett"},
    "forsvarstilsatteforskriften": {"id": "FORSKRIFT-2017-06-24-997", "domain": "arbeidsrett"},
    "forskrift om arbeidsavklaringspenger": {"id": "FORSKRIFT-2017-12-13-2100", "domain": "arbeidsrett"},
    "forskrift om unntak fra arbeidsmiljøloven med tilhørende forskrifter": {"id": "FORSKRIFT-2018-12-20-2182", "domain": "arbeidsrett"},
    "forskrift om kontrolltiltak over arbeidstakere": {"id": "FORSKRIFT-2019-01-25-53", "domain": "arbeidsrett"},
    "forskrift om arbeidsgivers lønnsplikt under permittering": {"id": "FORSKRIFT-2020-03-20-374", "domain": "arbeidsrett"},
    "forskrift om arbeid i arbeidsgivers hjem og husholdning": {"id": "FORSKRIFT-2022-06-03-969", "domain": "arbeidsrett"},
    "forskrift om arbeidsmiljølovens anvendelse": {"id": "FORSKRIFT-2024-04-11-607", "domain": "arbeidsrett"},
    "forskrift om allmenngjøring av tariffavtale": {"id": "FORSKRIFT-2024-10-21-2533", "domain": "arbeidsrett"},
    "forskrift om delvis allmenngjøring av tariffavtaler": {"id": "FORSKRIFT-2024-10-21-2534", "domain": "arbeidsrett"},
    "rammeforskriften": {"id": "FORSKRIFT-2010-02-12-158", "domain": "arbeidsrett"},
    "forskrift om helse, miljø og sikkerhet i petroleumsvirksomheten": {"id": "FORSKRIFT-2010-02-12-158", "domain": "arbeidsrett"},
    "aktivitetsforskriften": {"id": "FORSKRIFT-2010-04-29-613", "domain": "arbeidsrett"},
    "forskrift om utføring av aktiviteter i petroleumsvirksomheten": {"id": "FORSKRIFT-2010-04-29-613", "domain": "arbeidsrett"},

    # ── ARSREGNSKAP ──────────────────────────────────────────────────

    "regnskapsloven": {"id": "LOV-1998-07-17-56", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om årsregnskap mv.": {"id": "LOV-1998-07-17-56", "domain": "arsregnskap_og_selskapsrapportering"},

    "bokføringsloven": {"id": "LOV-2004-11-19-73", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om bokføring": {"id": "LOV-2004-11-19-73", "domain": "arsregnskap_og_selskapsrapportering"},

    "revisorloven": {"id": "LOV-2020-11-20-128", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om revisjon og revisorer": {"id": "LOV-2020-11-20-128", "domain": "arsregnskap_og_selskapsrapportering"},

    "regnskapsførerloven": {"id": "LOV-2022-12-16-90", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om regnskapsførere": {"id": "LOV-2022-12-16-90", "domain": "arsregnskap_og_selskapsrapportering"},

    "lov om endringer i regnskapsloven mv.": {"id": "LOV-2024-06-21-42", "domain": "arsregnskap_og_selskapsrapportering"},

    "riksrevisjonsloven": {"id": "LOV-2024-12-13-77", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om riksrevisjonen": {"id": "LOV-2024-12-13-77", "domain": "arsregnskap_og_selskapsrapportering"},

    # Arsregnskap — forskrifter
    "forskrift om årsregnskap og årsberetning": {"id": "FORSKRIFT-2005-06-30-745", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om bokføring": {"id": "FORSKRIFT-2004-12-01-1558", "domain": "arsregnskap_og_selskapsrapportering"},
    "verdipapirforskriften": {"id": "FORSKRIFT-2007-06-29-876", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om revisjon og revisorer": {"id": "FORSKRIFT-2020-12-18-2988", "domain": "arsregnskap_og_selskapsrapportering"},
    "regnskapsførerforskriften": {"id": "FORSKRIFT-2022-12-16-2270", "domain": "arsregnskap_og_selskapsrapportering"},
    "økonomiforskrift til barnehageloven": {"id": "FORSKRIFT-2022-12-16-2322", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om forenklet anvendelse av internasjonale regnskapsstandarder": {"id": "FORSKRIFT-2022-02-07-182", "domain": "arsregnskap_og_selskapsrapportering"},
    "budsjett- og regnskapsforskriften for kommuner og fylkeskommuner mv.": {"id": "FORSKRIFT-2019-06-07-714", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om kontrollutvalg og revisjon": {"id": "FORSKRIFT-2019-06-17-904", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om private universiteter, høyskoler og fagskoler – krav til regnskap": {"id": "FORSKRIFT-2017-12-21-2383", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om retningslinjer og rapport": {"id": "FORSKRIFT-2020-12-11-2730", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om økonomiforvaltningen i sokn i den norske kirke": {"id": "FORSKRIFT-2020-12-08-2646", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om taksering av formues-, inntekts- og fradragsposter mv.": {"id": "FORSKRIFT-2024-11-28-2903", "domain": "arsregnskap_og_selskapsrapportering"},

    # ── AVTALERETT ───────────────────────────────────────────────────

    "avtaleloven": {"id": "LOV-1918-05-31-4", "domain": "avtalerett"},
    "lov om avslutning av avtaler, om fuldmagt og om ugyldige viljeserklæringer": {"id": "LOV-1918-05-31-4", "domain": "avtalerett"},

    "kjøpsloven": {"id": "LOV-1988-05-13-27", "domain": "avtalerett"},
    "lov om kjøp": {"id": "LOV-1988-05-13-27", "domain": "avtalerett"},

    "forbrukerkjøpsloven": {"id": "LOV-2002-06-21-34", "domain": "avtalerett"},
    "lov om forbrukerkjøp": {"id": "LOV-2002-06-21-34", "domain": "avtalerett"},

    "ehandelsloven": {"id": "LOV-2003-05-23-35", "domain": "avtalerett"},
    "lov om visse sider av elektronisk handel og andre informasjonssamfunnstjenester": {"id": "LOV-2003-05-23-35", "domain": "avtalerett"},

    "angrerettloven": {"id": "LOV-2014-06-20-27", "domain": "avtalerett"},
    "lov om opplysningsplikt og angrerett ved fjernsalg og salg utenom faste forretningslokaler": {"id": "LOV-2014-06-20-27", "domain": "avtalerett"},

    "digitalytelsesloven": {"id": "LOV-2022-06-17-56", "domain": "avtalerett"},
    "lov om levering av digitale ytelser til forbrukere": {"id": "LOV-2022-06-17-56", "domain": "avtalerett"},

    "bokloven": {"id": "LOV-2023-06-16-64", "domain": "avtalerett"},
    "lov om omsetning av bøker": {"id": "LOV-2023-06-16-64", "domain": "avtalerett"},

    "finansavtaleloven": {"id": "LOV-2020-12-18-146", "domain": "avtalerett"},
    "lov om finansavtaler": {"id": "LOV-2020-12-18-146", "domain": "avtalerett"},

    "tidspartloven": {"id": "LOV-2012-05-25-27", "domain": "avtalerett"},
    "lov om avtaler om deltidsbruksrett og langtidsferieprodukter mv.": {"id": "LOV-2012-05-25-27", "domain": "avtalerett"},

    "markedsføringsloven": {"id": "LOV-2009-01-09-2", "domain": "avtalerett"},
    "lov om kontroll med markedsføring og avtalevilkår mv.": {"id": "LOV-2009-01-09-2", "domain": "avtalerett"},

    # Avtalerett — forskrifter
    "anskaffelsesforskriften": {"id": "FORSKRIFT-2016-08-12-974", "domain": "avtalerett"},
    "forskrift om offentlige anskaffelser": {"id": "FORSKRIFT-2016-08-12-974", "domain": "avtalerett"},
    "forsikringsavtaleforskriften": {"id": "FORSKRIFT-2022-03-04-323", "domain": "avtalerett"},
    "forskrift om forsikringsavtaler": {"id": "FORSKRIFT-2022-03-04-323", "domain": "avtalerett"},
    "forskrift om standard opplysningsskjemaer": {"id": "FORSKRIFT-2012-07-03-766", "domain": "avtalerett"},
    "forskrift om urimelig handelspraksis": {"id": "FORSKRIFT-2009-06-01-565", "domain": "avtalerett"},
    "forskrift om elektronisk faktura i offentlige anskaffelser": {"id": "FORSKRIFT-2019-04-01-444", "domain": "avtalerett"},

    # ── INKASSO OG TVANGSFULLBYRDELSE ────────────────────────────────

    "inkassoloven": {"id": "LOV-1988-05-13-26", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om inkassovirksomhet og annen inndriving av forfalte pengekrav": {"id": "LOV-1988-05-13-26", "domain": "inkasso_og_tvangsfullbyrdelse"},

    "tvangsfullbyrdelsesloven": {"id": "LOV-1992-06-26-86", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om tvangsfullbyrdelse": {"id": "LOV-1992-06-26-86", "domain": "inkasso_og_tvangsfullbyrdelse"},

    "bidragsinnkrevingsloven": {"id": "LOV-2005-04-29-20", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om innkreving av underholdsbidrag mv.": {"id": "LOV-2005-04-29-20", "domain": "inkasso_og_tvangsfullbyrdelse"},

    "si-loven": {"id": "LOV-2013-01-11-3", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om statens innkrevingssentral": {"id": "LOV-2013-01-11-3", "domain": "inkasso_og_tvangsfullbyrdelse"},

    "innkrevingsloven": {"id": "LOV-2025-04-25-12", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om innkreving av statlige krav mv.": {"id": "LOV-2025-04-25-12", "domain": "inkasso_og_tvangsfullbyrdelse"},

    "lov om endringer i gjeldsordningsloven mv.": {"id": "LOV-2024-06-25-56", "domain": "inkasso_og_tvangsfullbyrdelse"},

    # Inkasso — forskrifter
    "inkassoforskriften": {"id": "FORSKRIFT-1989-12-14-1153", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift til inkassoloven m.m.": {"id": "FORSKRIFT-1989-12-14-1153", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift til inkassoloven m.m. (inkassoforskriften)": {"id": "FORSKRIFT-1989-12-14-1153", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift til inkassoloven": {"id": "FORSKRIFT-1989-12-14-1153", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om kjøpers renteplikt": {"id": "FORSKRIFT-2000-04-28-368", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om inkassosatsen": {"id": "FORSKRIFT-2002-12-13-1641", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "utleggsregistreringsforskriften": {"id": "FORSKRIFT-2008-02-19-158", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om utvidet registrering av utleggsforretninger": {"id": "FORSKRIFT-2008-02-19-158", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om elektronisk kommunikasjon med namsmannen og statens innkrevingssentral": {"id": "FORSKRIFT-2010-06-25-977", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "si-forskriften": {"id": "FORSKRIFT-2013-06-01-565", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om livsoppholdssatser": {"id": "FORSKRIFT-2014-06-13-724", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om saksøktes ansvar": {"id": "FORSKRIFT-2020-10-23-2120", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om fakturering av kredittkortgjeld mv.": {"id": "FORSKRIFT-2017-04-04-427", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om utmåling av tvangsmulkt og overtredelsesgebyr": {"id": "FORSKRIFT-2023-02-14-193", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om innkreving og regnskapsmessig behandling av uerholdelige bidragskrav": {"id": "FORSKRIFT-2001-01-09-18", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om bidragsinnkrevingslovens anvendelsesområde": {"id": "FORSKRIFT-2018-03-21-388", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om adgang til å kreve gebyr og sektoravgift": {"id": "FORSKRIFT-2013-01-08-16", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om innkrevingsforskriften": {"id": "FORSKRIFT-2025-12-11-2494", "domain": "inkasso_og_tvangsfullbyrdelse"},

    # ── KONKURSRETT OG INSOLVENS ─────────────────────────────────────

    "konkursloven": {"id": "LOV-1984-06-08-58", "domain": "konkursrett_og_insolvens"},
    "lov om gjeldsforhandling og konkurs": {"id": "LOV-1984-06-08-58", "domain": "konkursrett_og_insolvens"},

    "dekningsloven": {"id": "LOV-1984-06-08-59", "domain": "konkursrett_og_insolvens"},
    "lov om fordringshavernes dekningsrett": {"id": "LOV-1984-06-08-59", "domain": "konkursrett_og_insolvens"},

    "rekonstruksjonsloven": {"id": "LOV-2020-05-07-38", "domain": "konkursrett_og_insolvens"},
    "lov om rekonstruksjon": {"id": "LOV-2020-05-07-38", "domain": "konkursrett_og_insolvens"},

    "gjeldsordningsloven": {"id": "LOV-1992-07-17-99", "domain": "konkursrett_og_insolvens"},
    "lov om frivillig og tvungen gjeldsordning for privatpersoner": {"id": "LOV-1992-07-17-99", "domain": "konkursrett_og_insolvens"},

    # Konkurs — forskrifter
    "forskrift om overgangsbestemmelser til gjeldsordningsloven": {"id": "FORSKRIFT-2003-04-04-432", "domain": "konkursrett_og_insolvens"},
    "nedsettelsesforskriften": {"id": "FORSKRIFT-2016-06-17-713", "domain": "konkursrett_og_insolvens"},
    "forskrift om nedsettelse av renter": {"id": "FORSKRIFT-2016-06-17-713", "domain": "konkursrett_og_insolvens"},
    "forskrift om midlertidig unntak fra prioritetsreglene under rekonstruksjon": {"id": "FORSKRIFT-2020-05-11-974", "domain": "konkursrett_og_insolvens"},
    "forskrift om minimumsavdrag på lån": {"id": "FORSKRIFT-2024-09-27-2348", "domain": "konkursrett_og_insolvens"},

    # ── MANDA / FUSJON / FISJON ──────────────────────────────────────

    "aksjeloven": {"id": "LOV-1997-06-13-44", "domain": "manda_fusjon_fisjon"},
    "lov om aksjeselskaper": {"id": "LOV-1997-06-13-44", "domain": "manda_fusjon_fisjon"},

    "allmennaksjeloven": {"id": "LOV-1997-06-13-45", "domain": "manda_fusjon_fisjon"},
    "lov om allmennaksjeselskaper": {"id": "LOV-1997-06-13-45", "domain": "manda_fusjon_fisjon"},

    "foretaksregisterloven": {"id": "LOV-1985-06-21-78", "domain": "manda_fusjon_fisjon"},
    "lov om foretaksregisteret": {"id": "LOV-1985-06-21-78", "domain": "manda_fusjon_fisjon"},

    "selskapsloven": {"id": "LOV-1985-06-21-83", "domain": "manda_fusjon_fisjon"},
    "lov om ansvarlige selskaper og kommandittselskaper": {"id": "LOV-1985-06-21-83", "domain": "manda_fusjon_fisjon"},

    "anskaffelsesloven": {"id": "LOV-2016-06-17-73", "domain": "manda_fusjon_fisjon"},
    "lov om offentlige anskaffelser": {"id": "LOV-2016-06-17-73", "domain": "manda_fusjon_fisjon"},

    "samvirkelova": {"id": "LOV-2007-06-29-81", "domain": "manda_fusjon_fisjon"},
    "lov om samvirkeforetak": {"id": "LOV-2007-06-29-81", "domain": "manda_fusjon_fisjon"},

    # Manda — forskrifter
    "forskrift om melding av foretakssammenslutninger mv.": {"id": "FORSKRIFT-2013-12-11-1466", "domain": "manda_fusjon_fisjon"},

    # ── OBLIGASJONSRETT ──────────────────────────────────────────────

    "husleieloven": {"id": "LOV-1999-03-26-17", "domain": "obligasjonsrett"},
    "lov om husleieavtaler": {"id": "LOV-1999-03-26-17", "domain": "obligasjonsrett"},

    "voldserstatningsloven": {"id": "LOV-2022-06-17-57", "domain": "obligasjonsrett"},
    "lov om erstatning fra staten til voldsutsatte": {"id": "LOV-2022-06-17-57", "domain": "obligasjonsrett"},

    # ── PANTERETT OG SIKKERHETSRETT ──────────────────────────────────

    "panteloven": {"id": "LOV-1980-02-08-2", "domain": "panterett_og_sikkerhetsrett"},
    "lov om pant": {"id": "LOV-1980-02-08-2", "domain": "panterett_og_sikkerhetsrett"},

    "tinglysingsloven": {"id": "LOV-1935-03-07-2", "domain": "panterett_og_sikkerhetsrett"},
    "lov om tinglysing": {"id": "LOV-1935-03-07-2", "domain": "panterett_og_sikkerhetsrett"},

    "lov om finansiell sikkerhetsstillelse": {"id": "LOV-2004-03-26-17", "domain": "panterett_og_sikkerhetsrett"},

    "lov om internasjonale sikkerhetsretter i mobilt løsøre": {"id": "LOV-2010-11-12-58", "domain": "panterett_og_sikkerhetsrett"},

    "matrikkellova": {"id": "LOV-2005-06-17-101", "domain": "panterett_og_sikkerhetsrett"},
    "lov om eigedomsregistrering": {"id": "LOV-2005-06-17-101", "domain": "panterett_og_sikkerhetsrett"},

    "eierseksjonsloven": {"id": "LOV-2017-06-16-65", "domain": "panterett_og_sikkerhetsrett"},
    "lov om eierseksjoner": {"id": "LOV-2017-06-16-65", "domain": "panterett_og_sikkerhetsrett"},

    "eiendomsmeglingsloven": {"id": "LOV-2007-06-29-73", "domain": "panterett_og_sikkerhetsrett"},
    "lov om eiendomsmegling": {"id": "LOV-2007-06-29-73", "domain": "panterett_og_sikkerhetsrett"},

    # Panterett — forskrifter
    "forskrift om tomtefeste m.m.": {"id": "FORSKRIFT-2001-06-08-570", "domain": "panterett_og_sikkerhetsrett"},
    "matrikkelforskriften": {"id": "FORSKRIFT-2009-06-26-864", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om eiendomsregistrering": {"id": "FORSKRIFT-2009-06-26-864", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om mortifikasjon av skuldbrev": {"id": "FORSKRIFT-2008-06-20-620", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om rettsvern": {"id": "FORSKRIFT-2011-02-11-133", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om sikkerhetsstillelse": {"id": "FORSKRIFT-2017-12-19-2293", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om eiendomsregistrering på svalbard": {"id": "FORSKRIFT-2021-12-17-3633", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om rett til å kreve seksjonering etter eierseksjonsloven § 9": {"id": "FORSKRIFT-2018-06-18-921", "domain": "panterett_og_sikkerhetsrett"},

    # ── PENGEKRAVSRETT ───────────────────────────────────────────────

    "forsinkelsesrenteloven": {"id": "LOV-1976-12-17-100", "domain": "pengekravsrett_fordringer"},
    "lov om renter ved forsinket betaling m.m.": {"id": "LOV-1976-12-17-100", "domain": "pengekravsrett_fordringer"},

    "gjeldsbrevloven": {"id": "LOV-1939-02-17-1", "domain": "pengekravsrett_fordringer"},
    "lov om gjeldsbrev": {"id": "LOV-1939-02-17-1", "domain": "pengekravsrett_fordringer"},

    "løsørepantloven": {"id": "LOV-1854-02-03-1", "domain": "pengekravsrett_fordringer"},

    # Pengekravsrett — forskrifter
    "forskrift om rentesatser etter dekningsloven": {"id": "FORSKRIFT-2003-02-14-145", "domain": "pengekravsrett_fordringer"},
    "forskrift om rentesats etter ekteskapsloven": {"id": "FORSKRIFT-2007-02-13-164", "domain": "pengekravsrett_fordringer"},
    "forskrift om tilbaketrekking av betalingsmidler": {"id": "FORSKRIFT-2017-04-05-450", "domain": "pengekravsrett_fordringer"},
    "forskrift om avgrensning av tvungne betalingsmidler": {"id": "FORSKRIFT-2021-12-17-3771", "domain": "pengekravsrett_fordringer"},
    "forskrift om forsinkelsesrente og kompensasjon": {"id": "FORSKRIFT-2025-12-18-2658", "domain": "pengekravsrett_fordringer"},

    # ── PERSONVERN / GDPR ────────────────────────────────────────────

    "personopplysningsloven": {"id": "LOV-2018-06-15-38", "domain": "personvern_gdpr_business_compliance"},
    "lov om behandling av personopplysninger": {"id": "LOV-2018-06-15-38", "domain": "personvern_gdpr_business_compliance"},

    "helseregisterloven": {"id": "LOV-2014-06-20-43", "domain": "personvern_gdpr_business_compliance"},
    "lov om helseregistre og behandling av helseopplysninger": {"id": "LOV-2014-06-20-43", "domain": "personvern_gdpr_business_compliance"},

    "pasientjournalloven": {"id": "LOV-2014-06-20-42", "domain": "personvern_gdpr_business_compliance"},
    "lov om behandling av helseopplysninger ved ytelse av helsehjelp": {"id": "LOV-2014-06-20-42", "domain": "personvern_gdpr_business_compliance"},

    "politiregisterloven": {"id": "LOV-2010-05-28-16", "domain": "personvern_gdpr_business_compliance"},
    "lov om behandling av opplysninger i politiet og påtalemyndigheten": {"id": "LOV-2010-05-28-16", "domain": "personvern_gdpr_business_compliance"},

    "folkeregisterloven": {"id": "LOV-2016-12-09-88", "domain": "personvern_gdpr_business_compliance"},
    "lov om folkeregistrering": {"id": "LOV-2016-12-09-88", "domain": "personvern_gdpr_business_compliance"},

    "kredittopplysningsloven": {"id": "LOV-2019-12-20-109", "domain": "personvern_gdpr_business_compliance"},
    "lov om behandling av opplysninger i kredittopplysningsvirksomhet": {"id": "LOV-2019-12-20-109", "domain": "personvern_gdpr_business_compliance"},

    "digitalsikkerhetsloven": {"id": "LOV-2023-12-20-108", "domain": "personvern_gdpr_business_compliance"},
    "lov om digital sikkerhet": {"id": "LOV-2023-12-20-108", "domain": "personvern_gdpr_business_compliance"},

    "forretningshemmelighetsloven": {"id": "LOV-2020-03-27-15", "domain": "personvern_gdpr_business_compliance"},
    "lov om vern av forretningshemmeligheter": {"id": "LOV-2020-03-27-15", "domain": "personvern_gdpr_business_compliance"},

    "gjeldsinformasjonsloven": {"id": "LOV-2017-06-16-47", "domain": "personvern_gdpr_business_compliance"},
    "lov om gjeldsinformasjon ved kredittvurdering av privatpersoner": {"id": "LOV-2017-06-16-47", "domain": "personvern_gdpr_business_compliance"},

    # Personvern — forskrifter
    "ehandelsforskriften": {"id": "FORSKRIFT-2003-06-12-744", "domain": "personvern_gdpr_business_compliance"},
    "eforvaltningsforskriften": {"id": "FORSKRIFT-2004-06-25-988", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om elektronisk kommunikasjon med og i forvaltningen": {"id": "FORSKRIFT-2004-06-25-988", "domain": "personvern_gdpr_business_compliance"},
    "nois-registerforskriften": {"id": "FORSKRIFT-2005-06-17-611", "domain": "personvern_gdpr_business_compliance"},
    "sysvak-registerforskriften": {"id": "FORSKRIFT-2003-06-20-739", "domain": "personvern_gdpr_business_compliance"},
    "pasientjournalforskriften": {"id": "FORSKRIFT-2019-03-01-168", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om behandling av personopplysninger": {"id": "FORSKRIFT-2018-06-15-876", "domain": "personvern_gdpr_business_compliance"},
    "overgangsregler om behandling av personopplysninger": {"id": "FORSKRIFT-2018-06-15-877", "domain": "personvern_gdpr_business_compliance"},
    "kredittopplysningsforskriften": {"id": "FORSKRIFT-2022-05-20-883", "domain": "personvern_gdpr_business_compliance"},
    "kunnskapsbankforskriften": {"id": "FORSKRIFT-2022-06-01-954", "domain": "personvern_gdpr_business_compliance"},
    "partilovforskriften": {"id": "FORSKRIFT-2014-02-05-107", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om medisinske kvalitetsregistre": {"id": "FORSKRIFT-2019-06-21-789", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om pseudonymt register": {"id": "FORSKRIFT-2006-02-17-204", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om reservasjonsregisteret": {"id": "FORSKRIFT-2009-06-05-598", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om nasjonalt register": {"id": "FORSKRIFT-2022-01-25-120", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om digitaliseringsdirektoratets tilgang til taushetsbelagte opplysninger": {"id": "FORSKRIFT-2023-06-20-955", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om behandling av personopplysninger i lånekassen": {"id": "FORSKRIFT-2021-12-17-3713", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om etikkrådets og norges banks behandling av personopplysninger": {"id": "FORSKRIFT-2019-06-27-924", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om datasenter": {"id": "FORSKRIFT-2024-12-18-3313", "domain": "personvern_gdpr_business_compliance"},
    "ekomforskriften": {"id": "FORSKRIFT-2024-12-20-3410", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om elektroniske kommunikasjonsnett og elektroniske kommunikasjonstjenester": {"id": "FORSKRIFT-2024-12-20-3410", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om bruk av informasjons- og kommunikasjonsteknologi": {"id": "FORSKRIFT-2003-05-21-630", "domain": "personvern_gdpr_business_compliance"},

    # ── SELSKAPSRETT ─────────────────────────────────────────────────

    "stiftelsesloven": {"id": "LOV-2001-06-15-59", "domain": "selskapsrett"},
    "lov om stiftelser": {"id": "LOV-2001-06-15-59", "domain": "selskapsrett"},

    "prokuraloven": {"id": "LOV-1985-06-21-80", "domain": "selskapsrett"},
    "lov om prokura": {"id": "LOV-1985-06-21-80", "domain": "selskapsrett"},

    "bustadbyggjelagslova": {"id": "LOV-2003-06-06-38", "domain": "selskapsrett"},
    "lov om bustadbyggjelag": {"id": "LOV-2003-06-06-38", "domain": "selskapsrett"},

    "burettslagslova": {"id": "LOV-2003-06-06-39", "domain": "selskapsrett"},
    "lov om burettslag": {"id": "LOV-2003-06-06-39", "domain": "selskapsrett"},

    "helseforetaksloven": {"id": "LOV-2001-06-15-93", "domain": "selskapsrett"},
    "lov om helseforetak m.m.": {"id": "LOV-2001-06-15-93", "domain": "selskapsrett"},

    "finansforetaksloven": {"id": "LOV-2015-04-10-17", "domain": "selskapsrett"},
    "lov om finansforetak og finanskonsern": {"id": "LOV-2015-04-10-17", "domain": "selskapsrett"},

    "verdipapirhandelloven": {"id": "LOV-2007-06-29-75", "domain": "selskapsrett"},
    "lov om verdipapirhandel": {"id": "LOV-2007-06-29-75", "domain": "selskapsrett"},

    "verdipapirfondloven": {"id": "LOV-2011-11-25-44", "domain": "selskapsrett"},
    "lov om verdipapirfond": {"id": "LOV-2011-11-25-44", "domain": "selskapsrett"},

    "børsloven": {"id": "LOV-2019-03-15-6", "domain": "selskapsrett"},
    "verdipapirsentralloven": {"id": "LOV-2019-03-15-6", "domain": "selskapsrett"},
    "lov om verdipapirsentraler og verdipapiroppgjør mv.": {"id": "LOV-2019-03-15-6", "domain": "selskapsrett"},

    "innskuddspensjonsloven": {"id": "LOV-2000-11-24-81", "domain": "selskapsrett"},
    "lov om innskuddspensjon i arbeidsforhold": {"id": "LOV-2000-11-24-81", "domain": "selskapsrett"},

    "studentsamskipnadsloven": {"id": "LOV-2007-12-14-116", "domain": "selskapsrett"},
    "lov om studentsamskipnader": {"id": "LOV-2007-12-14-116", "domain": "selskapsrett"},

    "lov om register over reelle rettighetshavere": {"id": "LOV-2019-03-01-2", "domain": "selskapsrett"},

    "suppleringsskatteloven": {"id": "LOV-2024-01-12-1", "domain": "selskapsrett"},
    "lov om suppleringsskatt på underbeskattet inntekt i konsern": {"id": "LOV-2024-01-12-1", "domain": "selskapsrett"},

    "karanteneloven": {"id": "LOV-2015-06-19-70", "domain": "selskapsrett"},
    "lov om informasjonsplikt, karantene og saksforbud for politikere, embetsmenn og tjenestemenn": {"id": "LOV-2015-06-19-70", "domain": "selskapsrett"},

    "konfliktrådsloven": {"id": "LOV-2014-06-20-49", "domain": "selskapsrett"},
    "lov om konfliktrådsbehandling": {"id": "LOV-2014-06-20-49", "domain": "selskapsrett"},

    "enhetsregisterloven": {"id": "LOV-2025-06-20-105", "domain": "selskapsrett"},
    "lov om enhetsregisteret": {"id": "LOV-2025-06-20-105", "domain": "selskapsrett"},

    "foretaksregisterloven 2025": {"id": "LOV-2025-06-20-106", "domain": "selskapsrett"},
    "lov om foretaksregisteret 2025": {"id": "LOV-2025-06-20-106", "domain": "selskapsrett"},

    "representantytelsesloven": {"id": "LOV-2025-06-20-57", "domain": "selskapsrett"},
    "lov om godtgjøring og andre ytelser til stortingsrepresentanter": {"id": "LOV-2025-06-20-57", "domain": "selskapsrett"},

    # Selskapsrett — forskrifter
    "forskrift om kontrollkomité": {"id": "FORSKRIFT-2003-01-31-86", "domain": "selskapsrett"},
    "forskrift om studentsamskipnader": {"id": "FORSKRIFT-2008-07-22-828", "domain": "selskapsrett"},
    "forskrift om statens finansfond": {"id": "FORSKRIFT-2009-05-08-495", "domain": "selskapsrett"},
    "forskrift om selskapets opplysningsplikt før og etter generalforsamlingen": {"id": "FORSKRIFT-2009-07-06-983", "domain": "selskapsrett"},
    "forskrift om registrering og offentleggjering av mellombalansar": {"id": "FORSKRIFT-2020-10-24-2199", "domain": "selskapsrett"},
    "forskrift om aksjeselskapers og allmennaksjeselskapers adgang til å yte finansiell bistand": {"id": "FORSKRIFT-2019-12-09-1698", "domain": "selskapsrett"},
    "forskrift om innsyn i aksjeeierboken": {"id": "FORSKRIFT-2024-11-17-2804", "domain": "selskapsrett"},
    "forskrift om elektronisk stiftelse og registrering av aksjeselskaper": {"id": "FORSKRIFT-2023-12-22-2310", "domain": "selskapsrett"},

    # ── TVISTELOSNING SMB ────────────────────────────────────────────

    "tvisteloven": {"id": "LOV-2005-06-17-90", "domain": "tvistelosning_smb"},
    "lov om mekling og rettergang i sivile tvister": {"id": "LOV-2005-06-17-90", "domain": "tvistelosning_smb"},

    "voldgiftsloven": {"id": "LOV-2004-05-14-25", "domain": "tvistelosning_smb"},
    "lov om voldgift": {"id": "LOV-2004-05-14-25", "domain": "tvistelosning_smb"},

    # Tvistelosning — forskrifter
    "forskrift om tvistebehandling på norske skip": {"id": "FORSKRIFT-2002-04-25-424", "domain": "tvistelosning_smb"},
    "forskrift om løsning av tvister mellom arbeidstaker og arbeidsgiver": {"id": "FORSKRIFT-2007-03-12-294", "domain": "tvistelosning_smb"},
    "forskrift om konfliktrådsbehandling": {"id": "FORSKRIFT-2014-06-30-923", "domain": "tvistelosning_smb"},
    "forskrift om husleietvistutvalget": {"id": "FORSKRIFT-2016-06-21-765", "domain": "tvistelosning_smb"},
    "overgangsregler til lov 11. mai 2023 nr. 13": {"id": "FORSKRIFT-2023-06-02-779", "domain": "tvistelosning_smb"},
    "overgangsregler til tvisteloven": {"id": "FORSKRIFT-2023-06-02-779", "domain": "tvistelosning_smb"},

    # ── EVAL ROUND 2 ADDITIONS — all 95 laws missing from registry ───────

    # arbeidsrett — forskrifter
    "forskrift om arbeid som utføres i arbeidstakers hjem": {"id": "FORSKRIFT-2002-07-05-715", "domain": "arbeidsrett"},
    "hjemmearbeidsforskriften": {"id": "FORSKRIFT-2002-07-05-715", "domain": "arbeidsrett"},
    "forskrift om overføring av forhandlingsansvaret": {"id": "FORSKRIFT-2003-01-31-90", "domain": "arbeidsrett"},
    "forskrift om helse og sikkerhet i eksplosjonsfarlige atmosfærer": {"id": "FORSKRIFT-2003-06-30-911", "domain": "arbeidsrett"},
    "atex-forskriften": {"id": "FORSKRIFT-2003-06-30-911", "domain": "arbeidsrett"},
    "forskrift om arbeidsmiljø, sikkerhet og helse for dem som arbeider om bord på skip": {"id": "FORSKRIFT-2005-01-01-8", "domain": "arbeidsrett"},
    "forskrift om arbeidsmiljø, sikkerhet og helse": {"id": "FORSKRIFT-2005-01-01-8", "domain": "arbeidsrett"},
    "forskrift om garanti for arbeidsvederlag og hjemreise for arbeidstakere på utenlandske skip": {"id": "FORSKRIFT-2005-02-18-146", "domain": "arbeidsrett"},
    "forskrift om garanti for arbeidsvederlag": {"id": "FORSKRIFT-2005-02-18-146", "domain": "arbeidsrett"},
    "forskrift om arbeidstakernes rett til innflytelse i europeiske selskaper": {"id": "FORSKRIFT-2005-04-01-273", "domain": "arbeidsrett"},
    "forskrift om arbeidstid for sjåfører og andre innenfor vegtransport": {"id": "FORSKRIFT-2005-06-10-543", "domain": "arbeidsrett"},
    "sjåfør-arbeidstidsforskriften": {"id": "FORSKRIFT-2005-06-10-543", "domain": "arbeidsrett"},
    "forskrift om arbeidstid i institusjoner som har medleverordninger": {"id": "FORSKRIFT-2005-06-24-686", "domain": "arbeidsrett"},
    "medleverforskriften": {"id": "FORSKRIFT-2005-06-24-686", "domain": "arbeidsrett"},
    "forskrift om unntak fra lov 10. desember 2004 nr. 76 om arbeidsmarkedstjenester": {"id": "FORSKRIFT-2005-08-12-893", "domain": "arbeidsrett"},
    "vedtak om at midlertidig forskrift 19. desember 2003": {"id": "FORSKRIFT-2006-03-03-394", "domain": "arbeidsrett"},
    "vedtak om midlertidig forskrift 2003": {"id": "FORSKRIFT-2006-03-03-394", "domain": "arbeidsrett"},
    "forskrift om innskuddspensjonsordninger som skal oppfylle minstekravene": {"id": "FORSKRIFT-2006-06-30-870", "domain": "arbeidsrett"},
    "innskuddspensjonsforskriften minstekrav": {"id": "FORSKRIFT-2006-06-30-870", "domain": "arbeidsrett"},
    "forskrift om overgangsbestemmelser til lov om angrerett": {"id": "FORSKRIFT-2006-06-30-874", "domain": "avtalerett"},
    "overgangsbestemmelser angrerett": {"id": "FORSKRIFT-2006-06-30-874", "domain": "avtalerett"},
    "forskrift om løsning av tvister mellom arbeids- og velferdsetaten og kommunene": {"id": "FORSKRIFT-2007-03-12-294", "domain": "tvistelosning_smb"},
    "tvisteforskriften nav og kommunene": {"id": "FORSKRIFT-2007-03-12-294", "domain": "tvistelosning_smb"},
    "forskrift om arbeids- og hviletid på norske passasjer- og lasteskip mv.": {"id": "FORSKRIFT-2007-06-26-705", "domain": "arbeidsrett"},
    "hviletidsforskriften skip": {"id": "FORSKRIFT-2007-06-26-705", "domain": "arbeidsrett"},
    "forskrift om overgangsregler til lov 29. juni 2007 nr. 74 om regulerte markeder": {"id": "FORSKRIFT-2007-06-29-750", "domain": "selskapsrett"},
    "overgangsregler børsloven 2007": {"id": "FORSKRIFT-2007-06-29-750", "domain": "selskapsrett"},
    "vedtak om at midlertidig forskrift 19. desember 2003 nr. 1595 videreføres": {"id": "FORSKRIFT-2008-06-02-526", "domain": "arbeidsrett"},
    "vedtak videreføring midlertidig forskrift 2008": {"id": "FORSKRIFT-2008-06-02-526", "domain": "arbeidsrett"},
    "forskrift om arbeidstid mv. for arbeidstakere i grensekryssende interoperabel jernbanedrift": {"id": "FORSKRIFT-2008-07-03-783", "domain": "arbeidsrett"},
    "jernbane arbeidstidsforskriften": {"id": "FORSKRIFT-2008-07-03-783", "domain": "arbeidsrett"},
    "forskrift om politiattest i henhold til arbeidsmarkedsloven": {"id": "FORSKRIFT-2012-03-23-248", "domain": "arbeidsrett"},
    "politiattestforskriften arbeidsmarked": {"id": "FORSKRIFT-2012-03-23-248", "domain": "arbeidsrett"},
    "forskrift om overgangsregler til lov 22. juni 2012 nr. 35 om endringer i regnskapsloven": {"id": "FORSKRIFT-2012-06-22-568", "domain": "arsregnskap_og_selskapsrapportering"},
    "overgangsregler regnskapsloven 2012": {"id": "FORSKRIFT-2012-06-22-568", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om rammeplan for bachelor i regnskap og revisjon": {"id": "FORSKRIFT-2012-06-27-687", "domain": "arsregnskap_og_selskapsrapportering"},
    "rammeplan regnskap og revisjon": {"id": "FORSKRIFT-2012-06-27-687", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om standard opplysningsskjemaer etter lov om tidspartavtaler": {"id": "FORSKRIFT-2012-07-03-766", "domain": "avtalerett"},
    "tidspartavtaleforskriften skjemaer": {"id": "FORSKRIFT-2012-07-03-766", "domain": "avtalerett"},
    "forskrift om endringer i personopplysningsforskriften": {"id": "FORSKRIFT-2013-08-09-970", "domain": "personvern_gdpr_business_compliance"},
    "personopplysningsforskriften endringer": {"id": "FORSKRIFT-2013-08-09-970", "domain": "personvern_gdpr_business_compliance"},
    "overgangsregler til lov 11. april 2014 nr. 12 om finansforetak": {"id": "FORSKRIFT-2014-05-06-608", "domain": "panterett_og_sikkerhetsrett"},
    "overgangsregler finansforetaksloven 2014": {"id": "FORSKRIFT-2014-05-06-608", "domain": "panterett_og_sikkerhetsrett"},
    "forskrift om stønad til arbeids- og utdanningsreiser": {"id": "FORSKRIFT-2014-05-16-648", "domain": "arbeidsrett"},
    "reisestønadforskriften": {"id": "FORSKRIFT-2014-05-16-648", "domain": "arbeidsrett"},
    "forskrift om utmelding fra pensjonsordning for apotekvirksomhet": {"id": "FORSKRIFT-2014-05-20-663", "domain": "arbeidsrett"},
    "utmeldingsforskriften apotekpensjon": {"id": "FORSKRIFT-2014-05-20-663", "domain": "arbeidsrett"},
    "forskrift om helseundersøkelse av arbeidstakere på norske skip og flyttbare innretninger": {"id": "FORSKRIFT-2014-06-05-805", "domain": "arbeidsrett"},
    "helseundersøkelsesforskriften skip": {"id": "FORSKRIFT-2014-06-05-805", "domain": "arbeidsrett"},
    "forskrift om tilsyn med ordninger for avtalefestet pensjon": {"id": "FORSKRIFT-2014-06-18-837", "domain": "arbeidsrett"},
    "afp-tilsynsforskriften": {"id": "FORSKRIFT-2014-06-18-837", "domain": "arbeidsrett"},
    "forskrift om adgang til ved tariffavtale å fravike reglene om arbeidstid": {"id": "FORSKRIFT-2015-07-06-874", "domain": "arbeidsrett"},
    "tariffunntaksforskriften arbeidstid": {"id": "FORSKRIFT-2015-07-06-874", "domain": "arbeidsrett"},
    "vedtak om fastsettelse av renter for beskatning av naturressurser": {"id": "FORSKRIFT-2016-01-26-59", "domain": "arsregnskap_og_selskapsrapportering"},
    "naturressursrentevedtaket": {"id": "FORSKRIFT-2016-01-26-59", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om beregning av kapitalavkastning i livsforsikrings- og pensjonsforetak": {"id": "FORSKRIFT-2017-01-06-10", "domain": "arsregnskap_og_selskapsrapportering"},
    "kapitalavkastningsforskriften": {"id": "FORSKRIFT-2017-01-06-10", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift til lov om statens ansatte mv. om arbeidstid": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},
    "forskrift til statsansatteloven": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},
    "statsansatterforskriften arbeidstid": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},
    "forskrift om pensjonsgrunnlag i pensjonsordning for apotekvirksomhet": {"id": "FORSKRIFT-2017-12-20-2306", "domain": "arbeidsrett"},
    "apotekpensjonsforskriften": {"id": "FORSKRIFT-2017-12-20-2306", "domain": "arbeidsrett"},
    "forskrift om forsøk med å gi kommunen ansvar for å arrangere tilrettelagt videregående opplæring": {"id": "FORSKRIFT-2017-12-20-2308", "domain": "arbeidsrett"},
    "forsøksforskriften videregående": {"id": "FORSKRIFT-2017-12-20-2308", "domain": "arbeidsrett"},
    "forskrift om terskelverdier for beslutning om å revidere": {"id": "FORSKRIFT-2018-01-03-7", "domain": "arsregnskap_og_selskapsrapportering"},
    "terskelverdiforskriften revisjon": {"id": "FORSKRIFT-2018-01-03-7", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om arbeids- og velferdsetatens tilgang til opplysninger fra innkrevingssentralen": {"id": "FORSKRIFT-2018-03-13-340", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "nav-tilgangsforskriften": {"id": "FORSKRIFT-2018-03-13-340", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om kontrolltiltak overfor arbeidstakere som er omfattet av lov om skipssikkerhet": {"id": "FORSKRIFT-2019-01-25-53", "domain": "arbeidsrett"},
    "kontrolltiltaksforskriften sjøfolk": {"id": "FORSKRIFT-2019-01-25-53", "domain": "arbeidsrett"},
    "forskrift om sikkerhet og arbeidsmiljø ved transport og injeksjon av co2": {"id": "FORSKRIFT-2020-02-25-186", "domain": "arbeidsrett"},
    "co2-sikkerhetsforskriften": {"id": "FORSKRIFT-2020-02-25-186", "domain": "arbeidsrett"},
    "forskrift om unntak fra taushetsplikt ved rapportering til helsemyndighetene": {"id": "FORSKRIFT-2020-03-19-351", "domain": "personvern_gdpr_business_compliance"},
    "taushetspliktunntak helserapportering": {"id": "FORSKRIFT-2020-03-19-351", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om virkningstidspunkt for bestemmelsene i kapittel 2 i midlertidig lov": {"id": "FORSKRIFT-2020-03-26-458", "domain": "arbeidsrett"},
    "virkningstidspunktforskriften 2020": {"id": "FORSKRIFT-2020-03-26-458", "domain": "arbeidsrett"},
    "forskrift om midlertidig unntak fra prioritetsreglene under rekonstruksjon etter midlertidig lov": {"id": "FORSKRIFT-2020-05-11-974", "domain": "konkursrett_og_insolvens"},
    "rekonstruksjonsforskriften prioritet": {"id": "FORSKRIFT-2020-05-11-974", "domain": "konkursrett_og_insolvens"},
    "forskrift om unntak i samordningsberegningen for inntekt": {"id": "FORSKRIFT-2020-12-04-2590", "domain": "arbeidsrett"},
    "samordningsberegningsforskriften": {"id": "FORSKRIFT-2020-12-04-2590", "domain": "arbeidsrett"},
    "forskrift om opplysningsplikt til den offisielle lønnsstatistikken": {"id": "FORSKRIFT-2020-12-14-2753", "domain": "arbeidsrett"},
    "lønnsstatistikkforskriften": {"id": "FORSKRIFT-2020-12-14-2753", "domain": "arbeidsrett"},
    "forskrift om endring i forskrift om tjeneste for militært tilsatte": {"id": "FORSKRIFT-2021-10-05-2947", "domain": "arbeidsrett"},
    "militærtjenesteforskriften endring 2021": {"id": "FORSKRIFT-2021-10-05-2947", "domain": "arbeidsrett"},
    "forskrift om den norske kirkes medlemsregister": {"id": "FORSKRIFT-2021-11-14-3326", "domain": "personvern_gdpr_business_compliance"},
    "kirkemedlemsregisterforskriften": {"id": "FORSKRIFT-2021-11-14-3326", "domain": "personvern_gdpr_business_compliance"},
    "overgangsregler til lov om endringer i arbeidsmiljøloven m.m.": {"id": "FORSKRIFT-2022-12-20-2301", "domain": "arbeidsrett"},
    "overgangsregler arbeidsmiljøloven 2022": {"id": "FORSKRIFT-2022-12-20-2301", "domain": "arbeidsrett"},
    "forskrift om endring i forskrift om terskelverdier for beslutning": {"id": "FORSKRIFT-2023-02-13-186", "domain": "arsregnskap_og_selskapsrapportering"},
    "terskelverdiforskriften endring 2023": {"id": "FORSKRIFT-2023-02-13-186", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift til utfylling og gjennomføring mv. av suppleringsskatteloven": {"id": "FORSKRIFT-2024-03-26-541", "domain": "arsregnskap_og_selskapsrapportering"},
    "suppleringsskatteforskriften": {"id": "FORSKRIFT-2024-03-26-541", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om delvis allmenngjøring av industrioverenskomsten/vo-delen": {"id": "FORSKRIFT-2024-10-21-2535", "domain": "arbeidsrett"},
    "industrioverenskomsten allmenngjøring vo": {"id": "FORSKRIFT-2024-10-21-2535", "domain": "arbeidsrett"},
    "forskrift om delvis allmenngjøring av landsoverenskomsten for elektrofagene": {"id": "FORSKRIFT-2024-10-21-2536", "domain": "arbeidsrett"},
    "landsoverenskomsten elektro allmenngjøring": {"id": "FORSKRIFT-2024-10-21-2536", "domain": "arbeidsrett"},
    "forskrift om delvis allmenngjøring av tariffavtaler for godstransport": {"id": "FORSKRIFT-2024-10-29-2601", "domain": "arbeidsrett"},
    "godstransportforskriften allmenngjøring": {"id": "FORSKRIFT-2024-10-29-2601", "domain": "arbeidsrett"},
    "forskrift om endring i forskrift om omregning av avtalefestet pensjon": {"id": "FORSKRIFT-2024-11-08-2702", "domain": "arbeidsrett"},
    "omregningsforskriften afp 2024": {"id": "FORSKRIFT-2024-11-08-2702", "domain": "arbeidsrett"},
    "forskrift om tilskot frå merkur-programmet": {"id": "FORSKRIFT-2024-11-21-2989", "domain": "arsregnskap_og_selskapsrapportering"},
    "merkurprogrammet forskrift": {"id": "FORSKRIFT-2024-11-21-2989", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om digitalt dødsbo": {"id": "FORSKRIFT-2024-12-19-3276", "domain": "personvern_gdpr_business_compliance"},
    "digitalt dødsbo": {"id": "FORSKRIFT-2024-12-19-3276", "domain": "personvern_gdpr_business_compliance"},
    "forskrift om tilskudd til partsstyrte bransjeprogrammer under avtale om inkluderende arbeidsliv": {"id": "FORSKRIFT-2025-02-04-118", "domain": "arbeidsrett"},
    "bransjeprogramforskriften ia": {"id": "FORSKRIFT-2025-02-04-118", "domain": "arbeidsrett"},
    "forskrift om aspiranter i kriminalomsorgen": {"id": "FORSKRIFT-2025-04-05-619", "domain": "arbeidsrett"},
    "aspirantforskriften kriminalomsorg": {"id": "FORSKRIFT-2025-04-05-619", "domain": "arbeidsrett"},
    "forskrift om endring i forskrift om rapportering fra kraftforetak": {"id": "FORSKRIFT-2025-10-29-2134", "domain": "arsregnskap_og_selskapsrapportering"},
    "kraftforetakrapporteringsforskriften 2025": {"id": "FORSKRIFT-2025-10-29-2134", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om endring i forskrift til stiftelsesloven": {"id": "FORSKRIFT-2025-11-14-2275", "domain": "selskapsrett"},
    "stiftelseslovforskriften endring 2025": {"id": "FORSKRIFT-2025-11-14-2275", "domain": "selskapsrett"},
    "forskrift om endring i forskrift om tilskudd til fiskerihavneanlegg": {"id": "FORSKRIFT-2025-12-04-2426", "domain": "arsregnskap_og_selskapsrapportering"},
    "fiskerihavnetilskuddsforskriften 2025": {"id": "FORSKRIFT-2025-12-04-2426", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om endring i forskrift om overgangsregler for innkrevingssentralen": {"id": "FORSKRIFT-2025-12-10-2487", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "innkrevingsforskriften overgangsregler 2025": {"id": "FORSKRIFT-2025-12-10-2487", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om endring i enkelte forskrifter under justis- og beredskapsdepartementet som følge av innkrevingsloven": {"id": "FORSKRIFT-2025-12-14-2558", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "justisforskriften innkrevingsloven 2025": {"id": "FORSKRIFT-2025-12-14-2558", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om endring i enkelte forskrifter som følge av ikraftsetting av lov om innkreving": {"id": "FORSKRIFT-2025-12-15-2561", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "ikraftsettingsforskriften innkrevingsloven": {"id": "FORSKRIFT-2025-12-15-2561", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "forskrift om endring i forskrift om utførelse av arbeid, bruk av arbeidsutstyr": {"id": "FORSKRIFT-2025-12-16-2615", "domain": "arbeidsrett"},
    "utførelsesforskriften arbeid 2025": {"id": "FORSKRIFT-2025-12-16-2615", "domain": "arbeidsrett"},
    "forskrift om endring i enkelte forskrifter som følge av endring i skipssikkerhetsloven": {"id": "FORSKRIFT-2025-12-16-2617", "domain": "arbeidsrett"},
    "skipssikkerhetsforskriften endring 2025": {"id": "FORSKRIFT-2025-12-16-2617", "domain": "arbeidsrett"},
    "tiltaksforskriften endring 2025": {"id": "FORSKRIFT-2025-12-18-2918", "domain": "arbeidsrett"},
    "forskrift om endring i forskrift om arbeidsmarkedstiltak": {"id": "FORSKRIFT-2025-12-18-2918", "domain": "arbeidsrett"},

    # LOV entries — missing from registry
    "lov om beskyttelse av supplerende pensjonsrettigheter for arbeidstakere": {"id": "LOV-2001-12-14-95", "domain": "arbeidsrett"},
    "supplerende pensjonsrettigheter": {"id": "LOV-2001-12-14-95", "domain": "arbeidsrett"},
    "lov om heleide dattersamvirkeforetak": {"id": "LOV-2003-12-12-109", "domain": "selskapsrett"},
    "dattersamvirkeforetaksloven": {"id": "LOV-2003-12-12-109", "domain": "selskapsrett"},
    "lov om innovasjon norge": {"id": "LOV-2003-12-19-130", "domain": "selskapsrett"},
    "innovasjon norgeloven": {"id": "LOV-2003-12-19-130", "domain": "selskapsrett"},
    "lov om omdanning av kystverkets produksjonsvirksomhet": {"id": "LOV-2004-12-17-90", "domain": "selskapsrett"},
    "kystverketomdanningsloven": {"id": "LOV-2004-12-17-90", "domain": "selskapsrett"},
    "skattebetalingsloven": {"id": "LOV-2005-06-17-67", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om betaling og innkreving av skatte- og avgiftskrav": {"id": "LOV-2005-06-17-67", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om endringar i lov 26. juni 1992 nr. 86 om tvangsfullbyrdelse": {"id": "LOV-2005-06-17-89", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "tvangsfullbyrdelsesloven endringer 2005": {"id": "LOV-2005-06-17-89", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om statens pensjonsfond": {"id": "LOV-2005-12-21-123", "domain": "selskapsrett"},
    "statens pensjonsfondloven": {"id": "LOV-2005-12-21-123", "domain": "selskapsrett"},
    "lov om folketrygdfondet": {"id": "LOV-2007-06-29-44", "domain": "selskapsrett"},
    "folketrygdfondloven": {"id": "LOV-2007-06-29-44", "domain": "selskapsrett"},
    "lov om statens finansfond": {"id": "LOV-2009-03-06-12", "domain": "selskapsrett"},
    "statens finansfondloven": {"id": "LOV-2009-03-06-12", "domain": "selskapsrett"},
    "lov om avtalefestet pensjon for medlemmer av statens pensjonskasse": {"id": "LOV-2010-06-25-28", "domain": "arbeidsrett"},
    "avtalefestet pensjon statens pensjonskasse": {"id": "LOV-2010-06-25-28", "domain": "arbeidsrett"},
    "lov om kredittvurderingsbyråer": {"id": "LOV-2014-06-20-30", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "kredittvurderingsbyråerloven": {"id": "LOV-2014-06-20-30", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "referanseverdiloven": {"id": "LOV-2015-12-04-95", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om fastsettelse av finansielle referanseverdier": {"id": "LOV-2015-12-04-95", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om endringer i aksjelovgivningen mv.": {"id": "LOV-2021-06-11-84", "domain": "selskapsrett"},
    "aksjelovgivningsendringer 2021": {"id": "LOV-2021-06-11-84", "domain": "selskapsrett"},
    "lov om røystingsrådgjevarar": {"id": "LOV-2021-06-18-136", "domain": "selskapsrett"},
    "røystingsrådgjevararloven": {"id": "LOV-2021-06-18-136", "domain": "selskapsrett"},
    "lov om informasjonstilgang m.m. for det uavhengige utvalget": {"id": "LOV-2023-06-09-26", "domain": "personvern_gdpr_business_compliance"},
    "informasjonstilgangsloven utvalget 2023": {"id": "LOV-2023-06-09-26", "domain": "personvern_gdpr_business_compliance"},
    "lov om digitaliseringsdirektoratets tilgang til taushetsbelagte opplysninger": {"id": "LOV-2023-06-09-29", "domain": "personvern_gdpr_business_compliance"},
    "digitaliseringsdirektoratets tilgangslov": {"id": "LOV-2023-06-09-29", "domain": "personvern_gdpr_business_compliance"},
    "lov om endringer i konfliktrådsloven, straffeloven og straffeprosessloven mv.": {"id": "LOV-2023-12-20-110", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "konfliktrådsendringslov 2023": {"id": "LOV-2023-12-20-110", "domain": "inkasso_og_tvangsfullbyrdelse"},
    "lov om endringer i finansmarkedslovgivningen": {"id": "LOV-2024-06-25-60", "domain": "arsregnskap_og_selskapsrapportering"},
    "finansmarkedslovendringer 2024": {"id": "LOV-2024-06-25-60", "domain": "arsregnskap_og_selskapsrapportering"},
    "statsføretakslova": {"id": "LOV-2025-04-10-9", "domain": "selskapsrett"},
    "lov om statsføretak": {"id": "LOV-2025-04-10-9", "domain": "selskapsrett"},
    "lov om endringer i arbeidsmiljøloven, lov om aldersgrenser og lov om statens pensjonskasse": {"id": "LOV-2025-05-27-17", "domain": "arbeidsrett"},
    "aldersgrenseendringslov 2025": {"id": "LOV-2025-05-27-17", "domain": "arbeidsrett"},
    "lov om foretaksregisteret": {"id": "LOV-2025-06-20-106", "domain": "selskapsrett"},
    "foretaksregisterloven ny 2025": {"id": "LOV-2025-06-20-106", "domain": "selskapsrett"},
    "lov om endringer i bilansvarslova": {"id": "LOV-2025-06-20-80", "domain": "panterett_og_sikkerhetsrett"},
    "bilansvarslovendringslov 2025": {"id": "LOV-2025-06-20-80", "domain": "panterett_og_sikkerhetsrett"},
    "lov om behandling av personopplysninger i norges idrettsforbund": {"id": "LOV-2025-06-20-95", "domain": "personvern_gdpr_business_compliance"},
    "idrettsforbundet personopplysningsloven": {"id": "LOV-2025-06-20-95", "domain": "personvern_gdpr_business_compliance"},
    "lov om endringer i burettslagslova og eierseksjonsloven": {"id": "LOV-2025-12-19-114", "domain": "avtalerett"},
    "burettslagslovendringslov 2025": {"id": "LOV-2025-12-19-114", "domain": "avtalerett"},
    "lov om endringer i skatteloven om utdelinger": {"id": "LOV-2025-12-22-119", "domain": "arsregnskap_og_selskapsrapportering"},
    "skattellovendringslov utdelinger 2025": {"id": "LOV-2025-12-22-119", "domain": "arsregnskap_og_selskapsrapportering"},
    "lov om endringer i helselovgivningen tilgjengeliggjøring av helsedata": {"id": "LOV-2025-12-22-126", "domain": "personvern_gdpr_business_compliance"},
    "helselovgivningen tilgjengeliggjøring helsedata": {"id": "LOV-2025-12-22-126", "domain": "personvern_gdpr_business_compliance"},

    # overskuddsutdeling
    "forskrift om overskuddsutdeling fra nordpolet as": {"id": "FORSKRIFT-2000-04-05-347", "domain": "selskapsrett"},
    "nordpolet overskuddsutdeling": {"id": "FORSKRIFT-2000-04-05-347", "domain": "selskapsrett"},

    # lån til omsorgsboliger
    "forskrift om lån til omsorgsboliger, sykehjemsplasser og lokaler": {"id": "FORSKRIFT-2003-07-10-957", "domain": "panterett_og_sikkerhetsrett"},
    "omsorgsboliglånsforskriften": {"id": "FORSKRIFT-2003-07-10-957", "domain": "panterett_og_sikkerhetsrett"},

    # reservasjonsregisteret (personvern domain in eval)
    "forskrift om reservasjonsregisteret om markedsføring": {"id": "FORSKRIFT-2009-06-05-598", "domain": "personvern_gdpr_business_compliance"},
    "reservasjonsregisteret markedsføring": {"id": "FORSKRIFT-2009-06-05-598", "domain": "personvern_gdpr_business_compliance"},

    # overgangsregler til endringer i regnskapsloven 2011
    "forskrift om overgangsregler til lov om endringer i regnskapsloven 2011": {"id": "FORSKRIFT-2011-04-15-401", "domain": "arsregnskap_og_selskapsrapportering"},
    "overgangsregler regnskapsloven 2011": {"id": "FORSKRIFT-2011-04-15-401", "domain": "arsregnskap_og_selskapsrapportering"},


    # ── ADDITIONAL PRECISION ENTRIES (false-positive fixes) ──────────────

    # Disambiguation: 2025 Foretaksregisterloven (new law) vs 1985 version
    "lov om foretaksregisteret 2025 ny": {"id": "LOV-2025-06-20-106", "domain": "selskapsrett"},
    "enhetsregisterloven ny": {"id": "LOV-2025-06-20-105", "domain": "selskapsrett"},

    # Tvistelosning: specific forskrift about tvister between NAV and employees
    "forskrift om løsning av tvister mellom arbeids- og velferdsetaten og arbeidstakere": {"id": "FORSKRIFT-2007-03-12-294", "domain": "tvistelosning_smb"},

    # Overgangsregler with specific year references
    "forskrift om overgangsregler til lov 29. juni 2007 nr. 74": {"id": "FORSKRIFT-2007-06-29-750", "domain": "arsregnskap_og_selskapsrapportering"},
    "overgangsregler til lov 30. april 2021 nr. 26": {"id": "FORSKRIFT-2021-06-24-2176", "domain": "arsregnskap_og_selskapsrapportering"},
    "overgangsregler til lov 21. juni 2024 nr. 42": {"id": "FORSKRIFT-2024-10-11-2477", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om overgangsregler til lov 19. april 2013 nr. 15": {"id": "FORSKRIFT-2013-06-03-568", "domain": "arsregnskap_og_selskapsrapportering"},
    "forskrift om overgangsbestemmelser til lov av 10. januar 1992 nr. 99": {"id": "FORSKRIFT-2003-04-04-432", "domain": "konkursrett_og_insolvens"},

    # Statsansatte — forskrift (not the lov itself)
    "forskrift til lov om statens ansatte mv.": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},
    "statsansatterforskriften": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},
    "forskrift om arbeidstid mv. for ansatte i staten": {"id": "FORSKRIFT-2017-06-21-838", "domain": "arbeidsrett"},

    # Innskuddspensjon — the forskrift (not the lov)
    "forskrift om innskuddspensjonsordninger som skal opprettes": {"id": "FORSKRIFT-2006-06-30-870", "domain": "arbeidsrett"},
    "innskuddspensjonsforskriften": {"id": "FORSKRIFT-2006-06-30-870", "domain": "arbeidsrett"},

    # Regnskapsloven — utfyllingsforskrift
    "forskrift til utfylling og gjennomføring mv. av regnskapsloven": {"id": "FORSKRIFT-2006-09-07-1062", "domain": "arsregnskap_og_selskapsrapportering"},
    "utfyllingsforskriften til regnskapsloven": {"id": "FORSKRIFT-2006-09-07-1062", "domain": "arsregnskap_og_selskapsrapportering"},

    # A-opplysningsloven — opplysningsplikt forskrift
    "forskrift om opplysningsplikt til den offisielle lønnsstatistikken": {"id": "FORSKRIFT-2020-12-14-2753", "domain": "arbeidsrett"},

    # Tidspartloven — its own specific forskrift
    "forskrift om standard opplysningsskjemaer etter lov om tidspartavtaler": {"id": "FORSKRIFT-2012-07-03-766", "domain": "avtalerett"},

    # Allmenngjøringsloven AND petroleumsvirksomhetsloven (2025 combined amendment)
    "lov om endringer i allmenngjøringsloven og petroleumsvirksomhetsloven mv.": {"id": "LOV-2025-06-20-109", "domain": "arbeidsrett"},
    "allmenngjøringslovens anvendelse på innenriks skipsfart og rettighetshaveres plikt": {"id": "LOV-2025-06-20-109", "domain": "arbeidsrett"},

    # GDPR — treat both ID formats as equivalent
    "lov om behandling av personopplysninger (gdpr)": {"id": "LOV-2018-06-15-38", "domain": "personvern_gdpr_business_compliance"},
    "gdpr-forordningen": {"id": "LOV-2018-06-15-38", "domain": "personvern_gdpr_business_compliance"},


}


def _normalize(text: str) -> str:
    """Lowercase, strip accents partially preserved for Norwegian, strip punctuation noise."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'["\'\[\]]', '', text)
    return text


def _build_reverse_index() -> Dict[str, Dict]:
    """Build normalized lookup index from _STATUTE_TABLE."""
    index = {}
    for raw_name, info in _STATUTE_TABLE.items():
        normalized = _normalize(raw_name)
        if normalized:
            index[normalized] = info
    return index


_INDEX = _build_reverse_index()


class StatuteRegistry:
    """
    Fast deterministic lookup: Norwegian law name → {id, domain, url}.
    
    Call lookup(text) with any of:
      - Popular short name: "skipssikkerhetsloven"
      - Full name: "lov om skipssikkerhet"
      - Fragment from a query: "Lov om arbeidstvister (arbeidstvistloven)"
    
    Returns dict with keys: id, domain, url  — or None if not found.
    """

    # Patterns to extract law names from natural-language queries
    _LOV_PATTERN = re.compile(
        r'(lov om [^(,\n]+?)(?:\s*\(|innen\b|ved\b|om\s+\w|for\s+\w|til\s+\w|$)',
        re.IGNORECASE
    )
    _FORSKRIFT_PATTERN = re.compile(
        r'(forskrift om [^(,\n]+?)(?:\s*\(|innen\b|ved\b|for\s+\w|om\s+\w|$)',
        re.IGNORECASE
    )
    _OVERGANGSR_PATTERN = re.compile(
        r'(overgangsregler [^(,\n]+?)(?:\s*\(|for\s+\w|om\s+\w|$)',
        re.IGNORECASE
    )
    _POPULAR_PATTERN = re.compile(
        r'\(([^)]*(?:loven|lova|forskriften|lova\b)[^)]*)\)',
        re.IGNORECASE
    )

    def lookup(self, query_text: str) -> Optional[Dict]:
        """
        Try to find a statute match in the given text.
        Returns {id, domain, url} or None.
        
        Strategy (in order):
          1. Popular name from parentheses: "(skipssikkerhetsloven)"
          2. Full "Lov om X" / "Forskrift om X" name
          3. Direct normalized key lookup of the whole text
          4. Substring scan of index keys against normalized text
        """
        if not query_text:
            return None

        norm = _normalize(query_text)

        # ── 1. Popular name from parentheses ──────────────────────
        for m in self._POPULAR_PATTERN.finditer(query_text):
            candidate = _normalize(m.group(1))
            result = _INDEX.get(candidate)
            if result:
                logger.debug(f"📖 StatuteRegistry: popular match '{candidate}' → {result['id']}")
                return self._enrich(result)

        # ── 2. Full "Lov om X" / "Forskrift om X" / "Overgangsregler" ─
        for pattern in (self._LOV_PATTERN, self._FORSKRIFT_PATTERN, self._OVERGANGSR_PATTERN):
            for m in pattern.finditer(query_text):
                candidate = _normalize(m.group(1).strip())
                result = _INDEX.get(candidate)
                if result:
                    logger.debug(f"📖 StatuteRegistry: full-name match '{candidate}' → {result['id']}")
                    return self._enrich(result)

        # ── 3. Direct normalized key match ────────────────────────
        result = _INDEX.get(norm)
        if result:
            logger.debug(f"📖 StatuteRegistry: direct match → {result['id']}")
            return self._enrich(result)

        # ── 4. Substring scan (longest match wins) ────────────────
        best_match = None
        best_len = 0
        for key, info in _INDEX.items():
            if len(key) > best_len and key in norm:
                best_match = info
                best_len = len(key)

        if best_match and best_len > 12:   # min 12 chars to avoid false matches
            logger.debug(f"📖 StatuteRegistry: substring match (len={best_len}) → {best_match['id']}")
            return self._enrich(best_match)

        logger.debug(f"📖 StatuteRegistry: no match for '{query_text[:60]}'")
        return None

    @staticmethod
    def _enrich(info: Dict) -> Dict:
        """Add Lovdata URL to a statute info dict."""
        law_id = info["id"]
        url = _id_to_url(law_id)
        return {
            "id": law_id,
            "domain": info.get("domain", ""),
            "url": url,
        }

    def lookup_by_id(self, statute_id: str) -> Optional[Dict]:
        """Look up by LOV/FORSKRIFT ID directly."""
        for info in _STATUTE_TABLE.values():
            if info["id"] == statute_id:
                return self._enrich(info)
        return None

    def get_all_ids(self) -> List[str]:
        """Return all unique statute IDs in the registry."""
        return list({v["id"] for v in _STATUTE_TABLE.values()})


def _id_to_url(statute_id: str) -> str:
    """Convert LOV-YYYY-MM-DD-NNN or FORSKRIFT-YYYY-MM-DD-NNN to full Lovdata URL."""
    if not statute_id:
        return ""
    sid = statute_id.strip()
    if sid.upper().startswith("LOV-"):
        path = "lov"
        date_num = sid[4:]
    elif sid.upper().startswith("FORSKRIFT-"):
        path = "forskrift"
        date_num = sid[10:]
    else:
        return ""
    parts = date_num.split("-")
    if len(parts) == 4:
        year, month, day, num = parts
        try:
            num_clean = str(int(num))
        except ValueError:
            num_clean = num
        return f"https://lovdata.no/dokument/NL/{path}/{year}-{month}-{day}-{num_clean}"
    return ""


# Module-level singleton
_registry = StatuteRegistry()


def get_registry() -> StatuteRegistry:
    """Return the module-level StatuteRegistry singleton."""
    return _registry