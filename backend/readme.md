# Backend - Digirett AI Agent

FastAPI backend service for the Digirett AI Agent legal assistant.

## 📁 Structure

```
backend/
├── api/endpoints.py          # API endpoints
├── config.py                 # Configuration
├── core/auth.py              # Authentication
├── db/                       # Database clients (Supabase, Redis, Milvus)
├── main.py                   # FastAPI app entry
├── services/                 # Business logic
│   ├── chat_service.py
│   ├── conversation_service.py
│   ├── user_service.py
│   └── rag/                  # RAG pipeline
└── requirements.txt
```

## 🚀 Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file (see below)

# Run server
uvicorn main:app --reload --port 8000
```

Visit: http://localhost:8000/docs

## 🔧 Environment Variables

Create `.env` file:

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Redis
REDIS_URL=redis://localhost:6379/0

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=legal_documents

# Auth
JWT_SECRET_KEY=your-secret-key
ALLOWED_ORIGINS=http://localhost:3000
```



## 📚 Tech Stack

- **Framework**: FastAPI
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis
- **Vector DB**: Milvus
- **LLM**: (Pending) / LangChain

---

**Last Updated**: January 2026
