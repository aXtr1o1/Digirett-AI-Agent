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

class TestLibraryServiceCleanup(unittest.TestCase):

    def test_get_saved_messages_performs_cleanup(self):
        # Arrange
        mock_supabase = MagicMock()
        
        # We need to construct a chain mock for both the delete query and the select query.
        # Let's create helper functions or use MagicMock side-effects.
        delete_chain = MagicMock()
        select_chain = MagicMock()
        
        # Configure table() to return the appropriate chain
        # When table("saved_messages") is called:
        # First call is for cleanup (.delete())
        # Second call is for fetching (.select())
        mock_table_builder = MagicMock()
        mock_supabase.table.return_value = mock_table_builder
        
        # Set up delete chain
        mock_table_builder.delete.return_value = delete_chain
        delete_chain.eq.return_value = delete_chain
        delete_chain.lt.return_value = delete_chain
        
        # Set up select chain
        mock_table_builder.select.return_value = select_chain
        select_chain.eq.return_value = select_chain
        select_chain.order.return_value = select_chain
        
        # Mock responses
        delete_execute_result = MagicMock()
        delete_execute_result.data = []
        delete_chain.execute.return_value = delete_execute_result
        
        select_execute_result = MagicMock()
        # Mock returned data where one item is returned
        select_execute_result.data = [
            {
                "id": "saved-id-1",
                "message_id": "msg-id-1",
                "note": "some note",
                "saved_at": "2026-06-25T12:00:00Z",
                "messages": {
                    "message_id": "msg-id-1",
                    "role": "user",
                    "content": "Hello world",
                    "sources": [],
                    "metadata": {},
                    "created_at": "2026-06-25T11:00:00Z",
                    "conversation_id": "conv-id-1",
                    "conversations": {
                        "title": "My Title"
                    }
                }
            }
        ]
        select_chain.execute.return_value = select_execute_result
        
        service = LibraryService(supabase_client=mock_supabase)
        user_id = "test-user-uuid"

        # Act
        results = service.get_saved_messages(user_id)

        # Assert
        # 1. Verify delete chain was called to remove items older than 30 days
        mock_table_builder.delete.assert_called_once()
        delete_chain.eq.assert_any_call("user_id", user_id)
        
        # Retrieve the arguments passed to .lt() in the delete chain
        # .lt("saved_at", thirty_days_ago)
        lt_args, lt_kwargs = delete_chain.lt.call_args
        self.assertEqual(lt_args[0], "saved_at")
        
        # Parse the iso timestamp to ensure it's around 30 days ago
        saved_at_limit_str = lt_args[1]
        saved_at_limit = datetime.fromisoformat(saved_at_limit_str)
        now = datetime.now(timezone.utc)
        expected_limit = now - timedelta(days=30)
        
        # Check difference is very small (within 5 seconds)
        time_diff = abs((expected_limit - saved_at_limit).total_seconds())
        self.assertLess(time_diff, 5.0)

        # 2. Verify select query was executed
        mock_table_builder.select.assert_called_once_with(
            "*, messages(message_id, role, content, sources, metadata, created_at, conversation_id, conversations(title))"
        )
        select_chain.eq.assert_called_once_with("user_id", user_id)
        select_chain.order.assert_called_once_with("saved_at", desc=True)
        
        # 3. Verify results format
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message_id"], "msg-id-1")
        self.assertEqual(results[0]["conversation_title"], "My Title")

    def test_cleanup_exception_does_not_prevent_fetch(self):
        # Verify that if cleanup database operation fails, we still query and return library items
        mock_supabase = MagicMock()
        mock_table_builder = MagicMock()
        mock_supabase.table.return_value = mock_table_builder
        
        # Make delete() fail
        mock_table_builder.delete.side_effect = Exception("Database transient failure")
        
        # Setup select chain
        select_chain = MagicMock()
        mock_table_builder.select.return_value = select_chain
        select_chain.eq.return_value = select_chain
        select_chain.order.return_value = select_chain
        
        select_execute_result = MagicMock()
        select_execute_result.data = []
        select_chain.execute.return_value = select_execute_result
        
        service = LibraryService(supabase_client=mock_supabase)
        
        # Act
        results = service.get_saved_messages("test-user-uuid")
        
        # Assert
        # The function should swallow the exception log it as warning, and successfully fetch the items
        self.assertEqual(results, [])
        mock_table_builder.select.assert_called_once()

if __name__ == "__main__":
    unittest.main(verbosity=2)
