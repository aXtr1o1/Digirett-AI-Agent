"""
Unit Tests for trigger_handler.py
===================================
Comprehensive tests for the Lovdata manual trigger handler.

Run with:
    pytest tests/test_trigger_handler.py -v
    pytest tests/test_trigger_handler.py -v --cov=ingestion.src.scheduler.trigger_handler
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from datetime import datetime, timezone
from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_state():
    """Sample state data."""
    return {
        "last_archive_name": "lovtidend-avd1-2001-2025.tar.bz2",
        "last_check_time": "2026-01-31T02:00:00+00:00",
        "last_run_time": "2026-01-31T02:00:01+00:00",
        "last_run_status": "success",
        "total_files_processed": 50
    }


@pytest.fixture
def empty_state():
    """Empty state (first run)."""
    return {}


# ============================================================================
# Test run_trigger() - Dry Run Mode
# ============================================================================

class TestRunTriggerDryRun:
    """Test dry-run functionality."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_dry_run_with_changes(self, mock_has_new, mock_load, mock_save, sample_state):
        """Dry run should not execute pipeline even if changes detected."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (True, "new-2026.tar.bz2")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=True)
        
        # Should NOT save state or run pipeline
        mock_save.assert_not_called()
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_dry_run_no_changes(self, mock_has_new, mock_load, mock_save, sample_state):
        """Dry run should report no changes without running pipeline."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (False, "lovtidend-avd1-2001-2025.tar.bz2")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=True)
        
        # Should NOT save state or run pipeline
        mock_save.assert_not_called()
    
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_dry_run_api_failure(self, mock_has_new, mock_load):
        """Dry run should handle API failures gracefully."""
        mock_load.return_value = {}
        mock_has_new.side_effect = RuntimeError("API error")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        # Should not raise error
        run_trigger(batch_size=50, force=False, dry_run=True)


# ============================================================================
# Test run_trigger() - Normal Mode (No Changes)
# ============================================================================

class TestRunTriggerNoChanges:
    """Test behavior when no changes are detected."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_no_changes_no_force(self, mock_has_new, mock_load, mock_save, sample_state):
        """Should exit without running when no changes and no force."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (False, "lovtidend-avd1-2001-2025.tar.bz2")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=False)
        
        # Should NOT save state or run pipeline
        mock_save.assert_not_called()
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_no_changes_with_force(
        self, mock_pipeline, mock_has_new, mock_load, mock_save, sample_state
    ):
        """Should run pipeline when no changes but force=True."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (False, "lovtidend-avd1-2001-2025.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=True, dry_run=False)
        
        # Should run pipeline
        mock_pipeline.assert_called_once_with(limit=50)
        
        # Should save state
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "success"


# ============================================================================
# Test run_trigger() - Normal Mode (With Changes)
# ============================================================================

class TestRunTriggerWithChanges:
    """Test behavior when changes are detected."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_changes_detected_success(
        self, mock_pipeline, mock_has_new, mock_load, mock_save, sample_state
    ):
        """Should run pipeline when changes detected."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (True, "new-2026.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=100, force=False, dry_run=False)
        
        # Should run pipeline with correct batch size
        mock_pipeline.assert_called_once_with(limit=100)
        
        # Should update state
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_archive_name"] == "new-2026.tar.bz2"
        assert saved_state["last_run_status"] == "success"
        assert saved_state["total_files_processed"] == 150  # 50 + 100
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_changes_detected_pipeline_failure(
        self, mock_pipeline, mock_has_new, mock_load, mock_save, sample_state
    ):
        """Should handle pipeline failures and update state."""
        mock_load.return_value = sample_state
        mock_has_new.return_value = (True, "new-2026.tar.bz2")
        mock_pipeline.side_effect = RuntimeError("Pipeline crashed")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=False)
        
        # Should save error state
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_run_status"] == "pipeline_failed"
        assert saved_state["last_error"] == "Pipeline crashed"


# ============================================================================
# Test run_trigger() - First Run
# ============================================================================

class TestRunTriggerFirstRun:
    """Test behavior on first run (no previous state)."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_first_run_success(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should handle first run correctly."""
        mock_load.return_value = {}
        mock_has_new.return_value = (True, "first-2025.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=False)
        
        # Should run pipeline
        mock_pipeline.assert_called_once_with(limit=50)
        
        # Should initialize state
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_archive_name"] == "first-2025.tar.bz2"
        assert saved_state["total_files_processed"] == 50


# ============================================================================
# Test run_trigger() - Batch Size Variations
# ============================================================================

class TestRunTriggerBatchSize:
    """Test different batch size scenarios."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_custom_batch_size(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should use custom batch size."""
        mock_load.return_value = {"total_files_processed": 0}
        mock_has_new.return_value = (True, "archive.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=200, force=False, dry_run=False)
        
        mock_pipeline.assert_called_once_with(limit=200)
        
        saved_state = mock_save.call_args[0][0]
        assert saved_state["total_files_processed"] == 200
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_small_batch_size(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should handle small batch sizes."""
        mock_load.return_value = {"total_files_processed": 100}
        mock_has_new.return_value = (True, "archive.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=5, force=False, dry_run=False)
        
        mock_pipeline.assert_called_once_with(limit=5)
        
        saved_state = mock_save.call_args[0][0]
        assert saved_state["total_files_processed"] == 105


# ============================================================================
# Test run_trigger() - API Failures
# ============================================================================

class TestRunTriggerAPIFailures:
    """Test handling of API failures."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_api_failure(self, mock_has_new, mock_load, mock_save):
        """Should handle API failures gracefully."""
        mock_load.return_value = {}
        mock_has_new.side_effect = RuntimeError("API connection failed")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        # Should not raise error
        run_trigger(batch_size=50, force=False, dry_run=False)
        
        # Should NOT save state after API failure
        mock_save.assert_not_called()


# ============================================================================
# Test main() CLI
# ============================================================================

class TestMainCLI:
    """Test command-line interface."""
    
    @patch('ingestion.src.scheduler.trigger_handler.run_trigger')
    @patch('sys.argv', ['trigger_handler.py'])
    def test_main_default_args(self, mock_run):
        """Should use default arguments."""
        from ingestion.src.scheduler.trigger_handler import main
        
        main()
        
        mock_run.assert_called_once()
        args = mock_run.call_args[1]
        assert args['dry_run'] is False
        assert args['force'] is False
        assert args['batch_size'] > 0
    
    @patch('ingestion.src.scheduler.trigger_handler.run_trigger')
    @patch('sys.argv', ['trigger_handler.py', '--dry-run'])
    def test_main_dry_run_flag(self, mock_run):
        """Should pass dry-run flag."""
        from ingestion.src.scheduler.trigger_handler import main
        
        main()
        
        args = mock_run.call_args[1]
        assert args['dry_run'] is True
    
    @patch('ingestion.src.scheduler.trigger_handler.run_trigger')
    @patch('sys.argv', ['trigger_handler.py', '--force'])
    def test_main_force_flag(self, mock_run):
        """Should pass force flag."""
        from ingestion.src.scheduler.trigger_handler import main
        
        main()
        
        args = mock_run.call_args[1]
        assert args['force'] is True
    
    @patch('ingestion.src.scheduler.trigger_handler.run_trigger')
    @patch('sys.argv', ['trigger_handler.py', '--batch', '100'])
    def test_main_custom_batch(self, mock_run):
        """Should pass custom batch size."""
        from ingestion.src.scheduler.trigger_handler import main
        
        main()
        
        args = mock_run.call_args[1]
        assert args['batch_size'] == 100
    
    @patch('ingestion.src.scheduler.trigger_handler.run_trigger')
    @patch('sys.argv', ['trigger_handler.py', '--dry-run', '--force', '--batch', '200'])
    def test_main_all_flags(self, mock_run):
        """Should handle all flags together."""
        from ingestion.src.scheduler.trigger_handler import main
        
        main()
        
        args = mock_run.call_args[1]
        assert args['dry_run'] is True
        assert args['force'] is True
        assert args['batch_size'] == 200


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('requests.get')
    @patch('ingestion.src.main.run_pipeline')
    def test_full_workflow_success(
        self, mock_pipeline, mock_get, mock_load, mock_save
    ):
        """Test complete successful workflow."""
        # Setup
        mock_load.return_value = {
            "last_archive_name": "old-2025.tar.bz2",
            "total_files_processed": 50
        }
        
        mock_response = Mock()
        mock_response.json.return_value = [{
            "filename": "new-2026.tar.bz2",
            "size": 123456
        }]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        # Execute
        run_trigger(batch_size=100, force=False, dry_run=False)
        
        # Verify
        mock_pipeline.assert_called_once_with(limit=100)
        
        saved_state = mock_save.call_args[0][0]
        assert saved_state["last_archive_name"] == "new-2026.tar.bz2"
        assert saved_state["last_run_status"] == "success"
        assert saved_state["total_files_processed"] == 150
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('requests.get')
    @patch('ingestion.src.main.run_pipeline')
    def test_full_workflow_force_no_change(
        self, mock_pipeline, mock_get, mock_load, mock_save
    ):
        """Test forced run when no changes."""
        # Setup
        mock_load.return_value = {
            "last_archive_name": "same-2025.tar.bz2",
            "total_files_processed": 100
        }
        
        mock_response = Mock()
        mock_response.json.return_value = [{
            "filename": "same-2025.tar.bz2",
            "size": 123456
        }]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        # Execute with force
        run_trigger(batch_size=50, force=True, dry_run=False)
        
        # Verify - pipeline should run even without changes
        mock_pipeline.assert_called_once_with(limit=50)


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_zero_batch_size(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should handle zero batch size."""
        mock_load.return_value = {"total_files_processed": 0}
        mock_has_new.return_value = (True, "archive.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=0, force=False, dry_run=False)
        
        # Should still call pipeline with 0
        mock_pipeline.assert_called_once_with(limit=0)
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    def test_corrupted_state_file(self, mock_has_new, mock_load, mock_save):
        """Should handle corrupted state gracefully."""
        mock_load.return_value = {"corrupted": True}  # Missing expected fields
        mock_has_new.return_value = (True, "archive.tar.bz2")
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        with patch('ingestion.src.main.run_pipeline'):
            run_trigger(batch_size=50, force=False, dry_run=False)
        
        # Should not crash
        saved_state = mock_save.call_args[0][0]
        assert "last_run_status" in saved_state


# ============================================================================
# State Management Tests
# ============================================================================

class TestStateManagement:
    """Test state persistence and updates."""
    
    @patch('ingestion.src.scheduler.trigger_handler.save_state')
    @patch('ingestion.src.scheduler.trigger_handler.load_state')
    @patch('ingestion.src.scheduler.trigger_handler.has_new_data')
    @patch('ingestion.src.main.run_pipeline')
    def test_state_updates_on_success(
        self, mock_pipeline, mock_has_new, mock_load, mock_save
    ):
        """Should update all relevant fields on success."""
        mock_load.return_value = {
            "last_archive_name": "old.tar.bz2",
            "total_files_processed": 100
        }
        mock_has_new.return_value = (True, "new.tar.bz2")
        mock_pipeline.return_value = None
        
        from ingestion.src.scheduler.trigger_handler import run_trigger
        
        run_trigger(batch_size=50, force=False, dry_run=False)
        
        saved_state = mock_save.call_args[0][0]
        assert "last_check_time" in saved_state
        assert "last_run_time" in saved_state
        assert saved_state["last_archive_name"] == "new.tar.bz2"
        assert saved_state["last_run_status"] == "success"
        assert saved_state["total_files_processed"] == 150


if __name__ == "__main__":
    pytest.main([__file__, "-v"])