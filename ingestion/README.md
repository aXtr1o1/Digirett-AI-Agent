<<<<<<< HEAD
# Ingestion Layer Documentation

Lovdata RAG System – Ingestion Layer  
Production-ready ingestion pipeline for Norwegian legal documents.

The ingestion layer is responsible for **collecting, preprocessing, chunking, embedding, and storing legal documents** into the vector database used by the RAG backend.

---

## 🎯 Features

- ✅ Lovdata legal document ingestion  
- ✅ Robust preprocessing & text cleaning  
- ✅ Advanced chunking (parent–child, token-aware)  
- ✅ Embedding generation (BGE / OpenAI / Azure OpenAI)  
- ✅ Milvus vector database storage  
- ✅ Idempotent & repeatable ingestion runs  
- ✅ Structured metadata for traceability  
- ✅ Logging & error handling  
- ✅ Production-ready modular architecture  

---

## 📁 Project Structure

```text
DIGIRETT-AI-AGENT/
├── data/
│   ├── .gitkeep
│   └── README.md
├── ingestion/
│   └── src/
│       ├── processors/
│       │   ├── chunker.py
│       │   ├── embedder_sagemaker.py
│       │   └── text_processor.py
│       ├── storage/
│       │   ├── milvus_store.py
│       │   └── supabase_store.py
│       ├── verify/
│       │   ├── check_chunker.py
│       │   ├── del_milvus.py
│       │   ├── verify_milvus.py
│       │   └── verify_sagemaker.py
│       ├── __init__.py
│       ├── config.py
│       └── main.py
├── tests/
│   ├── demo_testing.py
│   ├── test_bge_embedding.py
│   ├── test_collector.py
│   ├── test_health.py
│   ├── test_milvus_store.py
│   └── test_supabase_store.py
├── .gitignore
├── ecosystem.config.js
├── README.md
└── requirements.txt

🚀 Quick Start

1️⃣ Install Dependencies

cd ingestion
python -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

2️⃣ Configure Environment

Copy .env.example to .env and update:

# Lovdata
# Company-specific raw XML data (example)
DATA_PATH=./data/raw_xml   # contains ~53 XML files

**# Embeddings**

EMBEDDING_PROVIDER=azure_openai
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=bge-m3

**# Milvus**
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=lovdata_legal_docs

**# Chunking**

CHUNK_SIZE=512
CHUNK_OVERLAP=64

3️⃣ Run the Ingestion Pipeline

Standard Ingestion Run

--- python -m ingestion.src.main

This command will:

Fetch legal documents from Lovdata

Clean and normalize text

Apply chunking strategy

Generate embeddings

Store vectors and metadata in Milvus

🧪 Testing
Run ingestion tests:

pytest tests/-demo_testing

🧠 Ingestion Flow

raw_files
    ↓
Raw Document Loader
    ↓
Text Cleaning & Normalization
    ↓
Chunking (Parent–Child / Token-Aware)
    ↓
Embedding Generation
    ↓
Milvus Vector Store

🧩 Chunking Strategy

Parent–Child Chunking
Parent chunk: legal section or article

Child chunks: smaller semantic units used for embeddings

Token-Aware Chunking
Prevents exceeding LLM token limits

Preserves semantic coherence

Dynamic Chunk Sizes
Adjusts chunk size based on document structure

📊 Logging & Monitoring

Logs are stored under logs/

tail -f logs/ingestion.log
Log Levels

DEBUG

INFO

WARNING

ERROR

Version: 1.0.0
Last Updated: January 2026
=======
# Ingestion Pipeline - Digirett AI Agent

Data ingestion pipeline for collecting, processing, and storing Norwegian legal documents from Lovdata.

## 📁 Structure

```
ingestion/
├── collectors/
│   └── lovdata_collector.py    # Lovdata API data collection
├── src/
│   ├── main.py                 # Pipeline entry point
│   ├── config.py               # Configuration
│   ├── processors/             # Data processing
│   │   ├── chunker.py          # Text chunking
│   │   ├── embedder.py         # Vector embeddings
│   │   └── text_processor.py   # Text preprocessing
│   ├── scheduler/               # Scheduling
│   │   ├── cron_scheduler.py   # Cron-based scheduling
│   │   └── trigger_handler.py  # Event triggers
│   └── storage/
│       └── milvus_store.py     # Milvus vector storage
├── data/
│   ├── checkpoints/            # Ingestion checkpoints
│   └── logs/                   # Pipeline logs
├── scripts/                     # Utility scripts
├── test/                       # Tests
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

# Run ingestion pipeline
python src/main.py
```

## 🔧 Environment Variables

Create `.env` file:

```env
# Lovdata API
LOVDATA_API_KEY=your-lovdata-api-key
LOVDATA_BASE_URL=https://api.lovdata.no

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=legal_documents


# Processing
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
```

## 📚 Tech Stack

- **Language**: Python 3.11+
- **API**: Lovdata API
- **Vector DB**: Milvus
- **Embeddings**: (Pending) 
- **Scheduling**: Cron / APScheduler

---

**Last Updated**: January 2026
>>>>>>> origin/Frontend
