import logging
from typing import Set
from pymilvus import Collection, connections
from ingestion.src.config import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION

logger = logging.getLogger(__name__)
logging.getLogger("pymilvus").setLevel(logging.ERROR)


def get_milvus_file_names() -> Set[str]:
    """
    Returns unique file names stored in Milvus.
    Uses ID-based pagination (SAFE for large collections).
    """

    connections.connect(
        alias="default",
        host=MILVUS_HOST,
        port=MILVUS_PORT,
    )

    collection = Collection(MILVUS_COLLECTION)
    collection.load()

    batch_size = 1000
    last_id = 0
    file_names = set()

    while True:
        results = collection.query(
            expr=f"id > {last_id}",
            output_fields=["id", "file_name"],
            limit=batch_size
        )

        if not results:
            break

        for r in results:
            file_names.add(r["file_name"])

        last_id = results[-1]["id"]

        if len(results) < batch_size:
            break

    return file_names


def print_milvus_stats():
    files = get_milvus_file_names()

    print("\n==============================")
    print(" MILVUS STORAGE STATISTICS")
    print("==============================")
    print(f"Total files stored  : {len(files)}")
    print("==============================\n")


if __name__ == "__main__":
    print_milvus_stats()