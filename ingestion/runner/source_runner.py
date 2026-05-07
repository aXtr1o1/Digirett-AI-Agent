"""
runner/source_runner.py
========================
Lightweight wrapper that calls the pipeline orchestrator in main.py.
"""

import argparse
import sys
import logging

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="DigiRett Pipeline Source Runner")
    parser.add_argument("--source", type=str, help="Specific source to run")
    parser.add_argument("--input", type=str, help="Path to input file/directory")
    parser.add_argument("--dry-run", action="store_true", help="Run without DB writes")
    args = parser.parse_args()

    # Import locally to avoid circular dependencies
    try:
        from ingestion.src.main import run_layered_pipeline
    except ImportError as e:
        logger.error("Could not import pipeline orchestrator: %s", e)
        sys.exit(1)

    try:
        run_layered_pipeline(
            source_name=args.source,
            dry_run=args.dry_run,
            input_path=args.input
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
