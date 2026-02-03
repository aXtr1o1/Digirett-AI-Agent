"""
Milvus Hierarchical Visualizer
Shows how Lovdata files are chunked and stored in Milvus
"""

import logging
from collections import defaultdict
from pymilvus import connections, Collection, utility
from ingestion.src.config import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION

# -------------------------------------------------
# Logging
# -------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("milvus-visual")


def visualize_milvus(limit_files: int = 3, preview_chars: int = 120):
    """
    Visualize how documents are stored in Milvus:
    File -> Parent -> Chunks
    """

    logger.info("=" * 80)
    logger.info("🧠 MILVUS COLLECTION INSPECTOR")
    logger.info("=" * 80)
    logger.info(f"Collection: {MILVUS_COLLECTION}")

    # -------------------------------------------------
    # Connect to Milvus
    # -------------------------------------------------
    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT
    )

    if not utility.has_collection(MILVUS_COLLECTION):
        logger.error("❌ Collection does not exist")
        return

    collection = Collection(MILVUS_COLLECTION)
    collection.load()

    logger.info(f"Total chunks stored: {collection.num_entities}")

    # -------------------------------------------------
    # Fetch records (SAFE FIELDS ONLY)
    # -------------------------------------------------
    records = collection.query(
        expr="id >= 0",
        output_fields=[
            "chunk_id",
            "file_name",
            "parent_index",
            "child_index",
            "parent_type",
            "parent_title",
            "text",
            "url",
        ],
        limit=10000
    )

    logger.info(f"Fetched {len(records)} records")

    # -------------------------------------------------
    # Build hierarchy (CRITICAL FIX)
    # -------------------------------------------------
    files = defaultdict(lambda: defaultdict(list))

    for r in records:
        files[r["file_name"]][r["parent_index"]].append(r)

    logger.info(f"Reconstructed {len(files)} files from Milvus")

    # -------------------------------------------------
    # Display hierarchy
    # -------------------------------------------------
    for f_idx, (file_name, parents) in enumerate(files.items(), 1):
        if f_idx > limit_files:
            break

        total_chunks = sum(len(v) for v in parents.values())

        logger.info("\n" + "=" * 80)
        logger.info(f"📄 FILE {f_idx}: {file_name}")
        logger.info(f"   Parents: {len(parents)} | Chunks: {total_chunks}")

        # Show URL once per file (if exists)
        file_url = None
        for p_chunks in parents.values():
            if p_chunks and p_chunks[0].get("url"):
                file_url = p_chunks[0]["url"]
                break

        if file_url:
            logger.info(f"   🔗 URL: {file_url}")

        # Parents
        for parent_idx, chunks in sorted(parents.items()):
            parent = chunks[0]

            logger.info(
                f"\n  🧱 Parent {parent_idx} "
                f"[{parent['parent_type']}] "
                f"{parent['parent_title'][:80]} "
                f"({len(chunks)} chunks)"
            )

            # Children
            for c in sorted(chunks, key=lambda x: x["child_index"]):
                preview = c["text"][:preview_chars].replace("\n", " ")
                logger.info(
                    f"     ├─ Child {c['child_index']} | "
                    f"ChunkID={c['chunk_id'][:8]} | "
                    f"{len(c['text'])} chars"
                )
                logger.info(f"     │  {preview}...")

    connections.disconnect("default")
    logger.info("\n✅ Visualization complete")


if __name__ == "__main__":
    visualize_milvus(limit_files=3)
