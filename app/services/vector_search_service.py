import os
import logging
import numpy as np
from typing import List, Dict
from dotenv import load_dotenv
from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosHttpResponseError

load_dotenv()
COSMOS_ENDPOINT       = os.getenv("COSMOS_DB_ENDPOINT")
COSMOS_KEY            = os.getenv("COSMOS_DB_KEY")
COSMOS_DB_NAME        = os.getenv("COSMOS_DB_DATABASE")
COSMOS_CONTAINER_NAME = os.getenv("COSMOS_DB_VECTOR_CONTAINER", "embeddings")

client    = CosmosClient(COSMOS_ENDPOINT, credential=COSMOS_KEY)
database  = client.get_database_client(COSMOS_DB_NAME)
container = database.get_container_client(COSMOS_CONTAINER_NAME)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s] %(message)s"))
logger.addHandler(handler)

def store_embedding(doc_id: str, embedding: List[float], metadata: Dict):
    item = {
        'id':       doc_id,
        'vector':   embedding,
        'metadata': metadata
    }
    try:
        container.upsert_item(item)
        logger.info(f"Upserted embedding {doc_id}")
    except CosmosHttpResponseError as e:
        logger.error(f"Failed to upsert embedding {doc_id}: {e}")

def store_embeddings_bulk(docs: List[Dict]):
    success = 0
    for doc in docs:
        item = {
            'id':       doc['id'],
            'vector':   doc['vector'],
            'metadata': doc['metadata']
        }
        try:
            container.upsert_item(item)
            success += 1
        except CosmosHttpResponseError as e:
            logger.error(f"Bulk upsert failed for {doc['id']}: {e}")
    logger.info(f"Bulk upsert completed: {success}/{len(docs)} items upserted.")

def query_similar_embeddings(query_vector: List[float], top_k: int = 5) -> List[Dict]:
    sql = """
    SELECT TOP @k c.metadata, VECTOR_DISTANCE(c.vector, @q) AS distance
    FROM c
    ORDER BY distance ASC
    """
    params = [
        {"name": "@q", "value": query_vector},
        {"name": "@k", "value": top_k}
    ]
    try:
        results = list(container.query_items(
            query=sql,
            parameters=params,
            enable_cross_partition_query=True
        ))
        return results
    except CosmosHttpResponseError as e:
        logger.error(f"Vector query failed: {e}")
        return []

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    a, b = np.asarray(vec1), np.asarray(vec2)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
