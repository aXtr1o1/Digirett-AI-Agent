
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class LegalBlock:
    """Represents a structural block within a legal section (ledd, list item, heading, text)."""
    block_type: str        
    text: str             
    prefix: Optional[str] = None  
    order: int = 0        


@dataclass(slots=True)
class NormalizedLegalSection:
    """Canonical data contract bridging law and regulation adapters to downstream processing."""
    legal_document_id: str
    canonical_document_id: str
    document_type: str                     # "LAW" | "REGULATION"
    document_title: str
    section_type: str                      # "LAW_PARAGRAPH" | "REGULATION_PROVISION"
    source_section_key: str                # e.g. "NL/lov/2005-06-17-62/§15-7" or "SF/forskrift/.../§3-11"
    section_number: str                    # e.g. "§ 15-7"
    section_title: Optional[str] = None    # Provision heading / caption
    chapter_number: Optional[str] = None   # e.g. "Kapittel 15"
    chapter_title: Optional[str] = None    # e.g. "Opphør av arbeidsforhold"
    raw_html: str = ""                     # Original provision HTML (innhold_html or legalArticle)
    source_text: str = ""                  # Faithful normalized text without semantic markup
    structured_blocks: List[LegalBlock] = field(default_factory=list)
    source_url: Optional[str] = None       # Lovdata citation URL
    candidate_domain_ids: List[str] = field(default_factory=list)
    is_active: bool = True                 # True if currently in force
    is_repealed: bool = False              # True if marked repealed (opphevet == 1)
    taxonomy_version: str = "1.0.1"
    subdomain_ids: List[str] = field(default_factory=list)
    subdomain_names: List[str] = field(default_factory=list)
    primary_subdomain_id: Optional[str] = None
    jurisdictions: List[str] = field(default_factory=list)
    b2b_b2c_types: List[str] = field(default_factory=list)
    relationship_types: List[str] = field(default_factory=list)
    tier: Optional[int] = None
    source_content_hash: str = ""
    version_date: str = ""

    def __post_init__(self):
        if not self.source_content_hash and self.source_text:
            self.source_content_hash = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()[:16]

    @property
    def is_processable(self) -> bool:
        """Determines if the section should proceed to chunking and vector storage."""
        return bool(
            self.is_active
            and not self.is_repealed
            and bool(self.source_text.strip())
            and bool(self.structured_blocks)
        )

    def to_rdb_dict(self) -> Dict[str, Any]:
        """Formats the section for Supabase PostgreSQL legal_sections table."""
        return {
            "section_id": self.source_section_key.replace("/", "-"),
            "record_type": self.section_type,
            "canonical_document_id": self.canonical_document_id,
            "legal_document_id": self.legal_document_id,
            "source_section_key": self.source_section_key,
            "section_number": self.section_number,
            "heading": self.section_title or self.section_number,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "text": self.source_text,
            "raw_html": self.raw_html,
            "candidate_domain_ids": self.candidate_domain_ids,
            "primary_domain_id": self.candidate_domain_ids[0] if self.candidate_domain_ids else None,
            "subdomain_ids": self.subdomain_ids,
            "subdomain_names": self.subdomain_names,
            "primary_subdomain_id": self.primary_subdomain_id or (self.subdomain_ids[0] if self.subdomain_ids else None),
            "jurisdictions": self.jurisdictions,
            "b2b_b2c_types": self.b2b_b2c_types,
            "relationship_types": self.relationship_types,
            "tier": self.tier,
            "is_active": self.is_active,
            "is_repealed": self.is_repealed,
            "vdb_eligible": self.is_processable and bool(self.candidate_domain_ids) and bool(self.subdomain_ids or self.primary_subdomain_id),
            "vdb_status": "SYNCED" if (self.is_processable and bool(self.candidate_domain_ids) and bool(self.subdomain_ids or self.primary_subdomain_id)) else "NOT_ELIGIBLE",
            "source_url": self.source_url or "",
            "source_section_url": self.source_url or "",
            "content_file_hash": self.source_content_hash,
            "content_hash": self.source_content_hash,
            "version_date": self.version_date,
            "taxonomy_version": self.taxonomy_version,
        }


@dataclass(slots=True)
class StructuralChunk:
    """Intermediate chunk emitted by LegalSectionChunker before taxonomy classification."""
    source_section_key: str
    chunk_index: int
    source_text: str
    token_count: int
    source_block_start: int
    source_block_end: int
    is_definition: bool
    cross_refs: List[str]
    section_ref: str


@dataclass(slots=True)
class SectionClassification:
    """Taxonomy routing result for a chunk with rich client constraints."""
    domain_id: str
    domain_name: str
    subdomain_id: Optional[str] = None
    subdomain_name: Optional[str] = None
    subdomain_ids: List[str] = field(default_factory=list)
    subdomain_names: List[str] = field(default_factory=list)
    jurisdiction: List[str] = field(default_factory=lambda: ["NO"])
    b2b_b2c: List[str] = field(default_factory=lambda: ["BOTH"])
    relationship_type: List[str] = field(default_factory=lambda: ["employment"])
    tier: int = 1
    taxonomy_version: str = "1.0.1"
    confidence: float = 1.0
    vdb_eligible: bool = True


@dataclass(slots=True)
class EnrichedMilvusChunk:
    """Final materialized entity ready for Milvus embedding and vector insertion."""
    chunk_id: str
    embedding_text: str
    source_text: str
    domain_id: str
    domain_name: str
    subdomain_id: str
    subdomain_name: str
    canonical_document_id: str
    legal_section_id: str
    source_section_key: str
    document_type: str
    doc_title: str
    section_number: str
    section_title: str
    citation_anchor: str
    source_url: str
    token_count: int
    chunk_index: int
    content_hash: str
    subdomain_ids: List[str] = field(default_factory=list)
    subdomain_names: List[str] = field(default_factory=list)
    jurisdictions: List[str] = field(default_factory=lambda: ["NO"])
    b2b_b2c_types: List[str] = field(default_factory=lambda: ["BOTH"])
    relationship_types: List[str] = field(default_factory=lambda: ["employment"])
    parent_law_canonical_id: str = ""
    parent_law_title: str = ""
    source_type: str = "lov"
    tier: int = 1
    language: str = "no"
    version_date: str = ""
    taxonomy_version: str = "1.0.1"
    metadata: Dict[str, Any] = field(default_factory=dict)
