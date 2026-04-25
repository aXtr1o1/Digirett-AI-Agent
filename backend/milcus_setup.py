from pymilvus import connections, Collection

# Connect to Milvus
connections.connect(alias="default", host="20.86.37.141", port="19530")

collection = Collection("classified_data")

# List all field names
fields = [field.name for field in collection.schema.fields]

print(fields)