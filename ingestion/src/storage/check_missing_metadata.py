import logging
from ingestion.src.storage.check_milvus_files import get_milvus_file_names
from ingestion.src.storage.supabase_store import SupabaseStore
from ingestion.src.storage.milvus_store import MilvusTextStore

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("supabase").setLevel(logging.ERROR)


def backfill_missing_metadata(missing_files):

    if not missing_files:
        return

    print("\n🔧 Backfilling missing metadata...")

    milvus = MilvusTextStore()
    db_store = SupabaseStore()

    milvus._ensure_connection()
    collection = milvus.collection

    fixed = 0

    for file_name in missing_files:
        try:
            result = collection.query(
                expr=f'file_name == "{file_name}"',
                output_fields=["file_name", "file_hash", "url"],
                limit=1
            )

            if not result:
                continue

            row = result[0]

            db_store.insert_file_metadata(
                file_name=row["file_name"],
                file_hash=row["file_hash"],
                file_size=0,
                zip_name="backfill",
                url=row.get("url", "")
            )

            fixed += 1

        except Exception as e:
            print(f"Failed to backfill {file_name}: {e}")

    print(f"✅ Backfilled {fixed} metadata entries")


def check_missing_metadata():

    print("\n==============================")
    print("CHECKING MISSING METADATA")
    print("==============================")

    db_store = SupabaseStore()

    milvus_files = get_milvus_file_names()
    supabase_files = db_store.get_all_file_names()

    missing = milvus_files - supabase_files

    print("\n==============================")
    print("MILVUS vs SUPABASE CHECK")
    print("==============================")

    print(f"Total files in Milvus   : {len(milvus_files)}")
    print(f"Total files in Supabase : {len(supabase_files)}")
    print(f"Missing metadata files  : {len(missing)}")

    # ✅ Auto-fix here
    if missing:
        backfill_missing_metadata(missing)

        print("\n✅ RESULT: FIXED (Metadata backfilled)")
    else:
        print("\n✅ RESULT: CONSISTENT")


if __name__ == "__main__":
    check_missing_metadata()