from pymilvus import connections, utility, Collection

connections.connect(host="20.86.37.141", port="19530")

print("Collections and row counts:")
for name in utility.list_collections():
    c = Collection(name)
    print(f"  {name:<30} rows={c.num_entities}")

print("\nDetail for demo_data:")
c = Collection("demo_data")
c.load()
print(f"  total rows: {c.num_entities}")

if c.num_entities > 0:
    res = c.query(
        expr='document_id != ""',
        output_fields=["document_id", "section_ref", "domain", "chunk_id"],
        limit=10,
    )
    print(f"  Sample records ({len(res)}):")
    for r in res:
        print(f"    doc_id={r['document_id']}  section={r['section_ref']}  domain={r['domain']}")
else:
    print("  No records found in demo_data.")

connections.disconnect("default")
