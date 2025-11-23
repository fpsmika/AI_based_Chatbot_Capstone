from openai import AzureOpenAI
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
        Query Azure OpenAI API with proper error handling and logging
        
        Args:
            prompt: The user's input prompt
            max_tokens: Maximum tokens to generate
            temperature: Creativity control (0-1)
            model: Override default deployment (optional)
            
        Returns:
            Generated response content
            
        Raises:
            HTTPException: For API errors with proper status codes
        """
        try:
            client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
            )
            
            deployment = model or settings.AZURE_OPENAI_DEPLOYMENT
            
            logger.info(f"Sending request to Azure OpenAI with deployment: {deployment}")
            
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            
            return response.choices[0].message.content
                
        except Exception as e:
            logger.error(f"Azure OpenAI error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"AI service error: {str(e)}"
            )