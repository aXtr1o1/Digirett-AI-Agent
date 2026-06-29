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
import asyncio
from unittest.mock import MagicMock, AsyncMock

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

from fastapi.testclient import TestClient
from main import app
from core.auth import ClerkUser, get_current_user
from services.hitl_service import HitlService
from services.brief_service import BriefService

class TestHitlEnhancements(unittest.TestCase):

    def setUp(self):
        self.mock_supabase = MagicMock()
        self.hitl_service = HitlService(self.mock_supabase)
        
        # Test roles
        self.lawyer_user = ClerkUser({
            "clerk_user_id": "lawyer_clerk_id",
            "email": "lawyer@example.com",
            "role": "lawyer",
            "db_role": "lawyer",
            "db_user_id": "lawyer_internal_id",
            "status": "active"
        })
        self.admin_user = ClerkUser({
            "clerk_user_id": "admin_clerk_id",
            "email": "admin@example.com",
            "role": "admin",
            "db_role": "admin",
            "db_user_id": "admin_internal_id",
            "status": "active"
        })

    def test_ticket_creation_domain_lookup(self):
        # 1. Mock the message retrieval that finds detected_domain in assistant response
        mock_msg_resp = MagicMock()
        mock_msg_resp.data = [{"metadata": {"detected_domain": "selskapsrett"}}]
        
        self.mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = mock_msg_resp
        
        # 2. Mock ticket insert
        mock_insert_resp = MagicMock()
        mock_insert_resp.data = [{"ticket_id": "123", "status": "open"}]
        self.mock_supabase.table.return_value.insert.return_value.execute.return_value = mock_insert_resp

        # Create ticket
        ticket = self.hitl_service.create_ticket(
            conversation_id="conv_abc",
            user_id="user_xyz",
            trigger_message_id="msg_1"
        )
        
        # Validate that detected_domain was query fetched and passed to supabase insert
        self.mock_supabase.table.assert_any_call("messages")
        self.mock_supabase.table.assert_any_call("hitl_tickets")
        
        # Verify the insert args contain detected_domain
        insert_args = self.mock_supabase.table.return_value.insert.call_args[0][0]
        self.assertEqual(insert_args["detected_domain"], "selskapsrett")

    def test_get_open_tickets_prioritizes_matching_domains(self):
        # Mock lawyer expertise domains
        mock_lp_resp = MagicMock()
        mock_lp_resp.data = [{"expertise_domains": ["Arbeidsrett", "Selskapsrett"]}]
        
        # Mock open tickets
        mock_tickets_resp = MagicMock()
        mock_tickets_resp.data = [
            {"ticket_id": "t1", "detected_domain": "eiendomsrett", "created_at": "2026-06-27T10:00:00Z"},
            {"ticket_id": "t2", "detected_domain": "selskapsrett", "created_at": "2026-06-27T10:05:00Z"},
            {"ticket_id": "t3", "detected_domain": "arbeidsrett", "created_at": "2026-06-27T10:02:00Z"},
        ]
        
        # Setup table routing mock return values
        def table_mock(table_name):
            mock_tbl = MagicMock()
            if table_name == "lawyer_profiles":
                mock_tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = mock_lp_resp
            else:
                mock_tbl.select.return_value.eq.return_value.order.return_value.execute.return_value = mock_tickets_resp
            return mock_tbl
            
        self.mock_supabase.table.side_effect = table_mock
        
        # Fetch sorted open tickets for lawyer
        open_tickets = self.hitl_service.get_open_tickets(lawyer_id="lawyer_123")
        
        # Verify sorting order: matches first, ordered by created_at. Non-matches last.
        # Matches: t2 ("selskapsrett"), t3 ("arbeidsrett"). Ordered by created_at: t3 (10:02) before t2 (10:05).
        # Non-match: t1 ("eiendomsrett").
        self.assertEqual(open_tickets[0]["ticket_id"], "t3")
        self.assertEqual(open_tickets[1]["ticket_id"], "t2")
        self.assertEqual(open_tickets[2]["ticket_id"], "t1")

    @patch("services.brief_service.AzureChatOpenAI")
    def test_case_brief_generation(self, mock_llm_class):
        async def run_test():
            # Mock LLM generation output
            mock_llm_instance = MagicMock()
            mock_llm_class.return_value = mock_llm_instance
            
            mock_resp = MagicMock()
            mock_resp.generations = [[MagicMock(text='''
            {
                "matter_type": "Company Formation",
                "key_issues": ["Vesting clause questions", "Equity split"],
                "relevant_laws": ["Aksjeloven"],
                "risk_level": "Moderate"
            }
            ''')]]
            mock_llm_instance.agenerate = AsyncMock(return_value=mock_resp)

            # Mock conversation messages select
            mock_messages_resp = MagicMock()
            mock_messages_resp.data = [
                {"role": "user", "content": "I need help setting up a shareholders agreement."},
                {"role": "assistant", "content": "Sure, under Aksjeloven, you should specify the equity splits."}
            ]
            
            def table_mock(table_name):
                mock_tbl = MagicMock()
                if table_name == "messages":
                    mock_tbl.select.return_value.eq.return_value.or_.return_value.order.return_value.execute.return_value = mock_messages_resp
                else:
                    mock_tbl.update.return_value.eq.return_value.execute.return_value = MagicMock()
                return mock_tbl
                
            self.mock_supabase.table.side_effect = table_mock

            # Run generator
            brief_service = BriefService(self.mock_supabase)
            brief = await brief_service.generate_case_brief("ticket_123", "conv_456")
            
            # Verify LLM call content and DB update execution
            self.assertEqual(brief["matter_type"], "Company Formation")
            self.assertEqual(brief["risk_level"], "Moderate")
            self.assertIn("Aksjeloven", brief["relevant_laws"])
            self.mock_supabase.table.assert_any_call("hitl_tickets")
            
        asyncio.run(run_test())

    def test_specialization_endpoints(self):
        client = TestClient(app)
        
        # Override get_current_user dependency
        app.dependency_overrides[get_current_user] = lambda: self.lawyer_user
        
        # Mock UserService helper
        import api.routes.hitl
        mock_user_svc = MagicMock()
        mock_user_svc.get_user_id_from_clerk_id.return_value = "lawyer_internal_id"
        api.routes.hitl._user_service = mock_user_svc
        api.routes.hitl._hitl_service = self.hitl_service
        
        # Mock upsert execution
        upsert_mock = MagicMock()
        self.mock_supabase.table.return_value.upsert.return_value.execute.return_value = upsert_mock
        upsert_mock.data = [{"lawyer_id": "lawyer_internal_id"}]

        # Test patch self specialization
        response = client.patch(
            "/api/v1/hitl/lawyer/profile/specialization",
            json={"expertise_domains": ["Selskapsrett", "Arbeidsrett"], "specialization_label": "Senior Counsel"}
        )
        self.assertEqual(response.status_code, 200)
        self.mock_supabase.table.assert_any_call("lawyer_profiles")
        
        upsert_payload = self.mock_supabase.table.return_value.upsert.call_args[0][0]
        self.assertIn("Selskapsrett", upsert_payload["expertise_domains"])
        self.assertEqual(upsert_payload["specialization_label"], "Senior Counsel")

if __name__ == "__main__":
    unittest.main()
