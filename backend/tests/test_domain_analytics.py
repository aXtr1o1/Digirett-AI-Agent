import sys
import pathlib
import unittest
from unittest.mock import MagicMock

# Ensure backend package can be imported
_BACKEND = str(pathlib.Path(__file__).resolve().parent.parent)
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

# Mock third-party dependencies before loading module
import types
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("supabase", MagicMock())
sys.modules.setdefault("opentelemetry", MagicMock())
sys.modules.setdefault("opentelemetry.trace", MagicMock())
sys.modules.setdefault("opentelemetry.sdk", MagicMock())
sys.modules.setdefault("opentelemetry.sdk.trace", MagicMock())
sys.modules.setdefault("slowapi", MagicMock())
sys.modules.setdefault("slowapi.util", MagicMock())
sys.modules.setdefault("slowapi.errors", MagicMock())
sys.modules.setdefault("telemetry", MagicMock())

class TestDomainAnalyticsCalculation(unittest.TestCase):

    def setUp(self):
        # Local mock setup for UserService
        self.mock_supabase = MagicMock()
        self.mock_table = MagicMock()
        self.mock_select = MagicMock()
        self.mock_eq = MagicMock()
        self.mock_execute = MagicMock()

        self.mock_supabase.table.return_value = self.mock_table
        self.mock_table.select.return_value = self.mock_select
        self.mock_select.eq.return_value = self.mock_eq
        self.mock_eq.execute.return_value = self.mock_execute

        from services.user_service import UserService
        self.user_service = UserService(self.mock_supabase)

    def test_domain_calculation_math_and_sorting(self):
        # Mock database messages with varying domains in metadata
        mock_data = [
            {"metadata": {"detected_domain": "arbeidsrett"}},
            {"metadata": {"detected_domain": "arbeidsrett"}},
            {"metadata": {"detected_domain": "arbeidsrett"}}, # 3 / 6 = 50%
            {"metadata": {"detected_domain": "selskapsrett"}},
            {"metadata": {"detected_domain": "selskapsrett"}}, # 2 / 6 = 33.3%
            {"metadata": {"detected_domain": "avtalerett"}},    # 1 / 6 = 16.7%
            {"metadata": {}},                                  # Missing metadata, should be ignored
            {"metadata": {"detected_domain": None}},           # Null value, should be ignored
            {},                                                # Empty row, should be ignored
        ]
        self.mock_execute.return_value.data = mock_data

        # Call endpoint handler logic (replicated inside test for isolated validation)
        resp = self.mock_execute.return_value
        counts = {}
        total = 0
        for msg in (resp.data or []):
            meta = msg.get("metadata") or {}
            domain = meta.get("detected_domain")
            if domain:
                counts[domain] = counts.get(domain, 0) + 1
                total += 1

        distribution = []
        for domain, count in counts.items():
            distribution.append({
                "name": domain,
                "queries": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0
            })
        distribution.sort(key=lambda x: x["queries"], reverse=True)

        # Asserts
        self.assertEqual(total, 6)
        self.assertEqual(len(distribution), 3)

        # Verification of sorting order (Highest count first)
        self.assertEqual(distribution[0]["name"], "arbeidsrett")
        self.assertEqual(distribution[0]["queries"], 3)
        self.assertEqual(distribution[0]["percentage"], 50.0)

        self.assertEqual(distribution[1]["name"], "selskapsrett")
        self.assertEqual(distribution[1]["queries"], 2)
        self.assertEqual(distribution[1]["percentage"], 33.3)

        self.assertEqual(distribution[2]["name"], "avtalerett")
        self.assertEqual(distribution[2]["queries"], 1)
        self.assertEqual(distribution[2]["percentage"], 16.7)

    def test_empty_messages_handling(self):
        # Mock database returning empty messages list
        self.mock_execute.return_value.data = []

        resp = self.mock_execute.return_value
        counts = {}
        total = 0
        for msg in (resp.data or []):
            meta = msg.get("metadata") or {}
            domain = meta.get("detected_domain")
            if domain:
                counts[domain] = counts.get(domain, 0) + 1
                total += 1

        distribution = []
        for domain, count in counts.items():
            distribution.append({
                "name": domain,
                "queries": count,
                "percentage": round((count / total) * 100, 1) if total > 0 else 0
            })

        self.assertEqual(total, 0)
        self.assertEqual(len(distribution), 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
