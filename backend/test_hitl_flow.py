# -*- coding: utf-8 -*-
"""
test_hitl_flow.py -- Full HITL lifecycle test
Run from: c:\\Users\\sabar\\Documents\\aXtrLabs\\Digirett-AI-Agent\\backend\\

Usage:
    python test_hitl_flow.py

IMPORTANT: JWT tokens expire ~60s. Refresh before running:
    DevTools Console -> await window.Clerk.session.getToken()
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time

import requests

# Load .env automatically
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# =============================================================================
# CONFIG -- paste fresh tokens here before every run
# =============================================================================

BASE_URL = "http://localhost:8000/api/v1"

# Get from: DevTools Console -> await window.Clerk.session.getToken()
USER_TOKEN   = "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18zRDFRQWJNQWkza2Q3TXpUdkt5TVFERDlCUmsiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwOi8vbG9jYWxob3N0OjMwMDAiLCJleHAiOjE3Nzg1NzU5MTAsImZ2YSI6Wzc1LC0xXSwiaWF0IjoxNzc4NTc1ODUwLCJpc3MiOiJodHRwczovL2JlY29taW5nLXBpcmFuaGEtNTYuY2xlcmsuYWNjb3VudHMuZGV2IiwibmJmIjoxNzc4NTc1ODQwLCJzaWQiOiJzZXNzXzNEY0JDR0tJdkVHZHBLaUhZbHpDbG52MFVjMSIsInN0cyI6ImFjdGl2ZSIsInN1YiI6InVzZXJfM0RjQkNONzhiMzF3WktTWTRtQjROeUdqU2R3IiwidiI6Mn0.BfFaElXImMc9UMIVbdO3zqaLEsB_bNhzqpdRlLzV1BuJOrG30MVu0qJPj1qL_6QVe9xqaPcp715Y9U7ZA9vL3AWdbD16jtWuQ96R2jesbeubcc5KLemlH0wVKWyeN6NKgG44VtzE0DxmZUXQqzFlK8wuzQdn4vX7aPRMLyBI-kQt1_xUvxksU2q1E4M4iwe7U2dOJlxFo4ja7nEjNIHFM_ZP6CZiRCufJqUpBTGyvFNBf_zdxFW3d2REex064-FB_7XLblwfUxwissGg39Wo2eSCi-NccDRgj1dolODkkdfcdWp52OP2ZAdWNpC04kkiV3yL5E6gHHUIQHJfZVN7vQ"
LAWYER_TOKEN = "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18zRDFRQWJNQWkza2Q3TXpUdkt5TVFERDlCUmsiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwOi8vbG9jYWxob3N0OjMwMDAiLCJleHAiOjE3Nzg1NzU5MDQsImZ2YSI6WzEsLTFdLCJpYXQiOjE3Nzg1NzU4NDQsImlzcyI6Imh0dHBzOi8vYmVjb21pbmctcGlyYW5oYS01Ni5jbGVyay5hY2NvdW50cy5kZXYiLCJuYmYiOjE3Nzg1NzU4MzQsInNpZCI6InNlc3NfM0RjSzczYU5uVE44UEhZeFlNdmNJUTU1aUZHIiwic3RzIjoiYWN0aXZlIiwic3ViIjoidXNlcl8zRFo5NGN0aEQwTklTVkd2S2Y1TG9TMWJIWEEiLCJ2IjoyfQ.wE5M271qiM4Zonx-4AhuqY2AaKrbQHieZmLcC20DA26QRF2jFw2aH3LfRWm5rvE5RJlFGqs38OeLVOdKxVbEsTr4u5JM1d3Uplc_1G61amfFRbef4UbaCmfkPniBvYBa2C_aUZZDkEd-4oacSykRNZGny3Bs_zqVvJJAhdzlkjGSRUNBPF8jrYqo9h25bI_xuEQ6HuE3Ty7lo-7VqlMMoac_rnxMIce9OjzPSRbBLSe5yU5AnFpfpSs7o5FQ8rH8gEW4CC8zH3K4wrX-ueuc-KGapdIkzV48qkrI-EBfxhYM2q5GNdtEcqnFQapkDSy56EI7a68sNPN48y0zt2rctw"
ADMIN_TOKEN  = "eyJhbGciOiJSUzI1NiIsImNhdCI6ImNsX0I3ZDRQRDExMUFBQSIsImtpZCI6Imluc18zRDFRQWJNQWkza2Q3TXpUdkt5TVFERDlCUmsiLCJ0eXAiOiJKV1QifQ.eyJhenAiOiJodHRwOi8vbG9jYWxob3N0OjMwMDAiLCJleHAiOjE3Nzg1NzU4OTgsImZ2YSI6WzEzLC0xXSwiaWF0IjoxNzc4NTc1ODM4LCJpc3MiOiJodHRwczovL2JlY29taW5nLXBpcmFuaGEtNTYuY2xlcmsuYWNjb3VudHMuZGV2IiwibmJmIjoxNzc4NTc1ODI4LCJzaWQiOiJzZXNzXzNEY0ljand4c1dZWVdjcW1scEJQWU9VYzUyYiIsInN0cyI6ImFjdGl2ZSIsInN1YiI6InVzZXJfM0RJTjFwbTZyN1N4SmhTV3hYNkh5cWU1bFA5IiwidiI6Mn0.IUftrVY2G6D-F4FhIfBoTVEFNQbSVrVYTPttr9QEbhato7ew9hZlIh8JpZzfDlxJUNLRuwlBmcEB_f6X5WUWObB2oYkBjaX4jxF4vL8ki_j-IK2drzJfY0Ywt-CppohgiXlD1I0UtbrRgn_WPp3SneQI5Ep46Yjy922UJL17qG1Gg8-mn_SkzPpHRaf2dFva6Vi_L_YE9lnifpxRYajjwIO7KYsQOAhq4ZGKJqoFzSWSsyHQ8ZOml_c-Y0IYKFnH7GWJrXRUMb4XMBwH8ehVlk6bGBOGR4nMz0cVd_OPZX97Fvkcq3duZIqXG8EqXc6hXBg85FgdH3oDu-GRjiYIJA"

CONVERSATION_ID    = "1e90ca64-da68-4b8d-997c-15495a1d1e44"
TRIGGER_MESSAGE_ID = "a354e566-7e4e-420b-bb75-146d9e74afa2"
CAL_WEBHOOK_SECRET = "0030feef884ee145aaef36317bde53bb09a900964ea8c19c5c49b6e2458b1ef4"

# Loaded from .env automatically
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

# =============================================================================
# Helpers
# =============================================================================

GRN  = "\033[92m"
RED  = "\033[91m"
BLU  = "\033[94m"
YLW  = "\033[93m"
GRY  = "\033[90m"
RST  = "\033[0m"
SEP  = GRY + "-" * 64 + RST

def ok(msg):
    print("  [PASS]  " + msg)

def fail(msg, detail=""):
    print(RED + "  [FAIL]  " + msg + RST)
    if detail:
        print("          " + detail)
    print(RED + "  Stopping. Fix the above before continuing." + RST)
    sys.exit(1)

def info(msg):
    print(BLU + "  [INFO]  " + RST + msg)

def warn(msg):
    print(YLW + "  [WARN]  " + RST + msg)

def check(label, condition, detail=""):
    if condition:
        ok(label)
    else:
        fail(label, detail)

def auth_check(response, label):
    """Check for auth failures and give a clear fix hint instead of crashing."""
    if response.status_code in (401, 403):
        print(RED + "  [FAIL]  " + label + " -- " + str(response.status_code) + " Unauthorized" + RST)
        print("  --> Token expired. Get a fresh one:")
        print("      DevTools Console -> await window.Clerk.session.getToken({template:'supabase'})")
        print("      Paste into test_hitl_flow.py lines 37-39, then re-run.")
        sys.exit(1)
    return True

def headers(token):
    return {"Authorization": "Bearer " + token, "Content-Type": "application/json"}

def db_get(table, filters):
    """Direct Supabase REST query for DB verification."""
    url = SUPABASE_URL + "/rest/v1/" + table
    params = {"select": "*"}
    for k, v in filters.items():
        params[k] = "eq." + str(v)
    r = requests.get(url, params=params, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": "Bearer " + SUPABASE_KEY,
    }, timeout=10)
    if not r.ok:
        warn("DB query failed: " + r.text[:200])
        return []
    return r.json()

def get_ticket(ticket_id):
    rows = db_get("hitl_tickets", {"ticket_id": ticket_id})
    return rows[0] if rows else {}

def show_ticket(ticket):
    fields = [
        "status", "assigned_lawyer_id", "assigned_at",
        "booking_cal_booking_id", "booking_url", "booking_confirmed_at",
        "resolved_at", "closed_at", "outcome_notes", "alert_sent_at",
    ]
    for f in fields:
        v = ticket.get(f)
        if v is not None:
            print("          DB." + f + " = " + str(v))

# Global ticket_id shared across all phases
ticket_id = None

# =============================================================================
# Token validation
# =============================================================================

def validate_tokens():
    print("\nChecking JWT tokens...")
    for name, tok in [("USER", USER_TOKEN), ("LAWYER", LAWYER_TOKEN), ("ADMIN", ADMIN_TOKEN)]:
        preview = (tok[:30] + "...") if tok and len(tok) > 30 else (tok or "(empty)")
        print("  " + name + " prefix: " + preview)

        if not tok or len(tok) < 50:
            print(RED + "  FATAL: " + name + "_TOKEN is blank -- paste a fresh one" + RST)
            sys.exit(1)

        try:
            part = tok.split(".")[1]
            part += "=" * (4 - len(part) % 4)
            payload = json.loads(base64.b64decode(part))
            remaining = payload.get("exp", 0) - time.time()
            if remaining > 0:
                ok(name + " valid (" + str(int(remaining)) + "s remaining)")
            else:
                # Expired -- warn only; the API will return 401 if token is truly rejected
                print(YLW + "  [WARN]  " + RST + name + " expired " +
                      str(int(-remaining)) + "s ago -- will try anyway.")
                print("          If you get 401 errors below, paste a fresh token and re-run.")
                print("          TIP: use getToken({template:'supabase'}) for a 614s token.")
        except Exception as exc:
            print(YLW + "  [WARN]  " + RST + name + " parse error: " + str(exc))

# =============================================================================
# PHASE 1 -- User escalates
# =============================================================================

def phase1_escalate():
    global ticket_id
    print("\n" + SEP)
    print("PHASE 1 -- User escalates conversation")
    print(SEP)

    r = requests.post(BASE_URL + "/hitl/escalate", json={
        "conversation_id":    CONVERSATION_ID,
        "trigger_message_id": TRIGGER_MESSAGE_ID,
        "user_note":          "Automated HITL test",
    }, headers=headers(USER_TOKEN), timeout=10)

    info("POST /hitl/escalate --> " + str(r.status_code))
    info("Response: " + r.text[:300])
    auth_check(r, "POST /hitl/escalate")

    # Handle already-escalated (reuse the existing ticket)
    if r.status_code == 400 and "already escalated" in r.text.lower():
        warn("Conversation already escalated. Looking up existing ticket...")
        rows = db_get("hitl_tickets", {"conversation_id": CONVERSATION_ID})
        active = [x for x in rows if x.get("status") in ("open", "assigned", "booked")]
        if active:
            ticket_id = active[0]["ticket_id"]
            warn("Reusing ticket: " + ticket_id + " | status=" + active[0]["status"])
            return
        fail("Duplicate escalation but no active ticket found in DB")

    check("HTTP 200", r.status_code == 200, "Got " + str(r.status_code) + ": " + r.text[:200])
    data = r.json()
    ticket_id = data.get("ticket_id")
    check("ticket_id in response", bool(ticket_id), str(data))

    time.sleep(0.5)
    ticket = get_ticket(ticket_id)
    check("DB: ticket exists", bool(ticket), "ticket_id=" + str(ticket_id))
    check("DB: status=open", ticket.get("status") == "open", "Got: " + str(ticket.get("status")))
    check("DB: conversation_id correct", ticket.get("conversation_id") == CONVERSATION_ID)
    show_ticket(ticket)
    info("ticket_id = " + ticket_id)

# =============================================================================
# PHASE 2 -- Escalation status check
# =============================================================================

def phase2_status():
    print("\n" + SEP)
    print("PHASE 2 -- Check escalation status")
    print(SEP)

    r = requests.get(BASE_URL + "/hitl/status/" + CONVERSATION_ID,
                     headers=headers(USER_TOKEN), timeout=10)
    info("GET /hitl/status/{conv_id} --> " + str(r.status_code))
    auth_check(r, "GET /hitl/status")
    check("HTTP 200", r.status_code == 200, r.text[:200])
    data = r.json()
    check("is_escalated = true", data.get("is_escalated") is True, str(data))

# =============================================================================
# PHASE 3 -- Lawyer queue
# =============================================================================

def phase3_queue():
    print("\n" + SEP)
    print("PHASE 3 -- Lawyer views open queue")
    print(SEP)

    r = requests.get(BASE_URL + "/hitl/queue", headers=headers(LAWYER_TOKEN), timeout=10)
    info("GET /hitl/queue --> " + str(r.status_code))
    check("HTTP 200", r.status_code == 200, r.text[:200])

    tickets = r.json()
    check("Response is a list", isinstance(tickets, list))

    our = next((t for t in tickets if t.get("ticket_id") == ticket_id), None)
    if our:
        ok("Our ticket is in the queue")
        check("user_email present", bool(our.get("user_email")), str(our.get("user_email")))
        info("user_display_name: " + str(our.get("user_display_name")))
        info("user_email:        " + str(our.get("user_email")))
        has_summary = bool(our.get("conversation_summary"))
        info("conversation_summary: " + ("present" if has_summary else "null (need 2+ chat exchanges first)"))
    else:
        status_now = get_ticket(ticket_id).get("status")
        if status_now != "open":
            warn("Ticket not in open queue (status=" + str(status_now) + "). Already claimed -- continuing.")
        else:
            fail("Our ticket not found in queue", "ticket_id=" + ticket_id)

# =============================================================================
# PHASE 4 -- Lawyer self-assigns
# =============================================================================

def phase4_assign():
    print("\n" + SEP)
    print("PHASE 4 -- Lawyer self-assigns ticket")
    print(SEP)

    current = get_ticket(ticket_id)
    if current.get("status") == "assigned":
        warn("Already assigned. Skipping. assigned_lawyer_id=" + str(current.get("assigned_lawyer_id")))
        return

    r = requests.patch(BASE_URL + "/hitl/tickets/" + ticket_id + "/assign",
                       headers=headers(LAWYER_TOKEN), timeout=10)
    info("PATCH /hitl/tickets/{id}/assign --> " + str(r.status_code))
    info("Response: " + r.text[:200])

    if r.status_code == 409:
        warn("409 -- Race condition fired correctly (ticket already claimed by another lawyer)")
    else:
        check("HTTP 200", r.status_code == 200, r.text[:200])

    time.sleep(0.5)
    ticket = get_ticket(ticket_id)
    check("DB: status=assigned",       ticket.get("status") == "assigned",
          "Got: " + str(ticket.get("status")))
    check("DB: assigned_lawyer_id set", bool(ticket.get("assigned_lawyer_id")),
          "Got: " + str(ticket.get("assigned_lawyer_id")))
    check("DB: assigned_at set",       bool(ticket.get("assigned_at")))
    show_ticket(ticket)
    info("Check your email -- user should have received a 'lawyer assigned' notification")

# =============================================================================
# PHASE 4B -- Ticket details
# =============================================================================

def phase4b_details():
    print("\n" + SEP)
    print("PHASE 4B -- Lawyer views ticket details")
    print(SEP)

    r = requests.get(BASE_URL + "/hitl/tickets/" + ticket_id + "/details",
                     headers=headers(LAWYER_TOKEN), timeout=10)
    info("GET /hitl/tickets/{id}/details --> " + str(r.status_code))

    if r.status_code == 403:
        warn("403 -- This JWT is for a different lawyer than the assigned one (correct security)")
        return

    check("HTTP 200 or 403", r.status_code in (200, 403), r.text[:200])
    data = r.json()
    has_user = "user_info" in data or "user_email" in data
    check("user info present", has_user, "Keys: " + str(list(data.keys())))
    info("Response keys: " + str(list(data.keys())))

# =============================================================================
# PHASE 5 -- Admin full queue
# =============================================================================

def phase5_admin_queue():
    print("\n" + SEP)
    print("PHASE 5 -- Admin views full case queue (all statuses)")
    print(SEP)

    r = requests.get(BASE_URL + "/admin/tickets", headers=headers(ADMIN_TOKEN), timeout=10)
    info("GET /admin/tickets --> " + str(r.status_code))
    check("HTTP 200", r.status_code == 200, r.text[:200])

    tickets = r.json()
    check("Response is a list", isinstance(tickets, list))
    our = next((t for t in tickets if t.get("ticket_id") == ticket_id), None)
    check("Our ticket in admin queue", bool(our), str(ticket_id) + " not found in " + str(len(tickets)) + " tickets")

    if our:
        info("status:                 " + str(our.get("status")))
        info("lawyer_name:            " + str(our.get("lawyer_name")))
        info("user_display_name:      " + str(our.get("user_display_name")))
        info("conversation_summary:   " + ("present" if our.get("conversation_summary") else "null"))
        info("booking_url:            " + str(our.get("booking_url")))

# =============================================================================
# PHASE 6A -- Cal.com slots
# =============================================================================

def phase6a_slots():
    print("\n" + SEP)
    print("PHASE 6A -- User fetches available Cal.com slots")
    print(SEP)

    r = requests.get(BASE_URL + "/cal/slots/" + ticket_id,
                     params={"timezone": "Europe/Oslo"},
                     headers=headers(USER_TOKEN), timeout=15)
    info("GET /cal/slots/{id} --> " + str(r.status_code))
    info("Response: " + r.text[:400])

    if r.status_code == 400 and "credentials" in r.text.lower():
        warn("Lawyer has no Cal.com credentials. Fix with SQL:")
        t = get_ticket(ticket_id)
        warn("UPDATE lawyer_profiles SET cal_event_type_id='ID', cal_api_key='KEY'")
        warn("WHERE lawyer_id = '" + str(t.get("assigned_lawyer_id")) + "';")
        return None

    if r.status_code == 400 and "assigned" in r.text.lower():
        warn("Ticket not yet in 'assigned' status -- slots only available after assignment")
        return None

    if r.status_code != 200:
        warn("Slots fetch failed (" + str(r.status_code) + ") -- skipping 6B. Check Cal.com credentials.")
        return None

    data = r.json()
    slots = data.get("slots", {})
    ok("Slots fetched | Days available: " + str(len(slots)))

    for day, day_slots in slots.items():
        if day_slots:
            first = day_slots[0]["time"]
            info("First available slot: " + first)
            return first

    warn("No slots available -- add availability in your Cal.com event type")
    return None

# =============================================================================
# PHASE 6B -- Create booking
# =============================================================================

def phase6b_booking(start_time):
    print("\n" + SEP)
    print("PHASE 6B -- User creates Cal.com booking")
    print(SEP)

    if not start_time:
        warn("Skipping -- no slots returned from Phase 6A")
        return None

    r = requests.post(BASE_URL + "/cal/bookings/" + ticket_id, json={
        "start_time": start_time,
        "timezone":   "Europe/Oslo",
    }, headers=headers(USER_TOKEN), timeout=20)
    info("POST /cal/bookings/{id} --> " + str(r.status_code))
    info("Response: " + r.text[:400])
    check("HTTP 200", r.status_code == 200, r.text[:200])

    data = r.json()
    cal_id = data.get("cal_booking_id")
    check("cal_booking_id in response", bool(cal_id), str(data))
    info("cal_booking_id = " + str(cal_id))
    return cal_id

# =============================================================================
# PHASE 6C -- Simulate Cal.com webhook
# =============================================================================

def phase6c_webhook(cal_booking_id=None):
    print("\n" + SEP)
    print("PHASE 6C -- Simulate Cal.com booking-confirmed webhook")
    print(SEP)

    booking_id = cal_booking_id or 99999
    meet_url   = "https://meet.google.com/hitl-test-link"

    payload = {
        "triggerEvent": "BOOKING_CREATED",
        "payload": {
            "id":        booking_id,
            "startTime": "2026-05-20T09:00:00Z",
            "metadata": {
                "ticketId":       ticket_id,
                "conversationId": CONVERSATION_ID,
                "source":         "digirett-hitl",
            },
            "references": [{
                "type":       "google_meet_video",
                "meetingUrl": meet_url,
            }],
        },
    }

    body = json.dumps(payload).encode("utf-8")
    sig  = hmac.new(CAL_WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

    r = requests.post(BASE_URL + "/webhooks/cal", data=body, headers={
        "Content-Type":        "application/json",
        "X-Cal-Signature-256": sig,
    }, timeout=10)
    info("POST /webhooks/cal --> " + str(r.status_code))
    info("Response: " + r.text[:300])
    check("HTTP 200", r.status_code == 200, r.text[:200])

    time.sleep(0.5)
    ticket = get_ticket(ticket_id)
    check("DB: status=booked",               ticket.get("status") == "booked",
          "Got: " + str(ticket.get("status")))
    check("DB: booking_url set",             bool(ticket.get("booking_url")),
          "Got: " + str(ticket.get("booking_url")))
    check("DB: booking_confirmed_at set",    bool(ticket.get("booking_confirmed_at")))
    check("DB: booking_cal_booking_id set",  bool(ticket.get("booking_cal_booking_id")))
    show_ticket(ticket)
    info("Check email -- user should have received a booking confirmation with Meet link")

# =============================================================================
# PHASE 8 -- Lawyer resolves
# =============================================================================

def phase8_resolve():
    print("\n" + SEP)
    print("PHASE 8 -- Lawyer resolves ticket with response + outcome notes")
    print(SEP)

    r = requests.post(BASE_URL + "/hitl/tickets/" + ticket_id + "/respond", json={
        "content":       "Per husleieloven ss. 22 your landlord cannot raise rent without 3 months notice. [AUTOMATED TEST]",
        "outcome_notes": "Test case resolved. User advised on husleieloven rights.",
    }, headers=headers(LAWYER_TOKEN), timeout=10)
    info("POST /hitl/tickets/{id}/respond --> " + str(r.status_code))
    info("Response: " + r.text[:300])

    if r.status_code == 403:
        warn("403 -- This lawyer JWT is not the assigned lawyer. Admin will close instead.")
        return False

    check("HTTP 200", r.status_code == 200, r.text[:200])

    time.sleep(0.5)
    ticket = get_ticket(ticket_id)
    check("DB: status=resolved",    ticket.get("status") == "resolved",
          "Got: " + str(ticket.get("status")))
    check("DB: resolved_at set",    bool(ticket.get("resolved_at")))
    check("DB: outcome_notes set",  bool(ticket.get("outcome_notes")),
          "Got: " + str(ticket.get("outcome_notes")))

    # Verify hitl_responses table
    responses = db_get("hitl_responses", {"ticket_id": ticket_id})
    check("DB: hitl_responses has entry", len(responses) > 0,
          "No rows in hitl_responses for ticket " + ticket_id)
    if responses:
        info("hitl_responses[0].content: " + str(responses[0].get("content", "")[:80]))

    show_ticket(ticket)
    return True

# =============================================================================
# PHASE 8B -- Admin closes
# =============================================================================

def phase8b_admin_close():
    print("\n" + SEP)
    print("PHASE 8B -- Admin closes ticket")
    print(SEP)

    r = requests.patch(BASE_URL + "/admin/tickets/" + ticket_id + "/close", json={
        "outcome_notes": "Admin closure: case billed and archived. [AUTOMATED TEST]",
    }, headers=headers(ADMIN_TOKEN), timeout=10)
    info("PATCH /admin/tickets/{id}/close --> " + str(r.status_code))
    info("Response: " + r.text[:200])
    check("HTTP 200", r.status_code == 200, r.text[:200])

    time.sleep(0.5)
    ticket = get_ticket(ticket_id)
    check("DB: status=closed",  ticket.get("status") == "closed",
          "Got: " + str(ticket.get("status")))
    check("DB: closed_at set",  bool(ticket.get("closed_at")))
    show_ticket(ticket)

# =============================================================================
# FINAL -- print full DB record
# =============================================================================

def final_summary():
    print("\n" + SEP)
    print("FINAL -- Complete DB record for ticket " + ticket_id)
    print(SEP)

    ticket = get_ticket(ticket_id)
    if not ticket:
        warn("Could not fetch ticket from DB")
        return

    all_fields = [
        "ticket_id", "conversation_id", "user_id", "assigned_lawyer_id",
        "status", "created_at", "assigned_at",
        "booking_cal_booking_id", "booking_url", "booking_confirmed_at",
        "resolved_at", "closed_at", "outcome_notes", "alert_sent_at",
    ]
    print("\n  Full ticket DB record:")
    for f in all_fields:
        val = ticket.get(f)
        prefix = "[SET] " if val else "[   ] "
        print("  " + prefix + f + ": " + str(val))

# =============================================================================
# Main
# =============================================================================

def main():
    print("\n" + "=" * 64)
    print("  HITL FULL LIFECYCLE TEST")
    print("=" * 64)

    validate_tokens()

    # Check backend is up
    try:
        r = requests.get(BASE_URL + "/health", timeout=5)
        ok("Backend reachable (HTTP " + str(r.status_code) + ")")
    except Exception as exc:
        fail("Backend not reachable: " + str(exc), "Run: uvicorn main:app --reload --port 8000")

    # Check Supabase credentials loaded
    if not SUPABASE_URL or not SUPABASE_KEY:
        fail("SUPABASE_URL / SUPABASE_KEY not loaded from .env")
    ok("Supabase credentials loaded from .env")

    # Run all phases
    phase1_escalate()
    phase2_status()
    phase3_queue()
    phase4_assign()
    phase4b_details()
    phase5_admin_queue()

    slot   = phase6a_slots()
    cal_id = phase6b_booking(slot)
    phase6c_webhook(cal_id)

    phase8_resolve()
    phase8b_admin_close()

    final_summary()

    print("\n" + "=" * 64)
    print("  ALL PHASES DONE  |  ticket_id: " + str(ticket_id))
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
