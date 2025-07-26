from app.services.embedding_service import embed_text
-from app.services.vector_search_service import query_similar_chunks
+from app.services.vector_search_service import query_similar_chunks_sql as query_similar_chunks
from app.services.ai_service import generate_response
from typing import Dict, Any, List
import datetime

class ChatService:

    def __init__(self, top_k: int = 5):
        self.top_k = top_k

    def process_query(self, user_query: str) -> Dict[str, Any]:
        # Embed user query
        query_vector = embed_text(user_query)

        # Run native vector search in Cosmos SQL‑API
        top_chunks = query_similar_chunks(query_vector, top_k=self.top_k)

        # Build context string from returned metadata
        context = self.build_context_string(top_chunks)
        prompt = (
            f"Answer the following hospital supply chain question using the provided data context.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {user_query}\n"
            f"Answer:"
        )

        answer = generate_response(prompt)

        return {
            "answer": answer.strip(),
            # sources now include full metadata objects
            "sources": [chunk['metadata'] for chunk in top_chunks],
            "timestamp": datetime.datetime.utcnow().isoformat()
        }

    def build_context_string(self, chunks: List[Dict[str, Any]]) -> str:
        context_list = []
        for chunk in chunks:
            # Use meaningful fields from metadata, e.g. item_desc
            item_desc = chunk.get('metadata', {}).get('item_desc', 'N/A')
            # Optionally include other metadata like transaction_id
            tx_id = chunk.get('metadata', {}).get('transaction_id', '')
            context_list.append(f"- {item_desc} (Transaction: {tx_id})")

        return "\n".join(context_list)
