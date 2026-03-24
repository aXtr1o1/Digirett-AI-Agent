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
python src/main.py or  python -m ingestion.src.main
```

## 🔧 Environment Variables

Create `.env` file:

```env
# .env.example
LOVDATA_BASE_URL=https://api.lovdata.no

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