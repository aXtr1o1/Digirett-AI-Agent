# backend/tests/conftest.py
import os
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# -------------------------------------------------------------------
# 1) Set env BEFORE importing anything that loads Settings()
# -------------------------------------------------------------------
def _set_test_env():
    os.environ.setdefault("APP_NAME", "digirett-test")
    os.environ.setdefault("VERSION", "0.0.0-test")
    os.environ.setdefault("DEBUG", "true")

    # IMPORTANT: List[str] must be JSON for pydantic-settings (v2)
    os.environ.setdefault("ALLOWED_ORIGINS", json.dumps(["*"]))

    os.environ.setdefault("LOG_DIR", "./logs")
    os.environ.setdefault("LOG_FILE", "test.log")
    os.environ.setdefault("LOG_LEVEL", "INFO")

    # dummy infra values (not used in unit tests)
    os.environ.setdefault("MILVUS_HOST", "localhost")
    os.environ.setdefault("MILVUS_PORT", "19530")
    os.environ.setdefault("MILVUS_COLLECTION", "test")
    os.environ.setdefault("MILVUS_METRIC_TYPE", "COSINE")
    os.environ.setdefault("EMBEDDING_DIMENSION", "1536")

    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("CACHE_TTL", "60")

    os.environ.setdefault("DEFAULT_TOP_K", "3")
    os.environ.setdefault("MAX_TOP_K", "10")
    os.environ.setdefault("MIN_SIMILARITY_SCORE", "0.4")
    os.environ.setdefault("CONTEXT_MAX_LENGTH", "12000")

    # dummy Azure values (NOT used because we fake chat service)
    os.environ.setdefault("AZURE_OPENAI_CHAT_ENDPOINT", "https://example.openai.azure.com")
    os.environ.setdefault("AZURE_OPENAI_CHAT_API_KEY", "test")
    os.environ.setdefault("AZURE_OPENAI_CHAT_API_VERSION", "2025-01-01-preview")
    os.environ.setdefault("AZURE_OPENAI_CHAT_DEPLOYMENT", "test")

    os.environ.setdefault("AZURE_OPENAI_EMBED_ENDPOINT", "https://example.openai.azure.com")
    os.environ.setdefault("AZURE_OPENAI_EMBED_API_KEY", "test")
    os.environ.setdefault("AZURE_OPENAI_EMBED_API_VERSION", "2023-05-15")
    os.environ.setdefault("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "test")

    os.environ.setdefault("PROMPT_VERSION", "test")


_set_test_env()

# -------------------------------------------------------------------
# 2) Now safe to import router (it imports Settings)
#    IMPORTANT: since you run pytest inside /backend, use "api.endpoints"
# -------------------------------------------------------------------
from backend.api.endpoints import router


# -------------------------------------------------------------------
# 3) Minimal fakes for endpoint dependencies
# -------------------------------------------------------------------
class FakeCache:
    def __init__(self):
        self._store = {}

    def generate_key(self, **kwargs):
        raw = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        return f"k::{hash(raw)}"

    def get(self, key):
        return self._store.get(key)

    def set(self, key, value, ttl=None):
        self._store[key] = value

    def close(self):
        return


class FakeEmbedder:
    async def embed_query(self, text: str):
        return [0.1, 0.2, 0.3]


class FakeRetriever:
    def __init__(self, results):
        self.results = results

    def search(self, emb, top_k, correlation_id=None):
        return self.results[:top_k]


class FakeChatService:
    def __init__(self, mode="relevant"):
        self.mode = mode

    async def stream(
        self,
        query,
        retriever_fn,
        embedder_fn,
        cache_get_fn,
        cache_set_fn,
        cache_key,
        top_k,
        include_sources,
        temperature,
        correlation_id,
        request=None,
    ):
        # always clear sources first
        yield f"data: {json.dumps({'type': 'sources', 'data': []}, ensure_ascii=False)}\n\n"

        # cache path
        cached = cache_get_fn(cache_key)
        if cached:
            sources = cached.get("sources", []) if include_sources else []
            answer = cached.get("answer", "")
            yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'data': answer}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cached': True}}, ensure_ascii=False)}\n\n"
            return

        if self.mode == "no_sources":
            msg = "No sources found."
            yield f"data: {json.dumps({'type': 'token', 'data': msg}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cached': False, 'note': 'no_sources'}}, ensure_ascii=False)}\n\n"
            return

        if self.mode == "out_of_scope":
            msg = "Out of scope."
            yield f"data: {json.dumps({'type': 'token', 'data': msg}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cached': False, 'note': 'out_of_scope'}}, ensure_ascii=False)}\n\n"
            return

        # relevant
        sources = []
        if include_sources:
            sources = [{
                "title": "Aksjeloven (ASL)",
                "url": "https://lovdata.no",
                "chunk_id": "c1",
                "chunk_text": "Excerpt…",
                "relevance_score": 0.91,
                "metadata": {"file_name": "asl.pdf"},
            }]

        answer = "Answer from Lovdata sources."
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'token', 'data': answer}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'complete', 'metadata': {'cached': False}}, ensure_ascii=False)}\n\n"

        cache_set_fn(cache_key, {"answer": answer, "sources": sources, "metadata": {"cached": False}})


# -------------------------------------------------------------------
# 4) Fixtures
# -------------------------------------------------------------------
@pytest.fixture
def make_test_app():
    def _make(mode="relevant"):
        app = FastAPI()
        app.state.cache = FakeCache()
        app.state.embedder = FakeEmbedder()
        app.state.retriever = FakeRetriever(results=[{"score": 0.9}])
        app.state.chat_service = FakeChatService(mode=mode)
        app.include_router(router)
        return app
    return _make


@pytest.fixture
def client(make_test_app):
    return TestClient(make_test_app("relevant"))


@pytest.fixture
def client_out_of_scope(make_test_app):
    return TestClient(make_test_app("out_of_scope"))


@pytest.fixture
def client_no_sources(make_test_app):
    return TestClient(make_test_app("no_sources"))
