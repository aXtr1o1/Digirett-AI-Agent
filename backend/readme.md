# Lovdata RAG API

A backend API that answers questions about Norwegian law using AI.
You ask a question, it finds the relevant law, and gives you a structured answer with sources.

---

## What You Need Before Starting

Make sure you have these installed on your computer:

| Tool | How to check | Download link |
|---|---|---|
| Python 3.11+ | Run `python --version` in terminal | https://www.python.org/downloads/ |
| pip | Run `pip --version` in terminal | Comes with Python |
| Git (optional) | Run `git --version` in terminal | https://git-scm.com/ |

---

## Step 1 — Get the Code

If you have Git:
```bash
git clone <your-repo-url>
cd backend
```

If you downloaded a ZIP file:
- Unzip it
- Open your terminal and navigate into the `backend` folder

```bash
cd path/to/backend
```

---

## Step 2 — Create a Virtual Environment

A virtual environment keeps this project's packages separate from the rest of your computer.

```bash
# Create the virtual environment
python -m venv venv

# Activate it — choose the right command for your OS:

# On Mac or Linux:
source venv/bin/activate

# On Windows (Command Prompt):
venv\Scripts\activate.bat

# On Windows (PowerShell):
venv\Scripts\Activate.ps1
```

You will see `(venv)` appear at the start of your terminal line. That means it worked.

---

## Step 3 — Install Dependencies

```bash
pip install -r requirements.txt
```

This installs all the Python packages the project needs. It may take 1–2 minutes.

---

## Step 4 — Create the .env File

The project needs secret keys and connection details. These go in a file called `.env` inside the `backend/` folder.

Create a new file called `.env` and paste this inside it, filling in your own values:

```env
# ── App ──────────────────────────────────────────────
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]

# ── Azure OpenAI (your AI model) ─────────────────────
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key-here
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-02-15-preview
OPENAI_TEMPERATURE=0.7

# ── Azure OpenAI Embeddings ───────────────────────────
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small
AZURE_OPENAI_EMBEDDING_API_VERSION=2024-02-15-preview

# ── Milvus (vector database) ─────────────────────────
MILVUS_HOST=your-milvus-host
MILVUS_PORT=19530
MILVUS_COLLECTION=lovdata_hierarchical_aoai_v1
DIMENSION=1536

# ── Supabase (main database) ─────────────────────────
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key

# ── Redis (caching) — already configured ─────────────
REDIS_HOST=
REDIS_DB=0
REDIS_PORT=
REDIS_PASSWORD=
ENABLE_CACHE=true

# ── RAG Settings ─────────────────────────────────────
DEFAULT_TOP_K=3
MAX_TOP_K=10
MIN_SIMILARITY_SCORE=0.0
CONTEXT_MAX_LENGTH=80000
```

> **Note:** Never share your `.env` file with anyone. Never commit it to Git.

---

## Step 5 — Run the Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

You should see output like this:

```
INFO  | Starting Lovdata RAG API...
INFO  | Connected to Milvus
INFO  | Redis connected
INFO  | Supabase connected
INFO  | All services ready — server is live
INFO  | Uvicorn running on http://0.0.0.0:8000
```

Your API is now running at: **http://localhost:8000**

---

## Step 6 — Verify It Works

Open your browser and go to:

```
http://localhost:8000/api/v1/health
```

You should see something like:

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "milvus_connected": true,
  "llm_connected": true,
  "cache_connected": true,
  "supabase_connected": true
}
```

If `status` is `"healthy"` — everything is working. ✅

---

## How to Use the API

### Interactive API Docs (easiest way)

Go to: **http://localhost:8000/docs**

This opens a visual interface where you can test every endpoint by clicking and typing — no code needed.

---

### Main Endpoints

#### Ask a Question (Streaming)
```
POST /api/v1/chat/stream
```
Send a question, get a streamed AI answer with sources.

**Request body:**
```json
{
  "query": "Hva er reglene for aksjeselskap i Norge?",
  "conversation_id": "optional-existing-id",
  "user_id": "your-user-id",
  "top_k": 3
}
```

#### Create a Conversation
```
POST /api/v1/conversations
```
```json
{
  "user_id": "your-user-id",
  "title": "My first conversation"
}
```

#### Get All Messages in a Conversation
```
GET /api/v1/messages/{conversation_id}
```

#### Get All Conversations for a User
```
GET /api/v1/conversations/user/{user_id}
```

#### Delete a Conversation
```
DELETE /api/v1/conversations/{conversation_id}
```

#### Health Check
```
GET /api/v1/health
```

---

## Running the Tests

Make sure the server is running first (Step 5), then open a second terminal:

```bash
# Activate the virtual environment first
source venv/bin/activate   # Mac/Linux
# or
venv\Scripts\activate.bat  # Windows

# Run tests
pytest tests/test_api.py -v
```

Expected output:
```
PASSED tests/test_api.py::test_health
PASSED tests/test_api.py::test_create_conversation
PASSED tests/test_api.py::test_stream_legal_query
PASSED tests/test_api.py::test_messages_persisted
PASSED tests/test_api.py::test_get_conversation
PASSED tests/test_api.py::test_get_user_conversations
PASSED tests/test_api.py::test_delete_conversation
```

---
