# from __future__ import annotations

# import argparse
# import csv
# import json
# import math
# import os
# import sys
# from collections import Counter
# from typing import Any

# from dotenv import load_dotenv
# from pymilvus import Collection, connections, utility
# from supabase import create_client

# # ─────────────────────────────────────────────────────────────────────────────
# # Terminal helpers
# # ─────────────────────────────────────────────────────────────────────────────

# W = 120  # line width


# def hr(char: str = "-") -> str:
#     return char * W


# def section(title: str) -> None:
#     print()
#     print(hr("="))
#     print(f"  {title}")
#     print(hr("="))


# def subsection(title: str) -> None:
#     print()
#     print(hr("-"))
#     print(f"  {title}")
#     print(hr("-"))


# def kv(key: str, value: Any, w: int = 30) -> None:
#     print(f"  {key:<{w}}: {value}")


# # ─────────────────────────────────────────────────────────────────────────────
# # Env
# # ─────────────────────────────────────────────────────────────────────────────

# def get_env(name: str, default: str | None = None) -> str:
#     value = os.getenv(name, default or "")
#     if not str(value).strip():
#         raise RuntimeError(f"Missing env var: {name}")
#     return str(value).strip()


# # ─────────────────────────────────────────────────────────────────────────────
# # Supabase
# # ─────────────────────────────────────────────────────────────────────────────

# SUPABASE_COLUMNS = (
#     "file_name,source_id,source_doc_url,domain,subdomain,"
#     "b2b_b2c,tier,jurisdiction,legal_validation,xml_bucket_path,"
#     "doc_title,created_at,updated_at"
# )

# SUPABASE_KEY_ORDER = [
#     "file_name", "source_id", "source_doc_url", "domain", "subdomain",
#     "b2b_b2c", "tier", "jurisdiction", "legal_validation",
#     "xml_bucket_path", "doc_title", "created_at", "updated_at",
# ]


# def fetch_supabase_row(file_name: str, table: str) -> dict | None:
#     url = get_env("SUPABASE_URL")
#     key = get_env("SUPABASE_SERVICE_KEY")
#     client = create_client(url, key)
#     resp = (
#         client.table(table)
#         .select(SUPABASE_COLUMNS)
#         .eq("file_name", file_name)
#         .limit(1)
#         .execute()
#     )
#     data = resp.data or []
#     return data[0] if data else None


# def print_supabase_row(row: dict) -> None:
#     section("SUPABASE FILE METADATA")
#     for k in SUPABASE_KEY_ORDER:
#         kv(k, row.get(k, ""))
#     for k, v in row.items():
#         if k not in SUPABASE_KEY_ORDER:
#             kv(k, v)


# # ─────────────────────────────────────────────────────────────────────────────
# # Milvus connection
# # ─────────────────────────────────────────────────────────────────────────────

# def connect_milvus() -> Collection:
#     host = get_env("MILVUS_HOST")
#     port = get_env("MILVUS_PORT")
#     name = get_env("MILVUS_COLLECTION")
#     connections.connect(alias="default", host=host, port=port)
#     col = Collection(name)
#     col.load()
#     return col


# # ─────────────────────────────────────────────────────────────────────────────
# # Schema helpers
# # ─────────────────────────────────────────────────────────────────────────────

# VECTOR_DTYPES = {"FLOAT_VECTOR", "BINARY_VECTOR"}


# def scalar_fields(col: Collection) -> list[str]:
#     return [f.name for f in col.schema.fields if str(f.dtype) not in VECTOR_DTYPES]


# def vector_field_name(col: Collection) -> str | None:
#     for f in col.schema.fields:
#         if str(f.dtype) in VECTOR_DTYPES:
#             return f.name
#     return None


# # ─────────────────────────────────────────────────────────────────────────────
# # Collection-level stats
# # ─────────────────────────────────────────────────────────────────────────────

# def print_collection_stats(col: Collection) -> None:
#     section(f"COLLECTION STATS - {col.name}")

#     try:
#         total = col.num_entities
#     except Exception:
#         total = "unknown"

#     kv("Collection name", col.name)
#     kv("Total entities (ALL docs)", total)
#     kv("Description", col.schema.description or "-")

#     try:
#         state = utility.load_state(col.name)
#         kv("Load state", state)
#     except Exception:
#         kv("Load state", "unknown")

#     subsection("SCHEMA - ALL FIELDS")
#     print(f"  {'#':<4} {'Field Name':<28} {'Dtype':<24} {'Extras'}")
#     print(hr("."))
#     for i, f in enumerate(col.schema.fields, 1):
#         extras = []
#         if f.is_primary:
#             extras.append("PRIMARY")
#         if getattr(f, "auto_id", False):
#             extras.append("auto_id")
#         if getattr(f, "max_length", None):
#             extras.append(f"max_length={f.max_length}")
#         if getattr(f, "dim", None):
#             extras.append(f"dim={f.dim}")
#         print(f"  {i:<4} {f.name:<28} {str(f.dtype):<24} {', '.join(extras)}")

#     subsection("INDEX INFO")
#     try:
#         indexes = col.indexes
#         if not indexes:
#             print("  No indexes found.")
#         for idx in indexes:
#             kv("  Field", idx.field_name)
#             kv("  Index type", idx.params.get("index_type", "—"))
#             kv("  Metric type", idx.params.get("metric_type", "—"))
#             for pk, pv in idx.params.get("params", {}).items():
#                 kv(f"    {pk}", pv)
#             print()
#     except Exception as exc:
#         print(f"  Could not fetch index info: {exc}")


# # ─────────────────────────────────────────────────────────────────────────────
# # Query chunks
# # ─────────────────────────────────────────────────────────────────────────────

# def query_chunks(
#     col: Collection,
#     *,
#     file_name: str,
#     source_doc_url: str,
#     limit: int,
#     fetch_embeddings: bool,
# ) -> tuple[list[dict], str, str]:
#     schema_field_names = {f.name for f in col.schema.fields}
#     output_fields = scalar_fields(col)

#     if fetch_embeddings:
#         vf = vector_field_name(col)
#         if vf:
#             output_fields.append(vf)

#     if "file_name" in schema_field_names:
#         expr = f'file_name == "{file_name}"'
#         rows = col.query(expr=expr, output_fields=output_fields, limit=limit)
#         return rows, "file_name", expr

#     if "source_doc_url" in schema_field_names:
#         expr = f'source_doc_url == "{source_doc_url}"'
#         rows = col.query(expr=expr, output_fields=output_fields, limit=limit)
#         return rows, "source_doc_url", expr

#     raise RuntimeError(
#         "Collection has neither 'file_name' nor 'source_doc_url'. "
#         f"Available fields: {sorted(schema_field_names)}"
#     )


# # ─────────────────────────────────────────────────────────────────────────────
# # Embedding stats
# # ─────────────────────────────────────────────────────────────────────────────

# def embedding_stats(vec: list[float]) -> dict[str, Any]:
#     if not vec:
#         return {"dim": 0, "norm": None, "min": None, "max": None, "mean": None}
#     norm = math.sqrt(sum(x * x for x in vec))
#     return {
#         "dim":  len(vec),
#         "norm": round(norm, 6),
#         "min":  round(min(vec), 6),
#         "max":  round(max(vec), 6),
#         "mean": round(sum(vec) / len(vec), 8),
#     }


# # ─────────────────────────────────────────────────────────────────────────────
# # Section URL builder
# # ─────────────────────────────────────────────────────────────────────────────

# def build_section_url(chunk: dict, supabase_row: dict) -> str:
#     base_url = (
#         str(chunk.get("source_doc_url", "")).strip()
#         or str(supabase_row.get("source_doc_url", "")).strip()
#     )
#     section_ref = str(chunk.get("section_ref", "")).strip()
#     if not base_url:
#         return ""
#     base = base_url.split("::")[0].split("#")[0].rstrip("/")
#     if not section_ref:
#         return base
#     anchor = section_ref.replace(" ", "")
#     return f"{base}#{anchor}"


# # ─────────────────────────────────────────────────────────────────────────────
# # Section heatmap
# # ─────────────────────────────────────────────────────────────────────────────

# def print_section_heatmap(rows: list[dict]) -> None:
#     subsection("SECTION COVERAGE HEATMAP  (chunks per section_ref)")
#     counts: Counter = Counter(r.get("section_ref", "") for r in rows)
#     max_count = max(counts.values(), default=1)
#     bar_scale = 50

#     for ref, cnt in sorted(counts.items(), key=lambda x: x[0]):
#         bar_len = max(1, round(cnt / max_count * bar_scale))
#         bar = "#" * bar_len
#         print(f"  {str(ref):<45} {bar:<52} {cnt}")


# # ─────────────────────────────────────────────────────────────────────────────
# # Print every chunk — ALL fields, FULL text, NO truncation
# # ─────────────────────────────────────────────────────────────────────────────

# # Fields to print first (in this order), before any remaining fields
# FIELD_PRINT_ORDER = [
#     "milvus_id",
#     "chunk_id",
#     "document_id",
#     "file_name",
#     "source_id",
#     "source_doc_url",
#     "section_ref",
#     "source_ref",
#     "domain",
#     "subdomain",
#     "b2b_b2c",
#     "tier",
#     "jurisdiction",
# ]


# def print_all_chunks(
#     rows: list[dict],
#     supabase_row: dict,
#     *,
#     fetch_embeddings: bool,
#     vf_name: str | None,
# ) -> dict:
#     """
#     Prints every chunk with ALL fields and FULL text — zero truncation.
#     Returns a quality_report dict used by print_summary().
#     """
#     quality: dict[str, Any] = {
#         "empty_text":            [],
#         "whitespace_only":       [],
#         "very_short":            [],
#         "missing_chunk_id":      [],
#         "missing_document_id":   [],
#         "embedding_missing":     [],
#         "embedding_dim_mismatch":[],
#     }
#     chunk_id_seen: Counter = Counter()
#     doc_id_seen:   Counter = Counter()

#     expected_dim = int(os.getenv("MILVUS_DIMENSION", "1536"))

#     section("FULL CHUNK CONTENT  —  ALL FIELDS  |  COMPLETE TEXT  (zero truncation)")

#     for idx, chunk in enumerate(rows, start=1):
#         section_url = build_section_url(chunk, supabase_row)
#         text        = chunk.get("text", "")
#         chunk_id    = chunk.get("chunk_id", "")
#         document_id = chunk.get("document_id", "")

#         chunk_id_seen[chunk_id] += 1
#         doc_id_seen[document_id] += 1

#         # -- Quality flags --
#         if not text:
#             quality["empty_text"].append(idx)
#         elif not text.strip():
#             quality["whitespace_only"].append(idx)
#         elif len(text.strip()) < 20:
#             quality["very_short"].append(idx)

#         if not chunk_id:
#             quality["missing_chunk_id"].append(idx)
#         if not document_id:
#             quality["missing_document_id"].append(idx)

#         # -- Chunk header --
#         print()
#         print(f"  +- CHUNK  [{idx} / {len(rows)}]  {'-' * (W - 20)}")

#         # -- Metadata: ordered fields first --
#         for field in FIELD_PRINT_ORDER:
#             if field in chunk:
#                 kv(f"  |  {field}", chunk[field], w=28)

#         # -- Metadata: any remaining scalar fields not in the order list --
#         skip_fields = set(FIELD_PRINT_ORDER) | {"text", "embedding"} | {vf_name or "__none__"}
#         for k, v in chunk.items():
#             if k not in skip_fields:
#                 kv(f"  |  {k}", v, w=28)

#         # -- Computed section URL --
#         kv("  |  section_url (computed)", section_url, w=28)

#         # -- Full text -- every character, every line --
#         print(f"  |")
#         print(f"  |  TEXT   length={len(text)} chars   lines={len(text.splitlines())}")
#         print(f"  +{'-' * (W - 3)}")
#         if text:
#             for line in text.splitlines():
#                 print(f"  |  {line}")
#         else:
#             print(f"  |  [EMPTY TEXT]")
#         print(f"  +{'-' * (W - 3)}")

#     # ── Duplicates ──
#     quality["chunk_id_duplicates"]   = {k: v for k, v in chunk_id_seen.items() if v > 1}
#     quality["document_id_duplicates"] = {k: v for k, v in doc_id_seen.items()   if v > 1}

#     return quality


# # ─────────────────────────────────────────────────────────────────────────────
# # Summary
# # ─────────────────────────────────────────────────────────────────────────────

# def print_summary(
#     rows:          list[dict],
#     quality:       dict,
#     query_field:   str,
#     expr:          str,
#     schema_fields: list[str],
# ) -> None:
#     section("SUMMARY")

#     section_counts  = Counter(r.get("section_ref",  "") for r in rows)
#     doc_id_counts   = Counter(r.get("document_id",  "") for r in rows)
#     chunk_id_counts = Counter(r.get("chunk_id",     "") for r in rows)

#     kv("Total Milvus chunk rows",   len(rows))
#     kv("Unique section_ref values", len(section_counts))
#     kv("Unique document_id values", len(doc_id_counts))
#     kv("Unique chunk_id values",    len(chunk_id_counts))
#     kv("Query field used",          query_field)
#     kv("Milvus expression",         expr)

#     subsection("DATA QUALITY CHECKS")

#     def flag(label: str, items: list | dict, ok_msg: str = "PASS") -> None:
#         count = len(items)
#         mark = "[FAIL]" if count else "[PASS]"
#         kv(f"  {mark}  {label}", f"{count} affected" if count else "")
#         if count and isinstance(items, list):
#             shown = items[:30]
#             suffix = f" ... (+{len(items)-30} more)" if len(items) > 30 else ""
#             print(f"         chunk indices: {shown}{suffix}")
#         elif count and isinstance(items, dict):
#             for k, v in list(items.items())[:15]:
#                 print(f"         {k!r}: {v} rows")

#     flag("Empty text chunks",                   quality["empty_text"])
#     flag("Whitespace-only text",                quality["whitespace_only"])
#     flag("Very short text  (< 20 chars)",       quality["very_short"])
#     flag("Missing chunk_id",                    quality["missing_chunk_id"])
#     flag("Missing document_id",                 quality["missing_document_id"])
#     flag("Duplicate chunk_id",                  quality["chunk_id_duplicates"])
#     flag("Duplicate document_id",               quality["document_id_duplicates"])

#     subsection("RE-INGESTION RISK")
#     dup_docs   = quality["document_id_duplicates"]
#     dup_chunks = quality["chunk_id_duplicates"]
#     if dup_docs or dup_chunks:
#         print("  [WARN] Duplicate rows detected - delete-then-re-insert is recommended.")
#         for did, cnt in dup_docs.items():
#             print(f"     document_id = {did!r}  ->  {cnt} rows in Milvus")
#     else:
#         print("  [PASS] No duplicate document_id or chunk_id rows.")

#     subsection("ALL SCHEMA FIELDS IN COLLECTION")
#     print(f"  {', '.join(schema_fields)}")

#     print()
#     print(hr("="))
#     print("  Done.")
#     print(hr("="))
#     print()


# # ─────────────────────────────────────────────────────────────────────────────
# # Export helpers
# # ─────────────────────────────────────────────────────────────────────────────

# def export_json(rows: list[dict], file_name: str, vf_name: str | None) -> None:
#     out_rows = [{k: v for k, v in r.items() if k != vf_name} for r in rows]
#     out_path = f"verify_milvus__{file_name}.json"
#     with open(out_path, "w", encoding="utf-8") as f:
#         json.dump(out_rows, f, ensure_ascii=False, indent=2)
#     print(f"\n  ✓  JSON exported  →  {out_path}  ({len(out_rows)} rows)")


# def export_csv(rows: list[dict], file_name: str, vf_name: str | None) -> None:
#     if not rows:
#         print("\n  No rows to export.")
#         return
#     out_path   = f"verify_milvus__{file_name}.csv"
#     fieldnames = [k for k in rows[0].keys() if k != vf_name]
#     with open(out_path, "w", newline="", encoding="utf-8") as f:
#         writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
#         writer.writeheader()
#         writer.writerows(rows)
#     print(f"\n  ✓  CSV exported  →  {out_path}  ({len(rows)} rows)")


# # ─────────────────────────────────────────────────────────────────────────────
# # Entry point
# # ─────────────────────────────────────────────────────────────────────────────

# def main() -> None:
#     load_dotenv()

#     parser = argparse.ArgumentParser(
#         description="Comprehensive Milvus inspector — full text, all fields, all stats."
#     )
#     parser.add_argument(
#         "--file", "-f",
#         help="Exact XML file name, e.g. lov-2017-06-16-51.xml",
#     )
#     parser.add_argument(
#         "--table",
#         default=os.getenv("SUPABASE_TABLE", "legal_documents"),
#         help="Supabase file metadata table  (default: legal_documents)",
#     )
#     parser.add_argument(
#         "--limit",
#         type=int,
#         default=5000,
#         help="Max Milvus rows to fetch  (default: 5000)",
#     )
#     parser.add_argument(
#         "--embeddings",
#         action="store_true",
#         help="Also fetch and inspect embedding vectors (slower, higher memory)",
#     )
#     parser.add_argument(
#         "--export",
#         choices=["json", "csv"],
#         default=None,
#         help="Export all chunk rows (vectors excluded) to JSON or CSV",
#     )
#     parser.add_argument(
#         "--collection-stats",
#         action="store_true",
#         dest="collection_stats",
#         help="Print collection-level stats only (no file filter)",
#     )
#     args = parser.parse_args()

#     if not args.file and not args.collection_stats:
#         parser.error("Provide --file <name.xml>  or  --collection-stats")

#     # ── Connect to Milvus ──
#     col = connect_milvus()
#     print_collection_stats(col)

#     if args.collection_stats and not args.file:
#         return

#     # ── Fetch Supabase row ──
#     file_name    = args.file
#     supabase_row = fetch_supabase_row(file_name, args.table)

#     if not supabase_row:
#         print(
#             f"\n  ✗  No Supabase row for file_name={file_name!r} "
#             f"in table={args.table!r}"
#         )
#         sys.exit(1)

#     print_supabase_row(supabase_row)

#     source_doc_url = str(supabase_row.get("source_doc_url", "")).strip()
#     if not source_doc_url:
#         print("\n  ✗  Supabase row has no source_doc_url — cannot query Milvus.")
#         sys.exit(1)

#     # ── Query Milvus ──
#     vf_name = vector_field_name(col)
#     rows, query_field, expr = query_chunks(
#         col,
#         file_name=file_name,
#         source_doc_url=source_doc_url,
#         limit=args.limit,
#         fetch_embeddings=args.embeddings,
#     )

#     schema_fields = sorted(f.name for f in col.schema.fields)

#     section(f"MILVUS QUERY - {len(rows)} chunks found")
#     kv("Query field",       query_field)
#     kv("Expression",        expr)
#     kv("Row limit",         args.limit)
#     kv("Embeddings fetched", args.embeddings)

#     if not rows:
#         print("\n  ✗  No chunks found in Milvus for this file.")
#         sys.exit(0)

#     # ── Section heatmap (quick orientation before full dump) ──
#     print_section_heatmap(rows)

#     # ── Full chunk dump — ALL fields, FULL text, NO truncation ──
#     quality = print_all_chunks(
#         rows,
#         supabase_row,
#         fetch_embeddings=args.embeddings,
#         vf_name=vf_name,
#     )

#     # ── Summary & quality report ──
#     print_summary(rows, quality, query_field, expr, schema_fields)

#     # ── Optional export ──
#     if args.export == "json":
#         export_json(rows, file_name, vf_name)
#     elif args.export == "csv":
#         export_csv(rows, file_name, vf_name)


# if __name__ == "__main__":
#     main()

"""
milvus_inspector.py
====================
Inspect what is stored in your Milvus instance:
  - Lists all collections
  - Shows schema (all fields + types) for each collection
  - Shows total row count
  - Prints sample records (text + all metadata) in a readable table

Usage:
    python milvus_inspector.py
    python milvus_inspector.py --collection demo_data
    python milvus_inspector.py --collection demo_data --limit 20
    python milvus_inspector.py --collection demo_data --dok-id NL/lov/2005-06-17-62
"""

from __future__ import annotations

import argparse
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

try:
    from pymilvus import connections, utility, Collection, MilvusException
except ImportError:
    print("ERROR: pymilvus not installed. Run: pip install pymilvus")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost").strip()
MILVUS_PORT = int(os.environ.get("MILVUS_PORT", "19530"))


def connect() -> None:
    print(f"Connecting to Milvus at {MILVUS_HOST}:{MILVUS_PORT} ...")
    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT,
        timeout=30,
    )
    print("Connected.\n")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def separator(char: str = "─", width: int = 88) -> str:
    return char * width


def print_schema(collection: Collection) -> None:
    print(f"\n{'SCHEMA':}")
    print(separator())
    schema = collection.schema
    for field in schema.fields:
        dtype = str(field.dtype).replace("DataType.", "")
        extra = ""
        if hasattr(field, "max_length") and field.max_length:
            extra = f"  max_length={field.max_length}"
        if hasattr(field, "dim") and field.dim:
            extra = f"  dim={field.dim}"
        pk_flag = " [PRIMARY KEY]" if field.is_primary else ""
        print(f"  {field.name:<30} {dtype:<20}{extra}{pk_flag}")
    print(separator())


def print_record(idx: int, hit, output_fields: list[str]) -> None:
    print(f"\n  ── Record {idx} ──────────────────────────────────────────────")
    for field in output_fields:
        value = getattr(hit, field, None)
        if value is None:
            # Try entity dict access
            try:
                value = hit.entity.get(field)
            except Exception:
                value = "<unavailable>"

        if isinstance(value, list) and len(value) > 6:
            # It's an embedding — just show shape
            display = f"[vector dim={len(value)}]"
        elif isinstance(value, str) and len(value) > 200:
            display = value[:200] + "..."
        else:
            display = repr(value)

        print(f"    {field:<28}: {display}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def list_collections() -> None:
    cols = utility.list_collections()
    if not cols:
        print("No collections found in this Milvus instance.")
        return
    print(f"Collections ({len(cols)}):")
    print(separator())
    for name in cols:
        try:
            col = Collection(name)
            col.load()
            count = col.num_entities
            print(f"  {name:<40} rows={count:,}")
        except Exception as exc:
            print(f"  {name:<40} [error reading: {exc}]")
    print(separator())


def inspect_collection(
    collection_name: str,
    limit: int = 10,
    dok_id_filter: str = None,
) -> None:
    print(f"\nInspecting collection: {collection_name}")
    print(separator("="))

    if not utility.has_collection(collection_name):
        print(f"ERROR: Collection '{collection_name}' does not exist.")
        print(f"Available collections: {utility.list_collections()}")
        return

    col = Collection(collection_name)
    col.load()

    # ── Schema ──────────────────────────────────────────────────────────────
    print_schema(col)

    # ── Row count ───────────────────────────────────────────────────────────
    total = col.num_entities
    print(f"\nTotal rows: {total:,}")

    # ── Determine output fields (all non-vector fields) ──────────────────────
    schema = col.schema
    vector_fields = set()
    all_fields = []
    for field in schema.fields:
        dtype = str(field.dtype)
        if "FLOAT_VECTOR" in dtype or "BINARY_VECTOR" in dtype:
            vector_fields.add(field.name)
        else:
            all_fields.append(field.name)

    print(f"\nMetadata fields (non-vector): {all_fields}")
    print(f"Vector fields (not shown):    {list(vector_fields)}")

    # ── Sample query ─────────────────────────────────────────────────────────
    print(f"\n{separator()}")
    if dok_id_filter:
        # Filter by document_id
        expr = f'document_id == "{dok_id_filter}"'
        print(f"Querying: expr='{expr}' | limit={limit}")
        try:
            results = col.query(
                expr=expr,
                output_fields=all_fields,
                limit=limit,
            )
        except MilvusException as exc:
            print(f"Query failed: {exc}")
            # Try alternative field name
            expr2 = f'dok_id == "{dok_id_filter}"'
            print(f"Retrying with expr='{expr2}'")
            results = col.query(expr=expr2, output_fields=all_fields, limit=limit)
    else:
        # Get first N records using primary key range (works for int PKs)
        # Fall back to a broad query if that fails
        print(f"Fetching first {limit} records...")
        try:
            pk_field = next(f for f in schema.fields if f.is_primary)
            if "INT" in str(pk_field.dtype):
                expr = f"{pk_field.name} >= 0"
            else:
                expr = f'{pk_field.name} != ""'
            results = col.query(
                expr=expr,
                output_fields=all_fields,
                limit=limit,
            )
        except Exception as exc:
            print(f"Primary key query failed ({exc}), trying fallback...")
            results = col.query(
                expr="",
                output_fields=all_fields,
                limit=limit,
            )

    print(f"\nResults: {len(results)} record(s)")
    print(separator())

    if not results:
        print("No records found.")
        return

    for i, hit in enumerate(results, 1):
        print(f"\n{'':>2}{'─'*84}")
        print(f"  RECORD {i}/{len(results)}")
        print(f"  {'─'*82}")
        for field in all_fields:
            value = hit.get(field) if isinstance(hit, dict) else getattr(hit, field, None)
            if value is None and isinstance(hit, dict):
                value = hit.get(field, "<null>")

            if isinstance(value, list) and len(value) > 6:
                display = f"[vector dim={len(value)}]"
            elif isinstance(value, str) and len(value) > 300:
                display = value[:300] + f"... [{len(value)} chars total]"
            elif value is None:
                display = "<null>"
            else:
                display = str(value)

            print(f"  {field:<28}: {display}")

    print(f"\n{separator('=')}")
    print(f"Showed {len(results)} of {total:,} total records in '{collection_name}'.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Milvus collections, schema, and stored data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python milvus_inspector.py\n"
            "  python milvus_inspector.py --collection demo_data\n"
            "  python milvus_inspector.py --collection demo_data --limit 20\n"
            "  python milvus_inspector.py --collection demo_data "
            "--dok-id NL/lov/2005-06-17-62\n"
        ),
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Collection name to inspect. If omitted, lists all collections.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of sample records to show (default: 10).",
    )
    parser.add_argument(
        "--dok-id",
        type=str,
        default=None,
        help="Filter records by document_id (dok_id). Shows all chunks for that doc.",
    )
    parser.add_argument(
        "--all-collections",
        action="store_true",
        help="Inspect schema + count for every collection.",
    )

    args = parser.parse_args()

    connect()

    if args.collection:
        inspect_collection(
            collection_name=args.collection,
            limit=args.limit,
            dok_id_filter=args.dok_id,
        )
    elif args.all_collections:
        list_collections()
        for name in utility.list_collections():
            inspect_collection(collection_name=name, limit=3)
    else:
        list_collections()
        print("\nTip: Run with --collection <name> to inspect records.")
        print("     Run with --all-collections to inspect all.")


if __name__ == "__main__":
    main()