import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pymilvus import connections, utility, Collection
from ingestion.src.config import MILVUS_HOST, MILVUS_PORT, MILVUS_COLLECTION

connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

print(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")
print("Collections and row counts:")
for name in utility.list_collections():
    c = Collection(name)
    print(f"  {name:<30} rows={c.num_entities}")

target_collection = MILVUS_COLLECTION
print(f"\nDetail for {target_collection}:")
if utility.has_collection(target_collection):
    c = Collection(target_collection)
    c.load()
    print(f"  total rows: {c.num_entities}")

    if c.num_entities > 0:
        res = c.query(
            expr='chunk_id != ""',
            output_fields=["chunk_id", "domain_name", "doc_title", "section_number"],
            limit=10,
        )
        print(f"  Sample records ({len(res)}):")
        for r in res:
            print(f"    chunk_id={r.get('chunk_id')} | title={r.get('doc_title', '')[:30]} | sec={r.get('section_number')} | domain={r.get('domain_name')}")
else:
    print(f"  Collection '{target_collection}' does not exist in Milvus.")

connections.disconnect("default")
