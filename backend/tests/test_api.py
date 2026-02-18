import requests
import json
import uuid
import time
from sseclient import SSEClient
import pytest

BASE_URL = "http://localhost:8000/api/v1"
USER_ID = "2a06144d-4675-4c38-b7f8-13c02da91af5"


@pytest.fixture(scope="session")
def conversation_id():
    print("\n🔹 Creating test conversation...")

    payload = {
        "user_id": USER_ID,
        "title": "Pytest Conversation"
    }

    response = requests.post(
        f"{BASE_URL}/conversations",
        json=payload
    )

    assert response.status_code == 200, "❌ Failed to create conversation"

    data = response.json()
    conv_id = data.get("conversation_id")

    assert conv_id is not None, "❌ No conversation_id returned"

    yield conv_id

    # Cleanup after all tests
    print("\n🧹 Cleaning up conversation...")
    requests.delete(f"{BASE_URL}/conversations/{conv_id}")
def print_section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def test_health():
    print_section("1️⃣ HEALTH CHECK")
    r = requests.get(f"{BASE_URL}/health")
    print("Status:", r.status_code)
    print("Response:", r.json())
    assert r.status_code == 200


def create_conversation():
    print_section("2️⃣ CREATE CONVERSATION")
    payload = {
        "user_id": USER_ID,
        "title": "System Test Conversation"
    }
    r = requests.post(f"{BASE_URL}/conversations", json=payload)
    print("Status:", r.status_code)
    data = r.json()
    print("Response:", data)
    assert r.status_code == 200
    return data["conversation_id"]


import requests
import json

def test_stream(conversation_id):
    print_section("3️⃣ STREAM TEST (SSE)")
    
    payload = {
        "user_id": USER_ID,
        "conversation_id": conversation_id,
        "query": "Explain Norwegian company law briefly.",
        "top_k": 3
    }

    response = requests.post(
        f"{BASE_URL}/chat/stream",
        json=payload,
        stream=True
    )

    assert response.status_code == 200, "❌ Stream endpoint failed!"

    full_answer = ""
    sources_found = False

    for line in response.iter_lines():
        if not line:
            continue

        decoded_line = line.decode("utf-8")

        # SSE format: "data: {...}"
        if decoded_line.startswith("data: "):
            json_data = decoded_line.replace("data: ", "")
            data = json.loads(json_data)

            if data.get("type") == "token":
                full_answer += data.get("data", "")

            if data.get("type") == "complete":
                metadata = data.get("metadata", {})
                sources = metadata.get("sources", [])

                print("\n✅ STREAM COMPLETE")
                print("Sources:", sources)

                if sources:
                    sources_found = True

                break

    print("\nAnswer Preview:", full_answer[:200])
    assert sources_found, "❌ No sources returned in stream!"

def test_get_messages(conversation_id):
    print_section("4️⃣ GET MESSAGES (Persistence Test)")

    r = requests.get(f"{BASE_URL}/messages/{conversation_id}")
    print("Status:", r.status_code)

    messages = r.json()
    print("Messages Count:", len(messages))

    assistant_messages = [m for m in messages if m["role"] == "assistant"]

    assert len(assistant_messages) > 0, "❌ No assistant message found!"

    last_assistant = assistant_messages[-1]

    print("Assistant Sources:", last_assistant.get("sources"))

    assert last_assistant.get("sources"), "❌ Sources missing after refresh!"


def test_delete_conversation(conversation_id):
    print_section("5️⃣ DELETE CONVERSATION")

    r = requests.delete(f"{BASE_URL}/conversations/{conversation_id}")
    print("Status:", r.status_code)
    print("Response:", r.json())
    assert r.status_code == 200


if __name__ == "__main__":
    test_health()
    conv_id = create_conversation()
    test_stream(conv_id)
    time.sleep(2)
    test_get_messages(conv_id)
    test_delete_conversation(conv_id)

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")