import sys
import pathlib
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta, timezone

# Fix sys.path so it finds backend packages
_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Mock third-party packages before importing LibraryService
import types
for _m in [
    "pymilvus", "redis", "redis.connection",
    "supabase", "langchain_openai",
    "langchain_core", "langchain_core.messages",
    "opentelemetry", "opentelemetry.trace",
    "opentelemetry.sdk", "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.instrumentation.fastapi",
    "slowapi", "slowapi.util", "slowapi.errors",
    "boto3", "telemetry", "telemetry.tracing",
]:
    sys.modules.setdefault(_m, MagicMock())

# Setup mock config settings
if "config" in sys.modules:
    import config
    _s = config.settings
else:
    _s = MagicMock()
    _fake_config = types.ModuleType("config")
    _fake_config.settings = _s
    sys.modules["config"] = _fake_config

from services.library_service import LibraryService

class TestLibraryService(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.mock_table_builder = MagicMock()
        self.mock_supabase.table.return_value = self.mock_table_builder
        self.mock_supabase._get.return_value = self.mock_supabase
        
        # Mock Storage client
        self.mock_storage = MagicMock()
        self.mock_supabase.storage.from_.return_value = self.mock_storage
        
        self.service = LibraryService(supabase_client=self.mock_supabase)

    def test_save_document_success_pdf(self):
        # Mock insert response
        insert_res = MagicMock()
        insert_res.data = [{
            "id": "doc-id-123",
            "user_id": "user-123",
            "file_name": "test.pdf",
            "file_type": "pdf",
            "char_count": 0,
            "note": "my note",
            "storage_path": "library/doc-id-123.pdf",
            "created_at": "2026-06-30T12:00:00Z",
            "expires_at": "2026-07-30T12:00:00Z"
        }]
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = insert_res
        
        # Act
        result = self.service.save_document(
            user_id="user-123",
            file_name="test.pdf",
            file_type="pdf",
            file_bytes=b"dummy PDF content",
            note="my note"
        )
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "doc-id-123")
        self.mock_storage.upload.assert_called_once()
        self.mock_table_builder.insert.assert_called_once()

    def test_save_document_success_docx(self):
        # Mock insert response
        insert_res = MagicMock()
        insert_res.data = [{
            "id": "doc-id-456",
            "user_id": "user-123",
            "file_name": "test.docx",
            "file_type": "docx",
            "char_count": 0,
            "note": "docx note",
            "storage_path": "library/doc-id-456.docx",
            "created_at": "2026-06-30T12:00:00Z",
            "expires_at": "2026-07-30T12:00:00Z"
        }]
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = insert_res
        
        # Act
        result = self.service.save_document(
            user_id="user-123",
            file_name="test.docx",
            file_type="docx",
            file_bytes=b"dummy DOCX content",
            note="docx note"
        )
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "doc-id-456")
        self.assertEqual(result["file_type"], "docx")

    def test_save_document_empty_note_defaults(self):
        insert_res = MagicMock()
        insert_res.data = [{
            "id": "doc-id-789",
            "user_id": "user-123",
            "file_name": "test.pdf",
            "file_type": "pdf",
            "char_count": 0,
            "note": "",
            "storage_path": "library/doc-id-789.pdf",
            "created_at": "2026-06-30T12:00:00Z",
            "expires_at": "2026-07-30T12:00:00Z"
        }]
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = insert_res
        
        # Act
        result = self.service.save_document(
            user_id="user-123",
            file_name="test.pdf",
            file_type="pdf",
            file_bytes=b"dummy PDF content",
            note=None  # note is None
        )
        
        # Assert
        self.assertEqual(result["note"], "")
        # Check what was passed to insert
        insert_args = self.mock_table_builder.insert.call_args[0][0]
        self.assertEqual(insert_args["note"], "")

    def test_save_document_parsing_failure_recovery(self):
        insert_res = MagicMock()
        insert_res.data = [{
            "id": "doc-id-fail-parse",
            "user_id": "user-123",
            "file_name": "corrupt.pdf",
            "file_type": "pdf",
            "char_count": 0,
            "note": "parsed note",
            "storage_path": "library/doc-id-fail-parse.pdf",
            "created_at": "2026-06-30T12:00:00Z",
            "expires_at": "2026-07-30T12:00:00Z"
        }]
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = insert_res
        
        # Make fitz.open raise exception
        with patch("fitz.open", side_effect=Exception("Corrupt file stream")):
            # Act
            result = self.service.save_document(
                user_id="user-123",
                file_name="corrupt.pdf",
                file_type="pdf",
                file_bytes=b"corrupt binary data",
                note="parsed note"
            )
        
        # Assert - should recover and insert the document details with 0 char_count
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], "doc-id-fail-parse")
        insert_args = self.mock_table_builder.insert.call_args[0][0]
        self.assertEqual(insert_args["char_count"], 0)
        self.assertEqual(insert_args["extracted_text"], "")

    def test_save_document_storage_upload_failure(self):
        # Make storage upload raise an exception
        self.mock_storage.upload.side_effect = Exception("S3 bucket write permission denied")
        
        # Act & Assert - should raise the exception to the caller
        with self.assertRaises(Exception) as context:
            self.service.save_document(
                user_id="user-123",
                file_name="test.pdf",
                file_type="pdf",
                file_bytes=b"dummy content"
            )
        self.assertIn("S3 bucket write permission denied", str(context.exception))
        self.mock_table_builder.insert.assert_not_called()

    def test_get_library_documents_triggers_cleanup(self):
        # Mock cleanup SELECT result (returns 1 expired item)
        select_res_1 = MagicMock()
        select_res_1.data = [{"id": "expired-id", "storage_path": "library/expired.pdf"}]
        
        # Mock final list result
        select_res_2 = MagicMock()
        select_res_2.data = [{"id": "active-id", "file_name": "active.pdf"}]
        
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.lt.return_value = self.mock_table_builder
        self.mock_table_builder.order.return_value = self.mock_table_builder
        self.mock_table_builder.delete.return_value = self.mock_table_builder
        
        self.mock_table_builder.execute.side_effect = [select_res_1, MagicMock(), select_res_2]
        
        # Act
        results = self.service.get_library_documents("user-123")
        
        # Assert
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "active-id")
        
        # Verify file deleted from storage
        self.mock_storage.remove.assert_called_once_with(["library/expired.pdf"])
        # Verify DB delete called
        self.mock_table_builder.delete.assert_called_once()

    def test_get_library_documents_partial_cleanup_success(self):
        # Mock 1 expired item
        select_res_1 = MagicMock()
        select_res_1.data = [{"id": "expired-id", "storage_path": "library/expired.pdf"}]
        
        # Mock final list result
        select_res_2 = MagicMock()
        select_res_2.data = []
        
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.lt.return_value = self.mock_table_builder
        self.mock_table_builder.order.return_value = self.mock_table_builder
        self.mock_table_builder.delete.return_value = self.mock_table_builder
        
        # Make storage remove raise exception
        self.mock_storage.remove.side_effect = Exception("Connection reset by peer")
        
        self.mock_table_builder.execute.side_effect = [select_res_1, MagicMock(), select_res_2]
        
        # Act
        results = self.service.get_library_documents("user-123")
        
        # Assert - cleanup failure in storage shouldn't block the database cleanup and final fetch
        self.assertEqual(results, [])
        self.mock_table_builder.delete.assert_called_once()

    def test_delete_library_document_success(self):
        # Mock single fetch for storage path
        single_res = MagicMock()
        single_res.data = {"storage_path": "library/del.pdf"}
        
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.single.return_value = self.mock_table_builder
        self.mock_table_builder.delete.return_value = self.mock_table_builder
        
        self.mock_table_builder.execute.side_effect = [single_res, MagicMock()]
        
        # Act
        success = self.service.delete_library_document("doc-123", "user-123")
        
        # Assert
        self.assertTrue(success)
        self.mock_storage.remove.assert_called_once_with(["library/del.pdf"])
        self.mock_table_builder.delete.assert_called_once()

    def test_delete_library_document_non_existent(self):
        # Mock query returning no data
        single_res = MagicMock()
        single_res.data = None
        
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.single.return_value = self.mock_table_builder
        self.mock_table_builder.delete.return_value = self.mock_table_builder
        
        self.mock_table_builder.execute.side_effect = [single_res, single_res, MagicMock()]
        
        # Act
        success = self.service.delete_library_document("non-existent-id", "user-123")
        
        # Assert - should return True (idempotent behaviour) and not attempt storage removal
        self.assertTrue(success)
        self.mock_storage.remove.assert_not_called()
        self.mock_table_builder.delete.assert_called_once()

    def test_update_library_document_note_success(self):
        update_res = MagicMock()
        update_res.data = [{"id": "doc-123", "note": "new note text"}]
        
        self.mock_table_builder.update.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = update_res
        
        # Act
        result = self.service.update_library_document_note("doc-123", "user-123", "new note text")
        
        # Assert
        self.assertIsNotNone(result)
        self.assertEqual(result["note"], "new note text")
        self.mock_table_builder.update.assert_called_once_with({"note": "new note text"})

    def test_update_library_document_note_non_existent(self):
        update_res = MagicMock()
        update_res.data = []
        
        self.mock_table_builder.update.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = update_res
        
        # Act
        result = self.service.update_library_document_note("non-existent-id", "user-123", "new note text")
        
        # Assert
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main(verbosity=2)
