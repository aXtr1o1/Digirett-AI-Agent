import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymilvus import connections, utility
from ingestion.src.config import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION

if "--confirm" not in sys.argv:
    response = input(f"DANGER: Are you sure you want to drop collection '{MILVUS_COLLECTION}' on {MILVUS_HOST}:{MILVUS_PORT}? (type 'yes' to confirm): ")
    if response.strip().lower() != "yes":
        print("Operation cancelled. Collection was not deleted.")
        sys.exit(0)

connections.connect(
    alias="default",
    host=MILVUS_HOST,
    port=MILVUS_PORT,
)

if utility.has_collection(MILVUS_COLLECTION):
    utility.drop_collection(MILVUS_COLLECTION)
    print(f"Collection '{MILVUS_COLLECTION}' deleted successfully")
else:
    print(f"Collection '{MILVUS_COLLECTION}' does not exist")

connections.disconnect("default")
