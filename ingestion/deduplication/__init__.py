# Deduplication package

from ingestion.deduplication.deduplicator import (
    CanonicalDeduplicator,
    Deduplicator,
    law_canonical_id,
    regulation_canonical_id,
)

__all__ = [
    "CanonicalDeduplicator",
    "Deduplicator",
    "law_canonical_id",
    "regulation_canonical_id",
]
