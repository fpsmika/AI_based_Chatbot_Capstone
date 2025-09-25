from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from uuid import uuid4
import json
import logging

from app.utils.db import get_db
from app.services.sql_service import get_sql_service
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Pydantic models
class ChatMessage(BaseModel):
    type: str
    content: str
    context: Optional[str] = None
    suggestions: Optional[List[str]] = []
    sources: Optional[List[Dict[str, Any]]] = []

class FileInfo(BaseModel):
    name: str
    batch_id: str
    rows_loaded: int
    uploaded_at: str

class ChatSession(BaseModel):
    id: str
    title: str
    created_at: str
    message_count: int
    updated_at: str

class CreateChatResponse(BaseModel):
    chat_id: str
    status: str

# Initialize tables on startup
def init_chat_tables():
    """Initialize chat history tables if they don't exist"""
    try:
        sql_service = get_sql_service()
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Create chat_sessions table
            create_chat_table = """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_sessions' AND xtype='U')
            CREATE TABLE chat_sessions (
                chat_id NVARCHAR(50) PRIMARY KEY,
                session_id NVARCHAR(50) NOT NULL,
                user_id NVARCHAR(50),
                title NVARCHAR(255),
                created_at DATETIME2 DEFAULT GETUTCDATE(),
                updated_at DATETIME2 DEFAULT GETUTCDATE(),
                message_count INT DEFAULT 0,
                file_info NVARCHAR(MAX),
                metadata NVARCHAR(MAX)
            );
            """
            cursor.execute(create_chat_table)
            
            # Create chat_messages table
            create_messages_table = """
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_messages' AND xtype='U')
            CREATE TABLE chat_messages (
                message_id NVARCHAR(50) PRIMARY KEY,
                chat_id NVARCHAR(50) NOT NULL,
                message_type NVARCHAR(20) NOT NULL,
                content NVARCHAR(MAX),
                timestamp DATETIME2 DEFAULT GETUTCDATE(),
                context NVARCHAR(MAX),
                suggestions NVARCHAR(MAX),
                sources NVARCHAR(MAX),
                metadata NVARCHAR(MAX),
                FOREIGN KEY (chat_id) REFERENCES chat_sessions(chat_id) ON DELETE CASCADE
            );
            """
            cursor.execute(create_messages_table)
            
            # Create indexes separately to avoid errors if they already exist
            try:
                cursor.execute("CREATE INDEX IX_chats_session_id ON chat_sessions(session_id)")
            except:
                pass
            
            try:
                cursor.execute("CREATE INDEX IX_chats_created_at ON chat_sessions(created_at DESC)")
            except:
                pass
            
            try:
                cursor.execute("CREATE INDEX IX_messages_chat_id ON chat_messages(chat_id)")
            except:
                pass
            
            try:
                cursor.execute("CREATE INDEX IX_messages_timestamp ON chat_messages(timestamp)")
            except:
                pass
            
            conn.commit()
            cursor.close()
            logger.info("Chat history tables initialized successfully")
            
    except Exception as e:
        logger.error(f"Failed to initialize chat tables: {e}")
        # Don't raise the exception - let the app continue

# Call init on module load
try:
    init_chat_tables()
except Exception as e:
    logger.warning(f"Could not initialize chat tables on startup: {e}")

@router.post("/cosmos/chats/{session_id}/create", response_model=CreateChatResponse)
async def create_chat(session_id: str):
    """Create a new chat session"""
    try:
        sql_service = get_sql_service()
        chat_id = str(uuid4())
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # First ensure tables exist
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_sessions' AND xtype='U')
                CREATE TABLE chat_sessions (
                    chat_id NVARCHAR(50) PRIMARY KEY,
                    session_id NVARCHAR(50) NOT NULL,
                    user_id NVARCHAR(50),
                    title NVARCHAR(255),
                    created_at DATETIME2 DEFAULT GETUTCDATE(),
                    updated_at DATETIME2 DEFAULT GETUTCDATE(),
                    message_count INT DEFAULT 0,
                    file_info NVARCHAR(MAX),
                    metadata NVARCHAR(MAX)
                );
            """)
            
            # Insert new chat
            query = """
            INSERT INTO chat_sessions (chat_id, session_id, user_id, title, created_at, updated_at, message_count)
            VALUES (?, ?, ?, ?, GETUTCDATE(), GETUTCDATE(), 0)
            """
            
            cursor.execute(query, (chat_id, session_id, None, "New Chat"))
            conn.commit()
            cursor.close()
        
        logger.info(f"Created new chat session: {chat_id}")
        return CreateChatResponse(chat_id=chat_id, status="success")
        
    except Exception as e:
        logger.error(f"Failed to create chat session: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cosmos/chats/{session_id}")
async def get_chats(session_id: str, limit: int = 50):
    """Get all chats for a session"""
    try:
        sql_service = get_sql_service()
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if table exists first
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'chat_sessions'
            """)
            
            if cursor.fetchone()[0] == 0:
                # Table doesn't exist, return empty list
                return {"chats": []}
            
            query = """
            SELECT TOP (?) 
                chat_id, title, created_at, message_count, updated_at, file_info
            FROM chat_sessions
            WHERE session_id = ?
            ORDER BY created_at DESC
            """
            
            cursor.execute(query, (limit, session_id))
            
            chats = []
            for row in cursor.fetchall():
                chat = {
                    "id": row[0],
                    "title": row[1] or "Untitled Chat",
                    "created_at": row[2].isoformat() if row[2] else datetime.utcnow().isoformat(),
                    "message_count": row[3] or 0,
                    "updated_at": row[4].isoformat() if row[4] else row[2].isoformat() if row[2] else datetime.utcnow().isoformat()
                }
                
                # Parse file_info if it exists
                if row[5]:
                    try:
                        chat["file_info"] = json.loads(row[5])
                    except:
                        pass
                
                chats.append(chat)
            
            cursor.close()
            return {"chats": chats}
            
    except Exception as e:
        logger.error(f"Failed to get chats: {e}")
        # Return empty list instead of raising error
        return {"chats": []}

@router.get("/cosmos/chats/{session_id}/{chat_id}")
async def get_chat_messages(session_id: str, chat_id: str):
    """Get all messages for a specific chat"""
    try:
        sql_service = get_sql_service()
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Ensure messages table exists
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_messages' AND xtype='U')
                CREATE TABLE chat_messages (
                    message_id NVARCHAR(50) PRIMARY KEY,
                    chat_id NVARCHAR(50) NOT NULL,
                    message_type NVARCHAR(20) NOT NULL,
                    content NVARCHAR(MAX),
                    timestamp DATETIME2 DEFAULT GETUTCDATE(),
                    context NVARCHAR(MAX),
                    suggestions NVARCHAR(MAX),
                    sources NVARCHAR(MAX),
                    metadata NVARCHAR(MAX)
                );
            """)
            
            # Verify chat belongs to session
            cursor.execute(
                "SELECT session_id FROM chat_sessions WHERE chat_id = ?",
                (chat_id,)
            )
            result = cursor.fetchone()
            if not result or result[0] != session_id:
                raise HTTPException(status_code=403, detail="Chat not found in session")
            
            # Get messages
            query = """
            SELECT 
                message_id, message_type, content, timestamp, 
                context, suggestions, sources
            FROM chat_messages
            WHERE chat_id = ?
            ORDER BY timestamp ASC
            """
            
            cursor.execute(query, (chat_id,))
            
            messages = []
            for row in cursor.fetchall():
                msg = {
                    "id": row[0],
                    "type": row[1],
                    "content": row[2] or "",
                    "timestamp": row[3].isoformat() if row[3] else datetime.utcnow().isoformat(),
                    "context": row[4]
                }
                
                # Parse JSON fields
                try:
                    msg["suggestions"] = json.loads(row[5]) if row[5] else []
                except:
                    msg["suggestions"] = []
                
                try:
                    msg["sources"] = json.loads(row[6]) if row[6] else []
                except:
                    msg["sources"] = []
                
                messages.append(msg)
            
            # Get chat info
            cursor.execute(
                """
                SELECT chat_id, title, created_at, message_count, updated_at, file_info
                FROM chat_sessions
                WHERE chat_id = ?
                """,
                (chat_id,)
            )
            
            chat_row = cursor.fetchone()
            chat_info = None
            if chat_row:
                chat_info = {
                    "id": chat_row[0],
                    "title": chat_row[1] or "Untitled Chat",
                    "created_at": chat_row[2].isoformat() if chat_row[2] else datetime.utcnow().isoformat(),
                    "message_count": chat_row[3] or 0,
                    "updated_at": chat_row[4].isoformat() if chat_row[4] else datetime.utcnow().isoformat()
                }
                
                if chat_row[5]:
                    try:
                        chat_info["file_info"] = json.loads(chat_row[5])
                    except:
                        pass
            
            cursor.close()
            
            return {
                "messages": messages,
                "chat_info": chat_info
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chat messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cosmos/chats/{chat_id}/messages")
async def save_message(chat_id: str, message: ChatMessage):
    """Save a message to a chat"""
    try:
        sql_service = get_sql_service()
        message_id = str(uuid4())
        
        # Convert lists/dicts to JSON strings for storage
        suggestions_json = json.dumps(message.suggestions)
        sources_json = json.dumps(message.sources)
        metadata_json = json.dumps({})
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Ensure messages table exists
            cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='chat_messages' AND xtype='U')
                CREATE TABLE chat_messages (
                    message_id NVARCHAR(50) PRIMARY KEY,
                    chat_id NVARCHAR(50) NOT NULL,
                    message_type NVARCHAR(20) NOT NULL,
                    content NVARCHAR(MAX),
                    timestamp DATETIME2 DEFAULT GETUTCDATE(),
                    context NVARCHAR(MAX),
                    suggestions NVARCHAR(MAX),
                    sources NVARCHAR(MAX),
                    metadata NVARCHAR(MAX)
                );
            """)
            
            query = """
            INSERT INTO chat_messages (
                message_id, chat_id, message_type, content, timestamp, 
                context, suggestions, sources, metadata
            )
            VALUES (?, ?, ?, ?, GETUTCDATE(), ?, ?, ?, ?)
            """
            
            cursor.execute(query, (
                message_id,
                chat_id,
                message.type,
                message.content,
                message.context,
                suggestions_json,
                sources_json,
                metadata_json
            ))
            
            # Update chat session
            update_query = """
            UPDATE chat_sessions 
            SET message_count = message_count + 1, 
                updated_at = GETUTCDATE()
            WHERE chat_id = ?
            """
            cursor.execute(update_query, (chat_id,))
            
            # Update title if it's the first user message
            if message.type == "user" and message.content:
                check_query = "SELECT message_count, title FROM chat_sessions WHERE chat_id = ?"
                cursor.execute(check_query, (chat_id,))
                result = cursor.fetchone()
                
                if result and result[0] <= 2 and result[1] == "New Chat":
                    content = message.content
                    title = content[:50] + "..." if len(content) > 50 else content
                    title_query = "UPDATE chat_sessions SET title = ? WHERE chat_id = ?"
                    cursor.execute(title_query, (title, chat_id))
            
            conn.commit()
            cursor.close()
        
        return {"message_id": message_id, "status": "success"}
        
    except Exception as e:
        logger.error(f"Failed to save message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/cosmos/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat and all its messages"""
    try:
        sql_service = get_sql_service()
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Delete messages first (in case CASCADE doesn't work)
            cursor.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
            
            # Delete chat
            cursor.execute("DELETE FROM chat_sessions WHERE chat_id = ?", (chat_id,))
            
            conn.commit()
            cursor.close()
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Failed to delete chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/cosmos/chats/{chat_id}/file-info")
async def update_file_info(chat_id: str, file_info: FileInfo):
    """Update file information for a chat"""
    try:
        sql_service = get_sql_service()
        file_info_json = json.dumps(file_info.dict())
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            query = """
            UPDATE chat_sessions 
            SET file_info = ?, updated_at = GETUTCDATE()
            WHERE chat_id = ?
            """
            
            cursor.execute(query, (file_info_json, chat_id))
            conn.commit()
            cursor.close()
        
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Failed to update file info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cosmos/chats/{session_id}/search")
async def search_chats(session_id: str, q: str):
    """Search chats by content"""
    try:
        if not q or len(q) < 2:
            raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
        
        sql_service = get_sql_service()
        search_term = f"%{q}%"
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            search_query = """
            SELECT DISTINCT c.chat_id, c.title, c.created_at, c.message_count
            FROM chat_sessions c
            LEFT JOIN chat_messages m ON c.chat_id = m.chat_id
            WHERE c.session_id = ? 
            AND (m.content LIKE ? OR c.title LIKE ?)
            ORDER BY c.updated_at DESC
            """
            
            cursor.execute(search_query, (session_id, search_term, search_term))
            
            chats = []
            for row in cursor.fetchall():
                chats.append({
                    "id": row[0],
                    "title": row[1] or "Untitled Chat",
                    "created_at": row[2].isoformat() if row[2] else datetime.utcnow().isoformat(),
                    "message_count": row[3] or 0
                })
            
            cursor.close()
            
            return {"results": chats, "query": q}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to search chats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cosmos/health")
async def chat_history_health():
    """Health check for chat history service"""
    try:
        sql_service = get_sql_service()
        
        with sql_service._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if tables exist
            cursor.execute("""
                SELECT COUNT(*) 
                FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME IN ('chat_sessions', 'chat_messages')
            """)
            
            table_count = cursor.fetchone()[0]
            cursor.close()
            
            return {
                "status": "healthy" if table_count == 2 else "initializing",
                "tables_exist": table_count == 2,
                "message": "Chat history service is operational" if table_count == 2 else "Tables being created"
            }
            
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }