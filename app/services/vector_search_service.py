import os
from typing import List, Dict
from pymongo import MongoClient
from pymongo.errors import PyMongoError
import numpy as np
from dotenv import load_dotenv

load_dotenv()

COSMOS_URI = os.getenv("COSMOS_URI")
COSMOS_DB_NAME = os.getenv("COSMOS_DB_NAME", "medmine")
COSMOS_COLLECTION_NAME = os.getenv("COSMOS_COLLECTION_NAME", "embeddings")

client = MongoClient(COSMOS_URI)
db = client[COSMOS_DB_NAME]
collection = db[COSMOS_COLLECTION_NAME]

def store_embedding(doc_id: str, embedding: List[float], metadata: Dict):
    try:
        document = {
            "_id": doc_id,
            "vector": embedding,
            "metadata": metadata
        }
        collection.insert_one(document)
        print(f" Inserted document {doc_id} into Cosmos DB.")
    except PyMongoError as e:
        print(f"Error inserting document: {e}")

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))

def query_similar_chunks(query_vector: List[float], top_k: int = 5) -> List[Dict]:
    try:
        results = []
        for doc in collection.find({}):
            stored_vector = doc["vector"]
            similarity = cosine_similarity(query_vector, stored_vector)
            results.append({
                "text": doc.get("metadata", {}).get("item_desc", ""),
                "metadata": doc["metadata"],
                "similarity": similarity
            })

        results = sorted(results, key=lambda x: x["similarity"], reverse=True)
        return results[:top_k]

    except PyMongoError as e:
        print(f" Error querying Cosmos DB: {e}")
        return []
