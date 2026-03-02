# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

from unittest.mock import patch, Mock


# 1️⃣ load_state empty
@patch("ingestion.src.scheduler.cron_scheduler.STATE_FILE")
def test_load_state_empty(mock_state):
    from ingestion.src.scheduler.cron_scheduler import load_state
    mock_state.exists.return_value = False
    assert load_state() == {}


# 2️⃣ save_state
@patch("ingestion.src.scheduler.cron_scheduler.CHECKPOINT_DIR")
@patch("builtins.open")
@patch("json.dump")
def test_save_state(mock_dump, mock_open, mock_dir):
    from ingestion.src.scheduler.cron_scheduler import save_state

    save_state({"a": 1})
    mock_dir.mkdir.assert_called_once()


# 3️⃣ fetch archive
@patch("requests.get")
def test_fetch_archive(mock_get):
    from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name
    r = Mock()
    r.json.return_value = [{"filename": "a.tar.bz2"}]
    r.raise_for_status = Mock()
    mock_get.return_value = r
    assert fetch_latest_archive_name() == "a.tar.bz2"


# 4️⃣ ingestion success
@patch("ingestion.src.scheduler.cron_scheduler._release_lock")
@patch("ingestion.src.scheduler.cron_scheduler._acquire_lock")
@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name")
@patch("ingestion.src.main.run_pipeline")
def test_ingestion_job_success(
    mock_pipeline,
    mock_fetch,
    mock_load,
    mock_save,
    mock_acquire,
    mock_release,
):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    mock_acquire.return_value = Mock()
    mock_load.return_value = {"total_files_processed": 10}
    mock_fetch.return_value = "new.tar.bz2"

    mock_pipeline.return_value = {
        "success": 5,
        "skipped": 0,
        "failed": 0,
        "total_files": 5,
    }

    exit_code = ingestion_job(force=False)
    assert exit_code == 0

    saved_state = mock_save.call_args[0][0]
    assert saved_state["last_archive_name"] == "new.tar.bz2"
    assert saved_state["total_files_processed"] == 15
    assert saved_state["last_run_status"] == "success"


# 5️⃣ API failure
@patch("ingestion.src.scheduler.cron_scheduler._release_lock")
@patch("ingestion.src.scheduler.cron_scheduler._acquire_lock")
@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name")
def test_ingestion_job_api_failure(
    mock_fetch,
    mock_load,
    mock_save,
    mock_acquire,
    mock_release,
):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    mock_acquire.return_value = Mock()
    mock_load.return_value = {}
    mock_fetch.side_effect = Exception("API down")

    exit_code = ingestion_job(force=False)
    assert exit_code == 1

    saved_state = mock_save.call_args[0][0]
    assert saved_state["last_run_status"] == "api_check_failed"


# 6️⃣ pipeline failure
@patch("ingestion.src.scheduler.cron_scheduler._release_lock")
@patch("ingestion.src.scheduler.cron_scheduler._acquire_lock")
@patch("ingestion.src.scheduler.cron_scheduler.save_state")
@patch("ingestion.src.scheduler.cron_scheduler.load_state")
@patch("ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name")
@patch("ingestion.src.main.run_pipeline")
def test_ingestion_job_pipeline_failure(
    mock_pipeline,
    mock_fetch,
    mock_load,
    mock_save,
    mock_acquire,
    mock_release,
):
    from ingestion.src.scheduler.cron_scheduler import ingestion_job

    mock_acquire.return_value = Mock()
    mock_load.return_value = {}
    mock_fetch.return_value = "new.tar.bz2"
    mock_pipeline.side_effect = RuntimeError("boom")

    exit_code = ingestion_job(force=False)
    assert exit_code == 1

    saved_state = mock_save.call_args[0][0]
    assert saved_state["last_run_status"] == "pipeline_failed"