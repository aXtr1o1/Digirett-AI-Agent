#del_milvus.py
from pymilvus import connections, utility

# Connect to your cloud instance
connections.connect(host="13.204.226.35", port="19530")

COLLECTION_NAME = "lovdata_hierarchical_chunks"

if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' deleted successfully.")
else:
    print(f"⚠️ Collection '{COLLECTION_NAME}' not found.")