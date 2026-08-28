import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ── PATH: make sure project root is importable ────────────────────────────────
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
INGESTION_ROOT = str(Path(__file__).resolve().parent.parent)
for p in [PROJECT_ROOT, INGESTION_ROOT]:
    if p not in sys.path:
        sys.path.insert(0, p)

_CI_ENV = {
    # ── Workbook / input ──────────────────────────────────────────────────────
    "XL_DATASET_FOLDER":                    "/tmp/xl_dataset",

    # ── Supabase ──────────────────────────────────────────────────────────────
    "SUPABASE_URL":                         "https://placeholder.supabase.co",
    "SUPABASE_SERVICE_KEY":                 "placeholder-service-key",
    "SUPABASE_BUCKET":                      "raw_xml_files",
    "SUPABASE_TABLE":                       "legal_documents",
    "SUPABASE_SOURCE_TABLE_AI":             "law_documents_metadata_ai_subdomain",
    "SUPABASE_SOURCE_TABLE_PREDEFINED":     "law_documents_metadata_predefined_subdomain",

    # ── Azure OpenAI ──────────────────────────────────────────────────────────
    "AZURE_OPENAI_ENDPOINT":                "https://placeholder.cognitiveservices.azure.com",
    "AZURE_OPENAI_KEY":                     "placeholder-azure-key",
    "AZURE_OPENAI_API_VERSION":             "2023-05-15",
    "AZURE_OPENAI_DEPLOYMENT":              "text-embedding-3-small",

    # ── Embedding ─────────────────────────────────────────────────────────────
    "EMBEDDING_PROVIDER":                   "azure_openai",
    "EMBEDDING_MODEL":                      "text-embedding-3-small",
    "EMBEDDING_DIMENSION":                  "1536",

    # ── Milvus ────────────────────────────────────────────────────────────────
    "MILVUS_HOST":                          "localhost",
    "MILVUS_PORT":                          "19530",
    "MILVUS_COLLECTION":                    "classified_data",
    "MILVUS_DIMENSION":                     "1536",
    "MILVUS_METRIC_TYPE":                   "IP",
    "MILVUS_INDEX_TYPE":                    "HNSW",

    # ── Chunking ──────────────────────────────────────────────────────────────
    "LEGAL_CHUNK_MAX_TOKENS":               "2000",
    "LEGAL_CHUNK_OVERLAP_TOKENS":           "200",
    "LEGAL_CHUNK_CHARS_PER_TOKEN":          "4",
    "CHUNK_SIZE":                           "1000",
    "CHUNK_OVERLAP":                        "200",
    "MAX_TOKENS_PER_CHUNK":                 "256",
    "OVERLAP_TOKENS":                       "50",
    "EMBEDDING_BATCH_SIZE":                 "4",
    "EMBEDDING_CHUNK_DELAY":                "0.5",

    # ── Scheduler ─────────────────────────────────────────────────────────────
    "SCHEDULER_BATCH_SIZE":                 "50",
    "SCHEDULER_CRON_HOUR":                  "2",
    "SCHEDULER_CRON_MINUTE":                "0",
    "SCHEDULER_API_TIMEOUT":                "30",

    # ── Lovdata API ───────────────────────────────────────────────────────────
    "LOVDATA_API_URL":                      "https://api.lovdata.no/v1/publicData",
}

for key, value in _CI_ENV.items():
    os.environ.setdefault(key, value)

# ── Create XL_DATASET_FOLDER so Path(...).exists() passes in validate_runtime_config ──
Path(os.environ["XL_DATASET_FOLDER"]).mkdir(parents=True, exist_ok=True)

# ── Block real external clients ───────────────────────────────────────────────
# Prevents accidental network calls during collection and test runs.
sys.modules.setdefault("supabase", MagicMock())
sys.modules.setdefault("pymilvus", MagicMock())

# ── Stub the missing xl_metadata_loader ──────────────────────────────────────
# lovdata_collector.py imports load_xl_single_file from this module at import
# time. The module doesn't exist on disk so we inject a stub here.
_xl_stub = MagicMock()
_xl_stub.load_xl_single_file = MagicMock(return_value=("domain", {}))
sys.modules.setdefault(
    "ingestion.src.processors.xl_metadata_loader", _xl_stub
)