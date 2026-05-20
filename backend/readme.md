# Digirett-AI-Agent
AI-powered Norwegian legal assistant with RAG pipeline, Lovdata integration, and multilingual support


## 🎯 Project Objectives

- **Accurate Legal Q&A**: Leverage Lovdata API for authoritative Norwegian legal information
- **Full RAG Pipeline**: Contextual answers using vector embeddings and semantic search
- **Multilingual Support**: English & Norwegian language support
- **Secure Authentication**: Role-based access control (RBAC)
- **Human-in-the-Loop**: Escalation workflow for complex legal queries
- **Audit Logging**: Comprehensive compliance and traceability
- **Scalable Infrastructure**: Foundation for Phase 2 document intelligence

## 🏗️ Architecture Overview

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  Ingestion  │
│  (Next.js)  │      │  (Python)    │      │  (Python)   │
│   Vercel    │      │              │      │             │
└─────────────┘      └──────────────┘      └─────────────┘
                            │                      │
                            ▼                      ▼
                     ┌──────────────┐      ┌─────────────┐
                     │   Redis      │      │   Milvus    │
                     │   Supabase   │      │     VDB     │
                     └──────────────┘      └─────────────┘
```

## 📁 Repository Structure

```
.
├── frontend/           # Next.js application
├── backend/            # Python backend services
├── ingestion/          # Data ingestion pipeline
├── .github/
│   └── workflows/      # CI/CD pipelines
```

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ (Frontend)
- Python 3.11+ (Backend & Ingestion)
- Docker & Docker Compose
- Git

### Installation

```bash
# Clone repository
git clone https://github.com/aXtr1o1/Digirett-AI-Agent.git 
cd Digirett-AI-Agent

# Checkout desired branch
git checkout 

# Install dependencies (see respective README files)
```

## 📚 Documentation

- [Frontend Documentation](./frontend/README.md)
- [Backend Documentation](./backend/README.md)

## 🔐 Environment Variables

Create `.env` files in respective directories. See `.env.example` files for required variables.

**Critical Variables:**
- `LOVDATA_API_KEY`: Lovdata API access
- `MILVUS_HOST`: Vector database connection
- `REDIS_URL`: Cache and session storage
- `SUPABASE_URL`: Database connection
- `AUTH_SECRET`: Authentication secret
```

## 🛠️ Technology Stack

### Frontend
- **Framework**: Next.js 14
- **Styling**: Tailwind CSS
- **Auth**: NextAuth.js
- **Deployment**: Vercel

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI
- **LLM Framework**: LangChain
- **Database**: Supabase (PostgreSQL)
- **Cache**: Redis
- **Vector DB**: Milvus

### Ingestion
- **Language**: Python 3.11+
- **API**: Lovdata API
- **Embeddings**: OpenAI / Azure OpenAI
- **Scheduling**: Cron / APScheduler

---

**Last Updated**: January 2026  
**Version**: 1.0.0