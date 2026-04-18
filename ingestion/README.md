# Ingestion Pipeline - Digirett AI Agent

Data ingestion pipeline for collecting, processing, and storing Norwegian legal documents from Lovdata.

## 🚀 What This Pipeline Does

For every Lovdata archive:

1. Download XML files from Lovdata API
2. Convert XML → structured legal text
3. Perform hierarchical token-based chunking
4. Generate embeddings using Azure OpenAI (text-embedding-3-small, 1536 dimensions)
5. Store vectors in Milvus
6. Store XML + metadata in Supabase
7. Skip already processed files using SHA256 hash
8. Run automatically every day via APScheduler

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
python -m ingestion.src.main
```

---

## ⚙️ Ingestion Modes

### ✅ Mode 1 — Lovdata API Ingestion (Recommended)

Pipeline automatically fetches legal XML from Lovdata.

Requires:

```
LOVDATA_BASE_URL=https://api.lovdata.no
```

---

### ✅ Mode 2 — Client Excel Dataset Ingestion (Offline Mode)

If Lovdata API is not used, the pipeline can ingest legal data from **client-provided Excel datasets**.

This mode is useful for:

- Client-specific legal datasets
- Offline deployments
- Testing environments
- Data migration workflows

---

## 📄 Configure Client Dataset Folder

Update `.env` file:

```
# ============================
# XL Client Dataset
# ============================
XL_DATASET_FOLDER=PATH_TO_CLIENT_DATASET
```

Example:

```
XL_DATASET_FOLDER=D:\aXtr Labs\Digirett-AI-Agent\ingestion\data\Client_dataset
```

Dataset folder structure:

```
Client_dataset/
    domain_name1.xlsx
    domain_name2.xlsx
```

Each Excel file represents one legal ingestion domain.

# Milvus
MILVUS_HOST=<your-milvus-host>
MILVUS_PORT=<your-milvus-port>
MILVUS_COLLECTION=your-milvus-collections
MILVUS_DIMENSION=MILVUS_DIMENSION

# Processing
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Supabase
SUPABASE_SERVICE_KEY=<your-supabase-service-key>
SUPABASE_BUCKET=<your-bucket-name>

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://<your-resource>.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=<your-azure-openai-key>
AZURE_OPENAI_API_VERSION=your-version
AZURE_OPENAI_DEPLOYMENT=text-embedding-3-small

# Embedding settings
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_BATCH_SIZE=1
EMBEDDING_CHUNK_DELAY=1.5

# Chunking
MAX_TOKENS_PER_CHUNK=512
OVERLAP_TOKENS=50
```
## ⏰ Scheduler 

The pipeline can run automatically using APScheduler.

## 🧪 Testing

``` bash
pytest
```

## 📚 Tech Stack

- **Language**: Python 3.11+
- **API**: Lovdata API
- **Vector DB**: Milvus
- **Embeddings**: Azure OpenAI (text-embedding-3-small) 
- **Scheduling**: Cron / APScheduler

---

**Last Updated**: February 2026 (Azure OpenAI migration)