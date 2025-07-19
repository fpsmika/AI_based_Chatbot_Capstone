from pydantic import BaseModel, Field

class ChatQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language question from the user.")

    class Config:
        schema_extra = {
            "example": {
                "query": "What was the total spend on Famotidine in Q1 2025?"
            }
        }
