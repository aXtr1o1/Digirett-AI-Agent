# Digirett AI Agent

AI-powered Norwegian Legal Assistant with a Retrieval-Augmented Generation (RAG) pipeline, Lovdata API integration, role-based access control (RBAC), and cross-conversation persistent user memory.

**Deployed Application:** [https://digirett-ai-agent-chi.vercel.app/](https://digirett-ai-agent-chi.vercel.app/)

---

## Project Objectives

*   **Lovdata API Q&A**: Authority-backed Norwegian legal question answering.
*   **Hybrid RAG Pipeline**: Context-aware queries using vector embeddings, semantic search, and keyword ranking.
*   **Multilingual Interface**: Auto-detects and answers in both Norwegian and English.
*   **Role-Based Security**: RBAC enforced via Clerk JWT signatures.
*   **Human-in-the-Loop (HITL)**: Direct ticket escalation routing unresolved queries to human legal professionals.
*   **User Fact Memory**: Asynchronously saves user preferences and attributes across sessions.

---

## Architecture Overview

```
                  ┌──────────────────────┐
                  │       Frontend       │
                  │   (Next.js 14 Web)   │
                  └──────────┬───────────┘
                             │ (WebSockets / HTTP)
                             ▼
                  ┌──────────────────────┐
                  │       Backend        │◀──────────────────┐
                  │   (FastAPI Python)   │                   │
                  └────┬────────────┬────┘                   │ (Read Vector Data)
                       │            │                        │
        (Write Cache)  ▼            ▼  (Read/Write DB)       │
                  ┌─────────┐  ┌──────────┐            ┌─────┴────┐
                  │  Redis  │  │ Supabase │            │  Milvus  │
                  └─────────┘  └──────────┘            └─────▲────┘
                                                             │
                                                             │ (Populate Embeddings)
                                                       ┌─────┴────┐
                                                       │Ingestion │
                                                       │ (Python) │
                                                       └──────────┘
```

### Component Directories
*   [frontend/](frontend/): Next.js web application.
*   [backend/](backend/): FastAPI application handling orchestrations, database synchronization, memory management, and token streaming.
*   [ingestion/](ingestion/): Collector, parser, normalizer, and indexing script that populates the Milvus vector database.

---

## End-to-End System Workflow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant FE as Frontend (Next.js)
    participant BE as Backend (FastAPI)
    participant Redis as Redis Cache
    participant DB as Supabase DB
    participant VDB as Milvus Vector DB

    User->>FE: Submits question (e.g., "What are overtid rules?")
    FE->>BE: Establishes WebSocket connection (with Clerk JWT)
    BE->>BE: Validates token and checks Rate Limits
    BE->>DB: Loads cross-conversation memory (UserMemoryAgent)
    BE->>BE: Classifies intent & language (LEGAL/CASUAL; NO/EN)
    
    rect rgb(240, 240, 240)
        Note over BE, VDB: If Intent is LEGAL
        BE->>BE: Aligns query vocabulary (QueryReasoningAgent)
        BE->>BE: Routes to legal subdomain (Deterministic Rules / Keyword Scorer / LLM Fallback)
        BE->>VDB: Multi-pass vector retrieval + BM25 filtering (RetrieverAgent)
        BE->>BE: Deduplicates & reranks chunks (ResultMerger & Reranker)
        BE->>BE: Generates response using Azure OpenAI (GeneratorAgent)
    end

    BE->>FE: Streams answer tokens + structured Lovdata sources
    BE->>DB: Saves messages to history (asynchronously)
    BE->>DB: Extracts & updates persistent user facts (async task)
    FE->>User: Renders streaming response & source citations
```

---

## Prerequisites

*   **Node.js**: `18.x` or higher
*   **Python**: `3.11.x` or higher
*   **Docker & Docker Compose** (for running local instances of Redis/Milvus)

### Global Configuration
Create `.env` configurations in the respective sub-folders (see `.env.example` templates in each folder). Crucial environment variables include:
*   `LOVDATA_API_KEY`: Auth credentials to retrieve Lovdata API content.
*   `MILVUS_HOST` & `MILVUS_PORT`: Connections to the Vector Database.
*   `REDIS_HOST` & `REDIS_PORT`: Context cache, title translators, and session stores.
*   `SUPABASE_URL` & `SUPABASE_KEY`: Persistent database schema and logs.
*   `CLERK_SECRET_KEY` & `CLERK_JWKS_URL`: User authentication credentials.

---

## Service Documentation

*   **Backend Service**: [backend/readme.md](backend/readme.md)
*   **Frontend Service**: See `frontend/README.md`
*   **Ingestion Service**: See `ingestion/README.md`
