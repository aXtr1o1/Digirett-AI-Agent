import logging

from ingestion.src.storage.milvus_store import MilvusTextStore
from ingestion.src.storage.supabase_store import SupabaseStore

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("supabase").setLevel(logging.ERROR)


# --------------------------------------------------
# MILVUS STATS
# --------------------------------------------------
def get_milvus_stats():
    milvus = MilvusTextStore()
    milvus._ensure_connection()

    collection = milvus.collection

    # ✅ FAST COUNT (NO QUERY)
    total_chunks = collection.num_entities

    # --------------------------------------------------
    # Get UNIQUE file names safely (batched)
    # --------------------------------------------------
    file_names = set()

    batch_size = 1000
    last_id = 0

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

    return total_chunks, len(file_names)


# --------------------------------------------------
# SUPABASE STATS
# --------------------------------------------------
def get_supabase_stats():
    db_store = SupabaseStore()
    file_names = db_store.get_all_file_names()
    return len(file_names)


# --------------------------------------------------
# MAIN CHECK
# --------------------------------------------------
def check_storage_status():

    print("\n===================================")
    print(" MILVUS vs SUPABASE STORAGE STATUS")
    print("===================================")

    total_chunks, total_milvus_files = get_milvus_stats()
    total_supabase_files = get_supabase_stats()

    print(f"\nMilvus total chunks : {total_chunks}")
    print(f"Milvus total files  : {total_milvus_files}")
    print(f"Supabase metadata   : {total_supabase_files}")

    if total_milvus_files == total_supabase_files:
        print("\n✅ STORAGE CONSISTENT")
    else:
        print("\n❌ STORAGE NOT CONSISTENT")


if __name__ == "__main__":
    check_storage_status()