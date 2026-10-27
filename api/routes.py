import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver

from api.chat import router as chat_router
from api.errors import registrar_handlers_de_erro
from api.whatsapp import router as whatsapp_router
from src.agents.graph import compilar_grafo
from src.calendario import obter_calendario
from src.config import settings
from src.logging_config import setup_logging
from src.services.whatsapp_service import AtendimentoWhatsApp
from src.whatsapp import WhatsAppCliente

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # conecta à agenda na subida: credencial inválida falha aqui, não na 1ª conversa
    obter_calendario()
    # histórico das conversas só em memória: é uma demo, nada é gravado em banco
    app.state.grafo = compilar_grafo(InMemorySaver())

    cliente = None
    app.state.whatsapp = None
    if settings.whatsapp_configurado:
        cliente = WhatsAppCliente(
            settings.whatsapp_access_token,
            settings.whatsapp_phone_number_id,
            settings.whatsapp_api_version,
        )
        app.state.whatsapp = AtendimentoWhatsApp(
            app.state.grafo, cliente, timedelta(minutes=settings.whatsapp_sessao_minutos)
        )
        logger.info("whatsapp: canal ativo (phone_number_id=%s)", settings.whatsapp_phone_number_id)
    else:
        logger.warning("whatsapp: canal desativado (variáveis WHATSAPP_* incompletas no .env)")

    try:
        yield
    finally:
        if cliente is not None:
            await cliente.fechar()


app = FastAPI(title="Agente Clínica Vida Plena", lifespan=lifespan)
registrar_handlers_de_erro(app)
app.include_router(chat_router)
app.include_router(whatsapp_router)
