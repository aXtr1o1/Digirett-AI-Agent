"""
conftest.py  —  ingestion/tests/conftest.py
============================================
Adds the project root (parent of the `ingestion/` package) to sys.path
so that `from ingestion.collectors.lovdata_collector import ...` resolves
correctly whether pytest is run from:

  • D:\aXtr Labs\Digirett-AI-Agent\ingestion     (local, current working dir)
  • /home/runner/work/.../ingestion               (GitHub Actions / CI)
  • anywhere else inside the repo

No changes to test_collector.py imports are required.
"""

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 1.  Make `ingestion` importable
#     __file__ = .../ingestion/tests/conftest.py
#     parent   = .../ingestion/
#     root     = .../Digirett-AI-Agent/           <- add this to sys.path
# ---------------------------------------------------------------------------
_tests_dir = Path(__file__).resolve().parent          # ingestion/tests/
_pkg_dir   = _tests_dir.parent                        # ingestion/
_repo_root = _pkg_dir.parent                          # Digirett-AI-Agent/

if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# ---------------------------------------------------------------------------
# 2.  Stub out every environment variable that config.py requires
#     so tests never crash with "missing env var" before a single test runs.
# ---------------------------------------------------------------------------
_ENV_DEFAULTS = {
    "LOVDATA_API_URL":      "https://api.lovdata.no",
    "SUPABASE_URL":         "https://test.supabase.co",
    "SUPABASE_SERVICE_KEY": "test-service-key",
    "SUPABASE_BUCKET":      "test-bucket",
    "MILVUS_HOST":          "localhost",
    "MILVUS_PORT":          "19530",
    "MILVUS_COLLECTION":    "test-collection",
    "EMBED_MODEL":          "test-model",
    "SUPABASE_TABLE":       "test-table",
    "XL_DATASET_FOLDER":    "tests/mock_xl",
}

for _key, _val in _ENV_DEFAULTS.items():
    os.environ.setdefault(_key, _val)