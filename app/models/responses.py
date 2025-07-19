from pydantic import BaseModel, Field
from typing import List, Dict, Optional

class ChatResponse(BaseModel):
    answer: str = Field(..., description="The generated AI response to the user's question.")
    sources: List[Dict] = Field(..., description="List of metadata from retrieved vector search context.")
    timestamp: str = Field(..., description="ISO timestamp of the response generation.")

    class Config:
        schema_extra = {
            "example": {
                "answer": "Based on the records, the hospital spent $5,000 on Famotidine in Q1 2025.",
                "sources": [
                    {
                        "TransactionID": "2018259684",
                        "Vendor": "Cencora",
                        "ItemDesc": "FAMOTIDINE 20MG TABS UD 10X10",
                        "Quantity": 100,
                        "TotalSpend": 5000,
                        "Month": "1",
                        "Year": "2025"
                    }
                ],
                "timestamp": "2025-07-06T22:10:00Z"
            }
        }
