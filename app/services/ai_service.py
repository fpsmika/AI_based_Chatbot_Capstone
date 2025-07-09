import os
import requests
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

LLAMA_API_URL = os.getenv("LLAMA_API_URL")        
LLAMA_API_KEY = os.getenv("LLAMA_API_KEY", "")    

DEFAULT_MAX_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "256"))
DEFAULT_MODEL_NAME = os.getenv("LLAMA_MODEL_NAME", "llama2")

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {LLAMA_API_KEY}" if LLAMA_API_KEY else ""
}


def generate_response(prompt: str, max_tokens: int = DEFAULT_MAX_TOKENS, **kwargs: Dict[str, Any]) -> str:
    """
    Generate a completion using the external LLaMA API.
    Compatible with Ollama, Together AI, or other hosted endpoints.
    """
    payload = {
        "model": DEFAULT_MODEL_NAME,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        **kwargs
    }

    try:
        response = requests.post(LLAMA_API_URL, json=payload, headers=HEADERS)
        response.raise_for_status()

        data = response.json()

        # If using TogetherAI or Replicate, the structure may vary
        if "choices" in data:
            return data["choices"][0]["text"].strip()
        elif "response" in data:
            return data["response"].strip()
        else:
            return str(data).strip()

    except requests.RequestException as e:
        print(f" LLaMA API error: {e}")
        return " Error generating response from LLaMA API."
