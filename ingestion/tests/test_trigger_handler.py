# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

import pytest
from unittest.mock import patch, Mock


@pytest.fixture
def sample_state():
    return {
        "last_archive_name": "old.tar.bz2",
        "total_files_processed": 50
    }


# ✅ IMPORTANT — patch the REAL function used
@patch("ingestion.src.scheduler.trigger_handler.save_state")
@patch("ingestion.src.scheduler.trigger_handler.load_state")
@patch("ingestion.src.scheduler.trigger_handler.fetch_latest_archive_name")
@patch("ingestion.src.main.run_pipeline")
def test_change_success(mock_pipeline, mock_fetch, mock_load, mock_save, sample_state):
    mock_load.return_value = sample_state
    mock_fetch.return_value = "new.tar.bz2"

    mock_pipeline.return_value = {
        "success": 5,
        "skipped": 0,
        "failed": 0,
        "total_files": 5,
    }

    from ingestion.src.scheduler.trigger_handler import run_trigger
    run_trigger(batch_size=50, force=False, dry_run=False)

    saved = mock_save.call_args[0][0]

    assert saved["last_archive_name"] == "new.tar.bz2"
    assert saved["last_run_status"] == "success"
    assert saved["total_files_processed"] == 55


@patch("ingestion.src.scheduler.trigger_handler.save_state")
@patch("ingestion.src.scheduler.trigger_handler.load_state")
@patch("ingestion.src.scheduler.trigger_handler.fetch_latest_archive_name")
def test_dry_run(mock_fetch, mock_load, mock_save):
    mock_load.return_value = {}
    mock_fetch.return_value = "new.tar.bz2"

    from ingestion.src.scheduler.trigger_handler import run_trigger
    run_trigger(batch_size=50, force=False, dry_run=True)

    mock_save.assert_not_called()

@patch("ingestion.src.scheduler.trigger_handler.save_state")
@patch("ingestion.src.scheduler.trigger_handler.load_state")
@patch("ingestion.src.scheduler.trigger_handler.fetch_latest_archive_name")
@patch("ingestion.src.main.run_pipeline")
def test_no_change_skip_pipeline(mock_pipeline, mock_fetch, mock_load, mock_save):
    mock_load.return_value = {
        "last_archive_name": "same.tar.bz2",
        "total_files_processed": 50
    }
    mock_fetch.return_value = "same.tar.bz2"

    from ingestion.src.scheduler.trigger_handler import run_trigger
    run_trigger(batch_size=50, force=False, dry_run=False)

    # 🚫 pipeline should not run
    mock_pipeline.assert_not_called()

@patch("ingestion.src.scheduler.trigger_handler.save_state")
@patch("ingestion.src.scheduler.trigger_handler.load_state")
@patch("ingestion.src.scheduler.trigger_handler.fetch_latest_archive_name")
@patch("ingestion.src.main.run_pipeline")
def test_force_runs_pipeline(mock_pipeline, mock_fetch, mock_load, mock_save):
    mock_load.return_value = {
        "last_archive_name": "same.tar.bz2",
        "total_files_processed": 50
    }
    mock_fetch.return_value = "same.tar.bz2"

    mock_pipeline.return_value = {
        "success": 3,
        "skipped": 0,
        "failed": 0,
        "total_files": 3,
    }

    from ingestion.src.scheduler.trigger_handler import run_trigger
    run_trigger(batch_size=50, force=True, dry_run=False)

    # ✅ pipeline should run because force=True
    mock_pipeline.assert_called_once()
