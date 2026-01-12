#!/bin/bash

# Milvus Deployment Script
# This script deploys Milvus using Docker Compose

set -e

echo "🚀 Starting Milvus deployment..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Load environment variables
if [ -f .env ]; then
    echo "📝 Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  No .env file found. Using default values."
fi

# Create necessary directories
echo "📁 Creating data directories..."
mkdir -p data/etcd
mkdir -p data/minio
mkdir -p data/milvus

# Pull latest images
echo "📥 Pulling Docker images..."
docker-compose pull || docker compose pull

# Stop existing containers if running
echo "🛑 Stopping existing containers..."
docker-compose down || docker compose down

# Start Milvus services
echo "▶️  Starting Milvus services..."
docker-compose up -d || docker compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo "🏥 Checking service health..."
max_attempts=30
attempt=0

while [ $attempt -lt $max_attempts ]; do
    if docker-compose ps | grep -q "milvus-standalone.*Up" || docker compose ps | grep -q "milvus-standalone.*Up"; then
        if curl -f http://localhost:9091/healthz &> /dev/null; then
            echo "✅ Milvus is healthy and ready!"
            break
        fi
    fi
    attempt=$((attempt + 1))
    echo "   Attempt $attempt/$max_attempts..."
    sleep 5
done

if [ $attempt -eq $max_attempts ]; then
    echo "❌ Milvus failed to start properly. Check logs with: docker-compose logs"
    exit 1
fi

# Display connection information
MILVUS_PORT=${MILVUS_PORT:-19530}
echo ""
echo "✅ Milvus deployment completed successfully!"
echo ""
echo "📊 Connection Information:"
echo "   Host: localhost (or your instance public IP)"
echo "   Port: $MILVUS_PORT"
echo "   Health Check: http://localhost:9091/healthz"
echo ""
echo "🔍 View logs: docker-compose logs -f"
echo "🛑 Stop services: docker-compose down"
echo ""
