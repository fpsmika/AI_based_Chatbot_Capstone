import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.services.ai_search_service import get_ai_search_service
from app.services.embedding_service import embed_text
import json
from uuid import uuid4

logger = logging.getLogger(__name__)

class ChatContextService:
    """Service for managing conversation context and history using the main search index"""
    
    def __init__(self):
        self.ai_search = get_ai_search_service()
        # SIMPLIFIED: Always use the main index since it has all necessary fields
        self.use_main_index = True
    
    def _get_target_index_name(self) -> str:
        """Get the target index name for chat context storage"""
        # SIMPLIFIED: Always use the main index
        return self.ai_search.index_name

    async def index_chat_message(self, message_data: Dict[str, Any]) -> bool:
        """Index a chat message using the main index schema"""
        try:
            if not self.ai_search.is_configured:
                logger.warning("AI Search not configured, skipping message indexing")
                return False
            
            # Generate embedding for the message content
            content = message_data.get("content", "")
            if not content:
                return False
            
            content_vector = embed_text(content)
            target_index = self._get_target_index_name()
            
            # FIXED: Properly format LoadDate for Azure Search
            current_time = datetime.now()
            load_date_formatted = current_time.strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # SIMPLIFIED: Always use main index schema that fits your chatbot-index-1
            doc = {
                "id": str(uuid4()),
                "content": f"Chat {message_data.get('message_type', 'message')}: {content}",
                "content_vector": content_vector,
                "batch_id": f"chat-{message_data.get('chat_id', 'unknown')}",
                "TransactionID": f"CHAT-{message_data.get('message_id', str(uuid4()))}",
                "FacilityID": "CHAT-FACILITY",
                "ItemDesc": f"Chat: {message_data.get('message_type', 'unknown')} message",
                "Manufacturer": "ChatBot",
                "Vendor": "ChatBot",
                "VendorID": "CHAT-VENDOR",
                "ManufacturerID": "CHAT-MFG",
                "ManufacturercatalogNum": "CHAT-CAT",
                "FacilityType": "ChatBot",
                "Region": "ChatBot", 
                "BedSize": "N/A",
                "Department": "ChatBot",
                "Category": "ChatBot",
                "PricePaid": 0.0,
                "TotalSpend": 0.0,
                "UnitCost": 0.0,
                "Quantity": 0,
                "Month": current_time.month,
                "Year": current_time.year,
                "LoadDate": load_date_formatted,  # FIXED: Use properly formatted date
                "metadata": json.dumps({
                    **message_data,
                    "is_chat_message": True,
                    "original_message_type": message_data.get("message_type")
                }, default=str)
            }
            
            # Upload to your existing index
            result = self.ai_search.upload_documents_to_index([doc], target_index)
            
            success = result.get("uploaded", 0) > 0
            if success:
                logger.info(f"Successfully indexed chat message {doc['id']} in {target_index}")
            else:
                logger.warning(f"Failed to index chat message: {result.get('error')}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to index chat message: {e}")
            return False

    async def _get_recent_history(self, chat_id: str, limit: int) -> List[Dict[str, Any]]:
        """Get recent conversation history from the main index"""
        try:
            target_index = self._get_target_index_name()
            
            # Search for chat messages in your main index using batch_id
            filter_expr = f"batch_id eq 'chat-{chat_id}'"
            
            results = self.ai_search.search_in_index(
                query="*",
                index_name=target_index,
                filters=filter_expr,
                top=limit * 2  # Get more to sort by timestamp
            )
            
            # Sort by LoadDate (which we use for chat timestamps)
            if results:
                try:
                    sorted_results = sorted(
                        results, 
                        key=lambda x: x.get("LoadDate", ""), 
                        reverse=True
                    )
                    return sorted_results[:limit]
                except Exception as sort_error:
                    logger.debug(f"Failed to sort results by timestamp: {sort_error}")
                    return results[:limit]
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to get recent history: {e}")
            return []

    async def get_conversation_context(
        self, 
        current_message: str, 
        chat_id: str, 
        session_id: str,
        context_limit: int = 5
    ) -> Dict[str, Any]:
        """Get comprehensive conversation context for the current message"""
        try:
            context_data = {
                "has_context": False,
                "context_summary": "",
                "recent_history": [],
                "similar_conversations": [],
                "context_embedding": None
            }
            
            if not self.ai_search.is_configured:
                logger.warning("AI Search not configured, returning empty context")
                return context_data
            
            # 1. Get recent conversation history
            recent_history = await self._get_recent_history(chat_id, context_limit)
            
            # 2. Find similar past conversations using vector search in main index
            similar_conversations = await self._find_similar_conversations(
                current_message, session_id, exclude_chat_id=chat_id
            )
            
            # 3. Build context summary
            context_summary = self._build_context_summary(
                recent_history, similar_conversations, current_message
            )
            
            context_data.update({
                "has_context": bool(recent_history or similar_conversations),
                "context_summary": context_summary,
                "recent_history": recent_history,
                "similar_conversations": similar_conversations
            })
            
            return context_data
            
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}")
            return {"has_context": False, "error": str(e)}

    async def _find_similar_conversations(
        self, 
        current_message: str, 
        session_id: str, 
        exclude_chat_id: str = None,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Find similar conversations using vector search in the main index"""
        try:
            # Generate embedding for current message
            query_vector = embed_text(current_message)
            
            # Build filter to find chat messages from this session
            filters = [f"search.ismatch('chat-', 'batch_id')"]  # Find chat messages
            if exclude_chat_id:
                filters.append(f"batch_id ne 'chat-{exclude_chat_id}'")
            filter_expr = " and ".join(filters)
            
            # Perform vector search in main index
            results = self.ai_search.vector_search_in_index(
                query_vector=query_vector,
                index_name=self.ai_search.index_name,
                filters=filter_expr,
                top=top_k
            )
            
            # Filter by minimum similarity
            filtered_results = [
                r for r in results 
                if r.get("similarity", 0) > 0.7
            ]
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Failed to find similar conversations: {e}")
            return []

    def _build_context_summary(
        self, 
        recent_history: List[Dict], 
        similar_conversations: List[Dict],
        current_message: str
    ) -> str:
        """Build a concise context summary"""
        summary_parts = []
        
        # Recent conversation context
        if recent_history:
            recent_topics = []
            for msg in recent_history[-3:]:  # Last 3 messages
                content = msg.get("content", "")[:100]
                msg_type = msg.get("message_type", "unknown")
                if content and msg_type == "user":
                    recent_topics.append(f"Asked about: {content}")
                elif content and msg_type == "assistant":
                    recent_topics.append(f"Discussed: {content}")
            
            if recent_topics:
                summary_parts.append(f"Recent conversation: {'; '.join(recent_topics)}")
        
        # Similar conversation context
        if similar_conversations:
            similar_topics = []
            for conv in similar_conversations[:2]:  # Top 2 similar
                content = conv.get("content", "")[:80]
                similarity = conv.get("similarity", 0)
                if content:
                    similar_topics.append(f"{content} (similarity: {similarity:.2f})")
            
            if similar_topics:
                summary_parts.append(f"Related past discussions: {'; '.join(similar_topics)}")
        
        return " | ".join(summary_parts) if summary_parts else ""

# Singleton instance
_chat_context_service = None

def get_chat_context_service() -> ChatContextService:
    """Get the shared chat context service instance"""
    global _chat_context_service
    if _chat_context_service is None:
        _chat_context_service = ChatContextService()
    return _chat_context_service


