from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from supabase import Client, create_client
from ingestion.src.config import settings

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_BUCKET = settings.supabase_bucket
LOVDATA_BASE_URL = settings.lovdata_base_url.rstrip("/")
DEFAULT_TAXONOMY_VERSION = settings.taxonomy_version


class SupabaseStore:
    """Supabase PostgreSQL storage manager writing to 9 production core tables & storage buckets."""

    def __init__(self):
        self.supabase: Optional[Client] = None
        self._connected = False
        self._taxonomy_seeded = False

    def _ensure_connection(self, auto_seed: bool = False) -> bool:
        if not self._connected:
            try:
                self.supabase = create_client(settings.supabase_url, settings.supabase_service_key)
                self._connected = True
                logger.info("SupabaseStore: Client initialized successfully.")
                if auto_seed and not self._taxonomy_seeded:
                    self.seed_taxonomy_and_catalogs()
                    self._taxonomy_seeded = True
            except Exception as exc:
                logger.warning("SupabaseStore: Client init warning: %s", exc)
                return False
        return True

    def seed_taxonomy_and_catalogs(self) -> None:
        """Seeds taxonomy_domains, taxonomy_subdomains, xapi_rettsomrade_catalog, and rettsomrade_mappings."""
        if not self.supabase:
            return
        try:
            # 1. Load taxonomy definitions from configs/taxonomies
            taxonomies_dir = settings.mapping_path.parent / "taxonomies"
            all_domains = []
            if taxonomies_dir.exists():
                for json_file in taxonomies_dir.glob("*.json"):
                    try:
                        tax_data = json.loads(json_file.read_text(encoding="utf-8"))
                        all_domains.extend(tax_data.get("domains", []))
                    except Exception as exc:
                        logger.warning("Error reading taxonomy file %s: %s", json_file, exc)

            # Build rich domain records with constraints
            dom_records = []
            sub_records = []
            for d in all_domains:
                dom_id = d.get("domain_id")
                if not dom_id:
                    continue
                subs = d.get("subdomains", [])
                tiers = [s.get("routing_constraints", {}).get("tier_ceiling") for s in subs if s.get("routing_constraints") and s.get("routing_constraints", {}).get("tier_ceiling")]
                juris = list(set([j for s in subs if s.get("routing_constraints") for j in s.get("routing_constraints", {}).get("jurisdiction", [])]))
                b2b = list(set([b for s in subs if s.get("routing_constraints") for b in s.get("routing_constraints", {}).get("b2b_b2c", [])]))
                rels = list(set([r for s in subs if s.get("routing_constraints") for r in s.get("routing_constraints", {}).get("relationship_type", [])]))

                dom_records.append({
                    "domain_id": dom_id,
                    "name": d.get("name_nb") or d.get("name_en") or dom_id,
                    "tier_ceiling": max(tiers) if tiers else 2,
                    "jurisdiction_allowed": juris if juris else ["NO"],
                    "b2b_b2c_allowed": b2b if b2b else ["BOTH"],
                    "relationship_type_allowed": rels if rels else ["commercial"],
                    "taxonomy_version": settings.taxonomy_version,
                    "is_active": True,
                })

                for s in subs:
                    sub_records.append({
                        "subdomain_id": s.get("subdomain_id"),
                        "domain_id": dom_id,
                        "name": s.get("name_en") or s.get("name") or s.get("subdomain_id"),
                        "scope_in": s.get("scope_in"),
                        "scope_out": s.get("scope_out"),
                        "routing_keywords": s.get("routing_keywords"),
                        "confusers": s.get("confusers"),
                        "required_sources": s.get("required_sources"),
                        "routing_constraints": s.get("routing_constraints"),
                        "taxonomy_version": settings.taxonomy_version,
                        "is_active": True,
                    })

            if dom_records:
                self.supabase.table("taxonomy_domains").upsert(dom_records, on_conflict="domain_id").execute()
            if sub_records:
                self.supabase.table("taxonomy_subdomains").upsert(sub_records, on_conflict="subdomain_id").execute()

            # 2. Catalogs & Mappings from rettsomrade_domain_mapping.json
            mapping_file = settings.mapping_path
            if mapping_file.exists():
                data = json.loads(mapping_file.read_text(encoding="utf-8"))
                mappings = data.get("mappings", [])
                if mappings:
                    cat_records = [
                        {"rettsomrade": x["rettsomrade"][:255], "seen_in_laws": True, "is_active": True}
                        for x in mappings
                        if x.get("rettsomrade")
                    ]
                    self.supabase.table("xapi_rettsomrade_catalog").upsert(cat_records, on_conflict="rettsomrade").execute()

                    # Seed rettsomrade_mappings
                    try:
                        res_check = self.supabase.table("rettsomrade_mappings").select("id").limit(1).execute()
                        if not res_check.data:
                            mapping_records = []
                            for x in mappings:
                                rett = x.get("rettsomrade", "")[:255]
                                if not rett:
                                    continue
                                dom_id = x.get("domain_id")
                                is_direct = bool(dom_id and dom_id.startswith("D"))
                                conf_val = x.get("confidence")
                                confidence = 1.0 if conf_val == "high" else (0.8 if conf_val == "medium" else (0.5 if conf_val == "low" else 1.0))
                                mapping_records.append({
                                    "rettsomrade": rett,
                                    "mapping_type": "DIRECT_SINGLE" if is_direct else "OUT_OF_SCOPE",
                                    "domain_id": dom_id if is_direct else None,
                                    "confidence": confidence,
                                    "note": x.get("note") or "",
                                    "mapping_version": data.get("mapping_version", "1.1.0"),
                                    "is_active": True,
                                })
                            if mapping_records:
                                self.supabase.table("rettsomrade_mappings").insert(mapping_records).execute()
                    except Exception as m_exc:
                        logger.debug("Notice seeding rettsomrade_mappings: %s", m_exc)

            logger.info("SupabaseStore: Seeded taxonomy domains, subdomains & rettsomrade catalog into database.")
        except Exception as exc:
            logger.warning("SupabaseStore: Notice during taxonomy/catalog seeding: %s", exc)

    def find_source_metadata_by_file_name(self, file_name: str) -> Optional[Dict[str, Any]]:
        if not self._ensure_connection() or not self.supabase:
            return None
        for table in ["predefined_source_metadata", "xapi_storage_objects", "legal_documents"]:
            try:
                res = self.supabase.table(table).select("*").eq("file_name", file_name).limit(1).execute()
                if res.data:
                    return res.data[0]
            except Exception:
                continue
        return None

    def download_xml_text_from_storage(self, bucket_path: str, bucket_name: str = "raw_xml_files") -> Optional[str]:
        if not self._ensure_connection() or not self.supabase:
            return None
        try:
            res = self.supabase.storage.from_(bucket_name).download(bucket_path)
            if res is not None:
                return res.decode("utf-8") if isinstance(res, bytes) else str(res)
            return None
        except Exception as exc:
            logger.warning("download_xml_text_from_storage failed | path=%s | error=%s", bucket_path, exc)
            return None

    def upsert_file_metadata(
        self,
        file_name: str,
        source_id: str,
        source_doc_url: str = "",
        domain: str = "",
        subdomain: str = "",
        b2b_b2c: str = "BOTH",
        tier: str = "CORE",
        jurisdiction: str = "NO",
        legal_validation: str = "VALID",
        xml_bucket_path: str = "",
        doc_title: str = "",
    ) -> bool:
        if not self._ensure_connection() or not self.supabase:
            return False
        try:
            data = {
                "file_name": file_name,
                "source_id": source_id,
                "source_doc_url": source_doc_url,
                "domain": domain,
                "subdomain": subdomain,
                "b2b_b2c": b2b_b2c,
                "tier": tier,
                "jurisdiction": jurisdiction,
                "legal_validation": legal_validation,
                "xml_bucket_path": xml_bucket_path,
                "doc_title": doc_title,
            }
            self.supabase.table("source_metadata").upsert(data, on_conflict="file_name").execute()
            logger.info("Supabase file metadata upserted | file_name=%s | source_id=%s", file_name, source_id)
            return True
        except Exception as exc:
            logger.error("upsert_file_metadata failed | file_name=%s | error=%s", file_name, exc)
            return False

    def upload_raw_json_to_storage(
        self,
        bucket_name: str,
        storage_path: str,
        json_data: Dict[str, Any] | List[Any],
    ) -> bool:
        """Uploads a raw JSON payload directly to Supabase Storage bucket."""
        if not self.supabase:
            return False

        try:
            raw_bytes = json.dumps(json_data, ensure_ascii=False, indent=2).encode("utf-8")
            # Upload file to Supabase Storage (upsert = True)
            self.supabase.storage.from_(bucket_name).upload(
                path=storage_path,
                file=raw_bytes,
                file_options={"content-type": "application/json", "upsert": "true"},
            )
            logger.debug("Uploaded raw JSON to Supabase Storage: bucket=%s path=%s", bucket_name, storage_path)
            return True
        except Exception as exc:
            logger.warning("Failed to upload raw JSON to Supabase Storage (%s/%s): %s", bucket_name, storage_path, exc)
            return False

    def download_json_from_storage(
        self,
        bucket_name: str = DEFAULT_STORAGE_BUCKET,
        storage_path: str = "ledger/ledger_manifest.json",
    ) -> Optional[Dict[str, Any]]:
        """Downloads and parses a JSON object directly from Supabase Storage."""
        if not self._ensure_connection() or not self.supabase:
            return None
        try:
            res = self.supabase.storage.from_(bucket_name).download(storage_path)
            if res is not None:
                content_str = res.decode("utf-8") if isinstance(res, bytes) else str(res)
                return json.loads(content_str)
            return None
        except Exception as exc:
            logger.info("Storage bucket JSON not found or error (%s/%s): %s", bucket_name, storage_path, exc)
            return None

    def get_or_create_bucket_ledger(
        self,
        bucket_name: str = DEFAULT_STORAGE_BUCKET,
        storage_path: str = "ledger/ledger_manifest.json",
    ) -> Dict[str, Any]:
        """Loads existing ledger JSON object from Supabase bucket or initializes a new one."""
        existing = self.download_json_from_storage(bucket_name, storage_path)
        if existing and isinstance(existing, dict) and "documents" in existing:
            logger.info("Loaded Supabase Storage Bucket Ledger: %d documents tracked", len(existing.get("documents", {})))
            return existing

        # Fallback: check if we can populate from DB
        db_docs = self.get_document_ledger_from_db()
        ledger_obj = {
            "ledger_version": "2.0.0",
            "last_synced_at": None,
            "total_documents": len(db_docs),
            "documents": db_docs,
        }
        logger.info("Initialized new Supabase Storage Bucket Ledger with %d DB documents", len(db_docs))
        return ledger_obj

    def save_bucket_ledger(
        self,
        ledger_data: Dict[str, Any],
        bucket_name: str = DEFAULT_STORAGE_BUCKET,
        storage_path: str = "ledger/ledger_manifest.json",
    ) -> bool:
        """Uploads updated ledger manifest JSON to Supabase Storage."""
        if not self._ensure_connection():
            return False
        return self.upload_raw_json_to_storage(bucket_name, storage_path, ledger_data)

    def get_document_ledger_from_db(self) -> Dict[str, Dict[str, Any]]:
        """Fetches document summaries from PostgreSQL legal_documents table with pagination."""
        if not self._ensure_connection() or not self.supabase:
            return {}
        try:
            docs = {}
            offset = 0
            page_size = 1000
            while True:
                res = (
                    self.supabase.table("legal_documents")
                    .select(
                        "canonical_document_id, dok_id, xapi_id, document_type, title, last_amended_date, paragraph_count, vdb_status, content_file_hash, updated_at"
                    )
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = res.data or []
                for row in rows:
                    canon_id = row.get("canonical_document_id") or row.get("dok_id")
                    if canon_id:
                        docs[canon_id] = {
                            "canonical_document_id": canon_id,
                            "dok_id": row.get("dok_id"),
                            "xapi_id": str(row.get("xapi_id") or ""),
                            "document_type": row.get("document_type", "LAW"),
                            "title": row.get("title") or "Untitled",
                            "last_amended_date": row.get("last_amended_date"),
                            "paragraph_count": row.get("paragraph_count", 0),
                            "vdb_status": row.get("vdb_status", "SYNCED"),
                            "content_file_hash": row.get("content_file_hash") or "",
                            "last_synced_at": row.get("updated_at") or datetime.now(timezone.utc).isoformat(),
                        }
                if len(rows) < page_size:
                    break
                offset += page_size
            return docs
        except Exception as exc:
            logger.warning("Failed to fetch legal_documents for ledger init: %s", exc)
            return {}

    def upsert_rettsomrade_catalog(self, areas: List[Dict[str, Any]]) -> int:
        if not self._ensure_connection() or not self.supabase or not areas:
            return 0
        try:
            records = []
            for area in areas:
                name = (area.get("rettsomrade") or "").strip()[:255]
                if not name:
                    continue
                law_cnt = int(area.get("law_count", 0))
                reg_cnt = int(area.get("regulation_count", 0))
                records.append({
                    "rettsomrade": name,
                    "seen_in_laws": bool(area.get("seen_in_laws", law_cnt > 0)),
                    "seen_in_regulations": bool(area.get("seen_in_regulations", reg_cnt > 0)),
                    "law_count": law_cnt,
                    "regulation_count": reg_cnt,
                    "is_active": True,
                })
            if records:
                self.supabase.table("xapi_rettsomrade_catalog").upsert(records, on_conflict="rettsomrade").execute()
                logger.info("SupabaseStore: Upserted %d areas into xapi_rettsomrade_catalog", len(records))
                return len(records)
            return 0
        except Exception as exc:
            logger.warning("Failed to upsert xapi_rettsomrade_catalog: %s", exc)
            return 0

    def upsert_legal_documents(self, documents: List[Dict[str, Any]]) -> int:
        if not self.supabase or not documents:
            return 0
        count = 0
        for doc in documents:
            try:
                candidate_domains = doc.get("candidate_domain_ids") or doc.get("candidate_domains") or []
                primary_domain_id = doc.get("primary_domain_id") or (candidate_domains[0] if candidate_domains else None)
                dok_id = str(doc.get("dok_id") or doc.get("canonical_document_id") or "").strip()
                title = str(doc.get("title") or doc.get("tittel") or doc.get("short_title") or doc.get("navn") or "Uten tittel").strip()
                short_title = str(doc.get("short_title") or doc.get("korttittel") or doc.get("title") or title).strip()
                source_doc_url = doc.get("source_doc_url") or doc.get("url") or (f"{LOVDATA_BASE_URL}/{dok_id}" if dok_id else "")
                rettsomrade = ",".join(doc.get("rettsomrade", [])) if isinstance(doc.get("rettsomrade"), list) else (doc.get("rettsomrade") or doc.get("rettsomrade_filter") or "")

                doc_file_hash = str(
                    doc.get("content_file_hash")
                    or doc.get("content_hash")
                    or doc.get("source_md5")
                    or doc.get("fil_md5")
                    or ""
                ).strip()

                data = {
                    "document_type": doc.get("document_type", "LAW"),
                    "canonical_document_id": (doc.get("canonical_document_id") or dok_id)[:255],
                    "xapi_id": str(doc.get("id") or doc.get("xapi_id") or "")[:255],
                    "dok_id": dok_id[:255],
                    "ref_id": str(doc.get("ref_id") or (f"lov/{dok_id.replace('NL/lov/', '')}" if "NL/lov/" in dok_id else dok_id))[:255],
                    "legacy_id": str(doc.get("legacy_id") or "")[:255] if doc.get("legacy_id") else None,
                    "sf_dok_id": str(doc.get("sf_dok_id") or "")[:255] if doc.get("sf_dok_id") else None,
                    "title": title,
                    "short_title": short_title[:512] if short_title else None,
                    "department": str(doc.get("department") or doc.get("departement") or "")[:255] if (doc.get("department") or doc.get("departement")) else None,
                    "source_type": str(doc.get("source_type") or doc.get("kilde_type") or doc.get("type") or "lov")[:100],
                    "rettsomrade": str(rettsomrade)[:255] if rettsomrade else None,
                    "primary_domain_id": str(primary_domain_id)[:64] if primary_domain_id else None,
                    "candidate_domains": candidate_domains,
                    "routing_status": "CLASSIFIED" if primary_domain_id else "PENDING",
                    "effective_date": doc.get("effective_date") or doc.get("dato_ikraft"),
                    "announced_date": doc.get("announced_date") or doc.get("dato_kunngjort"),
                    "last_amended_date": doc.get("last_amended_date") or doc.get("dato_sist_endret"),
                    "last_amended_by": str(doc.get("last_amended_by") or doc.get("sist_endret_av") or "")[:255] if (doc.get("last_amended_by") or doc.get("sist_endret_av")) else None,
                    "eos_reference": doc.get("eos_reference") or doc.get("eos_henvisning"),
                    "other_information": doc.get("other_information") or doc.get("annet_info"),
                    "source_md5": str(doc.get("source_md5") or doc.get("fil_md5") or "")[:64] if (doc.get("source_md5") or doc.get("fil_md5")) else None,
                    "content_storage_bucket": str(doc.get("content_storage_bucket", DEFAULT_STORAGE_BUCKET))[:255],
                    "content_storage_path": doc.get("content_storage_path"),
                    "content_file_hash": doc_file_hash[:64] if doc_file_hash else None,
                    "paragraph_count": doc.get("antall_paragrafer") or doc.get("paragraph_count") or 0,
                    "paragraph_count_source": doc.get("paragraph_count_source") or "XAPI_PARAGRAPH_ENDPOINT",
                    "vdb_status": "SYNCED",
                    "taxonomy_version": str(doc.get("taxonomy_version", DEFAULT_TAXONOMY_VERSION))[:20],
                    "source_created_at": doc.get("source_created_at") or doc.get("opprettet"),
                    "source_updated_at": doc.get("source_updated_at") or doc.get("oppdatert"),
                    "is_active": True,
                }
                self.supabase.table("legal_documents").upsert(data, on_conflict="canonical_document_id").execute()
                count += 1
            except Exception as exc:
                logger.warning("Failed to upsert legal_documents record '%s': %s", doc.get("canonical_document_id"), exc)
        logger.info("SupabaseStore: Upserted %d records into legal_documents", count)
        return count

    def upsert_legal_sections(self, sections: List[Dict[str, Any]]) -> int:
        if not self.supabase or not sections:
            return 0
        count = 0
        for sec in sections:
            try:
                canon_id = sec.get("canonical_document_id") or sec.get("regulation_canonical_id") or sec.get("law_dok_id")
                if not canon_id:
                    continue

                res = self.supabase.table("legal_documents").select("id").eq("canonical_document_id", canon_id).limit(1).execute()
                if not res.data:
                    continue

                parent_db_id = res.data[0]["id"]

                vdb_status = sec.get("vdb_status", "NOT_ELIGIBLE")
                vdb_eligible = bool(sec.get("vdb_eligible", True))
                candidate_domains = sec.get("candidate_domain_ids") or sec.get("classification") or []
                p_id = str(sec.get("paragraf_id") or sec.get("provision_id") or sec.get("section_id") or "").strip()
                source_section_key = sec.get("source_section_key") or f"{canon_id}/{p_id}"
                source_section_url = sec.get("source_section_url") or sec.get("source_url") or f"{LOVDATA_BASE_URL}/{canon_id}#{p_id}"
                sec_hash = str(
                    sec.get("content_file_hash")
                    or sec.get("content_hash")
                    or sec.get("vdb_content_hash")
                    or sec.get("source_content_hash")
                    or ""
                ).strip()

                primary_sub_id = sec.get("primary_subdomain_id")
                sub_ids = sec.get("subdomain_ids") or ([primary_sub_id] if primary_sub_id else [])

                if primary_sub_id and primary_sub_id != "NO_SUBDOMAIN":
                    juris = sec.get("jurisdictions") or []
                    b2b = sec.get("b2b_b2c_types") or []
                    rels = sec.get("relationship_types") or []
                    tier_num = sec.get("tier")
                    sub_names = sec.get("subdomain_names") or []

                    rich_classification = {
                        "primary_subdomain_id": primary_sub_id,
                        "subdomain_ids": sub_ids,
                        "subdomain_name": sub_names[0] if sub_names else None,
                        "subdomain_names": sub_names,
                        "jurisdiction": juris if juris else None,
                        "b2b_b2c": b2b if b2b else None,
                        "relationship_type": rels if rels else None,
                        "tier": tier_num,
                        "candidate_domains": candidate_domains,
                        "mapping_status": "MAPPED",
                    }
                else:
                    rich_classification = {
                        "primary_subdomain_id": None,
                        "subdomain_ids": [],
                        "subdomain_name": None,
                        "subdomain_names": [],
                        "jurisdiction": None,
                        "b2b_b2c": None,
                        "relationship_type": None,
                        "tier": None,
                        "candidate_domains": candidate_domains,
                        "mapping_status": "NO_SUBDOMAIN_MATCH",
                    }

                data = {
                    "legal_document_id": parent_db_id,
                    "section_type": str(sec.get("record_type") or sec.get("section_type") or "LAW_PARAGRAPH")[:50],
                    "section_id": str(p_id)[:255],
                    "section_number": str(sec.get("section_number") or "")[:100] if sec.get("section_number") else None,
                    "source_section_key": str(source_section_key)[:255],
                    "source_section_url": str(source_section_url)[:512] if source_section_url else None,
                    "section_title": str(sec.get("section_title") or sec.get("heading") or sec.get("title") or "") if (sec.get("section_title") or sec.get("heading") or sec.get("title")) else None,
                    "chapter_number": str(sec.get("chapter_number") or "")[:50] if sec.get("chapter_number") else None,
                    "chapter_title": str(sec.get("chapter_title") or "")[:255] if sec.get("chapter_title") else None,
                    "content_storage_bucket": str(sec.get("content_storage_bucket", DEFAULT_STORAGE_BUCKET))[:255],
                    "content_storage_path": str(sec.get("content_storage_path") or f"xapi/laws/{canon_id.replace('/', '-')}.json#{source_section_key}")[:255],
                    "content_file_hash": sec_hash[:64] if sec_hash else None,
                    "classification": rich_classification,
                    "primary_subdomain_id": rich_classification["primary_subdomain_id"],
                    "subdomain_ids": rich_classification["subdomain_ids"],
                    "subdomain_name": rich_classification["subdomain_name"],
                    "jurisdiction": rich_classification["jurisdiction"],
                    "b2b_b2c": rich_classification["b2b_b2c"],
                    "relationship_type": rich_classification["relationship_type"],
                    "tier": rich_classification["tier"],
                    "mapping_status": rich_classification["mapping_status"],
                    "taxonomy_version": str(sec.get("taxonomy_version", DEFAULT_TAXONOMY_VERSION))[:20],
                    "vdb_eligible": vdb_eligible,
                    "vdb_status": "SYNCED" if vdb_eligible else vdb_status,
                    "vdb_content_hash": sec_hash[:64] if sec_hash else None,
                    "vdb_synced_at": datetime.now(timezone.utc).isoformat() if vdb_eligible else None,
                    "source_updated_at": sec.get("source_updated_at") or sec.get("oppdatert"),
                    "is_active": True,
                }
                self.supabase.table("legal_sections").upsert(data, on_conflict="legal_document_id,source_section_key").execute()
                count += 1
            except Exception as exc:
                logger.warning("Failed to upsert legal_sections record '%s': %s", sec.get("source_section_key"), exc)
        logger.info("SupabaseStore: Upserted %d records into legal_sections", count)
        return count

    def upsert_law_regulation_maps(self, mappings: List[Dict[str, Any]]) -> int:
        """
        Upserts parent law to delegated regulation relationships into the law_regulation_map table.
        """
        if not self._ensure_connection() or not self.supabase or not mappings:
            return 0

        count = 0
        for m in mappings:
            try:
                law_id = m.get("law_canonical_id") or m.get("law_dok_id") or m.get("parent_law_canonical_id") or m.get("linked_from_law_dok_id")
                reg_id = m.get("regulation_canonical_id") or m.get("regulation_dok_id") or m.get("canonical_document_id") or m.get("dok_id")
                rel_type = m.get("relationship_type") or "DELEGATED_REGULATION"

                if not law_id or not reg_id:
                    continue

                # Lookup law UUID
                res_law = self.supabase.table("legal_documents").select("id").eq("canonical_document_id", str(law_id).strip()).limit(1).execute()
                if not res_law.data:
                    res_law = self.supabase.table("legal_documents").select("id").eq("dok_id", str(law_id).strip()).limit(1).execute()
                if not res_law.data:
                    continue
                law_uuid = res_law.data[0]["id"]

                # Lookup regulation UUID
                res_reg = self.supabase.table("legal_documents").select("id").eq("canonical_document_id", str(reg_id).strip()).limit(1).execute()
                if not res_reg.data:
                    res_reg = self.supabase.table("legal_documents").select("id").eq("dok_id", str(reg_id).strip()).limit(1).execute()
                if not res_reg.data:
                    continue
                reg_uuid = res_reg.data[0]["id"]

                payload = {
                    "law_document_id": law_uuid,
                    "regulation_document_id": reg_uuid,
                    "relationship_type": rel_type,
                }
                self.supabase.table("law_regulation_map").upsert(payload, on_conflict="law_document_id,regulation_document_id").execute()
                count += 1
            except Exception as exc:
                logger.debug("Failed to upsert law_regulation_map (%s -> %s): %s", m.get("law_dok_id"), m.get("regulation_dok_id"), exc)

        if count > 0:
            logger.info("SupabaseStore: Upserted %d relationships into law_regulation_map", count)
        return count

    def create_ingestion_run(self, run_type: str = "STAGE_1_FULL_COLLECTION") -> Optional[str]:
        if not self._ensure_connection() or not self.supabase:
            return None
        try:
            res = self.supabase.table("ingestion_runs").insert({
                "run_type": run_type,
                "status": "RUNNING",
                "taxonomy_version": settings.taxonomy_version,
                "started_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
            if res.data:
                run_id = res.data[0]["id"]
                logger.info("SupabaseStore: Created ingestion run id=%s", run_id)
                return run_id
        except Exception as exc:
            logger.error("Failed to create ingestion run: %s", exc)
        return None

    def complete_ingestion_run(self, run_id: str, summary: Dict[str, Any], status: str = "COMPLETED", error_message: Optional[str] = None) -> None:
        if not self._ensure_connection() or not self.supabase or not run_id:
            return
        try:
            self.supabase.table("ingestion_runs").update({
                "status": status,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "documents_discovered": summary.get("documents_discovered", 0),
                "documents_created": summary.get("documents_created", 0),
                "documents_updated": summary.get("documents_updated", 0),
                "documents_skipped": summary.get("documents_skipped", 0),
                "sections_processed": summary.get("sections_processed", 0),
                "sections_eligible": summary.get("sections_eligible", summary.get("sections_processed", 0)),
                "vdb_inserted": summary.get("vdb_inserted", 0) or summary.get("milvus_chunks_indexed", 0),
                "vdb_updated": summary.get("vdb_updated", 0),
                "vdb_deleted": summary.get("vdb_deleted", 0),
                "vdb_failed": summary.get("vdb_failed", 0),
                "error_message": error_message or summary.get("error_message"),
                "metadata": summary,
            }).eq("id", run_id).execute()
            logger.info("SupabaseStore: Completed ingestion run id=%s with status=%s", run_id, status)
        except Exception as exc:
            logger.error("Failed to complete ingestion run id=%s: %s", run_id, exc)

    def record_run_items(self, items: List[Dict[str, Any]]) -> int:
        """Inserts batch processing tracking records into ingestion_run_items."""
        if not self._ensure_connection() or not self.supabase or not items:
            return 0
        try:
            records = []
            for item in items:
                records.append({
                    "ingestion_run_id": item["ingestion_run_id"],
                    "stage": str(item.get("stage", "STAGE_2_EXTRACTION"))[:50],
                    "endpoint": str(item.get("endpoint", "/v1/lovdata/lover"))[:255],
                    "entity_type": str(item.get("entity_type", "LAW"))[:50],
                    "source_identifier": str(item.get("source_identifier", ""))[:255],
                    "domain_id": str(item.get("domain_id", ""))[:64] if item.get("domain_id") else None,
                    "rettsomrade": str(item.get("rettsomrade", ""))[:255] if item.get("rettsomrade") else None,
                    "offset": item.get("offset"),
                    "limit": item.get("limit"),
                    "status": str(item.get("status", "SUCCESS"))[:50],
                    "attempt_count": item.get("attempt_count", 1),
                    "http_status": item.get("http_status", 200),
                    "error_message": item.get("error_message"),
                    "raw_response_path": item.get("raw_response_path"),
                    "response_hash": item.get("response_hash"),
                    "started_at": item.get("started_at"),
                    "completed_at": item.get("completed_at"),
                })
            res = self.supabase.table("ingestion_run_items").insert(records).execute()
            logger.info("SupabaseStore: Recorded %d items into ingestion_run_items", len(records))
            return len(records)
        except Exception as exc:
            logger.warning("Failed to insert into ingestion_run_items: %s", exc)
            return 0