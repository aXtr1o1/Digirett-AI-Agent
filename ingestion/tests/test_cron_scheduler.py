# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

from unittest.mock import patch, Mock
import pytest


# ---------------------------------------------------------------------
# load_state / save_state
# ---------------------------------------------------------------------

@patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE")
def test_load_state_empty(mock_state):
    from ingestion.src.scheduler.cron_scheduler import load_state
    mock_state.exists.return_value = False
    assert load_state() == {}


@patch("ingestion.src.scheduler.cron_scheduler.CHECKPOINT_DIR")
@patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE")
def test_save_state(mock_state, mock_dir):
    from ingestion.src.scheduler.cron_scheduler import save_state
    mock_dir.mkdir = Mock()
    save_state({"a": 1})
    mock_dir.mkdir.assert_called_once()


# ---------------------------------------------------------------------
# fetch_latest_archive_name
# ---------------------------------------------------------------------

@patch("requests.get")
def test_fetch_archive(mock_get):
    from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name

    r = Mock()
    r.json.return_value = [{"filename": "a.tar.bz2"}]
    r.raise_for_status = Mock()
    mock_get.return_value = r

    assert fetch_latest_archive_name() == "a.tar.bz2"


# ---------------------------------------------------------------------
# ingestion_job — REAL FLOW (PDF CORRECT)
# ---------------------------------------------------------------------

@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("requests.get")
@patch("ingestion.src.main.run_pipeline")
def test_ingestion_job_success(mock_pipeline, mock_get, mock_load, mock_save):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    # Existing state
    mock_load.return_value = {"total_files_processed": 10}

    # API response
    r = Mock()
    r.json.return_value = [{"filename": "new.tar.bz2"}]
    r.raise_for_status = Mock()
    mock_get.return_value = r

    # Pipeline returns stats
    mock_pipeline.return_value = {
        "success": 5,
        "skipped": 1,
        "failed": 0,
        "total_files": 6,
    }

    ingestion_job()

    saved = mock_save.call_args[0][0]

    assert saved["last_archive_name"] == "new.tar.bz2"
    assert saved["last_run_status"] == "success"

    # ✅ Scheduler no longer updates file count
    assert saved["total_files_processed"] == 10



@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("requests.get")
def test_ingestion_job_api_failure(mock_get, mock_load, mock_save):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    mock_load.return_value = {}
    mock_get.side_effect = Exception("API down")

    ingestion_job()

    saved = mock_save.call_args[0][0]
    assert saved["last_run_status"] == "api_check_failed"


@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("requests.get")
@patch("ingestion.src.main.run_pipeline")
def test_ingestion_job_pipeline_failure(mock_pipeline, mock_get, mock_load, mock_save):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    mock_load.return_value = {}

    r = Mock()
    r.json.return_value = [{"filename": "a.tar.bz2"}]
    r.raise_for_status = Mock()
    mock_get.return_value = r

    mock_pipeline.side_effect = RuntimeError("boom")

    ingestion_job()

    saved = mock_save.call_args[0][0]
    assert saved["last_run_status"] == "pipeline_failed"


# ---------------------------------------------------------------------
# on_job_event
# ---------------------------------------------------------------------

def test_on_job_event():
    from ingestion.src.scheduler.cron_scheduler import on_job_event
    e = Mock()
    e.exception = None
    on_job_event(e)