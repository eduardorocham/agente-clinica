import logging

from fastapi import APIRouter, Depends, Request
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from src.services import chat_service
from src.services.chat_service import ConversaOut

logger = logging.getLogger(__name__)

# Erros de domínio (AgenteError) propagam e são convertidos em HTTP por api/errors.py
router = APIRouter(tags=["chat"])


class MensagemInput(BaseModel):
    conversa_id: str | None = None
    mensagem: str


def get_grafo(request: Request) -> CompiledStateGraph:
    """Dependência do FastAPI: o grafo compilado no lifespan (ver api/routes.py)."""
    return request.app.state.grafo


@router.post("/conversar", response_model=ConversaOut)
async def conversar(payload: MensagemInput, grafo: CompiledStateGraph = Depends(get_grafo)):
    return await chat_service.conversar(grafo, payload.mensagem, payload.conversa_id)
