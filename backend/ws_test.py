"""
ws_test.py — Test document query scenarios via WebSocket
Run: python ws_test.py

Requires: pip install websockets
"""

import asyncio
import json
import sys
import urllib.request

import websockets

# ── Config — update these if needed ──────────────────────────────────
BASE_HTTP = "http://localhost:8000"
BASE_WS   = "ws://localhost:8000"
CONV_ID   = "009c9c67-78f6-4f93-8fc9-5c2454180b35"
USER_ID   = "2a06144d-4675-4c38-b7f8-13c02da91af5"

# Candidate WebSocket paths — script tries each until one connects
WS_PATHS = [
    "/api/v1/chat/ws",
    "/api/v1/ws",
    "/ws",
]
# ─────────────────────────────────────────────────────────────────────


def check_http_health():
    """Quick HTTP check to confirm the server is reachable at all."""
    url = f"{BASE_HTTP}/api/v1/health"
    print(f"[1] Checking server via HTTP: GET {url}")
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        body = resp.read().decode()
        print(f"    OK Server reachable | status={resp.status} | body={body[:120]}")
        return True
    except Exception as exc:
        print(f"    FAIL Server NOT reachable: {exc}")
        print("    Make sure uvicorn is running in another terminal:")
        print("      uvicorn main:app --reload --port 8000")
        return False


async def find_ws_path():
    """Try each candidate WS path and return the first that connects."""
    print(f"\n[2] Trying WebSocket paths...")
    for path in WS_PATHS:
        url = BASE_WS + path
        print(f"    Trying {url} ...")
        try:
            async with websockets.connect(url, open_timeout=5) as ws:
                print(f"    OK Connected at {url}")
                return url
        except Exception as exc:
            print(f"    FAIL {type(exc).__name__}: {exc}")
    return None


async def send_query(ws, query: str, label: str):
    """Send one query over an open WebSocket and print streamed events."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Query: \"{query}\"")
    print(f"{'='*60}")

    payload = {
        "query":           query,
        "conversation_id": CONV_ID,
        "user_id":         USER_ID,
        "top_k":           5,
    }
    await ws.send(json.dumps(payload))

    full_answer = ""

    while True:
        try:
            raw   = await asyncio.wait_for(ws.recv(), timeout=120)
            event = json.loads(raw)
        except asyncio.TimeoutError:
            print("\n[TIMEOUT] No response in 120s")
            break

        etype = event.get("type")

        if etype == "intent":
            data = event.get("data", {})
            print(f"\n[INTENT]  intent={data.get('intent')}  language={data.get('language')}")

        elif etype == "token":
            token = event.get("data", "")
            print(token, end="", flush=True)
            full_answer += token

        elif etype == "sources":
            sources = event.get("data", [])
            if sources:
                print(f"\n[SOURCES] {len(sources)} source(s): {sources[:2]}")
            else:
                print(f"\n[SOURCES] (none)")

        elif etype == "complete":
            meta = event.get("metadata", {})
            print(f"\n\n[COMPLETE]")
            print(f"  intent     : {meta.get('intent')}")
            print(f"  score      : {meta.get('score')}")
            print(f"  confidence : {meta.get('confidence')}")
            print(f"  chunks     : {meta.get('chunks_retrieved', 0)}")
            print(f"  tokens     : {meta.get('tokens_generated', 0)}")
            break

        elif etype == "error":
            print(f"\n[ERROR] {event.get('message')}")
            break

    return full_answer


async def run_scenarios(ws_url: str):
    print(f"\n[3] Connecting to {ws_url} ...")

    async with websockets.connect(ws_url, open_timeout=10) as ws:
        print("    OK Connected\n")

        scenarios = [

            # ✅ 1. DOC QA (STRICT: NO VDB)
            (
                "SCENARIO 2 - DOCQA",
                "What does this document say? Give me a full summary of the company."
            ),

            # ✅ 2. LEGAL (USE DOC SUMMARY → VDB SEARCH)
            (
                "SCENARIO 3 - LEGAL",
                "What does Norwegian law say about share capital requirements for companies?"
            ),

            # ✅ 3. HYBRID (DOC + LAW)
            (
                "SCENARIO 4 - HYBRID",
                "Is the share capital in this document compliant with Norwegian Companies Act?"
            ),

            # ✅ 4. FOLLOW-UP (MEMORY)
            (
                "SCENARIO 5 - FOLLOWUP",
                "Explain that in simple terms."
            ),
        ]

        for label, query in scenarios:
            await send_query(ws, query, label)
            await asyncio.sleep(2)

    print(f"\n{'='*60}")
    print("All scenarios complete.")
    print(f"{'='*60}")
    print("\nCheck SERVER terminal logs for:")
    print("  'DOCQA pipeline'    -> Scenario 2 routed correctly")
    print("  'LEGAL pipeline'    -> Scenario 3 routed correctly")
    print("  'HYBRID pipeline'   -> Scenario 4 routed correctly")
    print("  'FOLLOWUP pipeline' -> Scenario 5 routed correctly")


async def main():
    if not check_http_health():
        sys.exit(1)

    ws_url = await find_ws_path()
    if not ws_url:
        print(
            "\nERROR: Could not connect to any WebSocket path.\n"
            "Check your chat.py for the exact @router.websocket('...') path\n"
            "and update WS_PATHS at the top of this script."
        )
        sys.exit(1)

    await run_scenarios(ws_url)


if __name__ == "__main__":
    asyncio.run(main())