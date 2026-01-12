#!/bin/bash

# Milvus Health Check Script
# This script checks the health of Milvus services

set -e

echo "🏥 Checking Milvus health..."

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed."
    exit 1
fi

# Check if containers are running
echo "📊 Container Status:"
docker-compose ps || docker compose ps

echo ""
echo "🔍 Health Checks:"

# Check Milvus health endpoint
if curl -f http://localhost:9091/healthz &> /dev/null; then
    echo "✅ Milvus standalone: Healthy"
else
    echo "❌ Milvus standalone: Unhealthy"
    exit 1
fi

# Check etcd
if docker-compose exec -T etcd etcdctl endpoint health &> /dev/null || \
   docker compose exec -T etcd etcdctl endpoint health &> /dev/null; then
    echo "✅ etcd: Healthy"
else
    echo "⚠️  etcd: Health check failed"
fi

# Check MinIO
if curl -f http://localhost:9000/minio/health/live &> /dev/null; then
    echo "✅ MinIO: Healthy"
else
    echo "⚠️  MinIO: Health check failed"
fi

echo ""
echo "✅ All health checks completed!"
