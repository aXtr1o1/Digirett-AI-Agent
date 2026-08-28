from unittest.mock import MagicMock
import pytest
from ingestion.src.processors.comparing_engine import ComparingEngine, ComparisonResult


def test_comparing_engine_diff_detection():
    mock_store = MagicMock()
    mock_store.get_or_create_bucket_ledger.return_value = {
        "ledger_version": "2.0.0",
        "last_synced_at": "2026-08-01T00:00:00Z",
        "total_documents": 2,
        "documents": {
            "LOV-1992-06-26-86": {
                "canonical_document_id": "LOV-1992-06-26-86",
                "dok_id": "LOV-1992-06-26-86",
                "last_amended_date": "2024-01-01",
                "paragraph_count": 50,
                "vdb_status": "SYNCED",
            },
            "LOV-2005-06-17-62": {
                "canonical_document_id": "LOV-2005-06-17-62",
                "dok_id": "LOV-2005-06-17-62",
                "last_amended_date": "2023-01-01",
                "paragraph_count": 20,
                "vdb_status": "SYNCED",
            },
        },
    }

    engine = ComparingEngine(supabase_store=mock_store)

    discovered_xapi = [
        # 1. Unchanged document
        {
            "canonical_document_id": "LOV-1992-06-26-86",
            "dok_id": "LOV-1992-06-26-86",
            "sist_endret": "2024-01-01",
            "antall_paragrafer": 50,
        },
        # 2. Modified document (amended date changed from 2023 to 2026)
        {
            "canonical_document_id": "LOV-2005-06-17-62",
            "dok_id": "LOV-2005-06-17-62",
            "sist_endret": "2026-08-20",
            "antall_paragrafer": 20,
        },
        # 3. New document (not in ledger)
        {
            "canonical_document_id": "LOV-2024-01-01-01",
            "dok_id": "LOV-2024-01-01-01",
            "sist_endret": "2024-01-01",
            "antall_paragrafer": 10,
        },
    ]

    result = engine.compare(discovered_xapi, detect_deletions=True)

    assert result.has_changes is True
    assert len(result.new_docs) == 1
    assert result.new_docs[0]["canonical_document_id"] == "LOV-2024-01-01-01"

    assert len(result.modified_docs) == 1
    assert result.modified_docs[0]["canonical_document_id"] == "LOV-2005-06-17-62"

    assert len(result.unchanged_docs) == 1
    assert result.unchanged_docs[0]["canonical_document_id"] == "LOV-1992-06-26-86"

    # Update ledger entry
    engine.update_document_entry(
        doc_id="LOV-2024-01-01-01",
        document_metadata=discovered_xapi[2],
        vdb_status="SYNCED",
    )

    ledger = engine.load_ledger()
    assert "LOV-2024-01-01-01" in ledger["documents"]
    assert ledger["documents"]["LOV-2024-01-01-01"]["vdb_status"] == "SYNCED"
