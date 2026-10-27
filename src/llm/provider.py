import logging

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import settings

logger = logging.getLogger(__name__)


def get_chat_model() -> BaseChatModel:
    """Retorna o chat model do Google (Gemini API) configurado por GEMINI_MODEL."""
    if not settings.gemini_api_key:
        logger.error("get_chat_model: GEMINI_API_KEY não configurada")
        raise RuntimeError("GEMINI_API_KEY não configurada.")

    logger.info("get_chat_model: inicializando ChatGoogleGenerativeAI (model=%s)", settings.gemini_model)
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.gemini_api_key,
        max_retries=0,  # retry fica só na RetryPolicy do nó (src/llm/retry.py)
    )
