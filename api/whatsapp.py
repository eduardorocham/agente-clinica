"""Webhook da WhatsApp Cloud API.

Configure na Meta a URL ``https://<seu-domínio>/webhook/whatsapp`` com o mesmo
``WHATSAPP_VERIFY_TOKEN`` do ``.env`` e assine o campo ``messages``.
"""

import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from src.config import settings
from src.services.whatsapp_service import AtendimentoWhatsApp
from src.whatsapp import assinatura_valida, extrair_mensagens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook/whatsapp", tags=["whatsapp"])


def _atendimento(request: Request) -> AtendimentoWhatsApp:
    atendimento = request.app.state.whatsapp
    if atendimento is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "WhatsApp não configurado no servidor.")
    return atendimento


@router.get("", response_class=PlainTextResponse)
async def verificar_webhook(
    modo: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    desafio: str = Query("", alias="hub.challenge"),
):
    """Handshake feito pela Meta ao cadastrar o webhook: devolve o ``hub.challenge``."""
    if modo == "subscribe" and settings.whatsapp_verify_token and token == settings.whatsapp_verify_token:
        logger.info("whatsapp: webhook verificado pela Meta")
        return desafio
    logger.warning("whatsapp: tentativa de verificação do webhook com token inválido")
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Token de verificação inválido.")


@router.post("")
async def receber_webhook(request: Request, background: BackgroundTasks):
    """Recebe eventos da Meta e responde 200 na hora.

    O agente pode levar vários segundos (LLM + Google Calendar) e a Meta reenvia o
    evento se a resposta demorar, então o atendimento roda em background.
    """
    atendimento = _atendimento(request)
    corpo = await request.body()
    if not assinatura_valida(corpo, request.headers.get("X-Hub-Signature-256"), settings.whatsapp_app_secret):
        logger.warning("whatsapp: webhook com assinatura inválida rejeitado")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Assinatura inválida.")

    try:
        payload = json.loads(corpo)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido.") from None

    for mensagem in extrair_mensagens(payload):
        if atendimento.registrar(mensagem.id):
            logger.info("whatsapp: mensagem recebida de ...%s (tipo=%s)", mensagem.telefone[-4:], mensagem.tipo)
            background.add_task(atendimento.atender, mensagem)
    return {"status": "recebido"}
