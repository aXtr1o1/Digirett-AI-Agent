# Digirett Backend / Lovdata RAG API

Welcome to the backend service for **Digirett**, an AI-powered Norwegian legal assistant. Built with Python and FastAPI, this service orchestrates a sophisticated Retrieval-Augmented Generation (RAG) pipeline, multi-agent AI workflows, and strict role-based access control to provide accurate, source-backed legal answers.

---

## 🌟 Key Features

*   **Hybrid RAG Pipeline**: Combines vector search via **Milvus** with relational metadata from **Supabase** (PostgreSQL) to retrieve precise legal excerpts from Lovdata.
*   **Multi-Agent AI System**: Uses **Azure OpenAI** and **LangChain** to orchestrate specialized agents (Document Classifier, RAG QA, Intent Detection).
*   **Document Intelligence**: Users can upload PDFs and DOCX files. Includes robust text extraction, fallback OCR using PyMuPDF, and auto-summarization.
*   **Role-Based Access Control (RBAC)**: Deeply integrated with **Clerk**, providing JWT-based authentication for Users, Admins, and Lawyers.
*   **Human-in-the-Loop (HITL)**: Workflow for escalating complex legal questions to human lawyers, including ticket management and notifications.
*   **Webhooks**: Synchronizes user creation via Clerk webhooks and handles Cal.com booking events.
*   **Caching & Rate Limiting**: Utilizes **Redis** to cache LLM responses, manage conversational history, and enforce quotas.

---

## 🏗️ Project Structure

```text
backend/
├── agents/          # LangChain AI agents (Generator, Intent, Memory, Classifier)
├── api/
│   └── routes/      # FastAPI endpoints (auth, chat, documents, hitl, webhooks)
├── core/            # Core configuration, Clerk authentication middleware
├── db/              # Database clients (Supabase, Redis, Milvus wrapper)
├── schemas/         # Pydantic models for request/response validation
├── services/        # Business logic (LLM, RAG, Document processing, Email)
├── telemetry/       # OpenTelemetry and logging interceptors
├── tests/           # Pytest test suites and local test scenarios
├── config.py        # Environment variables and BaseSettings
└── main.py          # FastAPI application entry point
```

---

## 🚀 Getting Started

### 1. Prerequisites

Make sure you have the following installed on your system:
*   **Python 3.11+**
*   **pip** (Python package manager)
*   Access to external services (Supabase, Milvus, Redis, Azure OpenAI, Clerk).

### 2. Installation

Clone the repository and set up your Python virtual environment to keep dependencies isolated:

```bash
# Navigate to the backend directory
cd backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Mac/Linux:
source venv/bin/activate
# On Windows (Command Prompt):
venv\Scripts\activate.bat
# On Windows (PowerShell):
venv\Scripts\Activate.ps1
```

Once the virtual environment is activated, install the required packages:

```bash
pip install -r requirements.txt
```

### 3. Configuration

The application requires various API keys and connection strings to operate. Create a `.env` file in the root of the `backend/` directory.

Here is a template of the required variables:

```env
# ── App Settings ──────────────────────────────────────────
ALLOWED_ORIGINS=["http://localhost:3000"]

# ── Azure OpenAI ──────────────────────────────────────────
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-api-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# ── Vector Database (Milvus) ──────────────────────────────
MILVUS_HOST=<milvus-host>
MILVUS_PORT=19530
MILVUS_COLLECTION=lovdata_hierarchical_aoai_v1

# ── Relational Database (Supabase) ────────────────────────
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_KEY=<your-anon-key>

# ── Caching (Redis) ───────────────────────────────────────
REDIS_HOST=<redis-host>
REDIS_PORT=6379

# ── Authentication (Clerk) ────────────────────────────────
CLERK_SECRET_KEY=<your-clerk-secret-key>
CLERK_JWKS_URL=https://<clerk-instance>/.well-known/jwks.json
CLERK_WEBHOOK_SECRET=<svix-webhook-secret>

# ── Notifications / Email ─────────────────────────────────
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASS=<your-resend-api-key>
```
> **Note:** Never commit your `.env` file to version control.

### 4. Running the Server

Start the FastAPI application using Uvicorn. The `--reload` flag will automatically restart the server when you make code changes.

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

When the server starts successfully, you will see output confirming connections to Milvus, Redis, and Supabase.

### 5. Verify the API is Running

Visit the Health Check endpoint in your browser:
[http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

You should see a JSON response verifying the health of all connected services:
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

---

## 📚 API Documentation

FastAPI automatically generates interactive Swagger documentation. Once your server is running, navigate to:

👉 **[http://localhost:8000/docs](http://localhost:8000/docs)**

From here, you can view all available routes, see required authentication headers, and test the endpoints directly from your browser.

### Key API Routes:
*   `POST /api/v1/chat/stream`: Main conversational endpoint. Streams AI responses based on legal context.
*   `POST /api/v1/documents/upload`: Uploads a PDF/DOCX for document-grounded Q&A.
*   `GET /api/v1/hitl/lawyer/tickets`: Retrieves open human-in-the-loop escalation tickets (Requires Lawyer role).
*   `POST /api/v1/webhooks/clerk`: Secure endpoint for receiving Clerk user updates.

---

## 🧪 Testing

To run the automated test suite, ensure your virtual environment is activated and your `.env` file is properly configured.

```bash
pytest tests/ -v
```

For executing local ad-hoc test scenarios without running the full server, you can use the provided scenario runner:
```bash
python tests/run_test_scenarios.py
```
