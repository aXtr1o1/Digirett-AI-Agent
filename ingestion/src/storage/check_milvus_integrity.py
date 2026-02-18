from pymilvus import connections, Collection
from supabase import create_client
from dotenv import load_dotenv
import os
from pymilvus import utility

load_dotenv()


# -------------------------------
# CONFIG
# -------------------------------
MILVUS_HOST = "localhost"
MILVUS_PORT = "19530"
COLLECTION_NAME = "lovdata_hierarchical_aoai_v1"

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


# -------------------------------
# Connect Milvus
# -------------------------------
print("Connecting to Milvus...")
connections.connect(
    alias="default",
    host=MILVUS_HOST,
    port=MILVUS_PORT
)

if not utility.has_collection(COLLECTION_NAME):
    print(f"⚠️ Collection '{COLLECTION_NAME}' does not exist yet.")
    milvus_count = 0
else:
    collection = Collection(COLLECTION_NAME)
    collection.load()
    milvus_count = collection.num_entities
print(f"✅ Milvus vectors count: {milvus_count}")


# -------------------------------
# Connect Supabase
# -------------------------------
print("Connecting to Supabase...")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.table("lovdata_metadata") \
    .select("id", count="exact") \
    .execute()

file_count = response.count

print(f"✅ Supabase completed files: {file_count}")


# -------------------------------
# RESULT
# -------------------------------
print("\n========== INTEGRITY CHECK ==========")

if milvus_count == 0:
    print("❌ No vectors found in Milvus!")
else:
    avg_chunks = milvus_count / file_count if file_count else 0
    print(f"Average chunks per file: {avg_chunks:.2f}")

print("=====================================")