import os
import uuid
import requests
from qdrant_client import QdrantClient
from qdrant_client.http import models

class AgentMemory:
    def __init__(self, collection_name: str = "heckworks_memory"):
        qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        
        self.client = QdrantClient(host=qdrant_host, port=qdrant_port, check_compatibility=False)
        self.collection_name = collection_name
        
        # TEI engine outputs 768 dimensions for this model
        self.tei_url = os.getenv("TEI_URL", "http://localhost:8080/embed")
        self.vector_size = 768

        self._ensure_collection_exists()

    def _get_embedding(self, text: str) -> list:
        """Sends text to your cluster's TEI engine to get vector embeddings."""
        response = requests.post(
            self.tei_url,
            json={"inputs": text},
            headers={"Content-Type": "application/json"}
        )
        if response.status_code != 200:
            raise RuntimeError(f"TEI embedding failed: {response.text}")
        return response.json()[0]

    def _ensure_collection_exists(self):
        """Ensures the Qdrant collection exists and matches the 768 vector size."""
        collections = self.client.get_collections().collections
        exists = any(col.name == self.collection_name for col in collections)
        
        if exists:
            self.client.delete_collection(collection_name=self.collection_name)
            
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=models.VectorParams(
                size=self.vector_size,
                distance=models.Distance.COSINE
            )
        )
        print(f"Initialized Qdrant collection '{self.collection_name}' with dimension {self.vector_size}")

    def store_memory(self, text_content: str, metadata: dict):
        """Stores a style rule, user correction, or context snippet into Qdrant."""
        vector = self._get_embedding(text_content)
        
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, text_content))
        
        point = models.PointStruct(
            id=point_id,
            vector=vector,
            payload={**metadata, "content": text_content}
        )
        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )
        print("Successfully stored memory vector.")

    def query_memory(self, query_text: str, limit: int = 3):
        """Retrieves relevant personal style context or corrections based on a prompt."""
        query_vector = self._get_embedding(query_text)
        
        # Updated to use query_points for newer qdrant-client versions
        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit
        )
        return [point.payload["content"] for point in response.points]

if __name__ == "__main__":
    memory = AgentMemory()
    memory.store_memory(
        "Never use exclamation points in formal engineering or client email replies. Keep tone concise and direct.",
        {"category": "style_guide", "author": "israel"}
    )
    
    results = memory.query_memory("How should I reply to a client?")
    print("Retrieved Context:", results)
