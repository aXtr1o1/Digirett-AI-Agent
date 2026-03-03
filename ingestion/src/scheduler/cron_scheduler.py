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

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows fallback
import gc
import subprocess
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

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
from ingestion.src.config import (  # noqa: E402
    CHECKPOINT_DIR, 
    LOG_DIR, 
    LOG_FILE,
    LOVDATA_API_URL  # ✅ FIX: Import from config instead of hardcoding
)

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
STATE_FILE = CHECKPOINT_DIR / "scheduler_state.json"
LOCK_FILE  = CHECKPOINT_DIR / "scheduler.lock"   # ✅ ADD THIS LINE

# These can be overridden via .env
BATCH_SIZE       = int(os.getenv("SCHEDULER_BATCH_SIZE", "50"))
CRON_HOUR        = int(os.getenv("SCHEDULER_CRON_HOUR", "2"))
CRON_MINUTE      = int(os.getenv("SCHEDULER_CRON_MINUTE", "0"))
API_TIMEOUT_SECS = int(os.getenv("SCHEDULER_API_TIMEOUT", "30"))

# ===========================================================================
# Lock — prevents two cron processes overlapping on the same instance
# ===========================================================================

def _acquire_lock():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    if fcntl is None:
        # Windows fallback (no locking)
        return open(os.devnull, "w")

    lock_fh = open(LOCK_FILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_fh.write(str(os.getpid()))
        lock_fh.flush()
        return lock_fh
    except BlockingIOError:
        lock_fh.close()
        return None

def _release_lock(lock_fh):
    if fcntl is None:
        lock_fh.close()
        return

    try:
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass

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
    resp = requests.get(LOVDATA_API_URL, timeout=API_TIMEOUT_SECS)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        raise RuntimeError("Lovdata list API returned empty response")
    return data[0]["filename"]

# ===========================================================================
# Crontab registration  —  write directly, no manual crontab -e needed
# ===========================================================================

def _register_cron() -> bool:
    """
    Write the crontab entry directly.
    Cron entry format (matches image):
        0 2 * * * /path/to/python /path/to/cron_scheduler.py

    - Already registered → skip (idempotent)
    - Stale entry exists → replace
    - Not present       → append
    """
    script_path = Path(__file__).resolve()
    python_path = sys.executable
    new_line    = (
        f"{CRON_MINUTE} {CRON_HOUR} * * * "
        f"{python_path} {script_path} "
        f">> {LOG_DIR}/cron_stdout.log 2>&1"
    )

    try:
        result   = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
    except FileNotFoundError:
        logger.error("❌ 'crontab' not found — is cron installed?")
        return False

    lines = existing.splitlines()

    if new_line in lines:
        logger.info("✅ Crontab already registered — no change needed")
        return True

    # Remove any stale entry for this script
    lines = [ln for ln in lines if str(script_path) not in ln]
    lines.append(new_line)

    new_crontab = "\n".join(lines) + "\n"
    try:
        write = subprocess.run(
            ["crontab", "-"],
            input=new_crontab, text=True, capture_output=True
        )
        if write.returncode != 0:
            logger.error(f"❌ crontab write failed: {write.stderr.strip()}")
            return False
    except Exception as exc:
        logger.error(f"❌ crontab write error: {exc}")
        return False

    logger.info(f"✅ Crontab registered: {new_line}")
    return True

# ===========================================================================
# Core job – called by APScheduler every tick
# ===========================================================================

def ingestion_job(force: bool = False) -> int:
    """
    Single run:
        1. Acquire lock  — prevents overlap on shared Milvus instance
        2. Check Lovdata API for new archive
        3. If changed (or forced) → run pipeline
        4. Save state
        5. Release lock
        6. Process exits  ← OS reclaims ALL memory

    Returns exit code: 0 = success/skip, 1 = error
    """
    lock_fh = _acquire_lock()
    if lock_fh is None:
        return 1

    state = load_state()
    now   = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 70)
    logger.info("🕐 Scheduler tick started")
    logger.info(f"   PID        : {os.getpid()}")
    logger.info(f"   Time       : {now}")
    logger.info(f"   Batch size : {BATCH_SIZE}")
    logger.info(f"   Force      : {force}")
    logger.info("=" * 70)

    exit_code = 0

    try:
        state["last_check_time"] = now

        # Step 1: Check Lovdata API
        try:
            latest_archive = fetch_latest_archive_name()
            logger.info(f"📦 Latest archive from API: {latest_archive}")
        except Exception as e:
            logger.error(f"❌ Failed to check Lovdata API: {e}", exc_info=True)
            state["last_run_status"] = "api_check_failed"
            state["last_error"]      = str(e)
            save_state(state)
            return 1

        last_archive = state.get("last_archive_name")

        if last_archive:
            logger.info(f"📋 Last known archive: {last_archive}")
        else:
            logger.info("📋 No previous archive recorded (first run)")

        if latest_archive == last_archive:
            logger.info(
                "📄 Archive unchanged — running ingestion to check modified files"
            )
            state["last_run_status"] = "checking_modifications"
        else:
            logger.info(f"🔄 Archive changed: {last_archive} → {latest_archive}")

        if not force and latest_archive == last_archive:
            logger.info("✅ No new archive — skipping pipeline. Use --force to override.")
            state["last_run_status"] = "no_change"
            save_state(state)
            return 0

        # Step 2: Run pipeline
        # Import here — heavy libs (pymilvus, openai, supabase) only load NOW
        # They will be freed when this process exits
        logger.info("🔁 Running ingestion pipeline...")
        state["last_run_time"] = now
        logger.info(f"🚀 Triggering ingestion pipeline (limit={BATCH_SIZE})...")

        try:
            from ingestion.src.main import run_pipeline

            stats = run_pipeline(limit=None)

            # Step 3: Update state
            state["last_archive_name"]     = latest_archive
            state["last_run_status"]       = "success"
            state["last_run_time"]         = now
            state["total_files_processed"] = (
                state.get("total_files_processed", 0) + stats["success"]
            )

            if "last_error" in state:
                del state["last_error"]

            logger.info("=" * 70)
            logger.info("📊 INGESTION SUMMARY")
            logger.info(f"Archive              : {latest_archive}")
            logger.info(f"New files processed  : {stats['success']}")
            logger.info(f"Skipped (duplicate)  : {stats['skipped']}")
            logger.info(f"Failed               : {stats['failed']}")
            logger.info(f"Total checked        : {stats['total_files']}")
            logger.info(f"Lifetime total       : {state['total_files_processed']}")
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
            state["last_run_status"] = "pipeline_failed"
            state["last_error"]      = str(e)
            exit_code = 1

        finally:
            # Force memory release before saving state and exiting
            gc.collect()
            gc.collect()

    except Exception as e:
        logger.critical(f"💥 Unexpected error: {e}", exc_info=True)
        state["last_run_status"] = "unexpected_error"
        state["last_error"]      = str(e)
        exit_code = 1

    finally:
        save_state(state)
        _release_lock(lock_fh)
        logger.info("🔓 Lock released — process exiting, memory freed")

    return exit_code


# ===========================================================================
# Entry point  —  run directly by OS cron or manually
# ===========================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Lovdata ingestion scheduler — OS Cron edition.\n"
            "Run with no flags to register crontab and start immediately."
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run pipeline even if archive has not changed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check API and print state only. No pipeline, no crontab change.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print last persisted state and exit.",
    )

    args = parser.parse_args()

    # --status
    if args.status:
        state = load_state()
        print("\n" + "=" * 70)
        print("SCHEDULER STATE")
        print("=" * 70)
        print(f"  State file     : {STATE_FILE}")
        print(f"  Lock file      : {LOCK_FILE}")
        print(f"  Lock active    : {LOCK_FILE.exists()}")
        print(f"  Last archive   : {state.get('last_archive_name', 'N/A')}")
        print(f"  Last check     : {state.get('last_check_time',   'N/A')}")
        print(f"  Last run       : {state.get('last_run_time',     'N/A')}")
        print(f"  Last status    : {state.get('last_run_status',   'N/A')}")
        print(f"  Total processed: {state.get('total_files_processed', 0):,}")
        if "last_error" in state:
            print(f"  Last error     : {state['last_error']}")
        print("=" * 70 + "\n")
        sys.exit(0)

    # --dry-run
    if args.dry_run:
        logger.info("🔍 DRY-RUN — no pipeline, no crontab change")
        state = load_state()
        logger.info(f"   State file   : {STATE_FILE}")
        logger.info(f"   Last archive : {state.get('last_archive_name', 'N/A')}")
        logger.info(f"   Last status  : {state.get('last_run_status',   'N/A')}")
        logger.info(f"   Total files  : {state.get('total_files_processed', 0)}")
        try:
            latest  = fetch_latest_archive_name()
            changed = latest != state.get("last_archive_name")
            logger.info(f"   Latest archive : {latest}")
            logger.info(
                f"   Would run?     : "
                f"{'YES — archive changed' if changed else 'NO — unchanged (use --force)'}"
            )
        except Exception as e:
            logger.error(f"   API check failed: {e}")
        sys.exit(0)

    # Default: register crontab + run now
    logger.info("=" * 70)
    logger.info("🚀 Lovdata Scheduler — OS Cron Mode")
    logger.info(f"   Script : {Path(__file__).resolve()}")
    logger.info(f"   Python : {sys.executable}")
    logger.info(f"   Schedule: daily at {CRON_HOUR:02d}:{CRON_MINUTE:02d} UTC")
    logger.info("=" * 70)

    # Register crontab entry so OS cron fires this script automatically
    _register_cron()

    # Run pipeline right now (first run / manual trigger)
    sys.exit(ingestion_job(force=args.force))


if __name__ == "__main__":
    main()