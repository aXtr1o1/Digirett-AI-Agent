# This Dockerfile is for building a custom Milvus image if needed
# For standard deployments, use the official Milvus image from docker-compose.yml

FROM milvusdb/milvus:v2.3.3

# Add any custom configurations or scripts here
# COPY configs/ /milvus/configs/

# Expose ports
EXPOSE 19530 9091

# Use the default Milvus entrypoint
ENTRYPOINT ["milvus", "run", "standalone"]
