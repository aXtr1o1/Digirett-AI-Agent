from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from ingestion.src.scheduler.cron_scheduler import (
    _acquire_lock,
    _release_lock,
    ingestion_job,
    load_state,
    save_state,
)


def test_lock_acquire_and_release():
    lock = _acquire_lock()
    assert lock is not None
    _release_lock(lock)


def test_save_and_load_state_serialization(tmp_path):
    test_state_file = tmp_path / "scheduler_state.json"
    with patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE", test_state_file):
        initial = load_state()
        assert initial == {}

        sample_state = {"status": "success", "total_processed": 42}
        save_state(sample_state)

        # Verify physical file creation and content
        assert test_state_file.exists()
        saved_on_disk = json.loads(test_state_file.read_text(encoding="utf-8"))
        assert saved_on_disk == sample_state

        loaded = load_state()
        assert loaded == sample_state


def test_state_overwrite(tmp_path):
    test_state_file = tmp_path / "scheduler_state.json"
    with patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE", test_state_file):
        save_state({"run": 1})
        save_state({"run": 2})
        assert load_state()["run"] == 2


def test_load_corrupted_state_recovers_gracefully(tmp_path):
    test_state_file = tmp_path / "corrupted_state.json"
    test_state_file.write_text("{corrupted json string", encoding="utf-8")
    with patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE", test_state_file):
        state = load_state()
        assert state == {}


def test_ingestion_job_success_verifies_all_interactions():
    mock_summary = {
        "target_docs_processed": 5,
        "sections_processed": 20,
        "milvus_chunks_indexed": 20,
        "comparison_summary": {"has_changes": True},
    }

    mock_runner = MagicMock()
    mock_runner.run_incremental_sync = AsyncMock(return_value=mock_summary)

    with patch("ingestion.src.main.RealTimePipelineRunner", return_value=mock_runner):
        with patch("ingestion.src.scheduler.cron_scheduler._acquire_lock", return_value=MagicMock()):
            with patch("ingestion.src.scheduler.cron_scheduler._release_lock") as mock_release:
                with patch("ingestion.src.scheduler.cron_scheduler.save_state") as mock_save:
                    code = ingestion_job(force=False, dry_run=True)

                    # 1. Exit code check
                    assert code == 0

                    # 2. Pipeline invoked
                    mock_runner.run_incremental_sync.assert_awaited_once()

                    # 3. Release lock called
                    mock_release.assert_called_once()

                    # 4. Save state called with success status
                    mock_save.assert_called_once()
                    saved_state = mock_save.call_args.args[0]
                    assert saved_state.get("last_run_status") == "success"
                    assert saved_state.get("total_files_processed") == 5


def test_ingestion_job_empty_summary():
    mock_runner = MagicMock()
    mock_runner.run_incremental_sync = AsyncMock(return_value={})

    with patch("ingestion.src.main.RealTimePipelineRunner", return_value=mock_runner):
        with patch("ingestion.src.scheduler.cron_scheduler._acquire_lock", return_value=MagicMock()):
            with patch("ingestion.src.scheduler.cron_scheduler._release_lock") as mock_release:
                with patch("ingestion.src.scheduler.cron_scheduler.save_state") as mock_save:
                    code = ingestion_job(force=False, dry_run=True)
                    assert code == 0
                    mock_release.assert_called_once()
                    mock_save.assert_called_once()


def test_ingestion_job_pipeline_failure_records_error():
    mock_runner = MagicMock()
    mock_runner.run_incremental_sync = AsyncMock(side_effect=RuntimeError("Simulated API failure"))

    with patch("ingestion.src.main.RealTimePipelineRunner", return_value=mock_runner):
        with patch("ingestion.src.scheduler.cron_scheduler._acquire_lock", return_value=MagicMock()):
            with patch("ingestion.src.scheduler.cron_scheduler._release_lock") as mock_release:
                with patch("ingestion.src.scheduler.cron_scheduler.save_state") as mock_save:
                    code = ingestion_job(force=False, dry_run=True)

                    # 1. Exit code is 1
                    assert code == 1

                    # 2. Release lock still called (in finally block)
                    mock_release.assert_called_once()

                    # 3. State recorded failure details
                    mock_save.assert_called_once()
                    saved_state = mock_save.call_args.args[0]
                    assert saved_state.get("last_run_status") == "pipeline_failed"
                    assert "Simulated API failure" in saved_state.get("last_error", "")


def test_ingestion_job_lock_collision():
    # When another process holds the lock, _acquire_lock returns None
    with patch("ingestion.src.scheduler.cron_scheduler._acquire_lock", return_value=None):
        code = ingestion_job()
        assert code == 1
