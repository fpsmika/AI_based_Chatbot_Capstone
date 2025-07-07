from llama_cpp import Llama
from app.core.config import settings

class AIService:
    _instance = None

    def __init__(self):
        self.model = Llama(
            model_path=settings.LLAMA_MODEL_PATH,
            n_ctx=2048,  # Context window size
            n_gpu_layers=40 if settings.USE_GPU else 0
        )

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

def get_ai_model():
    """FastAPI dependency injection"""
    return AIService.get_instance().model