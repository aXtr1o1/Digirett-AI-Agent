Digirett AI – Backend
=====================

This folder contains the FastAPI backend for the Digirett AI assistant.  
It exposes a streaming chat endpoint that answers questions about Norwegian company law using:

- Milvus as the vector database for legal document embeddings
- Azure OpenAI for both embeddings and chat completion
- Redis for caching responses
- SlowAPI for IP-based rate limiting

The backend is designed to be stateless; all persistent data lives in Milvus and Redis.


Project layout
--------------

From the repository root:

```text
backend/
  api/
    endpoints.py        # HTTP routes (e.g. /chat/stream)
  core/
    auth.py             # (reserved for auth/permissions)
  db/
    milvus_client.py    # Milvus connection and collection handling
    redis.py            # Redis-based cache client
  services/
    chat_service.py     # Orchestration of retrieval + LLM + streaming SSE
    conversation_service.py
    user_service.py
    rag/
      pipeline.py       # Build context from retrieved chunks
      retriever.py      # Search in Milvus
      generator.py      # Embedding generator (Azure OpenAI)
  config.py             # Pydantic settings (loads env from backend/.env)
  main.py               # FastAPI app factory and wiring
  models.py             # Pydantic request/response models
  requirements.txt      # Python dependencies for the backend
  tests/                # Backend unit/integration tests
```


Environment configuration
-------------------------

Configuration is managed via `pydantic-settings` in `config.py`.  
By default, settings are loaded from `backend/.env` (note: relative to the **repo root**):

```python
model_config = SettingsConfigDict(
    env_file="backend/.env",
    ...
)
```

Create a file `backend/.env` with at least the following variables.

### Application

```env
APP_NAME=Digirett AI Backend
VERSION=0.1.0
DEBUG=true
ALLOWED_ORIGINS=["http://localhost:3000"]
```

### Logging

```env
LOG_DIR=logs
LOG_FILE=backend.log
LOG_LEVEL=INFO        # e.g. DEBUG, INFO, WARNING, ERROR
```

### Rate limiting

```env
RATE_LIMIT_PER_MINUTE=250
```

### Milvus (vector database)

```env
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=digirett_chunks   # name of an existing Milvus collection
MILVUS_METRIC_TYPE=IP               # or COSINE, L2 etc., must match collection
EMBEDDING_DIMENSION=1024            # must match how the collection was created
```

Make sure Milvus is running and the collection exists before starting the backend.

### Redis (cache)

```env
REDIS_URL=redis://localhost:6379/0
ENABLE_CACHE=true
CACHE_TTL=3600
```

If you do not want caching, you can set `ENABLE_CACHE=false` or leave `REDIS_URL` empty.

### RAG behaviour

```env
DEFAULT_TOP_K=3
MAX_TOP_K=10
MIN_SIMILARITY_SCORE=0.30
CONTEXT_MAX_LENGTH=32000
```

These control how many documents are retrieved and how much context is passed to the LLM.

### Azure OpenAI – chat and embeddings

Two separate Azure OpenAI resources (or deployments) are used: one for chat and one for embeddings.

```env
# Chat model
AZURE_OPENAI_CHAT_ENDPOINT=https://your-chat-resource.openai.azure.com/
AZURE_OPENAI_CHAT_API_KEY=your-chat-api-key
AZURE_OPENAI_CHAT_API_VERSION=2024-02-01
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-4.1-mini   # or your chosen deployment name

# Embedding model
AZURE_OPENAI_EMBED_ENDPOINT=https://your-embed-resource.openai.azure.com/
AZURE_OPENAI_EMBED_API_KEY=your-embed-api-key
AZURE_OPENAI_EMBED_API_VERSION=api-version
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
```

### Prompt versioning

```env
PROMPT_VERSION=v1
```

`PROMPT_VERSION` is baked into cache keys so you can safely change prompts and invalidate old cache entries by bumping this value.


How to run the backend locally
------------------------------

Prerequisites:

- Python 3.11+ installed
- Milvus running and pre-populated with your legal document embeddings
- Redis running (recommended, but can be disabled)
- Valid Azure OpenAI deployments for chat and embeddings

From the **repository root** (where `backend/` lives):

1. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\Activate.ps1
   # macOS/Linux
   # source .venv/bin/activate
   ```

2. **Install backend dependencies**

   ```bash
   pip install -r backend/requirements.txt
   ```

3. **Create and fill in `backend/.env`**

   Use the example sections above and set all required secrets/URLs for Milvus, Redis and Azure OpenAI.

4. **Run the API with Uvicorn (development)**

   Run this **from the repo root** so that `backend/.env` is found:

   ```bash
   python -m uvicorn backend.main:app --reload --port 8000
   ```

   The app will start with CORS, rate limiting, Milvus, Redis and Azure OpenAI wired up.


Key endpoints
-------------

- **POST `/chat/stream`**  
  Streaming Server-Sent Events (SSE) endpoint that:

  - Takes a JSON body:

    ```json
    {
      "query": "Hva er reglene for aksjeselskap?",
      "top_k": 3,
      "include_sources": true,
      "temperature": 0.5
    }
    ```

  - Returns an SSE stream with events of shape:

    ```json
    { "type": "sources", "data": [...] }   // emitted once when sources are ready
    { "type": "token",   "data": "..." }   // incremental answer tokens
    { "type": "complete","metadata": {...} } // final metadata (timing, intent, etc.)
    ```

  This is the main endpoint consumed by the frontend.


Running tests
-------------

With the virtual environment active and test dependencies installed (they are already listed in `requirements.txt`):

```bash
pytest backend/tests
```

Most tests focus on the behaviour of the `/chat/stream` endpoint and its SSE contract.

