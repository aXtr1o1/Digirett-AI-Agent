import logging
from typing import Optional
from pymilvus import connections, Collection, utility

logger = logging.getLogger(__name__)

class MilvusClient:
    def __init__(self, host: str, port: int, collection: str):
        self.host = host
        self.port = port
        self.collection_name = collection
        self.collection: Optional[Collection] = None

    def connect(self):
        logger.info(f"Milvus connect {self.host}:{self.port}")
        connections.connect(alias="default", host=self.host, port=self.port)
        if not utility.has_collection(self.collection_name):
            raise RuntimeError(f"Milvus collection not found: {self.collection_name}")
        self.collection = Collection(self.collection_name)
        self.collection.load()
        logger.info(f"Milvus ready collection={self.collection_name} entities={self.collection.num_entities}")

    def get_collection(self) -> Collection:
        if not self.collection:
            raise RuntimeError("Milvus not connected")
        return self.collection

    def close(self):
        try:
            if self.collection:
                self.collection.release()
            connections.disconnect("default")
            logger.info("Milvus closed")
        except Exception:
            pass
