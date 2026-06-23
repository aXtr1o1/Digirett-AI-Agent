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

# Stub config settings
_s = MagicMock()
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
_s.INVITE_FROM_EMAIL = "noreply@digirett.no"
_s.ADMIN_ALERT_EMAIL = "admin@digirett.no"
_s.OPENAI_TEMPERATURE = 0.4
_fake_config = types.ModuleType("config")
_fake_config.settings = _s
sys.modules["config"] = _fake_config

from fastapi.testclient import TestClient
from main import app
from core.auth import ClerkUser, get_current_user
from api.routes import admin

class TestAdminRolesComprehensive(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.mock_user_svc = MagicMock()
        self.mock_email_svc = MagicMock()
        self.mock_hitl_svc = MagicMock()
        
        # Inject mock services
        admin.set_services(
            user_svc=self.mock_user_svc,
            email_svc=self.mock_email_svc,
            hitl_svc=self.mock_hitl_svc
        )
        
        # Reset dependency overrides
        app.dependency_overrides = {}
        
        # Setup roles users
        self.admin_user = ClerkUser({
            "clerk_user_id": "admin_clerk_id",
            "email": "admin@digirett.no",
            "role": "admin",
            "db_role": "admin",
            "status": "active"
        })
        self.sys_admin_user = ClerkUser({
            "clerk_user_id": "sys_clerk_id",
            "email": "sys@digirett.no",
            "role": "system_admin",
            "db_role": "system_admin",
            "status": "active"
        })
        self.standard_user = ClerkUser({
            "clerk_user_id": "user_clerk_id",
            "email": "user@example.com",
            "role": "user",
            "db_role": "user",
            "status": "active"
        })

    def _set_performer(self, user: ClerkUser):
        app.dependency_overrides[get_current_user] = lambda: user

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. READ ACTIONS ACCESS CONTROL (GET Routes)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_list_users_access(self):
        """Verify who can read all users."""
        self.mock_user_svc._supabase.table().select().order().execute.return_value = MagicMock(data=[])
        
        # Admin can view
        self._set_performer(self.admin_user)
        response = self.client.get("/api/v1/admin/users", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # System admin can view
        self._set_performer(self.sys_admin_user)
        response = self.client.get("/api/v1/admin/users", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # Standard user gets blocked
        self._set_performer(self.standard_user)
        response = self.client.get("/api/v1/admin/users", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

    def test_list_invitations_access(self):
        """Verify who can list pending invitations."""
        self.mock_user_svc.get_all_invitations.return_value = []
        
        self._set_performer(self.admin_user)
        response = self.client.get("/api/v1/admin/invitations", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        self._set_performer(self.sys_admin_user)
        response = self.client.get("/api/v1/admin/invitations", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        self._set_performer(self.standard_user)
        response = self.client.get("/api/v1/admin/invitations", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

    def test_domain_analytics_access(self):
        """Verify domain analytics read permissions."""
        self.mock_user_svc._supabase.table().select().eq().execute.return_value = MagicMock(data=[])
        
        self._set_performer(self.admin_user)
        response = self.client.get("/api/v1/admin/domain-analytics", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        self._set_performer(self.standard_user)
        response = self.client.get("/api/v1/admin/domain-analytics", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. WRITE ACTIONS ACCESS CONTROL (POST / PATCH / DELETE Routes)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_invite_user_permission(self):
        """Verify both Admin and System Admin can create invitations."""
        self.mock_user_svc.get_user_id_from_clerk_id.return_value = "performer_id"
        self.mock_user_svc.invite_user = AsyncMock(return_value=True)

        payload = {"email": "test@invite.com", "role": "lawyer"}
        
        # Admin can invite
        self._set_performer(self.admin_user)
        response = self.client.post("/api/v1/admin/invite", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # System Admin can invite
        self._set_performer(self.sys_admin_user)
        response = self.client.post("/api/v1/admin/invite", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # User is forbidden
        self._set_performer(self.standard_user)
        response = self.client.post("/api/v1/admin/invite", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

    def test_revoke_invitation_permission(self):
        """Verify both roles can revoke invitations."""
        self.mock_user_svc.revoke_invitation.return_value = True

        # Admin
        self._set_performer(self.admin_user)
        response = self.client.delete("/api/v1/admin/invitations/invite_123", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # System Admin
        self._set_performer(self.sys_admin_user)
        response = self.client.delete("/api/v1/admin/invitations/invite_123", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

    def test_promote_lawyer_permission(self):
        """Verify lawyer promotions are open to both roles."""
        self.mock_user_svc.get_user_id_from_clerk_id.return_value = "performer_id"
        self.mock_user_svc.promote_to_lawyer = AsyncMock(return_value=True)

        payload = {"user_id": "target_user_id"}
        
        self._set_performer(self.admin_user)
        response = self.client.post("/api/v1/admin/promote/lawyer", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        self._set_performer(self.sys_admin_user)
        response = self.client.post("/api/v1/admin/promote/lawyer", json=payload, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

    def test_ticket_management_permissions(self):
        """Verify both roles can assign, unassign, and close tickets."""
        self.mock_hitl_svc.admin_assign_ticket.return_value = True
        self.mock_hitl_svc.admin_unassign_ticket.return_value = True
        self.mock_hitl_svc.close_ticket_admin.return_value = True

        # Assignment overrides
        self._set_performer(self.admin_user)
        response = self.client.patch("/api/v1/admin/tickets/ticket_1/assign/lawyer_1", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        self._set_performer(self.sys_admin_user)
        response = self.client.patch("/api/v1/admin/tickets/ticket_1/assign/lawyer_1", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # Close ticket
        self._set_performer(self.admin_user)
        response = self.client.patch("/api/v1/admin/tickets/ticket_1/close", json={"outcome_notes": "All settled."}, headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. HIERARCHY SAFEGUARDS (Admin > System Admin Control Rules)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def test_suspend_user_hierarchy_rules(self):
        """Verify suspension hierarchy constraints."""
        # 1. Admin can suspend System Admin
        self.mock_user_svc.get_user_by_id.return_value = {
            "user_id": "sys_admin_id",
            "role": "system_admin"
        }
        self.mock_user_svc.suspend_user.return_value = True

        self._set_performer(self.admin_user)
        response = self.client.patch("/api/v1/admin/users/sys_admin_id/suspend", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

        # 2. System Admin CANNOT suspend Admin
        self.mock_user_svc.get_user_by_id.return_value = {
            "user_id": "admin_id",
            "role": "admin"
        }
        self._set_performer(self.sys_admin_user)
        response = self.client.patch("/api/v1/admin/users/admin_id/suspend", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)
        self.assertIn("System Admins cannot suspend", response.json()["message"])

        # 3. System Admin CANNOT suspend another System Admin
        self.mock_user_svc.get_user_by_id.return_value = {
            "user_id": "sys_admin_2",
            "role": "system_admin"
        }
        response = self.client.patch("/api/v1/admin/users/sys_admin_2/suspend", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 403)

        # 4. System Admin CAN suspend a Lawyer
        self.mock_user_svc.get_user_by_id.return_value = {
            "user_id": "lawyer_id",
            "role": "lawyer"
        }
        response = self.client.patch("/api/v1/admin/users/lawyer_id/suspend", headers={"Authorization": "Bearer token"})
        self.assertEqual(response.status_code, 200)

if __name__ == "__main__":
    unittest.main()
