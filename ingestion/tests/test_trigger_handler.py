# ---------- PATH FIX ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------

from unittest.mock import patch
import ingestion.src.scheduler.trigger_handler as trigger_module


# 7️⃣ dry run
@patch.object(trigger_module, "ingestion_job")
@patch.object(trigger_module, "fetch_latest_archive_name")
@patch.object(trigger_module, "load_state")
def test_dry_run(mock_load, mock_fetch, mock_ingest):
    mock_load.return_value = {}
    mock_fetch.return_value = "new.tar.bz2"

    trigger_module.run_trigger(batch_size=50, force=False, dry_run=True)
    mock_ingest.assert_not_called()


# 8️⃣ normal run (archive changed)
@patch.object(trigger_module, "ingestion_job")
@patch.object(trigger_module, "fetch_latest_archive_name")
@patch.object(trigger_module, "load_state")
def test_change_success(mock_load, mock_fetch, mock_ingest):
    mock_load.return_value = {"last_archive_name": "old.tar.bz2"}
    mock_fetch.return_value = "new.tar.bz2"
    mock_ingest.return_value = 0

    trigger_module.run_trigger(batch_size=50, force=False, dry_run=False)
    mock_ingest.assert_called_once()


# 9️⃣ no change skip
@patch.object(trigger_module, "ingestion_job")
@patch.object(trigger_module, "fetch_latest_archive_name")
@patch.object(trigger_module, "load_state")
def test_no_change_skip_pipeline(mock_load, mock_fetch, mock_ingest):
    mock_load.return_value = {"last_archive_name": "same.tar.bz2"}
    mock_fetch.return_value = "same.tar.bz2"

    trigger_module.run_trigger(batch_size=50, force=False, dry_run=False)
    mock_ingest.assert_not_called()


# 🔟 force run
@patch.object(trigger_module, "ingestion_job")
@patch.object(trigger_module, "fetch_latest_archive_name")
@patch.object(trigger_module, "load_state")
def test_force_runs_pipeline(mock_load, mock_fetch, mock_ingest):
    mock_load.return_value = {"last_archive_name": "same.tar.bz2"}
    mock_fetch.return_value = "same.tar.bz2"
    mock_ingest.return_value = 0

    trigger_module.run_trigger(batch_size=50, force=True, dry_run=False)
    mock_ingest.assert_called_once()


# 1️⃣1️⃣ API failure
@patch.object(trigger_module, "ingestion_job")
@patch.object(trigger_module, "fetch_latest_archive_name")
@patch.object(trigger_module, "load_state")
def test_trigger_api_failure(mock_load, mock_fetch, mock_ingest):
    mock_load.return_value = {}
    mock_fetch.side_effect = Exception("API down")

    trigger_module.run_trigger(batch_size=50, force=False, dry_run=False)
    mock_ingest.assert_not_called()