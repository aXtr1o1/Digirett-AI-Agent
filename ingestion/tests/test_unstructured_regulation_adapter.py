from __future__ import annotations

import pytest
from ingestion.adapters.regulation_section_adapter import RegulationSectionAdapter
from ingestion.src.chunking.legal_chunker import LegalSectionChunker


def test_stage_2a_inline_bold_headers():
    """Test Stage 2A: Discovers <b>§ 1.Virkeområde</b> inline jammed headers and splits cleanly."""
    reg = {
        "dok_id": "SF/forskrift/2025-01-01-500",
        "title": "Forskrift med fete paragrafoverskrifter",
        "fulltekst": """
        <div>
            <h1>Forskrift med fete paragrafoverskrifter</h1>
            <p><b>§ 1.Virkeområde</b> Denne forskriften gjelder for all virksomhet innen sektoren.</p>
            <p><b>§ 2.Ikrafttredelse</b> Forskriften trer i kraft 1. januar 2026.</p>
        </div>
        """,
        "dato": "2025-01-01",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 2
    assert sections[0].section_number == "§ 1"
    assert sections[0].source_section_key == "SF/forskrift/2025-01-01-500/§1"
    assert "virksomhet innen sektoren" in sections[0].source_text

    assert sections[1].section_number == "§ 2"
    assert sections[1].source_section_key == "SF/forskrift/2025-01-01-500/§2"
    assert "trer i kraft 1. januar 2026" in sections[1].source_text


def test_stage_2a_jammed_paragraph_headers():
    """Test Stage 2A: Discovers jammed § 23a. paragraph headers."""
    reg = {
        "dok_id": "SF/forskrift/2025-01-01-600",
        "title": "Forskrift med sammenpressede paragrafer",
        "fulltekst": """
        <div>
            <h1>Forskrift</h1>
            <p>§ 23a.Forskriften gjelder for alle skip i innenriks fart.</p>
            <p>§ 23b.Overgangsregler gjelder frem til 2027.</p>
        </div>
        """,
        "dato": "2025-01-01",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 2
    assert sections[0].section_number == "§ 23a"
    assert "skip i innenriks fart" in sections[0].source_text
    assert sections[1].section_number == "§ 23b"
    assert "Overgangsregler" in sections[1].source_text


def test_type_1_two_sections():
    """Test Type 1: Regulation with exactly two § sections."""
    reg = {
        "dok_id": "LTI/forskrift/2025-01-01-100",
        "title": "Forskrift om to paragrafer",
        "fulltekst": """
        <div>
            <h1>Forskrift om to paragrafer</h1>
            <h3>§ 1 Virkeområde</h3>
            <p>Denne forskriften gjelder for alle virksomheter i riket.</p>
            <h3>§ 2 Ikrafttredelse</h3>
            <p>Forskriften trer i kraft 1. juli 2025.</p>
        </div>
        """,
        "dato": "2025-01-01",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 2
    assert sections[0].section_number == "§ 1"
    assert sections[0].source_section_key == "LTI/forskrift/2025-01-01-100/§1"
    assert sections[0].is_processable is True
    assert "virksomheter i riket" in sections[0].source_text

    assert sections[1].section_number == "§ 2"
    assert sections[1].source_section_key == "LTI/forskrift/2025-01-01-100/§2"
    assert sections[1].is_processable is True
    assert "trer i kraft" in sections[1].source_text


def test_type_2_roman_numerals():
    """Test Type 2: Regulation with Roman numeral headers."""
    reg = {
        "dok_id": "LTI/forskrift/2025-02-02-200",
        "title": "Endringsforskrift med romertall",
        "fulltekst": """
        <div>
            <h1>Endringsforskrift</h1>
            <p><b>I.</b> I forskrift 15. mai 2020 nr. 123 gjøres følgende endringer i § 4 første ledd.</p>
            <p><b>II.</b> Forskriften trer i kraft straks.</p>
        </div>
        """,
        "dato": "2025-02-02",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 2
    assert sections[0].source_section_key == "LTI/forskrift/2025-02-02-200/sec-I"
    assert sections[0].is_processable is True
    assert "gj\u00f8res f\u00f8lgende endringer" in sections[0].source_text

    assert sections[1].source_section_key == "LTI/forskrift/2025-02-02-200/sec-II"
    assert sections[1].is_processable is True
    assert "trer i kraft straks" in sections[1].source_text


def test_type_3_single_paragraph():
    """Test Type 3: Single paragraph decree (e.g. LTI/forskrift/2025-06-10-967)."""
    reg = {
        "dok_id": "LTI/forskrift/2025-06-10-967",
        "title": "Delt ikraftsetting av lov 25. april 2025 nr. 12",
        "fulltekst": """
        <main class="documentBody" id="dokument">
            <h1>Delt ikraftsetting av lov 25. april 2025 nr. 12 om innkreving av statlige krav mv. (innkrevingsloven)</h1>
            <p>Delt ikraftsetting av lov 25. april 2025 nr. 12 om innkreving av statlige krav mv. (innkrevingsloven). Lovens § 3 trer i kraft 1. januar 2026.</p>
        </main>
        """,
        "dato_kunngjort": "2025-06-10 14:40:00",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 1
    assert sections[0].section_number == "sec-1"
    assert sections[0].source_section_key == "LTI/forskrift/2025-06-10-967/sec-1"
    assert sections[0].is_processable is True
    assert "Lovens § 3 trer i kraft 1. januar 2026" in sections[0].source_text

    # Verify chunking integration
    chunker = LegalSectionChunker(max_tokens=2000)
    chunks = chunker.chunk_section(sections[0])
    assert len(chunks) == 1
    assert chunks[0].section_ref == "sec-1"
    assert chunks[0].token_count > 0


def test_type_4_complex_tables_and_lists():
    """Test Type 4: Complex HTML containing tables and multi-tier lists."""
    reg = {
        "dok_id": "SF/forskrift/2025-03-03-300",
        "title": "Forskrift om gebyrsatser for mineralutvinning",
        "fulltekst": """
        <div>
            <h1>Gebyrsatser for mineralutvinning</h1>
            <p>Følgende satser gjelder for behandlingsgebyr:</p>
            <table>
                <tr><th>Kategori</th><th>Gebyr (NOK)</th></tr>
                <tr><td>Søknad om undersøkelsestillatelse</td><td>25 000</td></tr>
                <tr><td>Søknad om utvinningstillatelse</td><td>150 000</td></tr>
            </table>
            <ul>
                <li>Gebyr innbetales til Oljedirektoratet.</li>
                <li>Innbetalt gebyr refunderes ikke ved avslag.</li>
            </ul>
        </div>
        """,
        "dato": "2025-03-03",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) == 1
    sec = sections[0]
    assert sec.section_number == "sec-1"
    assert sec.source_section_key == "SF/forskrift/2025-03-03-300/sec-1"
    assert sec.is_processable is True
    assert len(sec.structured_blocks) >= 2
    
    # Table block preserved
    table_blocks = [b for b in sec.structured_blocks if b.block_type == "TABLE"]
    assert len(table_blocks) == 1
    assert "Søknad om utvinningstillatelse | 150 000" in table_blocks[0].text

    # Chunking test
    chunker = LegalSectionChunker(max_tokens=2000)
    chunks = chunker.chunk_section(sec)
    assert len(chunks) == 1
    assert "Søknad om utvinningstillatelse" in chunks[0].source_text


def test_type_4_oversized_safeguard():
    """Test Type 4 Oversized Safeguard: Text > 20,000 chars is partitioned into sections < 1500 tokens."""
    paragraph = "Dette er et langt avsnitt med tekniske og juridiske krav til mineralvirksomhet til havs. " * 30  # ~2700 chars
    long_html = f"<div><h1>Stor forskrift</h1>" + "".join(f"<p>{paragraph}</p>" for _ in range(10)) + "</div>"  # ~27,000 chars
    
    reg = {
        "dok_id": "SF/forskrift/2025-04-04-400",
        "title": "Stor teknisk forskrift",
        "fulltekst": long_html,
        "dato": "2025-04-04",
    }
    sections = RegulationSectionAdapter.adapt_all(reg)
    assert len(sections) >= 2  # Sub-chunked into multiple sections
    for sec in sections:
        assert sec.section_number.startswith("sec-")
        assert sec.is_processable is True
        assert len(sec.source_text) <= 20000
