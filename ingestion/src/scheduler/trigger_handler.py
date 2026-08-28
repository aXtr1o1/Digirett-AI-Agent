import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEDULER_DIR = Path(__file__).resolve().parent
SRC_DIR       = SCHEDULER_DIR.parent
INGESTION_DIR = SRC_DIR.parent
PROJECT_ROOT  = INGESTION_DIR.parent

for p in [str(PROJECT_ROOT), str(INGESTION_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ingestion.src.config import LOG_DIR, LOG_FILE
from ingestion.src.processors.comparing_engine import ComparingEngine
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.main import RealTimePipelineRunner, run_incremental

logger = logging.getLogger("digirett-trigger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _formatter = logging.Formatter("%(asctime)s | %(levelname)s | [trigger] %(message)s")
    _fh_sched = logging.FileHandler(LOG_DIR / "scheduler.log", encoding="utf-8")
    _fh_sched.setFormatter(_formatter)
    _fh_ingest = logging.FileHandler(LOG_FILE, encoding="utf-8")
    _fh_ingest.setFormatter(_formatter)
    _sh = logging.StreamHandler()
    _sh.setFormatter(_formatter)
    logger.addHandler(_fh_sched)
    logger.addHandler(_fh_ingest)
    logger.addHandler(_sh)



def run_trigger(
    domain: str = None,
    limit: int = None,
    force: bool = False,
    dry_run: bool = False,
):
    now = datetime.now(timezone.utc).isoformat()

    logger.info("=" * 70)
    logger.info("🔧 DigiRett Manual Trigger Handler")
    logger.info(f"   Time       : {now}")
    logger.info(f"   Domain     : {domain or 'ALL MAPPED'}")
    logger.info(f"   Limit      : {limit or 'None'}")
    logger.info(f"   Force      : {force}")
    logger.info(f"   Dry-run    : {dry_run}")
    logger.info("=" * 70)

    try:
        runner = RealTimePipelineRunner(dry_run=dry_run)
        summary = asyncio.run(runner.run_incremental_sync(
            domain_filter=domain,
            limit=limit,
            force=force,
        ))

        logger.info("\n📊 Manual Ingestion Run Summary:")
        print(json.dumps(summary, indent=2))
        logger.info("✅ Trigger execution completed successfully.")

    except Exception as exc:
        logger.error(f"❌ Trigger execution failed: {exc}", exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Manually trigger DigiRett Incremental Ingestion Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Compare against Supabase Bucket Ledger without DB/vector writes")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion of documents even if unchanged")
    parser.add_argument("--domain", type=str, default=None, help="Restrict to a specific domain ID or name")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of documents to process")
    parser.add_argument("--status", action="store_true", help="Print current Supabase Storage Bucket Ledger status")

    args = parser.parse_args()

    if args.status:
        store = SupabaseStore()
        engine = ComparingEngine(supabase_store=store)
        ledger = engine.load_ledger(force_refresh=True)
        docs = ledger.get("documents", {})

        print("\n" + "=" * 70)
        print("SUPABASE STORAGE BUCKET LEDGER STATUS")
        print("=" * 70)
        print(f"  Ledger Version   : {ledger.get('ledger_version', 'N/A')}")
        print(f"  Last Synced At   : {ledger.get('last_synced_at', 'N/A')}")
        print(f"  Total Documents  : {len(docs)}")
        synced_count = sum(1 for d in docs.values() if d.get("vdb_status") == "SYNCED")
        print(f"  Synced in Milvus : {synced_count}")
        print("=" * 70 + "\n")
        sys.exit(0)

    run_trigger(
        domain=args.domain,
        limit=args.limit,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()