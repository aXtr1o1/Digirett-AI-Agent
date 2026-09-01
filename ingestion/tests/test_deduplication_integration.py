from ingestion.deduplication.deduplicator import CanonicalDeduplicator, Deduplicator


def test_deduplicator_compatibility_and_canonical_deduplication():
    compat = Deduplicator(table_name="demo_1")

    first = compat.check({
        "doc_id": "NL/lov/2005-06-17-62",
        "source": "xapi",
        "content": "tekst som skal være lik",
    })
    second = compat.check({
        "doc_id": "NL/lov/2005-06-17-63",
        "source": "xapi",
        "content": "tekst som skal være lik",
    })

    assert first.get("is_duplicate") is False
    assert second.get("is_duplicate") is True
    assert second.get("duplicate_reason") == "content_hash"

    canonical = CanonicalDeduplicator()
    unique_laws = canonical.deduplicate_laws([
        {"dok_id": "NL/lov/2005-06-17-62", "domain_id": "D12_EMPLOYMENT"},
        {"dok_id": "NL/lov/2005-06-17-62", "domain_id": "D04_CONTRACT"},
    ])

    assert len(unique_laws) == 1
    assert sorted(unique_laws[0]["candidate_domain_ids"]) == ["D04_CONTRACT", "D12_EMPLOYMENT"]
