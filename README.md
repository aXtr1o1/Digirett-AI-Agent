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

## 🌿 Branch Strategy

| Branch | Purpose | CI/CD | Deploy Target |
|--------|---------|-------|---------------|
| `production` | Production-ready code (default) | ✅ | Production environment |
| `testing` | Integration testing & QA | ✅ | Testing environment |
| `frontend` | Frontend development | ❌ | - |
| `backend` | Backend development | ❌ | - |
| `ingestion` | Data pipeline development | ❌ | - |

### Workflow

1. **Development**: Work on `frontend`, `backend`, or `ingestion` branches
2. **Integration**: Merge all feature branches → `testing`
3. **Testing**: Run comprehensive tests, raise issues, document
4. **Production**: After successful testing → merge to `production`

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
- [Ingestion Pipeline Documentation](./ingestion/README.md)
- [Deployment Guide](./docs/DEPLOYMENT.md)
- [API Documentation](./docs/API.md)
- [Contributing Guidelines](./docs/CONTRIBUTING.md)

## 🔐 Environment Variables

Create `.env` files in respective directories. See `.env.example` files for required variables.

**Critical Variables:**
- `LOVDATA_API_KEY`: Lovdata API access
- `MILVUS_HOST`: Vector database connection
- `REDIS_URL`: Cache and session storage
- `SUPABASE_URL`: Database connection
- `AUTH_SECRET`: Authentication secret

## 🧪 Testing

```bash
# Run all tests
make test

# Run specific test suites
make test-frontend
make test-backend
make test-ingestion
make test-e2e
```

## 📦 Deployment

### Production Deployment

```bash
# Automated via CI/CD on merge to production
git checkout production
git merge testing
git push origin production
```

### Manual Deployment

```bash
# Frontend (Vercel)
cd frontend && vercel --prod

# Backend & Ingestion (Docker)
docker-compose -f docker/production.yml up -d
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


## 🗺️ Roadmap

### Phase 1 (Current)
- ✅ Core RAG pipeline
- ✅ Lovdata integration
- ✅ Basic UI
- 🔄 Human-in-the-loop workflow
- 🔄 Audit logging


---

**Last Updated**: January 2026  
**Version**: 1.0.0
