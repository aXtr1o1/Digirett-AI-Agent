from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Ensure project root & ingestion root are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
INGESTION_DIR = CURRENT_DIR.parent
PROJECT_ROOT = INGESTION_DIR.parent

for p in [str(PROJECT_ROOT), str(INGESTION_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from ingestion.src.config import (
    CHECKPOINT_DIR,
    DOCUMENT_BATCH_SIZE,
    EMBEDDING_BATCH_SIZE,
    LOVDATA_BASE_URL,
    NORMALIZED_DIR,
    REPORTS_DIR,
    logger,
    settings,
)
from ingestion.collectors.xapi_collector import XAPICollector
from ingestion.deduplication.deduplicator import (
    CanonicalDeduplicator,
    law_canonical_id,
    regulation_canonical_id,
)
from ingestion.adapters.law_section_adapter import LawSectionAdapter
from ingestion.adapters.regulation_section_adapter import RegulationSectionAdapter
from ingestion.models.legal_section import EnrichedMilvusChunk, NormalizedLegalSection
from ingestion.src.chunking import (
    ChunkContentValidator,
    ChunkEnricher,
    LegalSectionChunker,
    TaxonomyRouter,
)
from ingestion.src.processors.embedder import TokenAwareAzureEmbedder
from ingestion.src.processors.comparing_engine import ComparingEngine, ComparisonResult
from ingestion.src.processors.batch_checkpoint_manager import BatchCheckpointManager
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusChunkStore
from ingestion.src.tools.review_exporter import TaxonomyReviewExporter, ReviewItem
from ingestion.src.utils.jsonl_exporter import FormatNormaliser
from ingestion.validation.url_validator import LovdataURLValidator
class MappingBundle:
    """Encapsulates rettsområde -> domain_id mappings loaded from configuration."""

    def __init__(self, mapping_path: Optional[Path] = None):
        self.mapping_path = mapping_path
        self.is_client_mapping_loaded = False
        self.mapping_version = "1.1.0"
        self.direct_mappings: List[Dict[str, Any]] = []
        self.out_of_scope: List[Dict[str, Any]] = []
        self.legend: Dict[str, str] = {}

        p = Path(mapping_path) if mapping_path else settings.mapping_path
        if p and p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                self.is_client_mapping_loaded = True
                self.legend = data.get("domain_id_legend", {})
                mappings = data.get("mappings", [])
                self.direct_mappings = [
                    m for m in mappings
                    if m.get("domain_id") not in ["OUT_OF_SCOPE", "NEEDS_VERIFICATION", "NEEDS_ROUTING"]
                ]
                self.out_of_scope = [m for m in mappings if m.get("domain_id") == "OUT_OF_SCOPE"]
            except Exception as exc:
                logger.warning("Could not load rettsomrade mapping: %s", exc)

    def build_domain_plans(self) -> Dict[str, Any]:
        """Builds domain execution plans based on loaded direct mappings."""
        plans = {}
        for d_id, name in self.legend.items():
            if d_id not in ["OUT_OF_SCOPE", "NEEDS_VERIFICATION", "NEEDS_ROUTING"]:
                areas = [
                    m.get("rettsomrade")
                    for m in self.direct_mappings
                    if m.get("domain_id") == d_id and m.get("rettsomrade")
                ]
                plans[d_id] = type("DomainPlan", (), {
                    "domain_id": d_id,
                    "domain_name": name,
                    "rettsomrader": areas,
                })()
        return plans


def load_mapping(path: Optional[Union[str, Path]] = None) -> MappingBundle:
    """Loads and returns a MappingBundle instance."""
    return MappingBundle(Path(path) if path else settings.mapping_path)


def format_chunk_payload(chunk: EnrichedMilvusChunk) -> Dict[str, Any]:
    """Formats an EnrichedMilvusChunk into a dictionary for Milvus vector indexing."""
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.embedding_text,
        "token_count": chunk.token_count,
        "source_text": chunk.source_text,
        "domain_id": chunk.domain_id,
        "domain_name": chunk.domain_name,
        "subdomain_id": chunk.subdomain_id,
        "subdomain_name": chunk.subdomain_name,
        "subdomain_ids": chunk.subdomain_ids,
        "subdomain_names": chunk.subdomain_names,
        "canonical_document_id": chunk.canonical_document_id,
        "legal_document_id": chunk.canonical_document_id,
        "legal_section_id": chunk.legal_section_id,
        "source_section_key": chunk.source_section_key,
        "document_type": chunk.document_type,
        "doc_title": chunk.doc_title,
        "section_number": chunk.section_number,
        "section_title": chunk.section_title,
        "citation_anchor": chunk.citation_anchor,
        "source_url": chunk.source_url,
        "chunk_index": chunk.chunk_index,
        "content_hash": chunk.content_hash,
        "jurisdictions": chunk.jurisdictions,
        "b2b_b2c_types": chunk.b2b_b2c_types,
        "relationship_types": chunk.relationship_types,
        "parent_law_canonical_id": chunk.parent_law_canonical_id,
        "parent_law_title": chunk.parent_law_title,
        "source_type": chunk.source_type,
        "tier": chunk.tier,
        "language": chunk.language,
        "version_date": chunk.version_date,
        "taxonomy_version": chunk.taxonomy_version,
    }
class RealTimePipelineRunner:
    """Orchestrates real-time end-to-end xAPI data collection, embedding & storage."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.mapping_bundle = load_mapping(settings.mapping_path)
        self.domain_plans = self.mapping_bundle.build_domain_plans()
        self.deduplicator = CanonicalDeduplicator()
        self.normaliser = FormatNormaliser(output_dir=NORMALIZED_DIR)
        self.supabase_store = SupabaseStore()
        self.milvus_store = MilvusChunkStore()
        self.comparing_engine = ComparingEngine(supabase_store=self.supabase_store)
        self.batch_checkpoint_manager = BatchCheckpointManager()
        self.chunker = LegalSectionChunker()
        self.validator = ChunkContentValidator()
        self.taxonomy_router = TaxonomyRouter(
            domain_legend=self.mapping_bundle.legend if self.mapping_bundle.is_client_mapping_loaded else None
        )
        self.enricher = ChunkEnricher()
        self.embedder: Optional[TokenAwareAzureEmbedder] = None
        self.review_exporter = TaxonomyReviewExporter(output_dir=REPORTS_DIR)
        self.review_items: List[ReviewItem] = []

    def _get_embedder(self) -> TokenAwareAzureEmbedder:
        if self.embedder is None:
            self.embedder = TokenAwareAzureEmbedder()
        return self.embedder

    async def verify_environment(self) -> bool:
        """Verifies settings, Supabase connection, Milvus readiness, and xAPI connectivity."""
        logger.info("=== VERIFYING END-TO-END PIPELINE ENVIRONMENT ===")
        logger.info("xAPI Base URL: %s", settings.xapi_base_url)
        logger.info("Supabase URL: %s", settings.supabase_url or "Not Configured")
        logger.info(
            "Milvus Host: %s:%s | Collection: %s",
            self.milvus_store.host,
            self.milvus_store.port,
            self.milvus_store.collection_name,
        )

        if self.mapping_bundle.is_client_mapping_loaded:
            logger.info(
                "Client Domain Mapping File: LOADED (version=%s, %d direct mappings, %d out-of-scope)",
                self.mapping_bundle.mapping_version,
                len(self.mapping_bundle.direct_mappings),
                len(self.mapping_bundle.out_of_scope),
            )
        else:
            logger.info("Client Domain Mapping File: NOT LOADED (Operating in Pure Discovery Mode)")

        async with XAPICollector() as client:
            try:
                areas, _, _ = await client.get_areas()
                logger.info("xAPI Connection Verified: %d live rettsområder discovered", len(areas))
            except Exception as exc:
                logger.error("xAPI Connection Verification Failed: %s", exc)
                return False
        return True

    def get_candidate_domains_for_area(self, rettsomrade: str) -> List[str]:
        """Maps an xAPI rettsområde string to candidate DigiRett domain_ids."""
        if not rettsomrade or not self.mapping_bundle.direct_mappings:
            return []
        matches = [
            m.get("domain_id")
            for m in self.mapping_bundle.direct_mappings
            if m.get("rettsomrade", "").strip().lower() == rettsomrade.strip().lower()
        ]
        return [m for m in matches if m]

    async def resolve_target_areas(
        self,
        domain_filter: Optional[str] = None,
        client: Optional[XAPICollector] = None,
    ) -> List[str]:
       
        # --- 1. Filter Specified (CLI / Parameter) ---
        if domain_filter:
            filter_key = domain_filter.strip()
            filter_upper = filter_key.upper()
            if filter_upper in self.domain_plans:
                areas = self.domain_plans[filter_upper].rettsomrader
                logger.info(
                    "Filtered by Client Domain ID '%s' (%s): %d target rettsområder",
                    filter_upper,
                    self.domain_plans[filter_upper].domain_name,
                    len(areas),
                )
                return areas

            matched_plan = next(
                (p for p in self.domain_plans.values() if p.domain_name.lower() == filter_key.lower()),
                None,
            )
            if matched_plan:
                logger.info(
                    "Filtered by Client Domain Name '%s' (%s): %d target rettsområder",
                    matched_plan.domain_name,
                    matched_plan.domain_id,
                    len(matched_plan.rettsomrader),
                )
                return matched_plan.rettsomrader

            logger.info("Filtered by Direct xAPI Rettsområde '%s'", filter_key)
            return [filter_key]

        # --- 2. Primary Path: Local Client JSON Mapping ---
        if self.mapping_bundle.is_client_mapping_loaded and self.domain_plans:
            mapped_areas = set()
            for plan in self.domain_plans.values():
                mapped_areas.update(plan.rettsomrader)
            target_areas = sorted(mapped_areas)
            if target_areas:
                logger.info(
                    "Operating in Client Mapped Domains Mode (Primary Path): %d target areas across %d domains",
                    len(target_areas),
                    len(self.domain_plans),
                )
                return target_areas

        # --- 3. Fallback Path: Live xAPI Endpoint Discovery & Reconciliation ---
        logger.warning(
            "Client JSON mapping is empty or not loaded. Initiating Fallback: Querying live xAPI endpoint..."
        )
        try:
            if client is None:
                async with XAPICollector() as auto_client:
                    raw_areas, _, _ = await auto_client.get_areas()
            else:
                raw_areas, _, _ = await client.get_areas()

            fallback_areas = []
            out_of_scope_names = {
                (m.get("rettsomrade") or "").strip().lower()
                for m in self.mapping_bundle.out_of_scope
            }

            for item in raw_areas:
                area_name = (item.get("rettsomrade") or item.get("name") or "").strip()
                if not area_name:
                    continue

                # Strictly exclude OUT_OF_SCOPE
                if area_name.lower() in out_of_scope_names:
                    logger.debug("Fallback: Skipping OUT_OF_SCOPE area '%s'", area_name)
                    continue

                # If direct mappings exist, only include mapped
                if self.mapping_bundle.direct_mappings:
                    if self.get_candidate_domains_for_area(area_name):
                        fallback_areas.append(area_name)
                else:
                    # In pure discovery mode, include active areas
                    fallback_areas.append(area_name)

            logger.info(
                "Fallback Discovery Resolved: %d valid in-scope target areas from live xAPI",
                len(fallback_areas),
            )
            return sorted(set(fallback_areas))

        except Exception as exc:
            logger.error("Fallback live xAPI discovery failed: %s", exc)
            return []

    def chunk_and_enrich_sections(
        self,
        sections: List[NormalizedLegalSection],
    ) -> List[EnrichedMilvusChunk]:
        
        all_chunks: List[EnrichedMilvusChunk] = []

        for sec in sections:
            if not sec.is_processable:
                continue

            structural_chunks = self.chunker.chunk_section(sec)
            sec_sub_ids: Set[str] = set()
            sec_sub_names: Set[str] = set()

            for sc in structural_chunks:
                is_valid, _ = self.validator.validate(sc)
                if not is_valid:
                    continue

                classifications = self.taxonomy_router.classify(
                    chunk=sc,
                    candidate_domain_ids=sec.candidate_domain_ids,
                    section_heading=sec.section_title or sec.section_number,
                    document_type=sec.document_type,
                )
                for cls in classifications:
                    if not cls.vdb_eligible or not cls.subdomain_id or cls.subdomain_id == "NO_SUBDOMAIN":
                        category = "UNMAPPED_DOMAIN" if cls.domain_id in ("UNMAPPED", "OUT_OF_SCOPE") else "NO_SUBDOMAIN"
                        self.review_items.append(
                            ReviewItem(
                                canonical_document_id=sec.canonical_document_id,
                                document_type=sec.document_type,
                                document_title=sec.document_title,
                                section_number=sec.section_number,
                                heading=sec.section_title or sec.section_number,
                                chapter=f"{sec.chapter_number or ''} {sec.chapter_title or ''}".strip(),
                                domain_id=cls.domain_id,
                                subdomain_id=cls.subdomain_id or "NO_SUBDOMAIN",
                                review_category=category,
                                confidence=cls.confidence,
                                reason="No specific subdomain profile matched or general domain provision" if category == "NO_SUBDOMAIN" else "No candidate legal domain mapped",
                                sample_text=sc.source_text[:500],
                                source_url=sec.source_url or "",
                                vdb_eligible=False,
                            )
                        )
                        continue
                    enriched = self.enricher.enrich(sec, sc, cls)
                    all_chunks.append(enriched)

                    self.review_items.append(
                        ReviewItem(
                            canonical_document_id=sec.canonical_document_id,
                            document_type=sec.document_type,
                            document_title=sec.document_title,
                            section_number=sec.section_number,
                            heading=sec.section_title or sec.section_number,
                            chapter=f"{sec.chapter_number or ''} {sec.chapter_title or ''}".strip(),
                            domain_id=cls.domain_id,
                            subdomain_id=cls.subdomain_id,
                            subdomain_name=cls.subdomain_name or "",
                            review_category="MAPPED",
                            confidence=cls.confidence,
                            reason="Valid domain and subdomain mapped",
                            sample_text=sc.source_text[:500],
                            source_url=sec.source_url or "",
                            vdb_eligible=True,
                        )
                    )

                    for sid in (cls.subdomain_ids or ([cls.subdomain_id] if cls.subdomain_id else [])):
                        if sid and sid != "NO_SUBDOMAIN":
                            sec_sub_ids.add(sid)
                    for sname in (cls.subdomain_names or ([cls.subdomain_name] if cls.subdomain_name else [])):
                        if sname:
                            sec_sub_names.add(sname)

                    sec.jurisdictions = cls.jurisdiction
                    sec.b2b_b2c_types = cls.b2b_b2c
                    sec.relationship_types = cls.relationship_type
                    sec.tier = cls.tier
                    sec.taxonomy_version = cls.taxonomy_version

            sec.subdomain_ids = sorted(list(sec_sub_ids))
            sec.subdomain_names = sorted(list(sec_sub_names))
            sec.primary_subdomain_id = sec.subdomain_ids[0] if sec.subdomain_ids else None

        return all_chunks

    def embed_and_index_chunks(
        self,
        chunks: List[EnrichedMilvusChunk],
        batch_size: int = EMBEDDING_BATCH_SIZE,
    ) -> int:
        """Embeds chunks with Azure OpenAI and indexes vectors in Milvus in batches."""
        # Only index chunks with valid domain and subdomain
        indexable_chunks = [
            c for c in (chunks or [])
            if c.domain_id and c.domain_id != "UNMAPPED"
            and c.subdomain_id and c.subdomain_id != "NO_SUBDOMAIN"
        ]
        if not indexable_chunks or self.dry_run:
            return 0

        embedder = self._get_embedder()
        total_chunks = len(indexable_chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size
        stored_count = 0

        logger.info("Batch-Wise Embedding & Indexing: %d chunks across %d batches", total_chunks, total_batches)

        for b_idx in range(total_batches):
            batch = indexable_chunks[b_idx * batch_size : (b_idx + 1) * batch_size]
            payloads = [format_chunk_payload(c) for c in batch]

            embedded = embedder.embed_chunks(payloads, text_field="text")
            valid = [p for p in embedded if p.get("embedding") is not None]

            if valid:
                inserted = self.milvus_store.insert_chunks(valid, batch_size=batch_size)
                stored_count += inserted

            pct = min(100.0, ((b_idx + 1) / total_batches) * 100)
            logger.info(
                "[Milvus Batch %03d/%03d] Embedded & Stored %d chunks | Total: %d/%d (%.1f%%)",
                b_idx + 1,
                total_batches,
                len(valid),
                stored_count,
                total_chunks,
                pct,
            )

        return stored_count

    async def _process_law_document(
        self,
        law: Dict[str, Any],
        client: XAPICollector,
    ) -> Tuple[List[NormalizedLegalSection], List[EnrichedMilvusChunk]]:
        """Processes a single law: fetches paragraphs, normalizes sections, uploads raw JSON, and chunks."""
        xapi_id = law.get("id") or law.get("xapi_id") or ""
        dok_id = law.get("dok_id") or law.get("canonical_document_id") or ""
        law["canonical_document_id"] = dok_id
        law["document_type"] = "LAW"
        storage_path = f"xapi/laws/{dok_id.replace('/', '-')}.json"
        law["content_storage_bucket"] = "raw_json_files"
        law["content_storage_path"] = storage_path

        raw_paras: List[Dict[str, Any]] = []
        if xapi_id:
            try:
                detail = await client.get_law_detail(xapi_id)
                if detail and isinstance(detail, dict):
                    for k, v in detail.items():
                        if v is not None and k != "data":
                            law[k] = v
            except Exception as exc:
                logger.debug("Notice fetching detail for law %s: %s", dok_id, exc)

            try:
                raw_paras, _, _ = await client.get_law_paragraphs(xapi_id)
            except Exception as exc:
                logger.warning("Failed fetching paragraphs for law %s: %s", dok_id, exc)

        if not self.dry_run:
            self.supabase_store.upload_raw_json_to_storage("raw_json_files", storage_path, law)

        law_content_bytes = json.dumps(law, ensure_ascii=False, default=str).encode("utf-8")
        law["content_file_hash"] = (
            law.get("fil_md5")
            or law.get("source_md5")
            or hashlib.sha256(law_content_bytes).hexdigest()[:32]
        )

        norm_sections = LawSectionAdapter.adapt_all(raw_paras, law)
        law["paragraph_count"] = len(norm_sections)
        law["paragrafer"] = raw_paras

        doc_chunks = self.chunk_and_enrich_sections(norm_sections)
        return norm_sections, doc_chunks

    async def _process_regulation_document(
        self,
        reg: Dict[str, Any],
    ) -> Tuple[List[NormalizedLegalSection], List[EnrichedMilvusChunk]]:
        """Processes a single regulation: parses HTML fulltext, normalizes provisions, uploads raw JSON, and chunks."""
        canon_id = reg.get("canonical_document_id") or reg.get("canonical_id") or reg.get("dok_id") or ""
        reg["canonical_document_id"] = canon_id
        reg["dok_id"] = reg.get("dok_id") or canon_id
        reg["document_type"] = "REGULATION"
        storage_path = f"xapi/regulations/{canon_id.replace('/', '-')}.json"
        reg["content_storage_bucket"] = "raw_json_files"
        reg["content_storage_path"] = storage_path

        if not self.dry_run:
            self.supabase_store.upload_raw_json_to_storage("raw_json_files", storage_path, reg)

        reg_content_bytes = json.dumps(reg, ensure_ascii=False, default=str).encode("utf-8")
        reg["content_file_hash"] = (
            reg.get("fil_md5")
            or reg.get("source_md5")
            or hashlib.sha256(reg_content_bytes).hexdigest()[:32]
        )

        fulltext_html = reg.get("fulltekst") or reg.get("content") or ""
        has_usable_fulltext = bool(isinstance(fulltext_html, str) and fulltext_html.strip())
        reg["has_fulltext"] = has_usable_fulltext

        if has_usable_fulltext:
            norm_sections = RegulationSectionAdapter.adapt_all(reg)
            reg["paragraph_count"] = len(norm_sections)
        else:
            norm_sections = []
            reg["paragraph_count"] = 0

        doc_chunks = self.chunk_and_enrich_sections(norm_sections)
        return norm_sections, doc_chunks

    async def run(self, domain_filter: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Runs the complete real-time ingestion pipeline."""
        logger.info("==========================================================================")
        logger.info("   STARTING REAL-TIME xAPI END-TO-END DATA COLLECTION & VECTOR PIPELINE")
        logger.info("   Scope: CLIENT MAPPED DOMAINS | Domain Filter: %s | Limit: %s", domain_filter or "ALL MAPPED", limit or "None")
        logger.info("==========================================================================")

        run_id = None
        if not self.dry_run:
            run_id = self.supabase_store.create_ingestion_run(run_type="REALTIME_STAGE_1_COLLECTION")

        all_milvus_chunks: List[EnrichedMilvusChunk] = []
        all_normalized_sections: List[NormalizedLegalSection] = []
        collected_paragraphs: List[Dict[str, Any]] = []
        collected_provisions: List[Dict[str, Any]] = []

        async with XAPICollector() as client:
            # 1. Non-blocking Rettsområde Catalog Sync (Live drift detection)
            try:
                raw_areas, _, _ = await client.get_areas()
                logger.info("Discovered %d live xAPI areas for catalog sync", len(raw_areas))
                if not self.dry_run:
                    self.supabase_store.upsert_rettsomrade_catalog(raw_areas)
            except Exception as exc:
                logger.warning("Optional live xAPI catalog sync skipped/failed: %s", exc)

            target_areas = await self.resolve_target_areas(domain_filter, client=client)

            # 2. Laws Discovery & Collection
            collected_raw_laws: List[Dict[str, Any]] = []
            area_law_counts: Dict[str, int] = {}
            for area in target_areas:
                if not area:
                    continue
                try:
                    laws, _, _ = await client.get_laws_by_area(area)
                    area_law_counts[area] = len(laws)
                    for law in laws:
                        law["rettsomrade_filter"] = area
                        law["candidate_domain_ids"] = self.get_candidate_domains_for_area(area)
                    collected_raw_laws.extend(laws)
                except Exception as exc:
                    logger.warning("Error fetching laws for area '%s': %s", area, exc)

            unique_laws = self.deduplicator.deduplicate_laws(collected_raw_laws)
            if limit:
                unique_laws = unique_laws[:limit]
            logger.info(
                "Law Deduplication Complete: %d raw appearances -> %d unique laws",
                len(collected_raw_laws),
                len(unique_laws),
            )

            # 3. Process Laws
            for idx, law in enumerate(unique_laws, start=1):
                dok_id = law.get("dok_id", "unknown")
                title = law.get("title") or law.get("short_title") or law.get("tittel") or "Untitled Law"
                norm_sections, law_chunks = await self._process_law_document(law, client)
                all_normalized_sections.extend(norm_sections)
                all_milvus_chunks.extend(law_chunks)

                rdb_records = [s.to_rdb_dict() for s in norm_sections]
                collected_paragraphs.extend(rdb_records)

                if not self.dry_run:
                    self.supabase_store.upsert_legal_documents([law])
                    if rdb_records:
                        self.supabase_store.upsert_legal_sections(rdb_records)

                # Update in-memory Ledger entry
                self.comparing_engine.update_document_entry(
                    doc_id=dok_id,
                    document_metadata=law,
                    vdb_status="SYNCED" if not self.dry_run else "DRY_RUN",
                )

                domains_str = ",".join(law.get("candidate_domain_ids", [])) or "UNMAPPED"
                print(f"[{idx:03d}/{len(unique_laws):03d}] LAW | {title[:38]} ({dok_id}) -> Domain: {domains_str} | Sections: {len(norm_sections)} | Chunks: {len(law_chunks)} | RDB [OK]")

            # 4. Regulations Discovery
            central_regs: List[Dict[str, Any]] = []
            linked_regs: List[Dict[str, Any]] = []
            try:
                c_regs, _, _ = await client.get_central_regulations_for_domain(target_areas)
                for r in c_regs:
                    area = r.get("rettsomrade_filter")
                    r["candidate_domain_ids"] = self.get_candidate_domains_for_area(area) if area else []
                central_regs.extend(c_regs)
            except Exception as exc:
                logger.warning("Error fetching central regulations: %s", exc)

            # Catalog updates
            area_reg_counts: Dict[str, int] = {a: 0 for a in target_areas}
            for r in central_regs:
                r_areas = r.get("matched_rettsomrader") or ([r.get("rettsomrade_filter")] if r.get("rettsomrade_filter") else [])
                for a in r_areas:
                    if a in area_reg_counts:
                        area_reg_counts[a] += 1

            if not self.dry_run:
                catalog_updates = [
                    {
                        "rettsomrade": a,
                        "law_count": area_law_counts.get(a, 0),
                        "regulation_count": area_reg_counts.get(a, 0),
                        "seen_in_laws": area_law_counts.get(a, 0) > 0,
                        "seen_in_regulations": area_reg_counts.get(a, 0) > 0,
                    }
                    for a in target_areas
                ]
                if catalog_updates:
                    self.supabase_store.upsert_rettsomrade_catalog(catalog_updates)

            for law in unique_laws:
                dok_id = law.get("dok_id")
                if not dok_id:
                    continue
                try:
                    l_regs, _, _ = await client.get_regulations_for_law(dok_id)
                    for r in l_regs:
                        r["linked_from_law_dok_id"] = dok_id
                        r["candidate_domain_ids"] = law.get("candidate_domain_ids", [])
                    linked_regs.extend(l_regs)
                except Exception as exc:
                    logger.warning("Law-linked regulation fetch error for %s: %s", dok_id, exc)

            unique_regulations = self.deduplicator.deduplicate_regulations(central_regs, linked_regs)
            if limit:
                unique_regulations = unique_regulations[:limit]

            # 5. Process Regulations
            missing_fulltext_count = 0
            for idx, reg in enumerate(unique_regulations, start=1):
                canon_id = reg.get("canonical_id") or reg.get("dok_id") or ""
                title = reg.get("title") or reg.get("short_title") or reg.get("tittel") or "Untitled Regulation"
                norm_provisions, reg_chunks = await self._process_regulation_document(reg)
                all_normalized_sections.extend(norm_provisions)
                all_milvus_chunks.extend(reg_chunks)

                if not reg.get("has_fulltext"):
                    missing_fulltext_count += 1

                rdb_records = [p.to_rdb_dict() for p in norm_provisions]
                collected_provisions.extend(rdb_records)

                if not self.dry_run:
                    self.supabase_store.upsert_legal_documents([reg])
                    if rdb_records:
                        self.supabase_store.upsert_legal_sections(rdb_records)
                    parent_law_id = reg.get("linked_from_law_dok_id") or reg.get("parent_law_canonical_id")
                    if parent_law_id:
                        self.supabase_store.upsert_law_regulation_maps([{
                            "law_dok_id": parent_law_id,
                            "regulation_dok_id": canon_id,
                            "relationship_type": "DELEGATED_REGULATION",
                        }])

                # Update in-memory Ledger entry
                self.comparing_engine.update_document_entry(
                    doc_id=canon_id,
                    document_metadata=reg,
                    vdb_status="SYNCED" if not self.dry_run else "DRY_RUN",
                )

                domains_str = ",".join(reg.get("candidate_domain_ids", [])) or "UNMAPPED"
                status_str = f"Sections: {len(norm_provisions)} | Chunks: {len(reg_chunks)}" if reg.get("has_fulltext") else "NO FULLTEXT"
                print(f"[{idx:04d}/{len(unique_regulations):04d}] REGULATION | {title[:32]} ({canon_id}) -> Domain: {domains_str} | {status_str} | RDB [OK]")

            # 6. Export Normalized Datasets
            chunk_records = [
                {
                    "chunk_id": c.chunk_id,
                    "canonical_document_id": c.canonical_document_id,
                    "legal_section_id": c.legal_section_id,
                    "source_section_key": c.source_section_key,
                    "domain_id": c.domain_id,
                    "domain_name": c.domain_name,
                    "subdomain_id": c.subdomain_id,
                    "subdomain_name": c.subdomain_name,
                    "subdomain_ids": c.subdomain_ids,
                    "subdomain_names": c.subdomain_names,
                    "jurisdictions": c.jurisdictions,
                    "b2b_b2c_types": c.b2b_b2c_types,
                    "relationship_types": c.relationship_types,
                    "tier": c.tier,
                    "section_number": c.section_number,
                    "section_title": c.section_title,
                    "token_count": c.token_count,
                    "chunk_index": c.chunk_index,
                    "content_hash": c.content_hash,
                    "taxonomy_version": c.taxonomy_version,
                    "source_text": c.source_text,
                }
                for c in all_milvus_chunks
            ]
            self.normaliser.export_all(
                laws=unique_laws,
                paragraphs=collected_paragraphs,
                regulations=unique_regulations,
                provisions=collected_provisions,
                chunks=chunk_records,
            )

            # 7. Embed & Store in Milvus
            stored_milvus_count = self.embed_and_index_chunks(all_milvus_chunks, batch_size=EMBEDDING_BATCH_SIZE)

            # 8. Diagnostic Summary & Audit Report
            unique_central_ids = {regulation_canonical_id(r) for r in central_regs if regulation_canonical_id(r)}
            unique_linked_ids = {regulation_canonical_id(r) for r in linked_regs if regulation_canonical_id(r)}
            overlap_ids = unique_central_ids.intersection(unique_linked_ids)
            laws_with_paras = sum(1 for law in unique_laws if (law.get("paragraph_count") or 0) > 0)

            summary = {
                "scope": "CLIENT_MAPPED_DOMAINS",
                "mapping_version": self.mapping_bundle.mapping_version,
                "total_live_rettsomrader": len(raw_areas),
                "target_rettsomrader_count": len(target_areas),
                "raw_laws_collected": len(collected_raw_laws),
                "unique_laws": len(unique_laws),
                "laws_with_paragraphs": laws_with_paras,
                "law_paragraphs_rdb": len(collected_paragraphs),
                "central_regulations_raw": len(central_regs),
                "unique_central_regulations": len(unique_central_ids),
                "law_linked_regulation_relationships": len(linked_regs),
                "unique_law_linked_regulations": len(unique_linked_ids),
                "central_linked_overlap": len(overlap_ids),
                "unique_regulations": len(unique_regulations),
                "regulations_with_fulltext": len(unique_regulations) - missing_fulltext_count,
                "regulations_missing_fulltext": missing_fulltext_count,
                "countable_regulation_provisions_rdb": len(collected_provisions),
                "total_rdb_sections": len(collected_paragraphs) + len(collected_provisions),
                "total_materialized_milvus_chunks": len(all_milvus_chunks),
                "total_stored_milvus_chunks": stored_milvus_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            audit_file = REPORTS_DIR / "ingestion_audit_report.json"
            audit_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            state_file = CHECKPOINT_DIR / "ingestion_state.json"
            state_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

            if self.review_items:
                try:
                    excel_path, json_path = self.review_exporter.export_excel_report(self.review_items)
                    summary["review_report_excel"] = str(excel_path)
                    summary["review_items_count"] = len(self.review_items)
                    logger.info("Taxonomy Review Report generated: %s (%d items)", excel_path.name, len(self.review_items))
                except Exception as exc:
                    logger.warning("Failed to export taxonomy review report: %s", exc)

            if not self.dry_run:
                self.comparing_engine.save_ledger()

            if not self.dry_run and run_id:
                self.supabase_store.complete_ingestion_run(run_id, summary, status="COMPLETED")

            logger.info("==========================================================================")
            logger.info("   REAL-TIME END-TO-END INGESTION COMPLETED SUCCESSFULLY")
            logger.info("==========================================================================")
            return summary

    # -----------------------------------------------------------------------
    # Incremental Sync Execution (Batch Checkpoints & Comparing Engine)
    # -----------------------------------------------------------------------

    async def run_incremental_sync(
        self,
        domain_filter: Optional[str] = None,
        limit: Optional[int] = None,
        force: bool = False,
        detect_deletions: bool = False,
        batch_size: int = DOCUMENT_BATCH_SIZE,
        fresh_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs incremental sync by comparing live xAPI metadata against the Supabase Bucket Ledger.
        Processes documents batch-by-batch, saving dedicated batch checkpoints with zero duplication.
        """
        logger.info("==========================================================================")
        logger.info("   STARTING INCREMENTAL xAPI SYNC (BATCH CHECKPOINTS & COMPARING ENGINE)")
        logger.info(
            "   Scope: CLIENT MAPPED DOMAINS | Filter: %s | Force: %s | Batch Size: %s",
            domain_filter or "ALL MAPPED",
            force,
            batch_size,
        )
        logger.info("==========================================================================")

        if fresh_run:
            self.batch_checkpoint_manager.reset_checkpoints()

        run_id = None
        if not self.dry_run:
            run_id = self.supabase_store.create_ingestion_run(run_type="INCREMENTAL_LEDGER_SYNC")

        all_milvus_chunks: List[EnrichedMilvusChunk] = []
        all_normalized_sections: List[NormalizedLegalSection] = []

        async with XAPICollector() as client:
            # 1. Non-blocking Target Rettsområder Catalog Sync
            try:
                raw_areas, _, _ = await client.get_areas()
                if not self.dry_run:
                    self.supabase_store.upsert_rettsomrade_catalog(raw_areas)
            except Exception as exc:
                logger.warning("Optional live xAPI catalog sync skipped/failed: %s", exc)

            target_areas = await self.resolve_target_areas(domain_filter, client=client)

            # 2. Discover live Laws & Central Regulations
            discovered_laws: List[Dict[str, Any]] = []
            area_law_counts: Dict[str, int] = {}
            for area in target_areas:
                if not area:
                    continue
                try:
                    laws, _, _ = await client.get_laws_by_area(area)
                    area_law_counts[area] = len(laws)
                    for law in laws:
                        law["rettsomrade_filter"] = area
                        candidate_domains = self.get_candidate_domains_for_area(area)
                        law["candidate_domain_ids"] = candidate_domains
                        law["primary_domain_id"] = candidate_domains[0] if candidate_domains else None
                        law["document_type"] = "LAW"
                        law["canonical_document_id"] = law.get("dok_id")
                        law["title"] = law.get("tittel") or law.get("title") or "Uten tittel"
                        law["short_title"] = law.get("korttittel") or law.get("short_title") or law["title"]
                        law["department"] = law.get("departement") or law.get("department")
                        law["source_type"] = law.get("kilde_type") or law.get("source_type") or "lov"
                        law["paragraph_count"] = law.get("antall_paragrafer") or law.get("paragraph_count") or 0
                    discovered_laws.extend(laws)
                except Exception as exc:
                    logger.warning("Error fetching laws for area '%s': %s", area, exc)

            unique_discovered_laws = self.deduplicator.deduplicate_laws(discovered_laws)

            # Central Regulations
            central_regs: List[Dict[str, Any]] = []
            area_reg_counts: Dict[str, int] = {a: 0 for a in target_areas}
            try:
                central_regs, _, _ = await client.get_central_regulations_for_domain(target_areas)
                for reg in central_regs:
                    reg["document_type"] = "REGULATION"
                    reg["canonical_document_id"] = regulation_canonical_id(reg)
                    candidate_domains = list({
                        d for area in reg.get("rettsomrade", [])
                        for d in self.get_candidate_domains_for_area(area) if d
                    })
                    reg["candidate_domain_ids"] = candidate_domains
                    reg["primary_domain_id"] = candidate_domains[0] if candidate_domains else None
                    reg["title"] = reg.get("tittel") or reg.get("title") or "Uten tittel"
                    reg["short_title"] = reg.get("korttittel") or reg.get("short_title") or reg["title"]
                    reg["department"] = reg.get("departement") or reg.get("department")
                    reg["source_type"] = reg.get("kilde_type") or reg.get("source_type") or "forskrift"

                    for a in (reg.get("rettsomrade") or []):
                        if a in area_reg_counts:
                            area_reg_counts[a] += 1
            except Exception as exc:
                logger.warning("Error fetching central regulations: %s", exc)

            if not self.dry_run:
                catalog_updates = [
                    {
                        "rettsomrade": a,
                        "law_count": area_law_counts.get(a, 0),
                        "regulation_count": area_reg_counts.get(a, 0),
                        "seen_in_laws": area_law_counts.get(a, 0) > 0,
                        "seen_in_regulations": area_reg_counts.get(a, 0) > 0,
                    }
                    for a in target_areas
                ]
                if catalog_updates:
                    self.supabase_store.upsert_rettsomrade_catalog(catalog_updates)

            # Law-Linked Regulations
            linked_regs: List[Dict[str, Any]] = []
            laws_for_linked = unique_discovered_laws[:max(3, limit)] if limit else unique_discovered_laws
            for law in laws_for_linked:
                dok_id = law.get("dok_id")
                if not dok_id:
                    continue
                try:
                    l_regs, _, _ = await client.get_regulations_for_law(dok_id)
                    for r in l_regs:
                        r["linked_from_law_dok_id"] = dok_id
                        r["candidate_domain_ids"] = law.get("candidate_domain_ids", [])
                        r["primary_domain_id"] = law.get("primary_domain_id")
                        r["document_type"] = "REGULATION"
                        r["canonical_document_id"] = regulation_canonical_id(r)
                        r["title"] = r.get("tittel") or r.get("title") or "Uten tittel"
                        r["short_title"] = r.get("korttittel") or r.get("short_title") or r["title"]
                        r["department"] = r.get("departement") or r.get("department")
                        r["source_type"] = r.get("kilde_type") or r.get("source_type") or "forskrift"
                    linked_regs.extend(l_regs)
                except Exception as exc:
                    logger.debug("Law-linked regulation fetch for %s: %s", dok_id, exc)

            unique_discovered_regs = self.deduplicator.deduplicate_regulations(central_regs, linked_regs)
            all_discovered = unique_discovered_laws + unique_discovered_regs

            logger.info(
                "Discovery complete: %d unique laws + %d unique regulations = %d total documents",
                len(unique_discovered_laws),
                len(unique_discovered_regs),
                len(all_discovered),
            )

            # 3. Comparing Engine Check against Supabase Bucket Ledger
            self.comparing_engine.load_ledger(force_refresh=True)
            comparison = self.comparing_engine.compare(all_discovered, detect_deletions=detect_deletions)
            summary_comp = comparison.get_summary()

            logger.info("Comparison Result: %s", summary_comp)

            if not force and not comparison.has_changes:
                logger.info("✅ Supabase Bucket Ledger is 100%% up to date with xAPI. No re-ingestion needed.")
                if not self.dry_run and run_id:
                    self.supabase_store.complete_ingestion_run(run_id, summary_comp, status="NO_CHANGES")
                return summary_comp

            # Target Documents
            if force:
                target_docs = all_discovered
            else:
                target_docs = comparison.new_docs + comparison.modified_docs

            if limit and limit >= 3:
                laws = [d for d in target_docs if d.get("document_type") == "LAW"]
                cents = [d for d in target_docs if d.get("document_type") == "REGULATION" and not d.get("linked_from_law_dok_id")]
                links = [d for d in target_docs if d.get("document_type") == "REGULATION" and d.get("linked_from_law_dok_id")]
                selected = []
                if laws:
                    selected.append(laws[0])
                if cents:
                    selected.append(cents[0])
                if links:
                    selected.append(links[0])
                remaining = [d for d in target_docs if d not in selected]
                target_docs = (selected + remaining)[:limit]
            elif limit:
                target_docs = target_docs[:limit]

            # 3.5 URL Validation & Quarantine Gate
            if settings.url_validation_enabled:
                logger.info("Running URL Validation & Quarantine Gate for %d documents...", len(target_docs))
                validator = LovdataURLValidator(max_workers=settings.url_validation_concurrency)
                audit_records = validator.audit_documents(target_docs)
                excel_path, json_path = validator.export_reports(
                    records=audit_records,
                    output_dir=REPORTS_DIR,
                    file_basename="Document_url_analysis_sync_run",
                )
                valid_ids = {r.xapi_id for r in audit_records if r.overall_working or r.lovdata_status == 200}
                quarantined_docs = [d for d in target_docs if str(d.get("canonical_document_id") or d.get("dok_id") or d.get("id")) not in valid_ids]
                target_docs = [d for d in target_docs if str(d.get("canonical_document_id") or d.get("dok_id") or d.get("id")) in valid_ids]
                logger.info(
                    "URL Gate: %d passed (200 OK), %d quarantined (404/Err). Reports saved to %s",
                    len(target_docs), len(quarantined_docs), excel_path
                )

            # 4. Partition Target Docs into Distinct Batches
            doc_batches = self.batch_checkpoint_manager.partition_into_batches(target_docs, batch_size=batch_size)
            total_batches = len(doc_batches)
            logger.info("Partitioned %d target documents into %d batches (Batch size: %d)", len(target_docs), total_batches, batch_size)

            total_stored_milvus_count = 0

            # 5. Process Batch-by-Batch
            for batch_idx, current_batch_docs in enumerate(doc_batches, start=1):
                if not force and not fresh_run and self.batch_checkpoint_manager.is_batch_committed(batch_idx):
                    logger.info("[Batch %02d/%02d] Already COMMITTED. Skipping to prevent duplicate work.", batch_idx, total_batches)
                    continue

                unprocessed_docs = self.batch_checkpoint_manager.filter_unprocessed_documents(current_batch_docs)
                if not unprocessed_docs:
                    logger.info("[Batch %02d/%02d] All documents in batch already committed. Skipping.", batch_idx, total_batches)
                    continue

                logger.info("=== Executing Batch %02d/%02d (%d documents) ===", batch_idx, total_batches, len(unprocessed_docs))

                batch_chunks_count = 0
                batch_milvus_count = 0
                batch_processed_docs = []

                for doc_idx, doc in enumerate(unprocessed_docs, start=1):
                    doc_type = doc.get("document_type", "LAW")
                    canon_id = doc.get("canonical_document_id") or doc.get("dok_id") or ""
                    xapi_id = doc.get("id") or doc.get("xapi_id") or ""
                    title = doc.get("title") or doc.get("tittel") or doc.get("short_title") or "Uten tittel"
                    doc["title"] = title
                    doc["canonical_document_id"] = canon_id
                    doc["primary_domain_id"] = doc.get("candidate_domain_ids", [])[0] if doc.get("candidate_domain_ids") else None
                    doc["source_doc_url"] = doc.get("lovdata_url") or doc.get("source_doc_url") or (f"{LOVDATA_BASE_URL}/{canon_id}" if canon_id else "")

                    # Purge existing vectors for this document in Milvus before re-indexing
                    if not self.dry_run:
                        self.milvus_store.delete_chunks_by_document_id(canon_id)

                    if doc_type == "LAW":
                        norm_sections, doc_chunks = await self._process_law_document(doc, client)
                    else:
                        norm_sections, doc_chunks = await self._process_regulation_document(doc)

                    all_normalized_sections.extend(norm_sections)
                    all_milvus_chunks.extend(doc_chunks)
                    batch_chunks_count += len(doc_chunks)
                    rdb_records = [s.to_rdb_dict() for s in norm_sections]

                    # RDB Upsert
                    if not self.dry_run:
                        self.supabase_store.upsert_legal_documents([doc])
                        if rdb_records:
                            self.supabase_store.upsert_legal_sections(rdb_records)
                        if doc_type == "REGULATION":
                            parent_law_id = doc.get("linked_from_law_dok_id") or doc.get("parent_law_canonical_id")
                            if parent_law_id:
                                self.supabase_store.upsert_law_regulation_maps([{
                                    "law_dok_id": parent_law_id,
                                    "regulation_dok_id": canon_id,
                                    "relationship_type": "DELEGATED_REGULATION",
                                }])

                    # Embed & Store Vectors for this document
                    if not self.dry_run and doc_chunks:
                        indexed = self.embed_and_index_chunks(doc_chunks, batch_size=EMBEDDING_BATCH_SIZE)
                        batch_milvus_count += indexed
                        total_stored_milvus_count += indexed

                    # Update in-memory Ledger entry
                    self.comparing_engine.update_document_entry(
                        doc_id=canon_id,
                        document_metadata=doc,
                        vdb_status="SYNCED" if not self.dry_run else "DRY_RUN",
                    )
                    batch_processed_docs.append(doc)

                    # Supabase Ingestion Run Item tracking
                    if not self.dry_run and run_id:
                        rett_str = doc.get("rettsomrade_filter") or (
                            doc.get("rettsomrade") if isinstance(doc.get("rettsomrade"), str)
                            else (",".join(doc.get("rettsomrade", [])) if isinstance(doc.get("rettsomrade"), list) else "")
                        )
                        self.supabase_store.record_run_items([{
                            "ingestion_run_id": run_id,
                            "stage": "STAGE_3_INDEXING",
                            "endpoint": f"/v1/lovdata/lover/{xapi_id}" if doc_type == "LAW" else "/v1/lovdata/forskrifter",
                            "entity_type": doc_type,
                            "source_identifier": canon_id,
                            "domain_id": doc.get("primary_domain_id"),
                            "rettsomrade": str(rett_str)[:255] if rett_str else None,
                            "offset": 0,
                            "limit": 1,
                            "status": "SUCCESS",
                            "attempt_count": 1,
                            "http_status": 200,
                            "raw_response_path": doc.get("content_storage_path"),
                            "response_hash": doc.get("fil_md5") or doc.get("source_md5"),
                            "started_at": datetime.now(timezone.utc).isoformat(),
                            "completed_at": datetime.now(timezone.utc).isoformat(),
                        }])

                    print(f"  [Batch {batch_idx:02d}/{total_batches:02d} | Doc {doc_idx:03d}/{len(unprocessed_docs):03d}] Ingested {doc_type} {canon_id} | Chunks: {len(doc_chunks)} | Milvus [OK]")

                # Commit batch checkpoint, persist ledger & append to master Excel report
                if not self.dry_run:
                    self.batch_checkpoint_manager.commit_batch(
                        batch_index=batch_idx,
                        total_batches=total_batches,
                        documents=batch_processed_docs,
                        metrics={
                            "chunks_created": batch_chunks_count,
                            "milvus_vectors_indexed": batch_milvus_count,
                        },
                    )
                    self.comparing_engine.save_ledger()

                    # Batch-wise append to master Excel report
                    if self.review_items:
                        try:
                            self.review_exporter.append_batch_items(self.review_items, batch_index=batch_idx)
                        except Exception as exc:
                            logger.warning("Batch %d Excel append failed: %s", batch_idx, exc)

                # Explicit memory cleanup for multi-day continuous ingestion runs
                import gc
                gc.collect()

            # 6. Handle Deletions
            if comparison.deleted_doc_ids:
                for del_id in comparison.deleted_doc_ids:
                    if not self.dry_run:
                        self.milvus_store.delete_chunks_by_document_id(del_id)
                    self.comparing_engine.remove_document_entry(del_id)
                logger.info("Purged %d deleted documents from Milvus & Ledger", len(comparison.deleted_doc_ids))

            # 7. Save Updated Ledger JSON
            if not self.dry_run:
                self.comparing_engine.save_ledger()

            summary = {
                "target_docs_processed": len(target_docs),
                "total_batches": total_batches,
                "documents_discovered": len(all_discovered),
                "documents_created": summary_comp.get("new_count", 0),
                "documents_updated": summary_comp.get("modified_count", 0),
                "documents_skipped": summary_comp.get("unchanged_count", 0),
                "sections_processed": len(all_normalized_sections),
                "milvus_chunks_indexed": total_stored_milvus_count,
                "comparison_summary": summary_comp,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if self.review_items:
                try:
                    excel_path, json_path = self.review_exporter.export_excel_report(self.review_items)
                    summary["review_report_excel"] = str(excel_path)
                    summary["review_items_count"] = len(self.review_items)
                    logger.info("Taxonomy Review Report generated: %s (%d items)", excel_path.name, len(self.review_items))
                except Exception as exc:
                    logger.warning("Failed to export taxonomy review report: %s", exc)

            if not self.dry_run and run_id:
                self.supabase_store.complete_ingestion_run(run_id, summary, status="COMPLETED")

            logger.info("=== Incremental Ingestion Run Completed Successfully (All Batches Checkpointed) ===")
            return summary


# ---------------------------------------------------------------------------
# Compatibility Aliases & CLI Entrypoint
# ---------------------------------------------------------------------------

def run_pipeline(*args, **kwargs) -> Dict[str, Any]:
    """Compatibility alias to run the RealTimePipelineRunner."""
    runner = RealTimePipelineRunner()
    return asyncio.run(runner.run(*args, **kwargs))


def run_incremental(*args, **kwargs) -> Dict[str, Any]:
    """Compatibility alias to run incremental sync."""
    runner = RealTimePipelineRunner()
    return asyncio.run(runner.run_incremental_sync(*args, **kwargs))


def main() -> None:
    parser = argparse.ArgumentParser(description="DigiRett Real-Time End-to-End xAPI Pipeline (Client Mapped Domains)")
    parser.add_argument("--verify-only", action="store_true", help="Verify settings, DB, and API connectivity without running pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Run collection and normalization without DB writes")
    parser.add_argument("--incremental", action="store_true", default=True, help="Run incremental sync comparing live xAPI against Supabase Bucket Ledger (default)")
    parser.add_argument("--full-sync", action="store_true", help="Run full pipeline collection without incremental ledger filtering")
    parser.add_argument("--force", action="store_true", help="Force re-ingestion of all documents even if unchanged in ledger")
    parser.add_argument("--batch-size", type=int, default=DOCUMENT_BATCH_SIZE, help=f"Document batch size for dedicated batch checkpoints (default: {DOCUMENT_BATCH_SIZE})")
    parser.add_argument("--fresh-run", action="store_true", help="Reset all previous batch checkpoints and start fresh")
    parser.add_argument("--domain", type=str, help="Restrict pipeline to a specific domain (e.g. D12_EMPLOYMENT)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of laws and regulations to process (e.g. 10)")
    parser.add_argument("--rebuild-ledger", action="store_true", help="Rebuild Supabase Storage bucket ledger directly from PostgreSQL legal_documents table")
    parser.add_argument("--purge-unmapped-subdomains", action="store_true", help="Purge any vector chunks from Milvus where subdomain is NO_SUBDOMAIN")
    parser.add_argument("--export-review-report", action="store_true", help="Export unmapped / no-subdomain / review-required sections from database to Excel")
    parser.add_argument("--seed-taxonomies", action="store_true", help="Explicitly seed taxonomy definitions, rettsområde catalog, and mappings to Supabase")
    args = parser.parse_args()

    runner = RealTimePipelineRunner(dry_run=args.dry_run)

    if args.verify_only:
        success = asyncio.run(runner.verify_environment())
        sys.exit(0 if success else 1)

    if getattr(args, "seed_taxonomies", False):
        logger.info("Explicitly seeding taxonomies and catalogs to Supabase...")
        runner.supabase_store._ensure_connection()
        runner.supabase_store.seed_taxonomy_and_catalogs()
        print(json.dumps({"status": "SUCCESS", "message": "Taxonomies and catalogs seeded successfully"}, indent=2))
        sys.exit(0)

    if getattr(args, "export_review_report", False):
        logger.info("Exporting unmapped / review-required sections from database to Excel...")
        excel_path, json_path = TaxonomyReviewExporter.export_from_supabase_db(runner.supabase_store)
        print(json.dumps({
            "status": "SUCCESS",
            "excel_report": str(excel_path),
            "json_report": str(json_path),
        }, indent=2))
        sys.exit(0)

    if getattr(args, "purge_unmapped_subdomains", False):
        logger.info("Purging NO_SUBDOMAIN chunks from Milvus collection...")
        success = runner.milvus_store.purge_unmapped_subdomain_chunks()
        print(json.dumps({"status": "SUCCESS" if success else "FAILED", "purged": success}, indent=2))
        sys.exit(0 if success else 1)

    if getattr(args, "rebuild_ledger", False):
        logger.info("Rebuilding Supabase Bucket Ledger from legal_documents database table...")
        ledger_obj = runner.comparing_engine.rebuild_ledger_from_db()
        print(json.dumps({
            "status": "SUCCESS",
            "total_documents": ledger_obj.get("total_documents", 0),
            "last_synced_at": ledger_obj.get("last_synced_at"),
            "ledger_version": ledger_obj.get("ledger_version"),
        }, indent=2))
        sys.exit(0)

    try:
        if not args.full_sync:  # Incremental sync is the default resilient execution model
            summary = asyncio.run(runner.run_incremental_sync(
                domain_filter=args.domain,
                limit=args.limit,
                force=args.force,
                batch_size=args.batch_size,
                fresh_run=args.fresh_run,
            ))
        else:
            summary = asyncio.run(runner.run(
                domain_filter=args.domain,
                limit=args.limit,
            ))
        print(json.dumps(summary, indent=2))
    except Exception as exc:
        logger.error("Real-Time Pipeline Failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()