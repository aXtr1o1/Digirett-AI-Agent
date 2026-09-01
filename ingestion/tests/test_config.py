from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from ingestion.src.config import (
    Settings,
    settings,
    BASE_DIR,
    DATA_DIR,
    CHECKPOINT_DIR,
    NORMALIZED_DIR,
    REPORTS_DIR,
    LOG_DIR,
)
from ingestion.src.main import MappingBundle, load_mapping


def test_default_settings_instantiation():
    s = Settings()
    assert s.XAPI_BASE_URL.startswith("http")
    assert s.MILVUS_PORT == 19530
    assert s.TAXONOMY_VERSION == "1.1.0"
    assert s.DOCUMENT_BATCH_SIZE > 0
    assert s.LEGAL_CHUNK_MAX_TOKENS == 2000
    assert s.URL_VALIDATION_ENABLED is True


def test_directory_paths_exist():
    for folder in [BASE_DIR, DATA_DIR, CHECKPOINT_DIR, NORMALIZED_DIR, REPORTS_DIR, LOG_DIR]:
        assert folder.exists()
        assert folder.is_dir()


def test_settings_custom_override():
    custom = Settings(
        XAPI_CONCURRENCY=16,
        DOCUMENT_BATCH_SIZE=100,
        MILVUS_HOST="10.0.0.1",
    )
    assert custom.XAPI_CONCURRENCY == 16
    assert custom.DOCUMENT_BATCH_SIZE == 100
    assert custom.MILVUS_HOST == "10.0.0.1"


def test_mapping_bundle_load_client_file():
    bundle = load_mapping(settings.mapping_path)
    assert bundle.is_client_mapping_loaded is True
    assert len(bundle.direct_mappings) > 0
    assert len(bundle.out_of_scope) > 0
    assert "D12_EMPLOYMENT" in bundle.legend or len(bundle.legend) > 0


def test_mapping_bundle_build_domain_plans():
    bundle = load_mapping(settings.mapping_path)
    plans = bundle.build_domain_plans()
    assert isinstance(plans, dict)
    assert "D12_EMPLOYMENT" in plans or "D04_CONTRACT" in plans
    for d_id, plan in plans.items():
        assert plan.domain_id == d_id
        assert hasattr(plan, "rettsomrader")
        assert isinstance(plan.rettsomrader, list)
