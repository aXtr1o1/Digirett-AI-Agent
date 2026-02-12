# backend/tests/test_health.py
import json

def _collect_sse_events(resp_text: str):
    """
    Parses SSE payload like:
      data: {...}\n\n
    """
    out = []
    for block in resp_text.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        payload = block.replace("data:", "", 1).strip()
        try:
            out.append(json.loads(payload))
        except Exception:
            pass
    return out


def test_stream_returns_sse_headers(client):
    r = client.post("/chat/stream", json={"query": "hi", "include_sources": True})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")


def test_stream_relevant_emits_sources_then_token_then_complete(client):
    r = client.post("/chat/stream", json={"query": "aksjeloven", "include_sources": True})
    events = _collect_sse_events(r.text)

    types = [e.get("type") for e in events]
    assert "sources" in types
    assert "token" in types
    assert "complete" in types

    # last event should be complete
    assert events[-1]["type"] == "complete"


def test_stream_include_sources_false_returns_empty_sources(client):
    r = client.post("/chat/stream", json={"query": "aksjeloven", "include_sources": False})
    events = _collect_sse_events(r.text)

    # first sources cleared always
    first_sources = next(e for e in events if e.get("type") == "sources")
    assert first_sources["data"] == []


def test_stream_out_of_scope_emits_no_sources(client_out_of_scope):
    r = client_out_of_scope.post("/chat/stream", json={"query": "random", "include_sources": True})
    events = _collect_sse_events(r.text)

    # should NOT emit sources list with content
    sources_events = [e for e in events if e.get("type") == "sources"]
    assert sources_events[0]["data"] == []


def test_stream_no_sources_emits_no_sources(client_no_sources):
    r = client_no_sources.post("/chat/stream", json={"query": "unknown", "include_sources": True})
    events = _collect_sse_events(r.text)

    sources_events = [e for e in events if e.get("type") == "sources"]
    assert sources_events[0]["data"] == []
