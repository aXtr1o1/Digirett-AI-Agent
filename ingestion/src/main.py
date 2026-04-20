# from __future__ import annotations

# import gc
# import logging
# import re
# import sys
# import time
# import warnings
# from collections import defaultdict
# from dataclasses import asdict, is_dataclass
# from pathlib import Path
# from tempfile import TemporaryDirectory
# from typing import Any, Dict, List

# import psutil

# from ingestion.src.config import (
#     LOG_FILE,
#     PIPELINE_CPU_MAX,
#     PIPELINE_CPU_PAUSE,
#     PIPELINE_CPU_WARN,
#     PIPELINE_DOC_SLEEP,
#     validate_runtime_config,
# )
# from ingestion.src.loaders.excel_loader import ExcelLoader
# from ingestion.src.processors.chunk_validator import validate_chunk_content
# from ingestion.src.processors.chunker import DigiRettChunker, validate_chunk
# from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
# from ingestion.src.processors.text_processor import parse_lovdata_xml
# from ingestion.src.processors.validation_gate import ValidationGate
# from ingestion.src.storage.milvus_store import MilvusTextStore
# from ingestion.src.storage.supabase_store import SupabaseStore


# warnings.filterwarnings(
#     "ignore",
#     message="pkg_resources is deprecated as an API",
#     category=UserWarning,
# )

# validate_runtime_config()

# LOG_PATH = Path(LOG_FILE)
# LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# CHUNK_LOG_DIR = LOG_PATH.parent / "chunking"
# CHUNK_LOG_DIR.mkdir(parents=True, exist_ok=True)

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s | %(levelname)s | %(message)s",
#     handlers=[
#         logging.FileHandler(LOG_PATH, encoding="utf-8"),
#         logging.StreamHandler(sys.stdout),
#     ],
#     force=True,
# )

# logger = logging.getLogger("digirett-validated-ingestion")


# def _get_chunk_logger(file_name: str) -> logging.Logger:
#     stem = Path(file_name).stem
#     chunk_logger = logging.getLogger(f"chunking.{stem}")
#     chunk_logger.setLevel(logging.INFO)
#     chunk_logger.propagate = False

#     target_path = CHUNK_LOG_DIR / f"{stem}.log"

#     if not any(
#         isinstance(h, logging.FileHandler)
#         and Path(h.baseFilename) == target_path
#         for h in chunk_logger.handlers
#     ):
#         for handler in list(chunk_logger.handlers):
#             chunk_logger.removeHandler(handler)

#         file_handler = logging.FileHandler(
#             target_path,
#             encoding="utf-8",
#         )
#         file_handler.setFormatter(
#             logging.Formatter(
#                 "%(asctime)s | %(levelname)s | %(message)s"
#             )
#         )
#         chunk_logger.addHandler(file_handler)

#     return chunk_logger


# def _cpu_guard(label: str = "") -> None:
#     cpu = psutil.cpu_percent(interval=None)

#     if cpu >= PIPELINE_CPU_MAX:
#         logger.warning("CPU=%s%% [%s] — pausing 8s", cpu, label)
#         time.sleep(8.0)

#     elif cpu >= PIPELINE_CPU_PAUSE:
#         logger.warning("CPU=%s%% [%s] — pausing 3s", cpu, label)
#         time.sleep(3.0)

#     elif cpu >= PIPELINE_CPU_WARN:
#         logger.info("CPU=%s%% [%s]", cpu, label)


# def _wait_for_cpu(label: str = "") -> None:
#     max_wait = 60
#     waited = 0

#     while waited < max_wait:
#         cpu = psutil.cpu_percent(interval=1)

#         if cpu < PIPELINE_CPU_PAUSE:
#             return

#         logger.warning("Waiting for CPU (%s%%) [%s]", cpu, label)
#         time.sleep(3)
#         waited += 3

#     logger.warning(
#         "CPU still high after %ss — proceeding [%s]",
#         max_wait,
#         label,
#     )


# def _safe_str(value: Any) -> str:
#     if value is None:
#         return ""

#     try:
#         if isinstance(value, float) and value != value:
#             return ""
#     except Exception:
#         pass

#     text = str(value).strip()

#     if text.lower() in {"", "nan", "none", "null"}:
#         return ""

#     return text


# def _pick(*values: Any) -> str:
#     for value in values:
#         text = _safe_str(value)
#         if text:
#             return text
#     return ""


# def _normalise_source_doc_url(url: str) -> str:
#     """
#     Keep only the real base Lovdata document URL.
#     Removes any ::internal locator and any #fragment.
#     """
#     url = _safe_str(url)
#     if not url:
#         return ""

#     if "::" in url:
#         url = url.split("::", 1)[0]

#     if "#" in url:
#         url = url.split("#", 1)[0]

#     return url.rstrip("/")


# def _build_section_url(source_doc_url: str, section_ref: str) -> str:
#     """
#     Build a browser-clickable Lovdata section URL in the format:
#         https://lovdata.no/dokument/NL/lov/2017-06-16-51#§19

#     The § character is kept as-is (not percent-encoded) so the URL
#     matches Lovdata's own link format exactly.

#     Example:
#         base:    https://lovdata.no/dokument/NL/lov/2017-06-16-51
#         ref:     §19
#         result:  https://lovdata.no/dokument/NL/lov/2017-06-16-51#§19
#     """
#     base = _safe_str(source_doc_url)
#     anchor = _safe_str(section_ref)

#     if not base:
#         return ""

#     # Strip any existing :: locator or # fragment to get a clean base
#     base = base.split("::")[0].split("#")[0].rstrip("/")

#     if not anchor:
#         return base

#     # Remove spaces only — keep § as-is to match Lovdata's URL format
#     anchor_clean = anchor.replace(" ", "")

#     return f"{base}#{anchor_clean}"


# def _build_document_id(source_id: str, section_ref: str) -> str:
#     source_clean = re.sub(
#         r"[^A-Za-z0-9_-]+",
#         "-",
#         _safe_str(source_id).lower(),
#     ).strip("-")

#     ref_clean = re.sub(
#         r"[^A-Za-z0-9_-]+",
#         "-",
#         _safe_str(section_ref).replace("§", "par").lower(),
#     ).strip("-")

#     return f"{source_clean}__{ref_clean}"


# def _derive_source_id(
#     *,
#     metadata: Dict[str, Any],
#     source_doc_url: str,
#     file_name: str,
# ) -> str:
#     metadata_id = _safe_str(metadata.get("id"))
#     if metadata_id:
#         return metadata_id.upper()

#     url = _normalise_source_doc_url(source_doc_url)
#     match = re.search(
#         r"/(lov|forskrift)/(\d{4}-\d{2}-\d{2}(?:-\d+)?)",
#         url,
#         re.IGNORECASE,
#     )
#     if match:
#         prefix = "LOV" if match.group(1).lower() == "lov" else "FORSKRIFT"
#         return f"{prefix}-{match.group(2)}".upper()

#     stem = _safe_str(file_name).replace(".xml", "")
#     if stem:
#         return stem.upper()

#     return "UNKNOWN"


# def _derive_source_type(
#     *,
#     metadata: Dict[str, Any],
#     source_doc_url: str,
#     file_name: str,
# ) -> str:
#     meta_type = _safe_str(metadata.get("type")).lower()
#     if meta_type:
#         return meta_type

#     url = _normalise_source_doc_url(source_doc_url).lower()
#     fname = _safe_str(file_name).lower()

#     if "/forskrift/" in url or "/dokument/sf/" in url or fname.startswith("sf-"):
#         return "forskrift"

#     if "/lov/" in url or "/dokument/nl/" in url or fname.startswith("nl-") or fname.startswith("lov-"):
#         return "lov"

#     return "lov"


# def _derive_version_date(
#     *,
#     metadata: Dict[str, Any],
#     source_doc_url: str,
#     file_name: str,
# ) -> str:
#     metadata_date = _safe_str(metadata.get("dato"))
#     if metadata_date:
#         match = re.search(r"(\d{4}-\d{2}-\d{2})", metadata_date)
#         if match:
#             return match.group(1)

#     url = _normalise_source_doc_url(source_doc_url)
#     match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
#     if match:
#         return match.group(1)

#     fname = _safe_str(file_name)
#     match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", fname)
#     if match:
#         return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

#     return "1970-01-01"


# def _coerce_tier(value: Any) -> int:
#     text = _safe_str(value)
#     if not text:
#         return 1
#     try:
#         return int(float(text))
#     except Exception:
#         return 1


# def _row_to_dict(row: Any) -> Dict[str, Any]:
#     if isinstance(row, dict):
#         return dict(row)

#     if hasattr(row, "model_dump"):
#         return row.model_dump()

#     if hasattr(row, "dict"):
#         return row.dict()

#     if is_dataclass(row):
#         return asdict(row)

#     field_names = [
#         "file_name",
#         "domain_name",
#         "subdomain_name",
#         "b2b_b2c",
#         "jurisdiction",
#         "tier",
#         "source_link",
#         "legal_validation",
#         "canonical_subdomain",
#         "legal_notes",
#         "sheet_name",
#         "row_number",
#     ]

#     return {
#         field: getattr(row, field, None)
#         for field in field_names
#     }


# def _chunk_obj_to_dict(chunk_obj: Any) -> Dict[str, Any]:
#     if hasattr(chunk_obj, "to_dict"):
#         return chunk_obj.to_dict()

#     if isinstance(chunk_obj, dict):
#         return dict(chunk_obj)

#     if hasattr(chunk_obj, "__dict__"):
#         return {
#             key: value
#             for key, value in vars(chunk_obj).items()
#             if not key.startswith("_")
#         }

#     raise TypeError(f"Unsupported chunk object type: {type(chunk_obj)}")


# def run_pipeline(workbook_path: Path) -> Dict[str, int]:
#     logger.info("=" * 88)
#     logger.info("DIGIRETT VALIDATED INGESTION STARTED")
#     logger.info("Workbook: %s", workbook_path.resolve())
#     logger.info("=" * 88)

#     if not workbook_path.exists():
#         raise FileNotFoundError(
#             f"Workbook not found: {workbook_path}"
#         )

#     loader = ExcelLoader(workbook_path)
#     gate = ValidationGate()
#     chunker = DigiRettChunker()
#     embedder = TokenAwareAzureEmbedder()
#     supabase_store = SupabaseStore()
#     milvus_store = MilvusTextStore()

#     rows = loader.load()

#     if not rows:
#         logger.error("No rows found in workbook: %s", workbook_path)
#         return {
#             "rows_total": 0,
#             "rows_ingested": 0,
#             "rows_skipped_validation": 0,
#             "rows_skipped_missing_file_name": 0,
#             "rows_skipped_source_not_found": 0,
#             "rows_skipped_xml_not_found": 0,
#             "rows_failed": 0,
#             "chunks_total": 0,
#             "chunks_stored": 0,
#         }

#     stats = {
#         "rows_total": 0,
#         "rows_ingested": 0,
#         "rows_skipped_validation": 0,
#         "rows_skipped_missing_file_name": 0,
#         "rows_skipped_source_not_found": 0,
#         "rows_skipped_xml_not_found": 0,
#         "rows_failed": 0,
#         "chunks_total": 0,
#         "chunks_stored": 0,
#     }

#     try:
#         for row_idx, row in enumerate(rows, start=1):
#             stats["rows_total"] += 1

#             row_data = _row_to_dict(row)

#             file_name = _safe_str(row_data.get("file_name"))
#             sheet_name = _safe_str(row_data.get("sheet_name"))
#             row_number = _safe_str(row_data.get("row_number"))

#             logger.info("-" * 88)
#             logger.info(
#                 "ROW %s/%s | sheet=%s | row=%s | file_name=%s",
#                 row_idx,
#                 len(rows),
#                 sheet_name or "<unknown>",
#                 row_number or "<unknown>",
#                 file_name or "<missing>",
#             )

#             decision = gate.evaluate(row_data)

#             if not decision.should_ingest:
#                 stats["rows_skipped_validation"] += 1
#                 logger.info(
#                     "SKIP ROW | validation failed | reason=%s | legal_validation=%s",
#                     decision.reason,
#                     decision.legal_validation or "<empty>",
#                 )
#                 continue

#             if not file_name:
#                 stats["rows_skipped_missing_file_name"] += 1
#                 logger.warning("SKIP ROW | file_name is empty")
#                 continue

#             _cpu_guard(label=f"row:{row_idx}")
#             gc.collect()

#             matched = supabase_store.find_source_metadata_by_file_name(file_name)

#             if not matched:
#                 stats["rows_skipped_source_not_found"] += 1
#                 logger.warning(
#                     "SKIP ROW | file_name not found in source tables | file_name=%s",
#                     file_name,
#                 )
#                 continue

#             xml_bucket_path = _pick(
#                 matched.get("xml_bucket_path"),
#                 file_name,
#             )

#             xml_content = supabase_store.download_xml_text_from_storage(xml_bucket_path)

#             if not xml_content:
#                 stats["rows_skipped_xml_not_found"] += 1
#                 logger.error(
#                     "SKIP ROW | XML not found in Supabase bucket | file_name=%s | path=%s",
#                     file_name,
#                     xml_bucket_path,
#                 )
#                 continue

#             with TemporaryDirectory() as tmpdir:
#                 xml_tmp = Path(tmpdir) / file_name
#                 xml_tmp.write_text(xml_content, encoding="utf-8")
#                 parsed_text_doc = parse_lovdata_xml(xml_tmp)

#             if not parsed_text_doc or not parsed_text_doc.get("text"):
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | text_processor returned empty | file_name=%s",
#                     file_name,
#                 )
#                 continue

#             clean_text = _safe_str(parsed_text_doc.get("text"))
#             xml_meta = parsed_text_doc.get("metadata", {}) or {}

#             source_doc_url = _normalise_source_doc_url(
#                 _pick(
#                     row_data.get("source_link"),
#                     matched.get("source_doc_url"),
#                     matched.get("source_url"),
#                     matched.get("lovdata_url"),
#                     matched.get("source_link"),
#                     parsed_text_doc.get("document_url"),
#                     xml_meta.get("url"),
#                 )
#             )

#             if not source_doc_url:
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | source_doc_url resolved empty | file_name=%s",
#                     file_name,
#                 )
#                 continue

#             b2b_b2c = _pick(
#                 row_data.get("b2b_b2c"),
#                 matched.get("b2b_b2c"),
#                 "BOTH",
#             )

#             tier = _pick(
#                 row_data.get("tier"),
#                 matched.get("tier"),
#                 "1",
#             )

#             jurisdiction = _pick(
#                 row_data.get("jurisdiction"),
#                 matched.get("jurisdiction"),
#                 "NO",
#             )

#             doc_title = _pick(
#                 xml_meta.get("fulltittel"),
#                 xml_meta.get("korttittel"),
#                 matched.get("title"),
#                 file_name,
#             )

#             source_id = _derive_source_id(
#                 metadata=xml_meta,
#                 source_doc_url=source_doc_url,
#                 file_name=file_name,
#             )

#             source_type = _derive_source_type(
#                 metadata=xml_meta,
#                 source_doc_url=source_doc_url,
#                 file_name=file_name,
#             )

#             version_date = _derive_version_date(
#                 metadata=xml_meta,
#                 source_doc_url=source_doc_url,
#                 file_name=file_name,
#             )

#             chunk_logger = _get_chunk_logger(file_name)
#             chunk_logger.info("=" * 80)
#             chunk_logger.info("FILE | %s", file_name)
#             chunk_logger.info("SOURCE_ID | %s", source_id)
#             chunk_logger.info("SOURCE_DOC_URL | %s", source_doc_url)
#             chunk_logger.info("DOC_TITLE | %s", doc_title)
#             chunk_logger.info("SOURCE_TYPE | %s", source_type)
#             chunk_logger.info("VERSION_DATE | %s", version_date)
#             chunk_logger.info("DOMAIN | %s", decision.final_domain or "")
#             chunk_logger.info("SUBDOMAIN | %s", decision.final_subdomain or "")
#             chunk_logger.info("B2B_B2C | %s", b2b_b2c)
#             chunk_logger.info("JURISDICTION | %s", jurisdiction)
#             chunk_logger.info("=" * 80)

#             try:
#                 chunk_objs = chunker.chunk(
#                     text=clean_text,
#                     source_id=source_id,
#                     source_url=source_doc_url,
#                     doc_title=doc_title,
#                     domain=decision.final_domain or "",
#                     subdomain=decision.final_subdomain or "",
#                     source_type=source_type,
#                     tier=_coerce_tier(tier),
#                     version_date=version_date,
#                     language="nb",
#                 )
#             except Exception as exc:
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | chunker failed | file_name=%s | error=%s",
#                     file_name,
#                     exc,
#                 )
#                 continue

#             if not chunk_objs:
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | chunker returned 0 chunks | file_name=%s",
#                     file_name,
#                 )
#                 continue

#             chunks_by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

#             for chunk_obj in chunk_objs:
#                 ok, reason = validate_chunk(chunk_obj)
#                 if not ok:
#                     logger.warning(
#                         "SKIP CHUNK | file_name=%s | reason=%s",
#                         file_name,
#                         reason,
#                     )
#                     continue

#                 chunk_dict = _chunk_obj_to_dict(chunk_obj)

#                 content_ok, content_reason = validate_chunk_content(chunk_dict)
#                 if not content_ok:
#                     logger.warning(
#                         "SKIP CHUNK | content | file_name=%s | citation_anchor=%s"
#                         " | reason=%s | preview=%s",
#                         file_name,
#                         chunk_dict.get("citation_anchor", ""),
#                         content_reason,
#                         (chunk_dict.get("text") or "")[:80],
#                     )
#                     continue

#                 section_ref = _safe_str(chunk_dict.get("citation_anchor"))
#                 if not section_ref:
#                     logger.warning(
#                         "SKIP CHUNK | file_name=%s | missing citation_anchor",
#                         file_name,
#                     )
#                     continue

#                 # Build clean section URL in format: base#§19
#                 # Always rebuilt here from the clean source_doc_url
#                 # so we never carry over :: from chunker output
#                 section_url = _build_section_url(source_doc_url, section_ref)

#                 chunk_dict["file_name"] = file_name
#                 chunk_dict["source_id"] = source_id
#                 chunk_dict["source_doc_url"] = source_doc_url
#                 chunk_dict["source_url"] = section_url
#                 chunk_dict["section_ref"] = section_ref
#                 chunk_dict["section_url"] = section_url
#                 chunk_dict["domain"] = decision.final_domain or ""
#                 chunk_dict["subdomain"] = decision.final_subdomain or ""
#                 chunk_dict["b2b_b2c"] = b2b_b2c
#                 chunk_dict["tier"] = str(tier)
#                 chunk_dict["jurisdiction"] = jurisdiction

#                 chunks_by_section[section_ref].append(chunk_dict)

#             if not chunks_by_section:
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | no valid chunks after validation | file_name=%s",
#                     file_name,
#                 )
#                 continue

#             row_success = False
#             total_file_chunks = 0

#             for section_idx, (section_ref, section_chunks) in enumerate(
#                 chunks_by_section.items(),
#                 start=1,
#             ):
#                 document_id = _build_document_id(source_id, section_ref)
#                 section_url = _build_section_url(source_doc_url, section_ref)

#                 chunk_logger.info("-" * 80)
#                 chunk_logger.info("SECTION %s | %s", section_idx, section_ref)
#                 chunk_logger.info("DOCUMENT_ID | %s", document_id)
#                 chunk_logger.info("SECTION_URL | %s", section_url)
#                 chunk_logger.info("CHUNKS | %s", len(section_chunks))

#                 for idx, chunk in enumerate(section_chunks, start=1):
#                     chunk["document_id"] = document_id
#                     # Ensure section_url is always clean for every chunk
#                     chunk["source_url"] = section_url
#                     chunk["section_url"] = section_url
#                     chunk_logger.info(
#                         "chunk[%s] | chunk_id=%s | token_count=%s | section_url=%s",
#                         idx,
#                         chunk.get("chunk_id", ""),
#                         chunk.get("token_count", ""),
#                         section_url,
#                     )
#                     chunk_logger.info("TEXT_START")
#                     chunk_logger.info("%s", chunk.get("text", ""))
#                     chunk_logger.info("TEXT_END")

#                 try:
#                     embedded = embedder.embed_chunks(
#                         section_chunks,
#                         text_field="enriched_text",
#                     )
#                 except Exception as exc:
#                     logger.error(
#                         "FAIL SECTION | embedding failed | file_name=%s | section=%s | error=%s",
#                         file_name,
#                         section_ref,
#                         exc,
#                     )
#                     continue

#                 embedded = [c for c in embedded if c.get("embedding") is not None]
#                 if not embedded:
#                     logger.error(
#                         "FAIL SECTION | no embeddings returned | file_name=%s | section=%s",
#                         file_name,
#                         section_ref,
#                     )
#                     continue

#                 milvus_metadata = {
#                     "document_id": document_id,
#                     "file_name": file_name,
#                     "source_doc_url": source_doc_url,
#                     "section_ref": section_ref,
#                     "domain": decision.final_domain or "",
#                     "subdomain": decision.final_subdomain or "",
#                     "b2b_b2c": b2b_b2c,
#                     "tier": str(tier),
#                     "jurisdiction": jurisdiction,
#                 }

#                 _wait_for_cpu(label=f"milvus:{document_id}")

#                 try:
#                     milvus_result = milvus_store.insert_chunks(
#                         embedded,
#                         milvus_metadata,
#                     )
#                 except Exception as exc:
#                     logger.error(
#                         "FAIL SECTION | milvus insert failed | file_name=%s | section=%s | error=%s",
#                         file_name,
#                         section_ref,
#                         exc,
#                     )
#                     continue

#                 inserted = int(milvus_result.get("inserted", 0))
#                 stats["chunks_total"] += len(section_chunks)
#                 stats["chunks_stored"] += inserted
#                 total_file_chunks += inserted
#                 row_success = True

#                 logger.info(
#                     "SECTION DONE | file_name=%s | section=%s | section_url=%s | inserted=%s",
#                     file_name,
#                     section_ref,
#                     section_url,
#                     inserted,
#                 )

#             if row_success:
#                 supabase_ok = supabase_store.upsert_file_metadata(
#                     file_name=file_name,
#                     source_id=source_id,
#                     source_doc_url=source_doc_url,
#                     domain=decision.final_domain or "",
#                     subdomain=decision.final_subdomain or "",
#                     b2b_b2c=b2b_b2c,
#                     tier=str(tier),
#                     jurisdiction=jurisdiction,
#                     legal_validation=decision.legal_validation,
#                     xml_bucket_path=xml_bucket_path,
#                     doc_title=doc_title,
#                 )

#                 if supabase_ok:
#                     stats["rows_ingested"] += 1
#                     logger.info(
#                         "SUPABASE DONE | file_name=%s | chunks=%s",
#                         file_name,
#                         total_file_chunks,
#                     )
#                 else:
#                     stats["rows_failed"] += 1
#                     logger.error("SUPABASE FAILED | file_name=%s", file_name)
#             else:
#                 stats["rows_failed"] += 1
#                 logger.error(
#                     "ROW FAILED | nothing stored in Milvus | file_name=%s",
#                     file_name,
#                 )

#             time.sleep(PIPELINE_DOC_SLEEP)

#     finally:
#         milvus_store.close()

#     logger.info("=" * 88)
#     logger.info("DIGIRETT VALIDATED INGESTION COMPLETED")
#     logger.info("rows_total               : %s", stats["rows_total"])
#     logger.info("rows_ingested            : %s", stats["rows_ingested"])
#     logger.info("rows_skipped_validation  : %s", stats["rows_skipped_validation"])
#     logger.info("rows_skipped_missing     : %s", stats["rows_skipped_missing_file_name"])
#     logger.info("rows_skipped_source      : %s", stats["rows_skipped_source_not_found"])
#     logger.info("rows_skipped_xml         : %s", stats["rows_skipped_xml_not_found"])
#     logger.info("rows_failed              : %s", stats["rows_failed"])
#     logger.info("chunks_total             : %s", stats["chunks_total"])
#     logger.info("chunks_stored            : %s", stats["chunks_stored"])
#     logger.info("=" * 88)

#     return stats


# if __name__ == "__main__":
#     workbook_path = Path(
#         r"D:\axtrlabs\Digirett-AI-Agent\ingestion\data\Client_dataset\Domain_Metadata_VALIDATED (2).xlsx"
#     )

#     try:
#         run_pipeline(workbook_path=workbook_path)

#     except KeyboardInterrupt:
#         logger.warning("Pipeline stopped by user")
#         sys.exit(130)

#     except Exception as exc:
#         logger.error(
#             "Pipeline failed: %s",
#             exc,
#             exc_info=True,
#         )
#         sys.exit(1)

from __future__ import annotations

import gc
import logging
import re
import sys
import time
import warnings
from collections import defaultdict
from dataclasses import asdict, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List

import psutil

from ingestion.src.config import (
    LOG_FILE,
    PIPELINE_CPU_MAX,
    PIPELINE_CPU_PAUSE,
    PIPELINE_CPU_WARN,
    PIPELINE_DOC_SLEEP,
    validate_runtime_config,
)
from ingestion.src.loaders.excel_loader import ExcelLoader
from ingestion.src.processors.chunk_validator import validate_chunk_content
from ingestion.src.processors.chunker import DigiRettChunker, validate_chunk
from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
from ingestion.src.processors.text_processor import parse_lovdata_xml
from ingestion.src.processors.validation_gate import ValidationGate
from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.storage.supabase_store import SupabaseStore


warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=UserWarning,
)

validate_runtime_config()

LOG_PATH = Path(LOG_FILE)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

CHUNK_LOG_DIR = LOG_PATH.parent / "chunking"
CHUNK_LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

logger = logging.getLogger("digirett-validated-ingestion")


def _get_chunk_logger(file_name: str) -> logging.Logger:
    stem = Path(file_name).stem
    chunk_logger = logging.getLogger(f"chunking.{stem}")
    chunk_logger.setLevel(logging.INFO)
    chunk_logger.propagate = False

    target_path = CHUNK_LOG_DIR / f"{stem}.log"

    if not any(
        isinstance(h, logging.FileHandler)
        and Path(h.baseFilename) == target_path
        for h in chunk_logger.handlers
    ):
        for handler in list(chunk_logger.handlers):
            chunk_logger.removeHandler(handler)

        file_handler = logging.FileHandler(
            target_path,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(message)s"
            )
        )
        chunk_logger.addHandler(file_handler)

    return chunk_logger


def _cpu_guard(label: str = "") -> None:
    cpu = psutil.cpu_percent(interval=None)

    if cpu >= PIPELINE_CPU_MAX:
        logger.warning("CPU=%s%% [%s] — pausing 8s", cpu, label)
        time.sleep(8.0)

    elif cpu >= PIPELINE_CPU_PAUSE:
        logger.warning("CPU=%s%% [%s] — pausing 3s", cpu, label)
        time.sleep(3.0)

    elif cpu >= PIPELINE_CPU_WARN:
        logger.info("CPU=%s%% [%s]", cpu, label)


def _wait_for_cpu(label: str = "") -> None:
    max_wait = 60
    waited = 0

    while waited < max_wait:
        cpu = psutil.cpu_percent(interval=1)

        if cpu < PIPELINE_CPU_PAUSE:
            return

        logger.warning("Waiting for CPU (%s%%) [%s]", cpu, label)
        time.sleep(3)
        waited += 3

    logger.warning(
        "CPU still high after %ss — proceeding [%s]",
        max_wait,
        label,
    )


def _safe_str(value: Any) -> str:
    if value is None:
        return ""

    try:
        if isinstance(value, float) and value != value:
            return ""
    except Exception:
        pass

    text = str(value).strip()

    if text.lower() in {"", "nan", "none", "null"}:
        return ""

    return text


def _pick(*values: Any) -> str:
    for value in values:
        text = _safe_str(value)
        if text:
            return text
    return ""


def _normalise_source_doc_url(url: str) -> str:
    """
    Keep only the real base Lovdata document URL.
    Removes any ::internal locator and any #fragment.
    """
    url = _safe_str(url)
    if not url:
        return ""

    if "::" in url:
        url = url.split("::", 1)[0]

    if "#" in url:
        url = url.split("#", 1)[0]

    return url.rstrip("/")


def _build_section_url(source_doc_url: str, section_ref: str) -> str:
    """
    Build a browser-clickable Lovdata section URL in the format:
        https://lovdata.no/dokument/NL/lov/2017-06-16-51#§19

    The § character is kept as-is (not percent-encoded) so the URL
    matches Lovdata's own link format exactly.

    Example:
        base:    https://lovdata.no/dokument/NL/lov/2017-06-16-51
        ref:     §19
        result:  https://lovdata.no/dokument/NL/lov/2017-06-16-51#§19
    """
    base = _safe_str(source_doc_url)
    anchor = _safe_str(section_ref)

    if not base:
        return ""

    # Strip any existing :: locator or # fragment to get a clean base
    base = base.split("::")[0].split("#")[0].rstrip("/")

    if not anchor:
        return base

    # Remove spaces only — keep § as-is to match Lovdata's URL format
    anchor_clean = anchor.replace(" ", "")

    return f"{base}#{anchor_clean}"


def _build_document_id(source_id: str, section_ref: str) -> str:
    source_clean = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        _safe_str(source_id).lower(),
    ).strip("-")

    ref_clean = re.sub(
        r"[^A-Za-z0-9_-]+",
        "-",
        _safe_str(section_ref).replace("§", "par").lower(),
    ).strip("-")

    return f"{source_clean}__{ref_clean}"


def _derive_source_id(
    *,
    metadata: Dict[str, Any],
    source_doc_url: str,
    file_name: str,
) -> str:
    metadata_id = _safe_str(metadata.get("id"))
    if metadata_id:
        return metadata_id.upper()

    url = _normalise_source_doc_url(source_doc_url)
    match = re.search(
        r"/(lov|forskrift)/(\d{4}-\d{2}-\d{2}(?:-\d+)?)",
        url,
        re.IGNORECASE,
    )
    if match:
        prefix = "LOV" if match.group(1).lower() == "lov" else "FORSKRIFT"
        return f"{prefix}-{match.group(2)}".upper()

    stem = _safe_str(file_name).replace(".xml", "")
    if stem:
        return stem.upper()

    return "UNKNOWN"


def _derive_source_type(
    *,
    metadata: Dict[str, Any],
    source_doc_url: str,
    file_name: str,
) -> str:
    meta_type = _safe_str(metadata.get("type")).lower()
    if meta_type:
        return meta_type

    url = _normalise_source_doc_url(source_doc_url).lower()
    fname = _safe_str(file_name).lower()

    if "/forskrift/" in url or "/dokument/sf/" in url or fname.startswith("sf-"):
        return "forskrift"

    if "/lov/" in url or "/dokument/nl/" in url or fname.startswith("nl-") or fname.startswith("lov-"):
        return "lov"

    return "lov"


def _derive_version_date(
    *,
    metadata: Dict[str, Any],
    source_doc_url: str,
    file_name: str,
) -> str:
    metadata_date = _safe_str(metadata.get("dato"))
    if metadata_date:
        match = re.search(r"(\d{4}-\d{2}-\d{2})", metadata_date)
        if match:
            return match.group(1)

    url = _normalise_source_doc_url(source_doc_url)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", url)
    if match:
        return match.group(1)

    fname = _safe_str(file_name)
    match = re.search(r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", fname)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    return "1970-01-01"


def _coerce_tier(value: Any) -> int:
    text = _safe_str(value)
    if not text:
        return 1
    try:
        return int(float(text))
    except Exception:
        return 1


def _row_to_dict(row: Any) -> Dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)

    if hasattr(row, "model_dump"):
        return row.model_dump()

    if hasattr(row, "dict"):
        return row.dict()

    if is_dataclass(row):
        return asdict(row)

    field_names = [
        "file_name",
        "domain_name",
        "subdomain_name",
        "b2b_b2c",
        "jurisdiction",
        "tier",
        "source_link",
        "legal_validation",
        "canonical_subdomain",
        "legal_notes",
        "sheet_name",
        "row_number",
    ]

    return {
        field: getattr(row, field, None)
        for field in field_names
    }


def _chunk_obj_to_dict(chunk_obj: Any) -> Dict[str, Any]:
    if hasattr(chunk_obj, "to_dict"):
        return chunk_obj.to_dict()

    if isinstance(chunk_obj, dict):
        return dict(chunk_obj)

    if hasattr(chunk_obj, "__dict__"):
        return {
            key: value
            for key, value in vars(chunk_obj).items()
            if not key.startswith("_")
        }

    raise TypeError(f"Unsupported chunk object type: {type(chunk_obj)}")


def run_pipeline(workbook_path: Path) -> Dict[str, int]:
    logger.info("=" * 88)
    logger.info("DIGIRETT VALIDATED INGESTION STARTED")
    logger.info("Workbook: %s", workbook_path.resolve())
    logger.info("=" * 88)

    if not workbook_path.exists():
        raise FileNotFoundError(
            f"Workbook not found: {workbook_path}"
        )

    loader = ExcelLoader(workbook_path)
    gate = ValidationGate()
    chunker = DigiRettChunker()
    embedder = TokenAwareAzureEmbedder()
    supabase_store = SupabaseStore()
    milvus_store = MilvusTextStore()

    rows = loader.load()

    if not rows:
        logger.error("No rows found in workbook: %s", workbook_path)
        return {
            "rows_total": 0,
            "rows_ingested": 0,
            "rows_skipped_validation": 0,
            "rows_skipped_missing_file_name": 0,
            "rows_skipped_source_not_found": 0,
            "rows_skipped_xml_not_found": 0,
            "rows_failed": 0,
            "chunks_total": 0,
            "chunks_stored": 0,
        }

    stats = {
        "rows_total": 0,
        "rows_ingested": 0,
        "rows_skipped_validation": 0,
        "rows_skipped_missing_file_name": 0,
        "rows_skipped_source_not_found": 0,
        "rows_skipped_xml_not_found": 0,
        "rows_failed": 0,
        "chunks_total": 0,
        "chunks_stored": 0,
    }

    try:
        for row_idx, row in enumerate(rows, start=1):
            stats["rows_total"] += 1

            row_data = _row_to_dict(row)

            file_name = _safe_str(row_data.get("file_name"))
            sheet_name = _safe_str(row_data.get("sheet_name"))
            row_number = _safe_str(row_data.get("row_number"))

            logger.info("-" * 88)
            logger.info(
                "ROW %s/%s | sheet=%s | row=%s | file_name=%s",
                row_idx,
                len(rows),
                sheet_name or "<unknown>",
                row_number or "<unknown>",
                file_name or "<missing>",
            )

            decision = gate.evaluate(row_data)

            if not decision.should_ingest:
                stats["rows_skipped_validation"] += 1
                logger.info(
                    "SKIP ROW | validation failed | reason=%s | legal_validation=%s",
                    decision.reason,
                    decision.legal_validation or "<empty>",
                )
                continue

            if not file_name:
                stats["rows_skipped_missing_file_name"] += 1
                logger.warning("SKIP ROW | file_name is empty")
                continue

            _cpu_guard(label=f"row:{row_idx}")
            gc.collect()

            matched = supabase_store.find_source_metadata_by_file_name(file_name)

            if not matched:
                stats["rows_skipped_source_not_found"] += 1
                logger.warning(
                    "SKIP ROW | file_name not found in source tables | file_name=%s",
                    file_name,
                )
                continue

            xml_bucket_path = _pick(
                matched.get("xml_bucket_path"),
                file_name,
            )

            xml_content = supabase_store.download_xml_text_from_storage(xml_bucket_path)

            if not xml_content:
                stats["rows_skipped_xml_not_found"] += 1
                logger.error(
                    "SKIP ROW | XML not found in Supabase bucket | file_name=%s | path=%s",
                    file_name,
                    xml_bucket_path,
                )
                continue

            with TemporaryDirectory() as tmpdir:
                xml_tmp = Path(tmpdir) / file_name
                xml_tmp.write_text(xml_content, encoding="utf-8")
                parsed_text_doc = parse_lovdata_xml(xml_tmp)

            if not parsed_text_doc or not parsed_text_doc.get("text"):
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | text_processor returned empty | file_name=%s",
                    file_name,
                )
                continue

            clean_text = _safe_str(parsed_text_doc.get("text"))
            xml_meta = parsed_text_doc.get("metadata", {}) or {}

            source_doc_url = _normalise_source_doc_url(
                _pick(
                    row_data.get("source_link"),
                    matched.get("source_doc_url"),
                    matched.get("source_url"),
                    matched.get("lovdata_url"),
                    matched.get("source_link"),
                    parsed_text_doc.get("document_url"),
                    xml_meta.get("url"),
                )
            )

            if not source_doc_url:
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | source_doc_url resolved empty | file_name=%s",
                    file_name,
                )
                continue

            b2b_b2c = _pick(
                row_data.get("b2b_b2c"),
                matched.get("b2b_b2c"),
                "BOTH",
            )

            tier = _pick(
                row_data.get("tier"),
                matched.get("tier"),
                "1",
            )

            jurisdiction = _pick(
                row_data.get("jurisdiction"),
                matched.get("jurisdiction"),
                "NO",
            )

            doc_title = _pick(
                xml_meta.get("fulltittel"),
                xml_meta.get("korttittel"),
                matched.get("title"),
                file_name,
            )

            source_id = _derive_source_id(
                metadata=xml_meta,
                source_doc_url=source_doc_url,
                file_name=file_name,
            )

            source_type = _derive_source_type(
                metadata=xml_meta,
                source_doc_url=source_doc_url,
                file_name=file_name,
            )

            version_date = _derive_version_date(
                metadata=xml_meta,
                source_doc_url=source_doc_url,
                file_name=file_name,
            )

            chunk_logger = _get_chunk_logger(file_name)
            chunk_logger.info("=" * 80)
            chunk_logger.info("FILE | %s", file_name)
            chunk_logger.info("SOURCE_ID | %s", source_id)
            chunk_logger.info("SOURCE_DOC_URL | %s", source_doc_url)
            chunk_logger.info("DOC_TITLE | %s", doc_title)
            chunk_logger.info("SOURCE_TYPE | %s", source_type)
            chunk_logger.info("VERSION_DATE | %s", version_date)
            chunk_logger.info("DOMAIN | %s", decision.final_domain or "")
            chunk_logger.info("SUBDOMAIN | %s", decision.final_subdomain or "")
            chunk_logger.info("B2B_B2C | %s", b2b_b2c)
            chunk_logger.info("JURISDICTION | %s", jurisdiction)
            chunk_logger.info("=" * 80)

            try:
                chunk_objs = chunker.chunk(
                    text=clean_text,
                    source_id=source_id,
                    source_url=source_doc_url,
                    doc_title=doc_title,
                    domain=decision.final_domain or "",
                    subdomain=decision.final_subdomain or "",
                    source_type=source_type,
                    tier=_coerce_tier(tier),
                    version_date=version_date,
                    language="nb",
                )
            except Exception as exc:
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | chunker failed | file_name=%s | error=%s",
                    file_name,
                    exc,
                )
                continue

            if not chunk_objs:
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | chunker returned 0 chunks | file_name=%s",
                    file_name,
                )
                continue

            chunks_by_section: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

            for chunk_obj in chunk_objs:
                ok, reason = validate_chunk(chunk_obj)
                if not ok:
                    logger.warning(
                        "SKIP CHUNK | file_name=%s | reason=%s",
                        file_name,
                        reason,
                    )
                    continue

                chunk_dict = _chunk_obj_to_dict(chunk_obj)

                content_ok, content_reason = validate_chunk_content(chunk_dict)
                if not content_ok:
                    logger.warning(
                        "SKIP CHUNK | content | file_name=%s | citation_anchor=%s"
                        " | reason=%s | preview=%s",
                        file_name,
                        chunk_dict.get("citation_anchor", ""),
                        content_reason,
                        (chunk_dict.get("text") or "")[:80],
                    )
                    continue

                section_ref = _safe_str(chunk_dict.get("citation_anchor"))
                if not section_ref:
                    logger.warning(
                        "SKIP CHUNK | file_name=%s | missing citation_anchor",
                        file_name,
                    )
                    continue

                # Build clean section URL in format: base#§19
                # Always rebuilt here from the clean source_doc_url
                # so we never carry over :: from chunker output
                section_url = _build_section_url(source_doc_url, section_ref)

                chunk_dict["file_name"] = file_name
                chunk_dict["source_id"] = source_id
                chunk_dict["source_doc_url"] = source_doc_url
                chunk_dict["source_url"] = section_url
                chunk_dict["section_ref"] = section_ref
                chunk_dict["section_url"] = section_url
                chunk_dict["domain"] = decision.final_domain or ""
                chunk_dict["subdomain"] = decision.final_subdomain or ""
                chunk_dict["b2b_b2c"] = b2b_b2c
                chunk_dict["tier"] = str(tier)
                chunk_dict["jurisdiction"] = jurisdiction

                chunks_by_section[section_ref].append(chunk_dict)

            if not chunks_by_section:
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | no valid chunks after validation | file_name=%s",
                    file_name,
                )
                continue

            row_success = False
            total_file_chunks = 0

            for section_idx, (section_ref, section_chunks) in enumerate(
                chunks_by_section.items(),
                start=1,
            ):
                document_id = _build_document_id(source_id, section_ref)
                section_url = _build_section_url(source_doc_url, section_ref)

                chunk_logger.info("-" * 80)
                chunk_logger.info("SECTION %s | %s", section_idx, section_ref)
                chunk_logger.info("DOCUMENT_ID | %s", document_id)
                chunk_logger.info("SECTION_URL | %s", section_url)
                chunk_logger.info("CHUNKS | %s", len(section_chunks))

                for idx, chunk in enumerate(section_chunks, start=1):
                    chunk["document_id"] = document_id
                    # Ensure section_url is always clean for every chunk
                    chunk["source_url"] = section_url
                    chunk["section_url"] = section_url
                    chunk_logger.info(
                        "chunk[%s] | chunk_id=%s | token_count=%s | section_url=%s",
                        idx,
                        chunk.get("chunk_id", ""),
                        chunk.get("token_count", ""),
                        section_url,
                    )
                    chunk_logger.info("TEXT_START")
                    chunk_logger.info("%s", chunk.get("text", ""))
                    chunk_logger.info("TEXT_END")

                try:
                    embedded = embedder.embed_chunks(
                        section_chunks,
                        text_field="enriched_text",
                    )
                except Exception as exc:
                    logger.error(
                        "FAIL SECTION | embedding failed | file_name=%s | section=%s | error=%s",
                        file_name,
                        section_ref,
                        exc,
                    )
                    continue

                embedded = [c for c in embedded if c.get("embedding") is not None]
                if not embedded:
                    logger.error(
                        "FAIL SECTION | no embeddings returned | file_name=%s | section=%s",
                        file_name,
                        section_ref,
                    )
                    continue

                milvus_metadata = {
                    "document_id": document_id,
                    "source_id": source_id,
                    "file_name": file_name,
                    "source_doc_url": source_doc_url,
                    "section_ref": section_ref,
                    "source_url": section_url,  # ADDED
                    "domain": decision.final_domain or "",
                    "subdomain": decision.final_subdomain or "",
                    "b2b_b2c": b2b_b2c,
                    "tier": str(tier),
                    "jurisdiction": jurisdiction,
                }

                _wait_for_cpu(label=f"milvus:{document_id}")

                try:
                    milvus_result = milvus_store.insert_chunks(
                        embedded,
                        milvus_metadata,
                    )
                except Exception as exc:
                    logger.error(
                        "FAIL SECTION | milvus insert failed | file_name=%s | section=%s | error=%s",
                        file_name,
                        section_ref,
                        exc,
                    )
                    continue

                inserted = int(milvus_result.get("inserted", 0))
                stats["chunks_total"] += len(section_chunks)
                stats["chunks_stored"] += inserted
                total_file_chunks += inserted
                row_success = True

                logger.info(
                    "SECTION DONE | file_name=%s | section=%s | section_url=%s | inserted=%s",
                    file_name,
                    section_ref,
                    section_url,
                    inserted,
                )

            if row_success:
                supabase_ok = supabase_store.upsert_file_metadata(
                    file_name=file_name,
                    source_id=source_id,
                    source_doc_url=source_doc_url,
                    domain=decision.final_domain or "",
                    subdomain=decision.final_subdomain or "",
                    b2b_b2c=b2b_b2c,
                    tier=str(tier),
                    jurisdiction=jurisdiction,
                    legal_validation=decision.legal_validation,
                    xml_bucket_path=xml_bucket_path,
                    doc_title=doc_title,
                )

                if supabase_ok:
                    stats["rows_ingested"] += 1
                    logger.info(
                        "SUPABASE DONE | file_name=%s | chunks=%s",
                        file_name,
                        total_file_chunks,
                    )
                else:
                    stats["rows_failed"] += 1
                    logger.error("SUPABASE FAILED | file_name=%s", file_name)
            else:
                stats["rows_failed"] += 1
                logger.error(
                    "ROW FAILED | nothing stored in Milvus | file_name=%s",
                    file_name,
                )

            time.sleep(PIPELINE_DOC_SLEEP)

    finally:
        milvus_store.close()

    logger.info("=" * 88)
    logger.info("DIGIRETT VALIDATED INGESTION COMPLETED")
    logger.info("rows_total               : %s", stats["rows_total"])
    logger.info("rows_ingested            : %s", stats["rows_ingested"])
    logger.info("rows_skipped_validation  : %s", stats["rows_skipped_validation"])
    logger.info("rows_skipped_missing     : %s", stats["rows_skipped_missing_file_name"])
    logger.info("rows_skipped_source      : %s", stats["rows_skipped_source_not_found"])
    logger.info("rows_skipped_xml         : %s", stats["rows_skipped_xml_not_found"])
    logger.info("rows_failed              : %s", stats["rows_failed"])
    logger.info("chunks_total             : %s", stats["chunks_total"])
    logger.info("chunks_stored            : %s", stats["chunks_stored"])
    logger.info("=" * 88)

    return stats


if __name__ == "__main__":
    workbook_path = Path(
        r"D:\axtrlabs\Digirett-AI-Agent\ingestion\data\Client_dataset\Domain_Metadata_VALIDATED (2).xlsx"
    )

    try:
        run_pipeline(workbook_path=workbook_path)

    except KeyboardInterrupt:
        logger.warning("Pipeline stopped by user")
        sys.exit(130)

    except Exception as exc:
        logger.error(
            "Pipeline failed: %s",
            exc,
            exc_info=True,
        )
        sys.exit(1)