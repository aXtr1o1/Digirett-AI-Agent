import argparse
import gc
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None  # Windows fallback

SCHEDULER_DIR = Path(__file__).resolve().parent
SRC_DIR       = SCHEDULER_DIR.parent
INGESTION_DIR = SRC_DIR.parent
PROJECT_ROOT  = INGESTION_DIR.parent

for p in [str(PROJECT_ROOT), str(INGESTION_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ingestion.src.config import (
    CHECKPOINT_DIR,
    LOG_DIR,
    LOG_FILE,
    SCHEDULER_CRON_HOUR,
    SCHEDULER_CRON_MINUTE,
)

logger = logging.getLogger("digirett-scheduler")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s | %(levelname)s | [scheduler] %(message)s")
    _fh_sched = logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8")
    _fh_sched.setFormatter(_formatter)
    _fh_ingest = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh_ingest.setFormatter(_formatter)
    _sh = logging.StreamHandler()
    _sh.setFormatter(_formatter)
    logger.addHandler(_fh_sched)
    logger.addHandler(_fh_ingest)
    logger.addHandler(_sh)


STATE_FILE = CHECKPOINT_DIR / "scheduler_state.json"
LOCK_FILE  = CHECKPOINT_DIR / "scheduler.lock"

CRON_HOUR   = SCHEDULER_CRON_HOUR
CRON_MINUTE = SCHEDULER_CRON_MINUTE



def _acquire_lock():
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    if fcntl is None:
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

def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning(f"Could not load state from {STATE_FILE}: {exc}")
    return {}


def save_state(state: dict) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    logger.debug(f"State saved -> {STATE_FILE}")



def ingestion_job(force: bool = False, dry_run: bool = False) -> int:
    """
    Executes the incremental comparison and ingestion cycle.
    Returns exit code: 0 = success, 1 = error
    """
    lock_fh = _acquire_lock()
    if lock_fh is None:
        logger.warning("Another scheduler process is already running. Exiting.")
        return 1

    state = load_state()
    now   = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 70)
    logger.info("🕐 Scheduler tick started")
    logger.info(f"   PID        : {os.getpid()}")
    logger.info(f"   Time       : {now}")
    logger.info(f"   Schedule   : daily at {CRON_HOUR:02d}:{CRON_MINUTE:02d} UTC")
    logger.info(f"   Force      : {force}")
    logger.info(f"   Dry-run    : {dry_run}")
    logger.info("=" * 70)

    exit_code = 0
    state["last_check_time"] = now

    try:
        from ingestion.src.main import RealTimePipelineRunner
        import asyncio

        runner = RealTimePipelineRunner(dry_run=dry_run)
        summary = asyncio.run(runner.run_incremental_sync(force=force))

        state["last_run_status"] = "success"
        state["last_run_time"]   = now
        target_count = summary.get("target_docs_processed", 0)
        state["total_files_processed"] = state.get("total_files_processed", 0) + target_count

        if "last_error" in state:
            del state["last_error"]

        logger.info("=" * 70)
        logger.info("📊 INCREMENTAL INGESTION SUMMARY")
        logger.info(f"Target docs processed : {target_count}")
        logger.info(f"Sections processed    : {summary.get('sections_processed', 0)}")
        logger.info(f"Milvus chunks indexed : {summary.get('milvus_chunks_indexed', 0)}")
        logger.info(f"Comparison Breakdown  : {summary.get('comparison_summary', {})}")
        logger.info(f"Lifetime docs sync'd  : {state['total_files_processed']}")
        logger.info("=" * 70)

    except Exception as exc:
        logger.error(f"❌ Incremental pipeline failed: {exc}", exc_info=True)
        state["last_run_status"] = "pipeline_failed"
        state["last_error"]      = str(exc)
        exit_code = 1

    finally:
        save_state(state)
        _release_lock(lock_fh)
        gc.collect()
        gc.collect()

    return exit_code


def run_daemon(force: bool = False, dry_run: bool = False):
    logger.info("=" * 70)
    logger.info("🚀 DigiRett Cron Background Daemon Started")
    logger.info(f"   Daily Execution Target: {CRON_HOUR:02d}:{CRON_MINUTE:02d} UTC")
    logger.info(f"   PID                   : {os.getpid()}")
    logger.info("=" * 70)

    while True:
        now = datetime.now(timezone.utc)
        target = now.replace(hour=CRON_HOUR, minute=CRON_MINUTE, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)

        sleep_seconds = (target - now).total_seconds()
        hours, remainder = divmod(sleep_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        logger.info(f"Sleeping for {int(hours)}h {int(minutes)}m {int(seconds)}s until next sync at {target.strftime('%Y-%m-%d %H:%M:%S')} UTC...")
        time.sleep(sleep_seconds)

        logger.info("Waking up! Triggering scheduled daily incremental ingestion...")
        try:
            ingestion_job(force=force, dry_run=dry_run)
        except Exception as exc:
            logger.error(f"Error during scheduled tick: {exc}", exc_info=True)

        # Brief pause to avoid duplicate firing within the same minute
        time.sleep(65)

def main():
    parser = argparse.ArgumentParser(description="DigiRett Daily Incremental Ingestion Scheduler")
    parser.add_argument("--daemon", action="store_true", help="Run continuously in 24/7 background daemon mode.")
    parser.add_argument("--run-now", action="store_true", help="Execute a single incremental ingestion job tick right now.")
    parser.add_argument("--dry-run", action="store_true", help="Compare against Supabase Bucket Ledger without writing to DB/Milvus.")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion even if unchanged in ledger.")
    parser.add_argument("--status", action="store_true", help="Print last persisted scheduler state and exit.")

    args = parser.parse_args()

    if args.status:
        state = load_state()
        print("\n" + "=" * 70)
        print("SCHEDULER STATE CHECKPOINT")
        print("=" * 70)
        print(f"  State file      : {STATE_FILE}")
        print(f"  Lock active     : {LOCK_FILE.exists()}")
        print(f"  Last check time : {state.get('last_check_time',   'N/A')}")
        print(f"  Last run time   : {state.get('last_run_time',     'N/A')}")
        print(f"  Last status     : {state.get('last_run_status',   'N/A')}")
        print(f"  Total processed : {state.get('total_files_processed', 0):,}")
        if "last_error" in state:
            print(f"  Last error      : {state['last_error']}")
        print("=" * 70 + "\n")
        sys.exit(0)

    if args.daemon:
        run_daemon(force=args.force, dry_run=args.dry_run)
    else:
        exit_code = ingestion_job(force=args.force, dry_run=args.dry_run)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()