
import pandas as pd
import uuid
from app.utils.supply_data_parser import csv_to_purchase_chunks
from app.services.vector_search_service import store_embedding
from app.services.embedding_service import embed_bulk_text   

def process_and_embed_csv(file_path: str):
    """
    Read a CSV, convert rows to text chunks, embed them, and store them in Cosmos DB.
    """
    print(f"📥 Loading file: {file_path}")
    df = pd.read_csv(file_path)

    # Step 1: Convert rows to meaningful text chunks
    chunks = csv_to_purchase_chunks(df)  # List[Dict] with "text" and "metadata"

    # Step 2: Embed text
    texts = [chunk["text"] for chunk in chunks]
    embeddings = embed_bulk_text(texts)

    # Step 3: Store each embedding with metadata in Cosmos DB
    for i, embedding in enumerate(embeddings):
        metadata = chunks[i]["metadata"]
        doc_id = str(uuid.uuid4())
        store_embedding(doc_id=doc_id, embedding=embedding, metadata=metadata)

    print(f"✅ Embedded and uploaded {len(chunks)} rows to Cosmos DB.")

