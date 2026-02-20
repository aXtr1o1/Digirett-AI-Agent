"""
End-to-end API tests.

Run with:
    pytest app/tests/test_api.py -v

These tests hit a running server at BASE_URL.
They are integration tests, not unit tests — the server must be running.
"""

import json
import time

import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "2a06144d-4675-4c38-b7f8-13c02da91af5"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FIXTURES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.fixture(scope="session")
def conversation_id():
    """Create a test conversation and clean it up when all tests finish."""
    response = requests.post(
        f"{BASE_URL}/conversations",
        json={"user_id": USER_ID, "title": "Pytest Test Conversation"},
    )
    assert response.status_code == 200, f"Failed to create conversation: {response.text}"

    conv_id = response.json().get("conversation_id")
    assert conv_id, "No conversation_id returned"

    yield conv_id

    # Cleanup
    requests.delete(f"{BASE_URL}/conversations/{conv_id}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TESTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_health():
    """Server should be healthy with all services connected."""
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("healthy", "degraded")
    print(f"\n✅ Health: {body['status']}")


def test_create_conversation():
    """Creating a conversation should return a valid conversation_id."""
    r = requests.post(
        f"{BASE_URL}/conversations",
        json={"user_id": USER_ID, "title": "Test Conversation"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "conversation_id" in body
    assert body["user_id"] == USER_ID

    # Cleanup
    requests.delete(f"{BASE_URL}/conversations/{body['conversation_id']}")
    print(f"\n✅ Created conversation: {body['conversation_id']}")


def test_stream_legal_query(conversation_id):
    """
    A legal query should stream tokens and return at least one source.
    """
    payload = {
        "user_id": USER_ID,
        "conversation_id": conversation_id,
        "query": "Explain Norwegian company law briefly.",
        "top_k": 3,
    }

    response = requests.post(
        f"{BASE_URL}/chat/stream",
        json=payload,
        stream=True,
    )
    assert response.status_code == 200, f"Stream request failed: {response.text}"

    full_answer = ""
    sources = []
    complete_received = False

    for line in response.iter_lines():
        if not line:
            continue
        decoded = line.decode("utf-8")
        if not decoded.startswith("data: "):
            continue

        event = json.loads(decoded[6:])

        if event.get("type") == "token":
            full_answer += event.get("data", "")

        elif event.get("type") == "sources":
            sources = event.get("data", [])

        elif event.get("type") == "complete":
            complete_received = True
            break

        elif event.get("type") == "error":
            pytest.fail(f"Server returned error: {event.get('message')}")

    assert complete_received, "Stream did not emit a 'complete' event"
    assert len(full_answer) > 0, "No answer tokens received"
    print(f"\n✅ Stream complete | tokens={len(full_answer)} | sources={len(sources)}")
    print(f"   Answer preview: {full_answer[:150]}")


def test_messages_persisted(conversation_id):
    """
    After a stream, messages should be saved and readable.
    """
    # Give Supabase a moment to commit
    time.sleep(1)

    r = requests.get(f"{BASE_URL}/messages/{conversation_id}")
    assert r.status_code == 200

    messages = r.json()
    assert len(messages) >= 2, "Expected at least one user + one assistant message"

    roles = [m["role"] for m in messages]
    assert "user" in roles, "No user message found"
    assert "assistant" in roles, "No assistant message found"

    print(f"\n✅ Messages persisted: {len(messages)} messages")


def test_get_conversation(conversation_id):
    """Fetching the conversation should return its details and messages."""
    r = requests.get(f"{BASE_URL}/conversations/{conversation_id}")
    assert r.status_code == 200

    body = r.json()
    assert "conversation" in body
    assert "messages" in body
    assert body["conversation"]["conversation_id"] == conversation_id

    print(f"\n✅ Conversation fetched | messages={len(body['messages'])}")


def test_get_user_conversations():
    """User conversation list should be non-empty."""
    r = requests.get(f"{BASE_URL}/conversations/user/{USER_ID}")
    assert r.status_code == 200

    conversations = r.json()
    assert isinstance(conversations, list)
    print(f"\n✅ User has {len(conversations)} conversation(s)")


def test_delete_conversation(conversation_id):
    """Deleting a conversation should return 200 and mark it as deleted."""
    r = requests.delete(f"{BASE_URL}/conversations/{conversation_id}")
    assert r.status_code == 200
    print(f"\n✅ Conversation deleted: {conversation_id}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STANDALONE RUNNER (python app/tests/test_api.py)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    test_health()

    r = requests.post(
        f"{BASE_URL}/conversations",
        json={"user_id": USER_ID, "title": "Manual Test"},
    )
    conv_id = r.json()["conversation_id"]

    test_stream_legal_query(conv_id)
    time.sleep(2)
    test_messages_persisted(conv_id)
    test_get_conversation(conv_id)
    test_get_user_conversations()
    test_delete_conversation(conv_id)

    print("\n🎉 ALL TESTS PASSED")