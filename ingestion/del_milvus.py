from pymilvus import connections, utility

MILVUS_HOST = "20.86.37.141"
MILVUS_PORT = "19530"
COLLECTION_NAME = "demo_data"

connections.connect(
    alias="default",
    host=MILVUS_HOST,
    port=MILVUS_PORT,
)

if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}' deleted successfully")
else:
    print(f"Collection '{COLLECTION_NAME}' does not exist")

connections.disconnect("default")
