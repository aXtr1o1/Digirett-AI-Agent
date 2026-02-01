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
    has_new_data,
    BATCH_SIZE as DEFAULT_BATCH,
    STATE_FILE,
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

    try:
        changed, latest_archive = has_new_data(state)
    except Exception as e:
        logger.error(f"❌ API check failed: {e}")
        return

    # ------------------------------------------------------------------
    # Dry-run → just print and exit
    # ------------------------------------------------------------------
    if dry_run:
        logger.info("\n🔍 DRY-RUN results:")
        logger.info(f"   Latest archive : {latest_archive}")
        logger.info(f"   Changed        : {changed}")
        if changed:
            logger.info("   → Pipeline WOULD run if not in dry-run mode")
        else:
            logger.info("   → Pipeline would be SKIPPED (no change)")
        logger.info("\n✅ Dry-run complete. No data was modified.\n")
        return

    # ------------------------------------------------------------------
    # Decide whether to run
    # ------------------------------------------------------------------
    if not changed and not force:
        logger.info("\nℹ️  No new data and --force not set. Exiting.")
        logger.info("   Use --force to run anyway.\n")
        return

    if not changed and force:
        logger.info("\n⚡ --force set: running pipeline despite no archive change")

    # ------------------------------------------------------------------
    # Run the pipeline
    # ------------------------------------------------------------------
    state["last_run_time"] = now
    logger.info(f"\n🚀 Running ingestion pipeline (limit={batch_size})...\n")

    try:
        from ingestion.src.main import run_pipeline   # noqa: E402

        run_pipeline(limit=batch_size)

        # Success
        state["last_archive_name"]     = latest_archive
        state["last_run_status"]       = "success"
        state["total_files_processed"] = state.get("total_files_processed", 0) + batch_size

        logger.info("\n" + "=" * 70)
        logger.info("✅ Manual trigger completed successfully")
        logger.info(f"   Archive : {latest_archive}")
        logger.info(f"   Files   : +{batch_size} (total: {state['total_files_processed']})")
        logger.info("=" * 70 + "\n")

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