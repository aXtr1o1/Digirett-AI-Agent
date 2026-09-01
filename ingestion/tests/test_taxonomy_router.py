import pytest
from ingestion.src.chunking.taxonomy_router import TaxonomyRouter
from ingestion.models.legal_section import StructuralChunk


def test_taxonomy_router_loads_taxonomies():
    router = TaxonomyRouter()
    assert "D12_EMPLOYMENT" in router._domains
    assert "D04_CONTRACT" in router._domains
    assert len(router._domains) >= 10


def test_taxonomy_router_matches_employment_contract():
    router = TaxonomyRouter()
    chunk = StructuralChunk(
        source_section_key="NL/lov/2005-06-17-62/§14-6",
        chunk_index=0,
        source_text="Arbeidsavtalen skal inneholde opplysninger om forhold av vesentlig betydning i arbeidsforholdet, herunder prøvetid og stillingsprosent.",
        token_count=30,
        source_block_start=0,
        source_block_end=0,
        is_definition=False,
        cross_refs=[],
        section_ref="§ 14-6",
    )
    classifications = router.classify(
        chunk=chunk,
        candidate_domain_ids=["D12_EMPLOYMENT"],
        section_heading="Minimumskrav til innholdet i den skriftlige arbeidsavtalen",
        document_type="LAW",
    )
    assert len(classifications) == 1
    cls = classifications[0]
    assert cls.domain_id == "D12_EMPLOYMENT"
    assert cls.subdomain_id == "EL-01"
    assert "BOTH" in cls.jurisdiction
    assert "B2B" in cls.b2b_b2c
    assert "employment" in cls.relationship_type
    assert cls.tier == 1


def test_taxonomy_router_matches_termination():
    router = TaxonomyRouter()
    chunk = StructuralChunk(
        source_section_key="NL/lov/2005-06-17-62/§15-7",
        chunk_index=0,
        source_text="Arbeidstaker kan ikke sies opp uten at det er saklig begrunnet i virksomhetens, arbeidsgivers eller arbeidstakers forhold.",
        token_count=25,
        source_block_start=0,
        source_block_end=0,
        is_definition=False,
        cross_refs=[],
        section_ref="§ 15-7",
    )
    classifications = router.classify(
        chunk=chunk,
        candidate_domain_ids=["D12_EMPLOYMENT"],
        section_heading="Vern mot usaklig oppsigelse",
        document_type="LAW",
    )
    assert len(classifications) == 1
    cls = classifications[0]
    assert cls.domain_id == "D12_EMPLOYMENT"
    assert cls.subdomain_id == "EL-02"
    assert "employment" in cls.relationship_type
