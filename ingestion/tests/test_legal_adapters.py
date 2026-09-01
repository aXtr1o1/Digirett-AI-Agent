import pytest
from ingestion.models.legal_section import LegalBlock, NormalizedLegalSection
from ingestion.adapters.legal_html_parser import parse_legal_blocks
from ingestion.adapters.law_section_adapter import LawSectionAdapter
from ingestion.adapters.regulation_section_adapter import RegulationSectionAdapter


def test_parse_legal_blocks_nested_list_no_duplication():
    html = """
    <article class="legalP">
        Arbeidsgiver har plikt til å:
        <ol>
            <li>a) drøfte oppsigelsen med tillitsvalgte</li>
            <li>b) gi skriftlig begrunnelse</li>
        </ol>
    </article>
    """
    blocks = parse_legal_blocks(html)
    assert len(blocks) == 3
    assert blocks[0].block_type == "LEDD"
    assert blocks[0].text == "Arbeidsgiver har plikt til å:"

    assert blocks[1].block_type == "LIST_ITEM"
    assert blocks[1].prefix == "a)"
    assert blocks[1].text == "a) drøfte oppsigelsen med tillitsvalgte"

    assert blocks[2].block_type == "LIST_ITEM"
    assert blocks[2].prefix == "b)"
    assert blocks[2].text == "b) gi skriftlig begrunnelse"


def test_law_section_adapter_html_primary():
    paragraph = {
        "paragraf_id": "483079",
        "paragraf_nr": "15-7",
        "heading": "Vern mot usaklig oppsigelse",
        "kapittel_nr": "Kapittel 15",
        "kapittel_tittel": "Opphør av arbeidsforhold",
        "innhold_html": """
        <article class="legalP">
            (1) Arbeidstaker kan ikke sies opp uten at det er saklig begrunnet.
        </article>
        <article class="legalP">
            (2) Oppsigelse som skyldes virksomhetens forhold er ikke saklig begrunnet dersom:
            <ul>
                <li>a) arbeidsgiver har annet passende arbeid</li>
                <li>b) virksomheten ikke har vurdert omplassering</li>
            </ul>
        </article>
        """,
        "innhold_text": "Plain text fallback from xAPI",
        "opphevet": 0,
    }
    law_meta = {
        "dok_id": "NL/lov/2005-06-17-62",
        "title": "Arbeidsmiljøloven",
        "candidate_domain_ids": ["D12_EMPLOYMENT"],
    }

    section = LawSectionAdapter.adapt(paragraph, law_meta)

    assert section.document_type == "LAW"
    assert section.canonical_document_id == "NL/lov/2005-06-17-62"
    assert section.section_number == "§ 15-7"
    assert section.section_title == "Vern mot usaklig oppsigelse"
    assert section.chapter_number == "Kapittel 15"
    assert section.chapter_title == "Opphør av arbeidsforhold"
    assert section.is_active is True
    assert section.is_repealed is False
    assert section.is_processable is True
    assert len(section.structured_blocks) == 4
    assert "Plain text fallback" not in section.source_text
    assert "Arbeidstaker kan ikke sies opp" in section.source_text


def test_law_section_adapter_repealed_section():
    paragraph = {
        "paragraf_id": "100",
        "paragraf_nr": "10",
        "heading": "Opphevet paragraf",
        "innhold_html": "<article class='legalP'>(Opphevet ved lov 19 des 2008 nr. 110)</article>",
        "opphevet": 1,
    }
    law_meta = {
        "dok_id": "NL/lov/2005-06-17-62",
        "title": "Arbeidsmiljøloven",
        "candidate_domain_ids": ["D12_EMPLOYMENT"],
    }

    section = LawSectionAdapter.adapt(paragraph, law_meta)

    assert section.is_active is False
    assert section.is_repealed is True
    assert section.is_processable is False
    # But RDB export still works for source traceability
    rdb = section.to_rdb_dict()
    assert rdb["is_repealed"] is True
    assert rdb["is_active"] is False
    assert rdb["vdb_status"] == "NOT_ELIGIBLE"


def test_law_section_adapter_text_fallback():
    paragraph = {
        "paragraf_id": "50",
        "paragraf_nr": "5",
        "heading": "Fallback paragraf",
        "innhold_html": "",
        "innhold_text": "Dette er ren tekst uten HTML.\nAndre linje med tekst.",
        "opphevet": 0,
    }
    law_meta = {
        "dok_id": "NL/lov/1990-01-01-1",
        "title": "Testlov",
        "candidate_domain_ids": ["D04_CONTRACT"],
    }

    section = LawSectionAdapter.adapt(paragraph, law_meta)

    assert section.is_active is True
    assert len(section.structured_blocks) == 2
    assert "Dette er ren tekst" in section.source_text


def test_regulation_section_adapter_decomposition():
    reg_dict = {
        "canonical_id": "SF/forskrift/2021-06-01-100",
        "title": "Forskrift om arbeidstid",
        "candidate_domain_ids": ["D12_EMPLOYMENT"],
        "fulltekst": """
        <section class="kapittel">
            <h1>Kapittel 1. Innledende bestemmelser</h1>
            <article class="legalArticle" data-lovdata-url="SF/forskrift/2021-06-01-100/§1" data-name="§ 1">
                <span class="heading">Formål og virkeområde</span>
                <article class="legalP">Forskriften gjelder for alle virksomheter.</article>
            </article>
            <article class="legalArticle" data-lovdata-url="SF/forskrift/2021-06-01-100/§2" data-name="§ 2">
                <span class="heading">Definisjoner</span>
                <article class="legalP">Med arbeidstid menes den tid arbeidstaker står til disposisjon.</article>
            </article>
        </section>
        """,
    }

    sections = RegulationSectionAdapter.adapt_all(reg_dict)
    assert len(sections) == 2
    assert sections[0].source_section_key == "SF/forskrift/2021-06-01-100/§1"
    assert sections[0].section_number == "§ 1"
    assert sections[0].section_title == "Formål og virkeområde"
    assert sections[0].document_type == "REGULATION"

    assert sections[1].source_section_key == "SF/forskrift/2021-06-01-100/§2"
    assert sections[1].section_number == "§ 2"
    assert sections[1].section_title == "Definisjoner"
