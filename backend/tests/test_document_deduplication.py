import sys
import pathlib
import unittest
from unittest.mock import MagicMock, patch

# Fix sys.path so it finds backend packages
_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Mock third-party packages before importing DocumentService
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
    _s.DOC_MAX_PER_SESSION = 2
    _s.DOC_SESSION_TTL_SECONDS = 14400
    _fake_config = types.ModuleType("config")
    _fake_config.settings = _s
    sys.modules["config"] = _fake_config

from services.document_service import DocumentService

class TestDocumentDeduplication(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.mock_table_builder = MagicMock()
        self.mock_supabase.table.return_value = self.mock_table_builder
        self.mock_supabase._get.return_value = self.mock_supabase
        
        # Mock Storage client
        self.mock_storage = MagicMock()
        self.mock_supabase.storage.from_.return_value = self.mock_storage
        
        # Mock Redis client
        self.mock_redis = MagicMock()
        self.mock_redis._get.return_value = self.mock_redis
        
        self.service = DocumentService(
            supabase_client=self.mock_supabase,
            redis_client=self.mock_redis
        )
        
        # Patch check_doc_limit, parse_document, detect_document_language
        self.service.check_doc_limit = MagicMock(return_value=(True, 2))
        self.service.parse_document = MagicMock(return_value="parsed doc content")
        self.service.detect_document_language = MagicMock(return_value="en")
        
        # Patch session / quota methods
        self.service.get_quota_session = MagicMock(return_value={"doc_count": 0})
        self.service._save_quota_session = MagicMock()
        self.service.get_or_create_session = MagicMock(return_value={
            "session_id": "session-123",
            "doc_count": 0,
            "docs": []
        })
        self.service._save_session = MagicMock()

    def test_store_document_new(self):
        # 1. Mock Supabase responses: uploaded_files lookup empty
        lookup_res = MagicMock()
        lookup_res.data = []
        
        insert_res = MagicMock()
        insert_res.data = [{"document_id": "new-doc-id"}]
        
        # Setup method chaining calls
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.side_effect = [lookup_res, insert_res, insert_res, insert_res]

        # Act
        meta = self.service.store_document(
            conversation_id="conv-123",
            user_id="user-123",
            file_bytes=b"dummy bytes content",
            filename="document.pdf"
        )

        # Assert
        self.assertIsNotNone(meta)
        self.assertFalse(meta["duplicate"])
        self.service.parse_document.assert_called_once()
        self.mock_storage.upload.assert_called_once()

    def test_store_document_duplicate(self):
        # 1. Mock Supabase responses: uploaded_files lookup returns matched file with summary
        lookup_res = MagicMock()
        lookup_res.data = [{
            "file_hash": "dummy_hash",
            "extracted_text": "parsed doc content",
            "char_count": 18,
            "storage_path": "uploads/dummy_hash.pdf",
            "summary": "This is a cached mock summary."
        }]
        
        insert_res = MagicMock()
        insert_res.data = [{"document_id": "existing-doc-id"}]
        
        self.mock_table_builder.select.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.insert.return_value = self.mock_table_builder
        self.mock_table_builder.execute.side_effect = [lookup_res, insert_res, insert_res, insert_res]

        # Reset mocks
        self.service.parse_document.reset_mock()
        self.mock_storage.upload.reset_mock()

        # Act
        meta = self.service.store_document(
            conversation_id="conv-123",
            user_id="user-123",
            file_bytes=b"dummy bytes content",
            filename="document.pdf"
        )

        # Assert
        self.assertIsNotNone(meta)
        self.assertTrue(meta["duplicate"])
        self.assertEqual(meta["summary"], "This is a cached mock summary.")
        # Parsing and uploading must be bypassed entirely
        self.service.parse_document.assert_not_called()
        self.mock_storage.upload.assert_not_called()

    def test_update_file_summary(self):
        # Mock update response
        update_res = MagicMock()
        self.mock_table_builder.update.return_value = self.mock_table_builder
        self.mock_table_builder.eq.return_value = self.mock_table_builder
        self.mock_table_builder.execute.return_value = update_res

        # Act
        self.service.update_file_summary("dummy_hash", "new summary content")

        # Assert
        self.mock_table_builder.update.assert_called_once_with({"summary": "new summary content"})
        self.mock_table_builder.eq.assert_called_once_with("file_hash", "dummy_hash")

if __name__ == '__main__':
    unittest.main()
