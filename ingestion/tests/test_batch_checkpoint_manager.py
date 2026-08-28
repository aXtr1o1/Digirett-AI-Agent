import shutil
from pathlib import Path
import pytest
from ingestion.src.processors.batch_checkpoint_manager import BatchCheckpointManager


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    cp_dir = tmp_path / "checkpoints"
    cp_dir.mkdir(parents=True, exist_ok=True)
    yield cp_dir
    if cp_dir.exists():
        shutil.rmtree(cp_dir, ignore_errors=True)


def test_batch_partitioning_and_checkpoints(temp_checkpoint_dir):
    manager = BatchCheckpointManager(checkpoint_dir=temp_checkpoint_dir, run_id="test-run-001")

    # Create 12 sample documents
    docs = [
        {"canonical_document_id": f"LOV-2024-{i:03d}", "dok_id": f"LOV-2024-{i:03d}", "title": f"Law {i}"}
        for i in range(1, 13)
    ]

    # Partition into batches of 5 docs each -> should produce 3 batches (5, 5, 2)
    batches = manager.partition_into_batches(docs, batch_size=5)
    assert len(batches) == 3
    assert len(batches[0]) == 5
    assert len(batches[1]) == 5
    assert len(batches[2]) == 2

    # Commit Batch 1
    manager.commit_batch(
        batch_index=1,
        total_batches=3,
        documents=batches[0],
        metrics={"chunks_created": 25},
    )

    assert manager.is_batch_committed(1) is True
    assert manager.is_batch_committed(2) is False

    # Verify dedicated file checkpoint_batch_001.json exists
    cp1_file = manager.get_batch_checkpoint_path(1)
    assert cp1_file.exists()

    cp1_data = manager.load_batch_checkpoint(1)
    assert cp1_data["batch_id"] == "batch_001"
    assert cp1_data["document_count"] == 5
    assert cp1_data["metrics"]["chunks_created"] == 25

    # Test Cross-Batch Deduplication
    # If Batch 2 contains a duplicate doc from Batch 1, it should be filtered out
    batch_2_with_duplicate = [batches[0][0]] + batches[1]  # 1 duplicate + 5 new
    filtered = manager.filter_unprocessed_documents(batch_2_with_duplicate)
    assert len(filtered) == 5
    assert filtered[0]["canonical_document_id"] == "LOV-2024-006"

    # Commit Batch 2
    manager.commit_batch(
        batch_index=2,
        total_batches=3,
        documents=filtered,
        metrics={"chunks_created": 30},
    )
    assert manager.is_batch_committed(2) is True

    # Check manifest global committed count
    manifest = manager.load_manifest(force_refresh=True)
    assert len(manifest["global_committed_doc_ids"]) == 10
    assert manifest["completed_batches"] == 2
