#!/bin/bash

# Milvus Stop Script
# This script stops Milvus services gracefully

set -e

echo "🛑 Stopping Milvus services..."

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed."
    exit 1
fi

# Stop and remove containers
docker-compose down || docker compose down

echo "✅ Milvus services stopped successfully!"
