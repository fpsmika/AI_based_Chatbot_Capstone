import os
import uuid
import logging
import pandas as pd
from typing import List, Dict
from dotenv import load_dotenv
from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.vector_search_service import store_embeddings_bulk

# Load environment variables
load_dotenv()

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s] %(message)s"))
logger.addHandler(handler)

# Lazy model placeholder
_model = None

def _load_model():
    """Lazy load the SentenceTransformer model."""
    from sentence_transformers import SentenceTransformer
    model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    logger.info(f"Loading embedding model: {model_name}")
    return SentenceTransformer(model_name)

def embed_bulk_text(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts via a local SentenceTransformer model.

    Returns:
        A list of embedding vectors (Python lists), one for each input text.
    """
    global _model
    if _model is None:
        _model = _load_model()
    embeddings = _model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()

def process_and_embed_csv(file_path: str, batch_size: int = 500):
    """
    Read a CSV file from disk, split it into purchase chunks, generate embeddings in batches,
    and bulk upsert into Cosmos DB.

    Args:
        file_path: Path to the CSV file on disk.
        batch_size: Number of texts to embed per batch.
    """
    logger.info(f"Embedding pipeline start for file: {file_path}")
    # read and normalize columns
    df = pd.read_csv(file_path)
    df.columns = [c.lower() for c in df.columns]

    # parse into text+metadata chunks
    chunks = csv_to_purchase_chunks(df)
    total = len(chunks)
    logger.info(f"Parsed {total} chunks from data.")

    # prepare lists
    doc_ids   = [str(uuid.uuid4()) for _ in chunks]
    texts     = [chunk["text"] for chunk in chunks]
    metadatas = [chunk["metadata"] for chunk in chunks]

    # batch and upsert
    for batch_i in range(0, total, batch_size):
        batch_ids   = doc_ids[batch_i:batch_i+batch_size]
        batch_texts = texts[batch_i:batch_i+batch_size]
        batch_metas = metadatas[batch_i:batch_i+batch_size]

        logger.info(f"  Embedding batch {batch_i//batch_size + 1} ({len(batch_texts)} items)")
        embeddings = embed_bulk_text(batch_texts)

        # build docs
        docs = [
            {"id": did, "vector": vec, "metadata": meta}
            for did, vec, meta in zip(batch_ids, embeddings, batch_metas)
        ]

        store_embeddings_bulk(docs)
        logger.info(f"  Upserted batch {batch_i//batch_size + 1}")

    logger.info(f"Completed embedding & upserting {total} chunks.")
