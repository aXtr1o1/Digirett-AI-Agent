from __future__ import annotations

from typing import Optional
from pymilvus import (
    CollectionSchema,
    DataType,
    FieldSchema,
)

from ingestion.src.config import (
    MILVUS_DIMENSION,
    MILVUS_TEXT_LIMIT,
)

DEFAULT_VECTOR_DIM: int = MILVUS_DIMENSION


def get_collection_schema(vector_dim: Optional[int] = None) -> CollectionSchema:
    """Returns the canonical CollectionSchema for digirett legal chunks configured from environment/config."""
    dim = vector_dim if vector_dim is not None else MILVUS_DIMENSION
    text_limit = MILVUS_TEXT_LIMIT if MILVUS_TEXT_LIMIT else 65535

    fields = [
        FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=128, is_primary=True, description="Deterministic chunk identifier"),
        FieldSchema(name="legal_document_id", dtype=DataType.VARCHAR, max_length=128, description="Parent document identifier"),
        FieldSchema(name="legal_section_id", dtype=DataType.VARCHAR, max_length=128, description="Parent section identifier"),
        FieldSchema(name="canonical_document_id", dtype=DataType.VARCHAR, max_length=255, description="Canonical Lovdata ID"),
        FieldSchema(name="source_section_key", dtype=DataType.VARCHAR, max_length=255, description="Section anchor key"),
        FieldSchema(name="chunk_index", dtype=DataType.INT64, description="0-indexed chunk order"),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim, description="Vector embedding"),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=text_limit, description="Embedding chunk text"),
        FieldSchema(name="document_type", dtype=DataType.VARCHAR, max_length=30, description="LAW or REGULATION"),
        FieldSchema(name="doc_title", dtype=DataType.VARCHAR, max_length=512, description="Document title"),
        FieldSchema(name="section_number", dtype=DataType.VARCHAR, max_length=100, description="Section number e.g. § 1-1"),
        FieldSchema(name="section_title", dtype=DataType.VARCHAR, max_length=512, description="Section heading"),
        FieldSchema(name="citation_anchor", dtype=DataType.VARCHAR, max_length=255, description="Citation anchor"),
        FieldSchema(name="source_url", dtype=DataType.VARCHAR, max_length=512, description="Lovdata source URL"),
        FieldSchema(name="domain_id", dtype=DataType.VARCHAR, max_length=64, description="Primary legal domain ID"),
        FieldSchema(name="domain_name", dtype=DataType.VARCHAR, max_length=255, description="Primary legal domain name"),
        FieldSchema(name="subdomain_id", dtype=DataType.VARCHAR, max_length=64, description="Primary subdomain ID"),
        FieldSchema(name="subdomain_name", dtype=DataType.VARCHAR, max_length=255, description="Primary subdomain name"),
        FieldSchema(name="taxonomy_version", dtype=DataType.VARCHAR, max_length=20, description="Taxonomy version"),
        FieldSchema(name="parent_law_canonical_id", dtype=DataType.VARCHAR, max_length=255, description="Parent law dok_id if regulation"),
        FieldSchema(name="parent_law_title", dtype=DataType.VARCHAR, max_length=512, description="Parent law title if regulation"),
        FieldSchema(name="jurisdiction", dtype=DataType.VARCHAR, max_length=100, description="Jurisdictions"),
        FieldSchema(name="b2b_b2c", dtype=DataType.VARCHAR, max_length=20, description="B2B, B2C or BOTH"),
        FieldSchema(name="relationship_type", dtype=DataType.VARCHAR, max_length=50, description="Relationship type"),
        FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=50, description="Source type"),
        FieldSchema(name="tier", dtype=DataType.VARCHAR, max_length=30, description="Classification tier"),
        FieldSchema(name="language", dtype=DataType.VARCHAR, max_length=10, description="Language e.g. no"),
        FieldSchema(name="version_date", dtype=DataType.VARCHAR, max_length=30, description="Version date"),
        FieldSchema(name="content_hash", dtype=DataType.VARCHAR, max_length=64, description="Content SHA-256 hash"),
        FieldSchema(name="is_current", dtype=DataType.BOOL, description="Whether active version"),
        FieldSchema(name="retrieval_enabled", dtype=DataType.BOOL, description="Whether available for vector search"),
    ]
    return CollectionSchema(fields=fields, description="Canonical legal chunk vector index for DigiRett")
