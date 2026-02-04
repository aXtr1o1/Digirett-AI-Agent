"""
Lovdata Ingestion Cron Scheduler (APScheduler)
================================================
Runs on a fixed schedule (default: every day at 2:00 AM).

Workflow per tick:
    1. Call Lovdata /v1/publicData/list → get latest archive filename
    2. Compare against last known filename stored in scheduler_state.json
    3. If SAME   → "No change detected" → Exit tick (do nothing)
    4. If NEW    → archive name changed → new data available
        a. Download new archive (handled by lovdata_collector)
        b. Extract + parse XML
        c. Token-based chunking
        d. Generate embeddings (SageMaker BGE-M3)
        e. Store vectors in Milvus
        f. Store metadata in Supabase
        g. Update scheduler_state.json with new archive name + timestamp

State file: ingestion/data/checkpoints/scheduler_state.json
    {
        "last_archive_name": "lovtidend-avd1-2001-2025.tar.bz2",
        "last_check_time": "2026-01-31T02:00:00",
        "last_run_time": "2026-01-31T02:00:01",
        "last_run_status": "success",
        "total_files_processed": 50
    }

Key design decisions:
    - Change detection uses archive FILENAME from Lovdata API.
      Lovdata publishes new archives with new filenames when data changes
      (e.g. lovtidend-avd1-2001-2025.tar.bz2 → lovtidend-avd1-2001-2026.tar.bz2).
    - Deduplication is ALSO handled per-file inside run_pipeline via
      Supabase file_hash checks, so even if the same archive is re-ingested,
      already-processed files are skipped automatically.
    - BATCH_SIZE controls how many files to extract+process per run.
      The existing run_pipeline(limit=N) handles this.
    - If the pipeline crashes mid-run, the next scheduled tick will
      re-run with the same archive. Already-inserted files are skipped
      by the Supabase hash dedup, so only unprocessed files are retried.
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

# ---------------------------------------------------------------------------
# Resolve project root so that "ingestion.src.*" imports work regardless of
# where you launch this script from.
# ---------------------------------------------------------------------------
SCHEDULER_DIR = Path(__file__).resolve().parent          # ingestion/src/scheduler/
SRC_DIR       = SCHEDULER_DIR.parent                    # ingestion/src/
INGESTION_DIR = SRC_DIR.parent                          # ingestion/
PROJECT_ROOT  = INGESTION_DIR.parent                    # project root (DIGIRETT-AI-Agent/)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Now safe to import project modules
# ---------------------------------------------------------------------------
from ingestion.src.config import CHECKPOINT_DIR, LOG_DIR, LOG_FILE  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | [scheduler] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8"),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),   # shared ingestion log
        logging.StreamHandler(),
    ],
    force=True,
)
logger = logging.getLogger("lovdata-scheduler")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LOVDATA_LIST_URL = "https://api.lovdata.no/v1/publicData/list"
STATE_FILE       = CHECKPOINT_DIR / "scheduler_state.json"

# These can be overridden via .env  (see bottom of file for full list)
BATCH_SIZE       = int(os.getenv("SCHEDULER_BATCH_SIZE", "50"))
CRON_HOUR        = int(os.getenv("SCHEDULER_CRON_HOUR", "2"))
CRON_MINUTE      = int(os.getenv("SCHEDULER_CRON_MINUTE", "0"))
API_TIMEOUT_SECS = int(os.getenv("SCHEDULER_API_TIMEOUT", "30"))


# ===========================================================================
# State persistence
# ===========================================================================

def load_state() -> dict:
    """Load scheduler state from disk. Returns empty dict if no state yet."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"⚠️  Could not read state file, starting fresh: {e}")
    return {}


def save_state(state: dict) -> None:
    """Persist scheduler state to disk."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    logger.debug(f"State saved → {STATE_FILE}")


# ===========================================================================
# Change detection
# ===========================================================================

def fetch_latest_archive_name() -> str:
    """
    Ask Lovdata API: what is the current archive filename?
    Returns the filename string (e.g. 'lovtidend-avd1-2001-2025.tar.bz2').
    Raises on network / parse errors.
    """
    resp = requests.get(LOVDATA_LIST_URL, timeout=API_TIMEOUT_SECS)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RuntimeError("Lovdata list API returned empty response")
    return data[0]["filename"]



# ===========================================================================
# Core job – called by APScheduler every tick
# ===========================================================================

def ingestion_job():
    """
    Single scheduled tick:
        1. Check for new data
        2. If changed → run the full ingestion pipeline
        3. Update state
    """
    state = load_state()
    now   = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 70)
    logger.info("🕐 Scheduler tick started")
    logger.info(f"   Time       : {now}")
    logger.info(f"   Batch size : {BATCH_SIZE}")
    logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Step 1: Ask Lovdata what archive is current (for logging only)
    # ------------------------------------------------------------------
    state["last_check_time"] = now

    try:
        latest_archive = fetch_latest_archive_name()
        logger.info(f"📦 Latest Lovdata archive: {latest_archive}")
    except Exception as e:
        logger.error(f"❌ Failed to check Lovdata API: {e}")
        state["last_run_status"] = "api_check_failed"
        save_state(state)
        return

    logger.info("🔁 Running pipeline to detect new XML files via Supabase hash...")

    # ------------------------------------------------------------------
    # Step 3: New data → run pipeline
    # ------------------------------------------------------------------
    state["last_run_time"] = now
    logger.info(f"🚀 Triggering ingestion pipeline (limit={BATCH_SIZE})...")

    try:
        # Import here (not at module top) to avoid heavy initialisation
        # (boto3, pymilvus, supabase) when just doing the API check.
        from ingestion.src.main import run_pipeline   # noqa: E402

        stats = run_pipeline(limit=BATCH_SIZE)

        # ------------------------------------------------------------------
        # Step 4: Success → update state
        # ------------------------------------------------------------------
        state["last_archive_name"] = latest_archive
        state["last_run_status"] = "success"
        state["last_run_time"] = now

        logger.info("=" * 70)
        logger.info("📊 INGESTION SUMMARY")
        logger.info(f"Archive              : {latest_archive}")
        logger.info(f"New files processed  : {stats['success']}")
        logger.info(f"Skipped (duplicate)  : {stats['skipped']}")
        logger.info(f"Failed               : {stats['failed']}")
        logger.info(f"Total checked        : {stats['total_files']}")
        logger.info("=" * 70)


    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        state["last_run_status"] = "pipeline_failed"
        state["last_error"]      = str(e)
        # Do NOT update last_archive_name – next tick will retry

    save_state(state)


# ===========================================================================
# APScheduler event listener (optional console feedback)
# ===========================================================================

def on_job_event(event):
    if event.exception:
        logger.error(f"🚨 Job crashed: {event.exception}")
    else:
        logger.info("✔️  Job finished without exception")


# ===========================================================================
# Entry point
# ===========================================================================

def main():
    logger.info("=" * 70)
    logger.info("🛡️  Lovdata Cron Scheduler starting up")
    logger.info(f"   Schedule   : every day at {CRON_HOUR:02d}:{CRON_MINUTE:02d} UTC")
    logger.info(f"   Batch size : {BATCH_SIZE} files per run")
    logger.info(f"   State file : {STATE_FILE}")
    logger.info("=" * 70)

    # Show current state if it exists
    state = load_state()
    if state:
        logger.info("📋 Loaded previous state:")
        logger.info(f"   Last archive   : {state.get('last_archive_name', 'N/A')}")
        logger.info(f"   Last check     : {state.get('last_check_time', 'N/A')}")
        logger.info(f"   Last status    : {state.get('last_run_status', 'N/A')}")
        logger.info(f"   Total processed: {state.get('total_files_processed', 0)}")
    else:
        logger.info("📋 No previous state – this is the first run")

    # Create the scheduler
    scheduler = BlockingScheduler(timezone="UTC")

    # Register the cron job
    scheduler.add_job(
        ingestion_job,
        trigger=CronTrigger(hour=CRON_HOUR, minute=CRON_MINUTE),
        id="lovdata_ingestion",
        name="Lovdata Daily Ingestion",
        replace_existing=True,
    )

    # Listen for job completion events
    scheduler.add_listener(on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    logger.info("\n⏳ Waiting for next scheduled trigger...\n")
    logger.info("   Press Ctrl+C to stop the scheduler.\n")

    try:
        scheduler.start()          # blocks forever
    except KeyboardInterrupt:
        logger.info("\n👋 Scheduler stopped by user.")
        scheduler.shutdown()


if __name__ == "__main__":
    main()