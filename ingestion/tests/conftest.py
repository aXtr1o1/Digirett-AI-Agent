
import os
import pytest

# Set up mock environment variables before any imports
# This prevents RuntimeError when config.py validates required env vars
os.environ.setdefault("LOVDATA_API_URL", "https://api.lovdata.no")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")
os.environ.setdefault("SUPABASE_BUCKET", "test-bucket")
os.environ.setdefault("MILVUS_HOST", "localhost")
os.environ.setdefault("MILVUS_PORT", "19530")
os.environ.setdefault("MILVUS_COLLECTION", "test-collection")
os.environ.setdefault("EMBED_MODEL", "test-model")

