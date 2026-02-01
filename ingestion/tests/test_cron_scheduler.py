"""
Unit Tests for cron_scheduler.py
==================================
Comprehensive tests for the Lovdata APScheduler-based cron job.

Run with:
    pytest tests/test_cron_scheduler.py -v
    pytest tests/test_cron_scheduler.py -v --cov=ingestion.src.scheduler.cron_scheduler
"""

# ---------- PATH FIX (MUST BE FIRST) ----------
import sys, os
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
# --------------------------------------------

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, mock_open
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_state():
    """Sample state data for testing."""
    return {
        "last_archive_name": "lovtidend-avd1-2001-2025.tar.bz2",
        "last_check_time": "2026-01-31T02:00:00+00:00",
        "last_run_time": "2026-01-31T02:00:01+00:00",
        "last_run_status": "success",
        "total_files_processed": 50
    }


@pytest.fixture
def empty_state():
    """Empty state for first run."""
    return {}


@pytest.fixture
def mock_api_response():
    """Mock Lovdata API response."""
    return [
        {
            "filename": "lovtidend-avd1-2001-2025.tar.bz2",
            "size": 2645678912,
            "lastModified": "2026-01-29T15:30:00Z"
        }
    ]


@pytest.fixture
def mock_api_response_new():
    """Mock Lovdata API response with new archive."""
    return [
        {
            "filename": "lovtidend-avd1-2001-2026.tar.bz2",
            "size": 2745678912,
            "lastModified": "2026-01-30T10:00:00Z"
        }
    ]


# ============================================================================
# Test load_state()
# ============================================================================

class TestLoadState:
    """Test state loading functionality."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_load_state_file_exists_valid_json(self, mock_state_file, sample_state):
        """Should load valid JSON state file."""
        mock_state_file.exists.return_value = True
        
        from ingestion.src.scheduler.cron_scheduler import load_state
        
        with patch('builtins.open', mock_open(read_data=json.dumps(sample_state))):
            result = load_state()
        
        assert result == sample_state
    
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_load_state_file_not_exists(self, mock_state_file):
        """Should return empty dict when file doesn't exist."""
        mock_state_file.exists.return_value = False
        
        from ingestion.src.scheduler.cron_scheduler import load_state
        
        result = load_state()
        assert result == {}
    
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_load_state_invalid_json(self, mock_state_file):
        """Should return empty dict on JSON decode error."""
        mock_state_file.exists.return_value = True
        
        from ingestion.src.scheduler.cron_scheduler import load_state
        
        with patch('builtins.open', mock_open(read_data="{ invalid json")):
            result = load_state()
        
        assert result == {}
    
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_load_state_os_error(self, mock_state_file):
        """Should handle OS errors gracefully."""
        mock_state_file.exists.return_value = True
        
        from ingestion.src.scheduler.cron_scheduler import load_state
        
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            result = load_state()
        
        assert result == {}


# ============================================================================
# Test save_state()
# ============================================================================

class TestSaveState:
    """Test state saving functionality."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.CHECKPOINT_DIR')
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_save_state_creates_directory(self, mock_state_file, mock_checkpoint_dir, sample_state):
        """Should create checkpoint directory if needed."""
        mock_checkpoint_dir.mkdir = MagicMock()
        
        from ingestion.src.scheduler.cron_scheduler import save_state
        
        with patch('builtins.open', mock_open()) as m:
            save_state(sample_state)
        
        mock_checkpoint_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        m.assert_called_once()
    
    @patch('ingestion.src.scheduler.cron_scheduler.CHECKPOINT_DIR')
    @patch('ingestion.src.scheduler.cron_scheduler.STATE_FILE')
    def test_save_state_writes_json(self, mock_state_file, mock_checkpoint_dir, sample_state):
        """Should write JSON to file."""
        from ingestion.src.scheduler.cron_scheduler import save_state
        
        m = mock_open()
        with patch('builtins.open', m):
            save_state(sample_state)
        
        # Verify JSON was written
        handle = m()
        written_data = ''.join(call.args[0] for call in handle.write.call_args_list)
        assert "last_archive_name" in written_data
        assert "lovtidend-avd1-2001-2025.tar.bz2" in written_data


# ============================================================================
# Test fetch_latest_archive_name()
# ============================================================================

class TestFetchLatestArchiveName:
    """Test Lovdata API fetching."""
    
    @patch('requests.get')
    def test_fetch_success(self, mock_get, mock_api_response):
        """Should fetch and return archive name successfully."""
        mock_response = Mock()
        mock_response.json.return_value = mock_api_response
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name
        
        result = fetch_latest_archive_name()
        
        assert result == "lovtidend-avd1-2001-2025.tar.bz2"
        mock_get.assert_called_once()
    
    @patch('requests.get')
    def test_fetch_empty_response(self, mock_get):
        """Should raise error on empty API response."""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name
        
        with pytest.raises(RuntimeError, match="empty response"):
            fetch_latest_archive_name()
    
    @patch('requests.get')
    def test_fetch_http_error(self, mock_get):
        """Should propagate HTTP errors."""
        mock_get.side_effect = Exception("Connection error")
        
        from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name
        
        with pytest.raises(Exception, match="Connection error"):
            fetch_latest_archive_name()
    
    @patch('requests.get')
    def test_fetch_timeout(self, mock_get):
        """Should handle request timeout."""
        from requests.exceptions import Timeout
        mock_get.side_effect = Timeout("Request timed out")
        
        from ingestion.src.scheduler.cron_scheduler import fetch_latest_archive_name
        
        with pytest.raises(Timeout):
            fetch_latest_archive_name()


# ============================================================================
# Test has_new_data()
# ============================================================================

class TestHasNewData:
    """Test change detection logic."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name')
    def test_change_detected(self, mock_fetch, sample_state):
        """Should detect change when archive name differs."""
        mock_fetch.return_value = "lovtidend-avd1-2001-2026.tar.bz2"
        
        from ingestion.src.scheduler.cron_scheduler import has_new_data
        
        changed, latest_name = has_new_data(sample_state)
        
        assert changed is True
        assert latest_name == "lovtidend-avd1-2001-2026.tar.bz2"
    
    @patch('ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name')
    def test_no_change(self, mock_fetch, sample_state):
        """Should detect no change when archive name is same."""
        mock_fetch.return_value = "lovtidend-avd1-2001-2025.tar.bz2"
        
        from ingestion.src.scheduler.cron_scheduler import has_new_data
        
        changed, latest_name = has_new_data(sample_state)
        
        assert changed is False
        assert latest_name == "lovtidend-avd1-2001-2025.tar.bz2"
    
    @patch('ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name')
    def test_first_run_empty_state(self, mock_fetch, empty_state):
        """Should detect change on first run."""
        mock_fetch.return_value = "lovtidend-avd1-2001-2025.tar.bz2"
        
        from ingestion.src.scheduler.cron_scheduler import has_new_data
        
        changed, latest_name = has_new_data(empty_state)
        
        assert changed is True
        assert latest_name == "lovtidend-avd1-2001-2025.tar.bz2"


# ============================================================================
# Test ingestion_job()
# ============================================================================

class TestIngestionJob:
    """Test main job execution."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('ingestion.src.scheduler.cron_scheduler.has_new_data')
    def test_no_change_skips_pipeline(self, mock_has_new, mock_load, mock_save):
        """Should skip pipeline when no change detected."""
        mock_load.return_value = {"last_archive_name": "old.tar.bz2"}
        mock_has_new.return_value = (False, "old.tar.bz2")
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        ingestion_job()
        
        # Verify state was saved with skip status
        assert mock_save.called
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "skipped_no_change"
    
    @patch('ingestion.src.scheduler.cron_scheduler.BATCH_SIZE', 50)
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('ingestion.src.scheduler.cron_scheduler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_change_detected_runs_pipeline(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should run pipeline when change detected."""
        mock_load.return_value = {"total_files_processed": 50}
        mock_has_new.return_value = (True, "new-2026.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        ingestion_job()
        
        # Verify pipeline was called
        mock_pipeline.assert_called_once_with(limit=50)
        
        # Verify state was updated
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_archive_name"] == "new-2026.tar.bz2"
        assert saved_state["last_run_status"] == "success"
        assert saved_state["total_files_processed"] == 100
    
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('ingestion.src.scheduler.cron_scheduler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_pipeline_failure(self, mock_pipeline, mock_has_new, mock_load, mock_save):
        """Should handle pipeline failures gracefully."""
        mock_load.return_value = {}
        mock_has_new.return_value = (True, "new.tar.bz2")
        mock_pipeline.side_effect = RuntimeError("Pipeline crashed")
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        ingestion_job()
        
        # Verify error was recorded
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "pipeline_failed"
        assert saved_state["last_error"] == "Pipeline crashed"
        # Archive name should NOT be updated on failure
        assert "last_archive_name" not in saved_state
    
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('ingestion.src.scheduler.cron_scheduler.has_new_data')
    def test_api_check_failure(self, mock_has_new, mock_load, mock_save):
        """Should handle API check failures."""
        mock_load.return_value = {}
        mock_has_new.side_effect = RuntimeError("API error")
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        ingestion_job()
        
        # Verify error status was saved
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "api_check_failed"


# ============================================================================
# Test on_job_event()
# ============================================================================

class TestOnJobEvent:
    """Test APScheduler event listener."""
    
    def test_on_job_event_success(self):
        """Should handle successful job completion."""
        from ingestion.src.scheduler.cron_scheduler import on_job_event
        
        mock_event = Mock()
        mock_event.exception = None
        
        # Should not raise error
        on_job_event(mock_event)
    
    def test_on_job_event_failure(self):
        """Should handle job failure."""
        from ingestion.src.scheduler.cron_scheduler import on_job_event
        
        mock_event = Mock()
        mock_event.exception = RuntimeError("Job failed")
        
        # Should not raise error (just logs)
        on_job_event(mock_event)


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.BATCH_SIZE', 50)
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('requests.get')
    @patch('ingestion.src.main.run_pipeline')
    def test_full_workflow_with_new_data(
        self, mock_pipeline, mock_get, mock_load, mock_save
    ):
        """Test complete workflow when new data is available."""
        # Setup
        mock_load.return_value = {
            "last_archive_name": "old-2025.tar.bz2",
            "total_files_processed": 100
        }
        
        mock_response = Mock()
        mock_response.json.return_value = [{
            "filename": "new-2026.tar.bz2",
            "size": 123456
        }]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        # Execute
        ingestion_job()
        
        # Verify
        mock_pipeline.assert_called_once_with(limit=50)
        
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_archive_name"] == "new-2026.tar.bz2"
        assert saved_state["last_run_status"] == "success"
        assert saved_state["total_files_processed"] == 150
    
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('requests.get')
    def test_full_workflow_no_change(self, mock_get, mock_load, mock_save):
        """Test complete workflow when no change detected."""
        # Setup
        mock_load.return_value = {
            "last_archive_name": "same-2025.tar.bz2"
        }
        
        mock_response = Mock()
        mock_response.json.return_value = [{
            "filename": "same-2025.tar.bz2",
            "size": 123456
        }]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        # Execute
        ingestion_job()
        
        # Verify - pipeline should NOT be called
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "skipped_no_change"


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @patch('ingestion.src.scheduler.cron_scheduler.fetch_latest_archive_name')
    def test_unicode_archive_name(self, mock_fetch):
        """Should handle unicode characters in archive names."""
        mock_fetch.return_value = "lovdata-åäö-2025.tar.bz2"
        
        from ingestion.src.scheduler.cron_scheduler import has_new_data
        
        changed, latest_name = has_new_data({})
        
        assert latest_name == "lovdata-åäö-2025.tar.bz2"
    
    @patch('ingestion.src.scheduler.cron_scheduler.BATCH_SIZE', 10000)
    @patch('ingestion.src.scheduler.cron_scheduler.save_state')
    @patch('ingestion.src.scheduler.cron_scheduler.load_state')
    @patch('ingestion.src.scheduler.cron_scheduler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_very_large_batch_size(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should handle large batch sizes."""
        mock_load.return_value = {"total_files_processed": 0}
        mock_has_new.return_value = (True, "archive.tar.bz2")
        
        from ingestion.src.scheduler.cron_scheduler import ingestion_job
        
        ingestion_job()
        
        mock_pipeline.assert_called_once_with(limit=10000)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])