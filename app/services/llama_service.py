import requests
from fastapi import HTTPException
from app.core.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class LlamaService:
    @staticmethod
    def query(
        prompt: str, 
        max_tokens: int = 500, 
        temperature: float = 0.7,
        model: Optional[str] = None
    ) -> str:
        """
        Query OpenRouter API with proper error handling and logging
        
        Args:
            prompt: The user's input prompt
            max_tokens: Maximum tokens to generate
            temperature: Creativity control (0-1)
            model: Override default model from settings
            
        Returns:
            Generated response content
            
        Raises:
            HTTPException: For API errors with proper status codes
        """
        # Use provided model or fall back to settings
        model = model or settings.LLAMA_MODEL
        
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "HTTP-Referer": "http://localhost:8000",  # Match your actual domain
            "X-Title": settings.PROJECT_NAME,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            logger.info(f"Sending request to OpenRouter API with model: {model}")
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            # Enhanced error logging
            if response.status_code != 200:
                logger.error(
                    f"OpenRouter API error - Status: {response.status_code}\n"
                    f"Response: {response.text}\n"
                    f"Headers: {response.headers}"
                )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Handle response variations
            if "choices" in response_data and response_data["choices"]:
                return response_data["choices"][0]["message"]["content"]
            elif "message" in response_data:
                return response_data["message"]["content"]
            else:
                error_msg = f"Unexpected OpenRouter response: {response_data}"
                logger.error(error_msg)
                raise HTTPException(
                    status_code=502,
                    detail="AI service returned unexpected format"
                )
                
        except requests.exceptions.HTTPError as e:
            error_detail = f"OpenRouter API HTTP Error: {str(e)}"
            if e.response is not None:
                error_detail += f" - {e.response.text}"
            logger.error(error_detail)
            raise HTTPException(
                status_code=e.response.status_code if e.response else 502,
                detail=error_detail
            )
            
        except requests.exceptions.RequestException as e:
            logger.error(f"OpenRouter connection error: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="AI service unavailable"
            )
            
        except Exception as e:
            logger.error(f"Unexpected error in LlamaService: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail="Internal AI processing error"
            )