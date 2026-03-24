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
python src/main.py or  python -m ingestion.src.main
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
