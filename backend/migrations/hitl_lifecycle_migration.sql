-- ============================================================
-- HITL Lifecycle Database Migration
-- Run these in the Supabase SQL Editor (Dashboard → SQL Editor)
-- ============================================================

-- ── 1. lawyer_profiles — Cal.com credentials per lawyer ──────────────
-- Each lawyer has their OWN Cal.com account.
-- Admin sets these via PATCH /api/v1/admin/lawyers/{id}/cal-credentials
ALTER TABLE lawyer_profiles
  ADD COLUMN IF NOT EXISTS cal_event_type_id TEXT,
  ADD COLUMN IF NOT EXISTS cal_api_key       TEXT;


-- ── 2. hitl_tickets — booking tracking + alert + outcome ─────────────

-- booking_cal_booking_id: Cal.com's booking ID (from webhook payload)
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS booking_cal_booking_id  TEXT;

-- booking_url: Google Meet link extracted from Cal.com booking references
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS booking_url             TEXT;

-- booking_confirmed_at: when Cal.com webhook fired confirming the booking
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS booking_confirmed_at    TIMESTAMPTZ;

-- outcome_notes: lawyer's internal case notes on resolution (Phase 8)
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS outcome_notes           TEXT;

-- alert_sent_at: set by background task so admin is alerted only once
--   per ticket (prevents duplicate 30-min alerts for same case)
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS alert_sent_at           TIMESTAMPTZ;

-- closed_at: timestamp when admin explicitly closes a case (status='closed')
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS closed_at               TIMESTAMPTZ;

-- resolved_at: timestamp when lawyer marks case resolved (status='resolved')
--   (add if it doesn't exist already in your schema)
ALTER TABLE hitl_tickets
  ADD COLUMN IF NOT EXISTS resolved_at             TIMESTAMPTZ;


-- ── 3. Verify the new columns ─────────────────────────────────────────
-- Run this SELECT to confirm all columns were added:
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'hitl_tickets'
  AND column_name IN (
    'booking_cal_booking_id',
    'booking_url',
    'booking_confirmed_at',
    'outcome_notes',
    'alert_sent_at',
    'closed_at',
    'resolved_at'
  )
ORDER BY column_name;

-- Expected result: 7 rows, one per column name above.


-- ── 4. Verify lawyer_profiles ─────────────────────────────────────────
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'lawyer_profiles'
  AND column_name IN ('cal_event_type_id', 'cal_api_key')
ORDER BY column_name;

-- Expected result: 2 rows.
