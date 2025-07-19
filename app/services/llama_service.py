import requests
from fastapi import HTTPException
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class LlamaService:
    @staticmethod
    def query(prompt: str, max_tokens: int = 500, temperature: float = 0.7):
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://your-app-domain.com",  # Required by OpenRouter
            "X-Title": "MedMine Supply Chatbot",  # Required by OpenRouter
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": settings.LLAMA_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            logger.info(f"Sending request to OpenRouter API with model: {settings.LLAMA_MODEL}")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Log the response status and headers for debugging
            logger.debug(f"OpenRouter response status: {response.status_code}")
            logger.debug(f"OpenRouter response headers: {response.headers}")
            
            response.raise_for_status()
            response_data = response.json()
            
            # Handle different response formats
            if "choices" in response_data and len(response_data["choices"]) > 0:
                return response_data["choices"][0]["message"]["content"]
            elif "message" in response_data:
                return response_data["message"]["content"]
            else:
                logger.error(f"Unexpected OpenRouter response format: {response_data}")
                raise HTTPException(
                    status_code=502,
                    detail="Unexpected response format from AI service"
                )
                
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenRouter API request failed: {str(e)}")
            raise HTTPException(
                status_code=502,
                detail=f"AI service connection error: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Unexpected error in LlamaService: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"AI service processing error: {str(e)}"
            )