import os
import uuid
import logging
import pandas as pd
from typing import List, Dict
from dotenv import load_dotenv
from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.vector_search_service import store_embeddings_bulk

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s] %(message)s"))
logger.addHandler(handler)

_model = None

def _load_model():
    from sentence_transformers import SentenceTransformer
    model_name = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    logger.info(f"Loading embedding model: {model_name}")
    return SentenceTransformer(model_name)

def embed_bulk_text(texts: List[str]) -> List[List[float]]:
    global _model
    if _model is None:
        _model = _load_model()
    # returns numpy array; convert to lists
    embeddings = _model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()

def process_and_embed_csv(file_path: str, batch_size: int = 500):
    logger.info(f"Embedding pipeline start for file: {file_path}")

    # 1) Read *without* lowercasing so parser sees "Month", "Year", etc.
    df = pd.read_csv(file_path)

    # 2) Turn it into text+metadata chunks
    chunks = csv_to_purchase_chunks(df)
    total  = len(chunks)
    logger.info(f"Parsed {total} chunks from data.")

    # 3) Prepare IDs, texts, metas
    doc_ids   = [str(uuid.uuid4()) for _ in chunks]
    texts     = [c["text"]     for c in chunks]
    metadatas = [c["metadata"] for c in chunks]

    # 4) Batch & upsert
    for batch_i in range(0, total, batch_size):
        batch_ids   = doc_ids  [batch_i:batch_i+batch_size]
        batch_texts = texts    [batch_i:batch_i+batch_size]
        batch_metas = metadatas[batch_i:batch_i+batch_size]

        logger.info(f"  Embedding batch {batch_i//batch_size + 1} ({len(batch_texts)} items)")
        try:
            embs = embed_bulk_text(batch_texts)
        except Exception as e:
            logger.error(f"  ✖️ Embedding failed for batch {batch_i//batch_size + 1}: {e}")
            continue

        docs = [
            {"id": did, "vector": vec, "metadata": meta}
            for did, vec, meta in zip(batch_ids, embs, batch_metas)
        ]

        try:
            store_embeddings_bulk(docs)
            logger.info(f"  ✅ Upserted batch {batch_i//batch_size + 1}")
        except Exception as e:
            logger.error(f"  ✖️ Upsert failed for batch {batch_i//batch_size + 1}: {e}")

    logger.info(f"Completed embedding & upserting {total} chunks.")
