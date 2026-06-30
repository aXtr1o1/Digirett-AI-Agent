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

class TestRatingsSystem(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        app.dependency_overrides = {}
        
        # Mock get_supabase globally and locally inside the ratings router
        import db.supabase_client
        import api.routes.ratings
        self.mock_supabase = MagicMock()
        self.mock_supabase.execute_query.side_effect = lambda query, **kwargs: query.execute()
        db.supabase_client.get_supabase = lambda: self.mock_supabase
        api.routes.ratings.get_supabase = lambda: self.mock_supabase
        
        # Setup test roles users
        self.standard_user = ClerkUser({
            "clerk_user_id": "user_clerk_id",
            "email": "user@example.com",
            "role": "user",
            "db_role": "user",
            "status": "active"
        })
        self.lawyer_user = ClerkUser({
            "clerk_user_id": "lawyer_clerk_id",
            "email": "lawyer@digirett.no",
            "role": "lawyer",
            "db_role": "lawyer",
            "status": "active"
        })

    def _set_performer(self, user: ClerkUser):
        app.dependency_overrides[get_current_user] = lambda: user

    def test_submit_rating_success(self):
        """Standard user should successfully rate their own resolved ticket."""
        self._set_performer(self.standard_user)
        
        # 1. Mock ticket lookup (owner matches, status resolved)
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "status": "resolved",
                "assigned_lawyer_id": "lawyer_internal_id"
            }
        ])
        
        # 2. Mock user profile lookup (returns internal user ID)
        self.mock_supabase.table("users").select().eq().single().execute.return_value = MagicMock(data={
            "user_id": "user_internal_id"
        })
        
        # 3. Mock rating insertion
        self.mock_supabase.table("consultation_ratings").upsert().execute.return_value = MagicMock(data=[{}])

        payload = {"ticket_id": "ticket_123", "rating": 5, "comment": "Excellent consultation."}
        response = self.client.post("/api/v1/ratings", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")

    def test_submit_rating_forbidden_non_owner(self):
        """User cannot rate a ticket owned by another user."""
        self._set_performer(self.standard_user)
        
        # Mock ticket owned by 'different_user_id'
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "different_user_id",
                "status": "resolved",
                "assigned_lawyer_id": "lawyer_internal_id"
            }
        ])
        
        self.mock_supabase.table("users").select().eq().single().execute.return_value = MagicMock(data={
            "user_id": "user_internal_id"
        })

        payload = {"ticket_id": "ticket_123", "rating": 5}
        response = self.client.post("/api/v1/ratings", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("You can only rate your own tickets", response.json()["message"])

    def test_submit_rating_invalid_state(self):
        """User cannot rate a ticket that is not resolved or closed."""
        self._set_performer(self.standard_user)
        
        # Mock ticket status 'open'
        self.mock_supabase.table("hitl_tickets").select().eq().execute.return_value = MagicMock(data=[
            {
                "ticket_id": "ticket_123",
                "user_id": "user_internal_id",
                "status": "open",
                "assigned_lawyer_id": "lawyer_internal_id"
            }
        ])
        
        self.mock_supabase.table("users").select().eq().single().execute.return_value = MagicMock(data={
            "user_id": "user_internal_id"
        })

        payload = {"ticket_id": "ticket_123", "rating": 5}
        response = self.client.post("/api/v1/ratings", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("You can only rate tickets that are resolved or closed", response.json()["message"])

if __name__ == "__main__":
    unittest.main()
