from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Set

# Ensure project & ingestion root paths in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
SRC_DIR = CURRENT_DIR.parent
INGESTION_DIR = SRC_DIR.parent
PROJECT_ROOT = INGESTION_DIR.parent

for p in [str(PROJECT_ROOT), str(INGESTION_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ingestion.src.config import REPORTS_DIR, logger, settings
from ingestion.collectors.xapi_collector import XAPICollector
from ingestion.src.main import RealTimePipelineRunner, load_mapping
from ingestion.validation.url_validator import LovdataURLValidator


async def run_url_audit(
    test_limit: int | None = None,
    max_workers: int = 5,
    output_dir: Path = REPORTS_DIR,
    old_excel_path: Path | None = None,
) -> None:
    print("\n" + "=" * 70)
    print("   STARTING 404 URL AUDIT & DISCOVERY ACROSS 12 TARGET DOMAINS")
    print(f"   Workers: {max_workers} | Limit: {test_limit or 'ALL'} | Output: {output_dir}")
    print("=" * 70 + "\n")

    mapping = load_mapping()
    plans = mapping.build_domain_plans()
    target_areas: Set[str] = set()
    for plan in plans.values():
        target_areas.update(plan.rettsomrader)

    print(f"[1/4] Resolved {len(target_areas)} in-scope rettsområder across 12 domains.")

    unique_laws: Dict[str, Dict[str, Any]] = {}
    unique_regulations: Dict[str, Dict[str, Any]] = {}

    async with XAPICollector() as client:
        # Fetch Laws per area
        for idx, area in enumerate(sorted(target_areas), 1):
            if test_limit and len(unique_laws) >= test_limit:
                break
            laws, _, _ = await client.get_laws_by_area(area)
            for law in laws:
                dok_id = law.get("dok_id") or law.get("id")
                if dok_id and str(dok_id) not in unique_laws:
                    unique_laws[str(dok_id)] = law

        # Fetch Central Regulations
        areas_to_query = list(target_areas)[:2] if test_limit else target_areas
        c_regs, _, _ = await client.get_central_regulations_for_domain(areas_to_query)
        for reg in c_regs:
            canon_id = reg.get("sf_dok_id") or reg.get("dok_id") or reg.get("id")
            if canon_id and str(canon_id) not in unique_regulations:
                unique_regulations[str(canon_id)] = reg

        print(f"[2/4] Discovered {len(unique_laws)} unique laws and {len(unique_regulations)} unique central regulations.")

        # Fetch Law-Linked Regulations
        law_linked_count = 0
        laws_to_link = list(unique_laws.items())
        if test_limit and test_limit > 0:
            laws_to_link = laws_to_link[:test_limit]

        for dok_id, law in laws_to_link:
            try:
                linked, _, _ = await client.get_regulations_for_law(dok_id)
                for reg in linked:
                    canon_id = reg.get("sf_dok_id") or reg.get("dok_id") or reg.get("id")
                    if canon_id and str(canon_id) not in unique_regulations:
                        law_linked_count += 1
                        unique_regulations[str(canon_id)] = reg
            except Exception as exc:
                logger.debug("Linked reg fetch for %s: %s", dok_id, exc)

        print(f"[3/4] Added {law_linked_count} law-linked regulations. Total unique regulations: {len(unique_regulations)}")

    all_docs: List[Dict[str, Any]] = []
    for l in unique_laws.values():
        d = dict(l)
        d["document_type"] = "LAW"
        all_docs.append(d)

    for r in unique_regulations.values():
        d = dict(r)
        d["document_type"] = "REGULATION"
        all_docs.append(d)

    if test_limit and test_limit > 0:
        print(f"\n[INFO] Applying test limit: Truncating from {len(all_docs)} to {test_limit} documents.")
        all_docs = all_docs[:test_limit]

    print(f"\n[4/4] Probing {len(all_docs)} Lovdata URLs using {max_workers} concurrent workers (duplicates excluded)...")
    validator = LovdataURLValidator(max_workers=max_workers)
    records = validator.audit_documents(all_docs)

    excel_file, json_file = validator.export_reports(
        records=records,
        output_dir=output_dir,
        file_basename="Document_url_analysis_12_domains",
        old_excel_path=old_excel_path,
    )

    fully_working = [r for r in records if r.overall_working]
    err_404 = [r for r in records if r.xapi_has_data_lovdata_404]
    network_errors = [r for r in records if r.status_category in ("NETWORK_TIMEOUT_ERROR", "PROBE_ERROR")]
    missing_both = [r for r in records if r.missing_data]

    print("\n" + "=" * 70)
    print("   404 URL AUDIT SUMMARY REPORT")
    print("=" * 70)
    print(f"  * Total Documents Audited      : {len(records)}")
    print(f"  * Fully Working (200 OK)       : {len(fully_working)} ({(len(fully_working)/len(records)*100):.1f}%)")
    print(f"  * 404 Not Found (xAPI=OK)      : {len(err_404)}")
    print(f"  * Network / Timeout Errors     : {len(network_errors)}")
    print(f"  * Missing Both Sources         : {len(missing_both)}")
    print(f"  * Excel Workbook Report (5-sht): {excel_file}")
    print(f"  * JSON Audit Report            : {json_file}")
    print("=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit 404 and broken Lovdata URLs across all target domains.")
    parser.add_argument("--test-limit", type=int, default=None, help="Limit number of documents to probe")
    parser.add_argument("--workers", type=int, default=5, help="Number of concurrent probing workers (default: 5)")
    parser.add_argument("--output-dir", type=str, default=str(REPORTS_DIR), help="Output directory for reports")
    parser.add_argument("--compare-excel", type=str, default=None, help="Path to previous Excel file for delta comparison")
    args = parser.parse_args()

    try:
        asyncio.run(
            run_url_audit(
                test_limit=args.test_limit,
                max_workers=args.workers,
                output_dir=Path(args.output_dir),
                old_excel_path=Path(args.compare_excel) if args.compare_excel else None,
            )
        )
    except KeyboardInterrupt:
        print("\n[INFO] URL audit stopped by user.")


if __name__ == "__main__":
    main()
