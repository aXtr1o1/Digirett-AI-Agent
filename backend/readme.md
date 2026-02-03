# ============================================
# README.md
# Project Documentation
# ============================================

# Lovdata RAG System - FastAPI Backend

Production-ready RAG (Retrieval-Augmented Generation) system for Norwegian legal documents.

## 🎯 Features

- ✅ Semantic search over Lovdata legal documents
- ✅ AI-powered question answering with Azure OpenAI
- ✅ Real-time streaming responses
- ✅ Source citations with Lovdata URLs
- ✅ Redis caching for faster responses
- ✅ Rate limiting (250 requests/minute)
- ✅ Comprehensive logging and monitoring
- ✅ Error handling with automatic retries
- ✅ Production-ready architecture

## 📁 Project Structure

```
lovdata-rag/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration
│   ├── models.py               # Pydantic models
│   ├── services/
│   │   ├── milvus_service.py   # Milvus vector DB
│   │   ├── llm_service.py      # Azure OpenAI
│   │   ├── embedding_service.py # BGE-M3 embeddings
│   │   └── cache_service.py    # Redis caching
│   └── utils/
│       ├── logger.py           # Logging setup
│       └── metrics.py          # Metrics collection
├── tests/
│   ├── test_api.py
│   └── test_services.py
├── logs/
├── .env                        # Environment variables
├── requirements.txt            # Dependencies
├── README.md                   # This file
└── docker-compose.yml          # Docker setup

```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: 
.venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and update:

# API Settings
DEBUG=False
ALLOWED_ORIGINS=["*"]

# Milvus Settings
MILVUS_HOST=
MILVUS_PORT=
MILVUS_COLLECTION=lovdata_hierarchical_chunks
MILVUS_METRIC_TYPE=IP
MILVUS_INDEX_TYPE=HNSW
DIMENSION=1024

# LLM Provider Selection
LLM_PROVIDER=fireworks  # Options: "azure_openai" or "fireworks"



#AWS
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=ap-south-1


SAGEMAKER_EMBEDDING_ENDPOINT=embedding-bge-m3-endpoint

# Fireworks.ai Settings (NEW)
FIREWORKS_API_KEY=
FIREWORKS_MODEL=

# Embedding Service
EMBEDDING_MODEL=BAAI/bge-m3


# RAG Settings
DEFAULT_TOP_K=3
MAX_TOP_K=10
MIN_SIMILARITY_SCORE=0.30
CONTEXT_MAX_LENGTH=32000

# Rate Limiting
RATE_LIMIT_PER_MINUTE=250

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
CACHE_TTL=3600
ENABLE_CACHE=True

# Logging
LOG_LEVEL=INFO
LOG_DIR=./logs

# Monitoring
ENABLE_METRICS=True
METRICS_PORT=9090

# Retry Logic
MAX_RETRIES=3
RETRY_DELAY=1.0

```bash
# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4

# Milvus (already configured for your instance)
MILVUS_HOST=13.204.226.35
MILVUS_PORT=19530
```

### 3. Run the API

```bash
# Development mode (with auto-reload)
python -m uvicorn backend.main:app --reload

# Production mode
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 4. Access API

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 📚 API Endpoints

### 1. Health Check

```bash
GET /health

Response:
{
  "status": "healthy",
  "version": "1.0.0",
  "milvus_connected": true,
  "llm_connected": true,
  "cache_connected": true
}
```

### 2. Chat (RAG)

```bash
POST /chat

Request:
{
  "query": "Hva er reglene for aksjeselskap?",
  "top_k": 3,
  "include_sources": true,
  "temperature": 0.7
}

Response:
{
  "answer": "Aksjeselskap reguleres av aksjeloven...",
  "sources": [
    {
      "title": "Aksjeloven",
      "url": "https://lovdata.no/dokument/NL/lov/1997-06-13-44",
      "chunk_text": "§ 1-1. Aksjeselskap er...",
      "relevance_score": 0.92
    }
  ],
  "metadata": {
    "query_time": 1.23,
    "chunks_retrieved": 3,
    "tokens_used": 450
  }
}
```

### 3. Chat Streaming

```bash
POST /chat/stream

# Returns Server-Sent Events (SSE)
data: {"type": "sources", "data": [...]}
data: {"type": "token", "data": "Aksjeselskap"}
data: {"type": "token", "data": " reguleres"}
...
data: {"type": "complete", "metadata": {...}}
```

### 4. Search Only

```bash
POST /search

Request:
{
  "query": "skattelov selskap",
  "top_k": 10,
  "min_score": 0.5
}

Response:
{
  "results": [...],
  "total_found": 10,
  "query_time": 0.45
}
```

## 🧪 Testing with Postman

Import the Postman collection:

```bash
# Collection URL (to be provided)
```

Or test manually:

```bash
# Test health
curl http://localhost:8000/health

# Test chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Hva er aksjelov?",
    "top_k": 3
  }'
```

## 🔧 Configuration

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_TOP_K` | 3 | Number of chunks to retrieve |
| `RATE_LIMIT_PER_MINUTE` | 250 | Max requests per minute |
| `CACHE_TTL` | 3600 | Cache expiry in seconds |
| `AZURE_OPENAI_TEMPERATURE` | 0.7 | LLM creativity (0.0-2.0) |

## 📊 Monitoring

### Logs

```bash
# View logs
tail -f logs/rag_api.log

# Log levels: DEBUG, INFO, WARNING, ERROR
```


```

