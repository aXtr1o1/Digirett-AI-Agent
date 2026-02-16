from pymilvus import connections, utility

# -----------------------------------
# Milvus connection details
# -----------------------------------
MILVUS_HOST = "13.204.226.35"
MILVUS_PORT = "19530"

COLLECTION_NAME = "lovdata_hierarchical_aoai_v1"

# -----------------------------------
# Connect to Milvus
# -----------------------------------
connections.connect(
    alias="default",
    host=MILVUS_HOST,
    port=MILVUS_PORT,
)

print(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")

# -----------------------------------
# Drop collection
# -----------------------------------
if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)
    print(f"✅ Collection '{COLLECTION_NAME}' dropped successfully.")
else:
    print(f"⚠️ Collection '{COLLECTION_NAME}' does not exist.")

# -----------------------------------
# Disconnect
# -----------------------------------
connections.disconnect("default")
print("Disconnected from Milvus.")