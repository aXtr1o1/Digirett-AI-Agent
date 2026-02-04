"""
Lovdata Manual Trigger Handler
================================
Fire the ingestion pipeline RIGHT NOW without waiting for the cron schedule.

Usage:
    # Run pipeline immediately (same as the cron job would do, but on demand):
    python -m ingestion.src.scheduler.trigger_handler

    # Dry-run: only check the API, print state, do NOT run pipeline:
    python -m ingestion.src.scheduler.trigger_handler --dry-run

    # Override batch size for this single run:
    python -m ingestion.src.scheduler.trigger_handler --batch 100

    # Force run even if archive name hasn't changed:
    python -m ingestion.src.scheduler.trigger_handler --force
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve project root
# ---------------------------------------------------------------------------
SCHEDULER_DIR = Path(__file__).resolve().parent
SRC_DIR       = SCHEDULER_DIR.parent
INGESTION_DIR = SRC_DIR.parent
PROJECT_ROOT  = INGESTION_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.src.config import LOG_DIR, LOG_FILE                   # noqa: E402
from ingestion.src.scheduler.cron_scheduler import (                 # noqa: E402
    load_state,
    save_state,
    BATCH_SIZE as DEFAULT_BATCH,
    STATE_FILE,
    fetch_latest_archive_name,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | [trigger] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8"),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
    force=True,
)
logger = logging.getLogger("lovdata-trigger")


# ===========================================================================
# Core logic
# ===========================================================================

def run_trigger(batch_size: int, force: bool, dry_run: bool):
    state = load_state()
    now   = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 70)
    logger.info("🔧 Manual Trigger Handler")
    logger.info(f"   Time       : {now}")
    logger.info(f"   Batch size : {batch_size}")
    logger.info(f"   Force      : {force}")
    logger.info(f"   Dry-run    : {dry_run}")
    logger.info("=" * 70)

    # Show current persisted state
    if state:
        logger.info("\n📋 Current state:")
        logger.info(f"   Last archive    : {state.get('last_archive_name', 'N/A')}")
        logger.info(f"   Last check      : {state.get('last_check_time', 'N/A')}")
        logger.info(f"   Last run status : {state.get('last_run_status', 'N/A')}")
        logger.info(f"   Total processed : {state.get('total_files_processed', 0)}")
    else:
        logger.info("\n📋 No previous state found – first run")

    # ------------------------------------------------------------------
    # Check API for changes
    # ------------------------------------------------------------------
    state["last_check_time"] = now
    previous_archive = state.get("last_archive_name")


    try:
        latest_archive = fetch_latest_archive_name()
        logger.info(f"📦 Latest Lovdata archive: {latest_archive}")
    except Exception as e:
        logger.error(f"❌ API check failed: {e}")
        return
    
    # --------------------------------------------------------------
    # Skip run if no change and not forced
    # --------------------------------------------------------------
    if not force and previous_archive == latest_archive:
        logger.info("\n⏭️  No new archive detected. Skipping ingestion.")
        state["last_run_status"] = "no_change"
        save_state(state)
        return

    # ------------------------------------------------------------------
    # Dry-run → just print and exit
    # ------------------------------------------------------------------
    if dry_run:
        logger.info("\n🔍 DRY-RUN results:")
        logger.info(f"   Latest archive : {latest_archive}")
        logger.info("   → Pipeline WOULD run in normal mode")
        logger.info("\n✅ Dry-run complete.\n")
        return


    # ------------------------------------------------------------------
    # Run the pipeline
    # ------------------------------------------------------------------
    state["last_run_time"] = now
    logger.info(f"\n🚀 Running ingestion pipeline (limit={batch_size})...\n")

    try:
        from ingestion.src.main import run_pipeline   # noqa: E402

        stats = run_pipeline(limit=batch_size)

        # Success
        state["last_archive_name"]     = latest_archive
        state["last_run_status"]       = "success"
        state["total_files_processed"] = state.get("total_files_processed", 0) + stats["success"]

        logger.info("=" * 70)
        logger.info("📊 MANUAL TRIGGER SUMMARY")
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

    save_state(state)


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Manually trigger Lovdata ingestion pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only check the API and print state. Do NOT run the pipeline.",
    )
    parser.add_argument(
        "--batch",
        type=int,
        default=DEFAULT_BATCH,
        help=f"Number of files to process (default: {DEFAULT_BATCH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Run the pipeline even if the archive name hasn't changed.",
    )

    args = parser.parse_args()

    run_trigger(
        batch_size=args.batch,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()