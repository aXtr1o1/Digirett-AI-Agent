

# ── Fix sys.path FIRST so Python finds backend/ packages ─────────────
import sys, os, pathlib, types, asyncio, unittest
from unittest.mock import MagicMock, AsyncMock


_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# ── Stub every heavy import BEFORE any project file is touched ────────

# 1. config  (agents/intent_agent.py does `from config import settings`)
if "config" in sys.modules:
    import config
    _s = config.settings
else:
    _s = MagicMock()
    _fake_config          = types.ModuleType("config")
    _fake_config.settings = _s
    sys.modules["config"] = _fake_config

_s.AZURE_OPENAI_ENDPOINT             = "https://fake.openai.azure.com"
_s.AZURE_OPENAI_API_KEY              = "fake-key"
_s.AZURE_OPENAI_API_VERSION          = "2024-02-01"
_s.AZURE_OPENAI_DEPLOYMENT           = "gpt-4o-mini"
_s.AZURE_OPENAI_EMBEDDING_DEPLOYMENT = "text-embedding-3-small"
_s.AZURE_OPENAI_EMBEDDING_API_VERSION= "2024-02-01"
_s.OPENAI_TEMPERATURE                = 0.4

# 2. Third-party packages that would fail without installation/servers
for _m in [
    "pymilvus", "redis", "redis.connection",
    "supabase", "langchain_openai",
    "langchain_core", "langchain_core.messages",
    "opentelemetry", "opentelemetry.trace",
    "opentelemetry.sdk", "opentelemetry.sdk.trace",
    "opentelemetry.sdk.trace.export",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.instrumentation.fastapi",
    "slowapi", "slowapi.util", "slowapi.errors",
    "boto3", "telemetry", "telemetry.tracing",
]:
    sys.modules.setdefault(_m, MagicMock())

# 3. tenacity — replace @retry with identity decorator so MilvusClient loads
_ten = types.ModuleType("tenacity")
_ten.retry              = lambda *a, **kw: (lambda fn: fn)
_ten.stop_after_attempt = lambda n: None
_ten.wait_exponential   = lambda **kw: None
sys.modules["tenacity"] = _ten

# 4. langchain_core.messages — provide callable stubs
_lcm = types.ModuleType("langchain_core.messages")
_lcm.HumanMessage  = lambda content: {"role": "user",   "content": content}
_lcm.SystemMessage = lambda content: {"role": "system", "content": content}
_lcm.AIMessage     = lambda content: {"role": "ai",     "content": content}
sys.modules["langchain_core.messages"] = _lcm


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestChatRequestSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from schemas.requests import ChatRequest   # backend/schemas/requests.py
        cls.CR = ChatRequest

    def test_valid_payload_accepted(self):
        req = self.CR(
            query="Hva er reglene for aksjeselskap?",
            conversation_id="550e8400-e29b-41d4-a716-446655440000",
            user_id="2a06144d-4675-4c38-b7f8-13c02da91af5",
            top_k=5,
            include_sources=True,
            temperature=0.4,
        )
        self.assertEqual(req.query, "Hva er reglene for aksjeselskap?")
        self.assertEqual(req.top_k, 5)

    def test_blank_query_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CR(query="     ")

    def test_query_whitespace_stripped(self):
        req = self.CR(query="  aksjeloven § 6-1  ")
        self.assertEqual(req.query, "aksjeloven § 6-1")

    def test_top_k_above_max_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CR(query="test", top_k=11)

    def test_temperature_above_max_rejected(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.CR(query="test", temperature=1.1)

    def test_optional_fields_default_to_none(self):
        req = self.CR(query="test query")
        self.assertIsNone(req.conversation_id)
        self.assertIsNone(req.user_id)
        self.assertEqual(req.top_k, 5)
        self.assertTrue(req.include_sources)




class TestMemoryAgent(unittest.TestCase):

    def _make_agent(self, redis_result, supabase_rows):
        """
        Build a MemoryAgent with fully mocked Redis and Supabase.
        Mirrors the exact Supabase chain used in memory_agent.py:
          .table().select().eq().or_().order().limit().execute()
        """
        from agents.memory_agent import MemoryAgent

        # Redis mock
        mock_redis = MagicMock()
        mock_redis.get_context.return_value = redis_result

        # Supabase chained mock
        execute_result      = MagicMock()
        execute_result.data = supabase_rows
        chain               = MagicMock()
        chain.execute.return_value = execute_result
        # Every chained method returns the same chain object
        chain.select.return_value  = chain
        chain.eq.return_value      = chain
        chain.or_.return_value     = chain
        chain.order.return_value   = chain
        chain.limit.return_value   = chain

        mock_supabase = MagicMock()
        mock_supabase.table.return_value = chain

        return MemoryAgent(redis_client=mock_redis, supabase_client=mock_supabase)

    def test_redis_hit_returns_cached_messages(self):
        """When Redis has data, Supabase must never be called."""
        cached = [
            {"role": "user",      "content": "Hva er styreleder?"},
            {"role": "assistant", "content": "Styreleder leder styret."},
        ]
        agent  = self._make_agent(redis_result=cached, supabase_rows=[])
        result = agent.run("conv-redis-001", limit=10)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"],    "user")
        self.assertEqual(result[1]["content"], "Styreleder leder styret.")
        agent._supabase.table.assert_not_called()

    def test_redis_miss_falls_back_to_supabase(self):
        """When Redis returns None, messages must come from Supabase."""
        rows = [
            {"role": "user",      "content": "Hva er aksjeloven?", "created_at": "2026-01-01"},
            {"role": "assistant", "content": "Aksjeloven regulerer AS.", "created_at": "2026-01-01"},
        ]
        agent  = self._make_agent(redis_result=None, supabase_rows=rows)
        result = agent.run("conv-supa-001", limit=10)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"],    "user")
        self.assertEqual(result[1]["content"], "Aksjeloven regulerer AS.")
        agent._supabase.table.assert_called_once_with("messages")

    def test_normalize_drops_system_and_empty_messages(self):
        """
        _normalize() must keep only role=user|assistant with non-empty content.
        System messages and empty-content entries must be dropped.
        """
        from agents.memory_agent import MemoryAgent

        raw = [
            {"role": "user",      "content": "Hello"},
            {"role": "system",    "content": "You are an AI"},   # dropped
            {"role": "assistant", "content": ""},                 # dropped (empty)
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = MemoryAgent._normalize(raw)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["role"],    "user")
        self.assertEqual(result[1]["content"], "Hi there!")

    def test_both_sources_fail_returns_empty_list(self):
        """When Redis and Supabase both raise, run() must return [] not raise."""
        from agents.memory_agent import MemoryAgent

        mock_redis = MagicMock()
        mock_redis.get_context.side_effect = Exception("Redis down")

        mock_supabase = MagicMock()
        mock_supabase.table.side_effect = Exception("Supabase down")

        agent  = MemoryAgent(redis_client=mock_redis, supabase_client=mock_supabase)
        result = agent.run("conv-both-fail-001", limit=10)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)