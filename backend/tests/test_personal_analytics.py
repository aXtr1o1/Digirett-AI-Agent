import sys
import pathlib
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure backend package can be imported
_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Mock third-party dependencies before loading main app
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
    "stripe", "jinja2",
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

from fastapi.testclient import TestClient
from main import app
from core.auth import ClerkUser, require_db_role, get_current_user
from services.hitl_service import HitlService

class MockSupabaseQuery:
    def __init__(self, data=None):
        self.data = data or []
        self._action = None

    def select(self, *args, **kwargs): return self
    
    def eq(self, field, value, *args, **kwargs):
        if field == "action":
            self._action = value
        return self
        
    def in_(self, *args, **kwargs): return self
    def gte(self, *args, **kwargs): return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    
    def execute(self, *args, **kwargs):
        res = MagicMock()
        if self._action == "ticket.unassigned":
            res.data = []
        else:
            res.data = self.data
        res.count = len(res.data)
        return res

class TestPersonalAnalytics(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.hitl_service = HitlService(self.mock_supabase)
        
        # Test lawyer clerk user
        self.lawyer_clerk_user = ClerkUser({
            "clerk_user_id": "lawyer_clerk_id",
            "email": "lawyer@example.com",
            "role": "lawyer",
            "db_role": "lawyer",
            "db_user_id": "lawyer_internal_id",
            "status": "active"
        })

    def test_get_lawyer_personal_analytics(self):
        def table_mock_side_effect(table_name):
            if table_name == "hitl_tickets":
                return MockSupabaseQuery([
                    {
                        "ticket_id": "t1",
                        "created_at": "2026-07-04T09:30:00.000000Z",
                        "assigned_at": "2026-07-04T10:00:00.000000Z",
                        "resolved_at": "2026-07-04T12:00:00.000000Z"
                    }
                ])
            elif table_name == "ticket_messages":
                return MockSupabaseQuery([
                    {
                        "ticket_id": "t1",
                        "created_at": "2026-07-04T10:30:00.000000Z"
                    }
                ])
            elif table_name == "consultation_ratings":
                return MockSupabaseQuery([
                    {"rating": 5},
                    {"rating": 4}
                ])
            elif table_name == "audit_logs":
                return MockSupabaseQuery([
                    {"id": 1}
                ])
            elif table_name == "conversations":
                return MockSupabaseQuery([
                    {"conversation_id": "c1"},
                    {"conversation_id": "c2"}
                ])
            elif table_name == "messages":
                return MockSupabaseQuery([
                    {"message_id": "m1"},
                    {"message_id": "m2"}
                ])
            return MockSupabaseQuery()
            
        self.mock_supabase.table.side_effect = table_mock_side_effect
        
        # Run analytics method directly
        stats = self.hitl_service.get_lawyer_personal_analytics("lawyer_internal_id")
        
        self.assertEqual(stats["total_cases_handled"], 1)
        self.assertEqual(stats["avg_resolution_time_seconds"], 7200) # 2 hours
        self.assertEqual(stats["avg_response_time_seconds"], 1800) # 30 mins
        self.assertEqual(stats["average_rating"], 4.5) # (5+4)/2
        self.assertEqual(stats["total_conversations"], 2)
        self.assertEqual(stats["total_escalations"], 1)
        self.assertEqual(stats["total_user_messages"], 2)
        self.assertEqual(stats["total_bot_messages"], 2)
        self.assertEqual(stats["acceptance_rate_percentage"], 100.0)

    @patch("api.routes.hitl.require_db_role")
    @patch("api.routes.hitl._user_service")
    @patch("api.routes.hitl._hitl_service")
    def test_endpoint_personal_analytics(self, mock_hitl_service, mock_user_service, mock_require_role):
        # Setup mock authentication & service resolution
        mock_require_role.return_value = lambda: self.lawyer_clerk_user
        mock_user_service.get_user_id_from_clerk_id.return_value = "lawyer_internal_id"
        mock_hitl_service.get_lawyer_personal_analytics.return_value = {
            "total_cases_handled": 10,
            "cases_this_week": 2,
            "avg_response_time_seconds": 600,
            "avg_resolution_time_seconds": 14400,
            "acceptance_rate_percentage": 90.0,
            "average_rating": 4.8
        }
        
        client = TestClient(app)
        
        # Override dependency
        app.dependency_overrides[require_db_role("lawyer", "admin")] = lambda: self.lawyer_clerk_user
        app.dependency_overrides[get_current_user] = lambda: self.lawyer_clerk_user
        
        response = client.get("/api/v1/hitl/lawyer/analytics/personal")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_cases_handled"], 10)
        self.assertEqual(data["average_rating"], 4.8)
        self.assertEqual(data["acceptance_rate_percentage"], 90.0)
        
        app.dependency_overrides.clear()

if __name__ == "__main__":
    unittest.main()
