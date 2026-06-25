import sys
import pathlib
import unittest
from unittest.mock import MagicMock, AsyncMock

# Fix sys.path so it finds backend packages
_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Mock third-party packages before importing main
import types
class MockRateLimitExceeded(Exception):
    pass

_slowapi_errors = types.ModuleType("slowapi.errors")
_slowapi_errors.RateLimitExceeded = MockRateLimitExceeded
sys.modules["slowapi.errors"] = _slowapi_errors

for _m in [
    "pymilvus", "redis", "redis.connection",
    "supabase", "langchain_openai",
    "langchain_core", "langchain_core.messages",
    "opentelemetry", "opentelemetry.trace",
    "opentelemetry.sdk", "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation.fastapi",
    "slowapi", "slowapi.util",
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

_s.AZURE_OPENAI_ENDPOINT = "https://fake.openai.azure.com"
_s.AZURE_OPENAI_API_KEY = "fake-key"
_s.AZURE_OPENAI_DEPLOYMENT = "gpt-4o-mini"
_s.LOG_LEVEL = "INFO"
_s.ALLOWED_ORIGINS = ["*"]
_s.ROOT_PATH = ""
_s.SUPABASE_URL = "https://fake.supabase.co"
_s.SUPABASE_KEY = "fake-key"
_s.SUPABASE_SERVICE_ROLE_KEY = "fake-key"
_s.MILVUS_HOST = "localhost"
_s.MILVUS_PORT = 19530
_s.MILVUS_COLLECTION = "lovdata"
_s.REDIS_HOST = "localhost"
_s.REDIS_PORT = 6379
_s.REDIS_DB = 0
_s.REDIS_PASSWORD = ""
_s.SMTP_HOST = "localhost"
_s.SMTP_PORT = 25
_s.SMTP_USER = ""
_s.SMTP_PASS = ""
_s.DOC_MAX_PER_SESSION = 2
_s.DOC_MAX_TURNS_PER_SESSION = 10
_s.DOC_MAX_TOKENS_PER_SESSION = 100000
_s.DOC_SESSION_TTL_SECONDS = 14400
_s.INVITE_FROM_EMAIL = "noreply@digirett.no"
_s.ADMIN_ALERT_EMAIL = "admin@digirett.no"
_s.OPENAI_TEMPERATURE = 0.4

from fastapi.testclient import TestClient
from main import app
from core.auth import ClerkUser, get_current_user

class TestTicketMessages(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides = {}
        
        # Mock get_supabase globally and locally inside routers
        import db.supabase_client
        import api.routes.ticket_messages
        self.mock_supabase = MagicMock()
        db.supabase_client.get_supabase = lambda: self.mock_supabase
        api.routes.ticket_messages.get_supabase = lambda: self.mock_supabase
        
        # Setup test roles users
        self.standard_user = ClerkUser({
            "clerk_user_id": "user_clerk_id",
            "email": "user@example.com",
            "role": "user",
            "db_role": "user",
            "db_user_id": "user_internal_id",
            "status": "active"
        })
        
        self.assigned_lawyer = ClerkUser({
            "clerk_user_id": "lawyer_clerk_id",
            "email": "lawyer@digirett.no",
            "role": "lawyer",
            "db_role": "lawyer",
            "db_user_id": "lawyer_internal_id",
            "status": "active"
        })
        
        self.unassigned_lawyer = ClerkUser({
            "clerk_user_id": "other_lawyer_clerk_id",
            "email": "other_lawyer@digirett.no",
            "role": "lawyer",
            "db_role": "lawyer",
            "db_user_id": "other_lawyer_internal_id",
            "status": "active"
        })
        
        self.admin_user = ClerkUser({
            "clerk_user_id": "admin_clerk_id",
            "email": "admin@digirett.no",
            "role": "admin",
            "db_role": "admin",
            "db_user_id": "admin_internal_id",
            "status": "active"
        })

    def _set_performer(self, user: ClerkUser):
        app.dependency_overrides[get_current_user] = lambda: user

    def test_get_messages_success_owner(self):
        """Ticket owner should successfully view messages."""
        self._set_performer(self.standard_user)
        
        # 1. Mock ticket details lookup
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])
        
        # 2. Mock messages list query
        self.mock_supabase.table("ticket_messages").select().eq().order().execute.return_value = MagicMock(data=[
            {
                "message_id": "msg_1",
                "ticket_id": "ticket_123",
                "sender_id": "lawyer_internal_id",
                "sender_role": "lawyer",
                "content": "Hello",
                "is_read": True
            }
        ])

        response = self.client.get("/api/v1/hitl/tickets/ticket_123/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)
        self.assertEqual(response.json()[0]["content"], "Hello")

    def test_get_messages_success_lawyer(self):
        """Assigned lawyer should successfully view messages."""
        self._set_performer(self.assigned_lawyer)
        
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])
        
        self.mock_supabase.table("ticket_messages").select().eq().order().execute.return_value = MagicMock(data=[])

        response = self.client.get("/api/v1/hitl/tickets/ticket_123/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_get_messages_forbidden_other_user(self):
        """Other users cannot view the ticket's messages."""
        self._set_performer(self.standard_user)
        
        # Ticket is owned by 'different_user_id'
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "different_user_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])

        response = self.client.get("/api/v1/hitl/tickets/ticket_123/messages")
        self.assertEqual(response.status_code, 403)
        self.assertIn("Unauthorized", response.json()["message"])

    def test_get_messages_forbidden_unassigned_lawyer(self):
        """Unassigned lawyer cannot view the ticket's messages."""
        self._set_performer(self.unassigned_lawyer)
        
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])

        response = self.client.get("/api/v1/hitl/tickets/ticket_123/messages")
        self.assertEqual(response.status_code, 403)

    def test_send_message_success(self):
        """Assigned lawyer can post message successfully."""
        self._set_performer(self.assigned_lawyer)
        
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])
        
        self.mock_supabase.table("ticket_messages").insert().execute.return_value = MagicMock(data=[
            {
                "message_id": "msg_new",
                "ticket_id": "ticket_123",
                "sender_id": "lawyer_internal_id",
                "sender_role": "lawyer",
                "content": "Here is my advice",
                "is_read": False
            }
        ])

        payload = {"content": "Here is my advice"}
        response = self.client.post("/api/v1/hitl/tickets/ticket_123/messages", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["content"], "Here is my advice")

    def test_mark_as_read_success(self):
        """Mark as read updates the database successfully."""
        self._set_performer(self.standard_user)
        
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "assigned_lawyer_id": "lawyer_internal_id",
                "status": "assigned"
            }
        ])
        
        self.mock_supabase.table("ticket_messages").update().eq().eq().eq().execute.return_value = MagicMock(data=[
            {"message_id": "msg_unread", "is_read": True}
        ])

        response = self.client.patch("/api/v1/hitl/tickets/ticket_123/messages/read")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

if __name__ == "__main__":
    unittest.main()
