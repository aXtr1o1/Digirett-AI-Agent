import pytest
from ingestion.models.legal_section import (
    LegalBlock,
    NormalizedLegalSection,
    StructuralChunk,
)
from ingestion.src.chunking.taxonomy_router import TaxonomyRouter, ChunkEnricher, build_chunk_id


def test_build_chunk_id_deterministic():
    chunk_id = build_chunk_id(
        canonical_document_id="NL/lov/2005-06-17-62",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        domain_id="D12_EMPLOYMENT",
        subdomain_id="EL-02",
        chunk_index=1,
    )
    assert chunk_id == "NL_lov_2005-06-17-62__NL-lov-2005-06-17-62-paragraf-15-7__D12_EMPLOYMENT__EL-02__0001"


def test_build_chunk_id_no_subdomain():
    chunk_id = build_chunk_id(
        canonical_document_id="NL/lov/2005-06-17-62",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        domain_id="D10_DISPUTE",
        subdomain_id=None,
        chunk_index=2,
    )
    assert chunk_id == "NL_lov_2005-06-17-62__NL-lov-2005-06-17-62-paragraf-15-7__D10_DISPUTE__NO_SUBDOMAIN__0002"


def test_multi_classification_and_enrichment():
    router = TaxonomyRouter()
    chunk = StructuralChunk(
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        chunk_index=1,
        source_text="Arbeidstaker kan ikke sies opp uten saklig grunn.",
        token_count=15,
        source_block_start=0,
        source_block_end=0,
        is_definition=False,
        cross_refs=[],
        section_ref="§ 15-7",
    )
    section = NormalizedLegalSection(
        legal_document_id="NL/lov/2005-06-17-62",
        canonical_document_id="NL/lov/2005-06-17-62",
        document_type="LAW",
        document_title="Arbeidsmiljøloven",
        section_type="LAW_PARAGRAPH",
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        section_number="§ 15-7",
        section_title="Vern mot usaklig oppsigelse",
        chapter_number="Kapittel 15",
        chapter_title="Opphør av arbeidsforhold",
        source_text="Arbeidstaker kan ikke sies opp uten saklig grunn.",
        structured_blocks=[LegalBlock(block_type="LEDD", text="Arbeidstaker kan ikke sies opp uten saklig grunn.", order=0)],
        candidate_domain_ids=["D12_EMPLOYMENT", "D10_DISPUTE"],
    )

    classifications = router.classify(chunk, section.candidate_domain_ids)
    assert len(classifications) == 2
    assert classifications[0].domain_id == "D12_EMPLOYMENT"
    assert classifications[1].domain_id == "D10_DISPUTE"

    enriched_1 = ChunkEnricher.enrich(section, chunk, classifications[0])
    assert "[LAW]" in enriched_1.embedding_text
    assert "Arbeidsmiljøloven" in enriched_1.embedding_text
    assert "Kapittel 15 - Opphør av arbeidsforhold" in enriched_1.embedding_text
    assert "§ 15-7 - Vern mot usaklig oppsigelse" in enriched_1.embedding_text
    assert enriched_1.source_text == chunk.source_text
    assert enriched_1.domain_id == "D12_EMPLOYMENT"


def test_enrichment_omits_none_metadata():
    section = NormalizedLegalSection(
        legal_document_id="SF/forskrift/2021-01-01",
        canonical_document_id="SF/forskrift/2021-01-01",
        document_type="REGULATION",
        document_title="Forskrift om diverse",
        section_type="REGULATION_PROVISION",
        source_section_key="SF/forskrift/2021-01-01/§1",
        section_number="§ 1",
        section_title=None,
        chapter_number=None,
        chapter_title=None,
        source_text="Kort forskriftstekst.",
        structured_blocks=[LegalBlock(block_type="TEXT", text="Kort forskriftstekst.", order=0)],
    )
    chunk = StructuralChunk(
        source_section_key="SF/forskrift/2021-01-01/§1",
        chunk_index=1,
        source_text="Kort forskriftstekst.",
        token_count=5,
        source_block_start=0,
        source_block_end=0,
        is_definition=False,
        cross_refs=[],
        section_ref="§ 1",
    )
    router = TaxonomyRouter()
    cls = router.classify(chunk, ["D04_CONTRACT"])[0]
    enriched = ChunkEnricher.enrich(section, chunk, cls)

    # Assure "None" does not appear as text
    assert "None" not in enriched.embedding_text
    assert "[REGULATION]\nForskrift om diverse\n§ 1\nKort forskriftstekst." == enriched.embedding_text
