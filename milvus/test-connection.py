#!/usr/bin/env python3
"""
Test script to verify Milvus connection
Usage: python test-connection.py [host] [port]
"""

import sys
import os

try:
    from pymilvus import connections, utility
except ImportError:
    print("❌ pymilvus is not installed. Install it with: pip install pymilvus")
    sys.exit(1)


def test_connection(host="localhost", port=19530):
    """Test connection to Milvus instance"""
    print(f"🔍 Testing connection to Milvus at {host}:{port}...")
    
    try:
        # Connect to Milvus
        connections.connect(
            alias="default",
            host=host,
            port=str(port)
        )
        print("✅ Successfully connected to Milvus!")
        
        # List collections
        collections = utility.list_collections()
        print(f"📊 Found {len(collections)} collection(s): {collections}")
        
        # Test basic operations
        print("✅ Connection test passed!")
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {str(e)}")
        return False
    finally:
        try:
            connections.disconnect("default")
        except:
            pass


if __name__ == "__main__":
    # Get host and port from command line or environment
    host = sys.argv[1] if len(sys.argv) > 1 else os.getenv("MILVUS_HOST", "localhost")
    port = int(sys.argv[2]) if len(sys.argv) > 2 else int(os.getenv("MILVUS_PORT", "19530"))
    
    success = test_connection(host, port)
    sys.exit(0 if success else 1)
