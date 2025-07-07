from fastapi import APIRouter, Depends, HTTPException
from app.services.llama_service import LlamaService
from app.utils.db import get_db
from sqlalchemy.orm import Session
from app.models.transaction import Transaction
from pydantic import BaseModel

router = APIRouter()

class ChatRequest(BaseModel):
    message: str

def get_transactions_text(db: Session, limit: int = 50) -> str:
    """Fetch transactions as formatted text using SQLAlchemy"""
    transactions = db.query(Transaction).order_by(Transaction.LoadDate.desc()).limit(limit).all()
    
    if not transactions:
        return "No transactions found."
    
    # Format as Markdown table
    headers = ["TransactionID", "FacilityType", "Region", "Vendor", "Year", "Month", "LoadDate"]
    
    table = "| " + " | ".join(headers) + " |\n"
    table += "|" + "|".join(["---"] * len(headers)) + "|\n"
    
    for transaction in transactions:
        row_data = [
            transaction.TransactionID,
            transaction.FacilityType,
            transaction.Region,
            transaction.Vendor,
            str(transaction.Year),
            str(transaction.Month),
            str(transaction.LoadDate)
        ]
        table += "| " + " | ".join(row_data) + " |\n"
    
    return table

@router.post("/chat")
async def chat_with_data(request: ChatRequest, db: Session = Depends(get_db)):
    """Enhanced chat endpoint with transaction context"""
    try:
        transactions = get_transactions_text(db)
        newline = "\n"  # Extract backslash from f-string
        
        prompt = f"""Analyze these healthcare transactions and answer the user query:
{transactions}

User Question: {request.message}

Provide a concise response with:
1. Direct answer
2. Relevant transaction examples
3. Any data patterns observed"""
        
        # Count transactions properly
        transaction_count = transactions.count(newline) - 2 if transactions.count(newline) > 2 else 0
        
        return {
            "response": LlamaService.query(prompt),
            "context": f"Analyzed {transaction_count} transactions"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))