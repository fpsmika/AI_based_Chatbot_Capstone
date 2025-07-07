import requests
from fastapi import HTTPException
from app.core.config import settings

class LlamaService:
    @staticmethod
    def query(prompt: str, max_tokens: int = 500):
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={
                    "model": settings.LLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            raise HTTPException(
                status_code=502,
                detail=f"AI service error: {str(e)}"
            )