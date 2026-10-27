"""Leitura do webhook da WhatsApp Cloud API (Meta).

Formato do payload: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MensagemRecebida:
    id: str
    telefone: str  # wa_id: só dígitos, com DDI (ex.: 5511988887777)
    tipo: str  # text, audio, image, ...
    texto: str | None
    nome_perfil: str | None


def assinatura_valida(corpo: bytes, assinatura: str | None, app_secret: str) -> bool:
    """Confere o header ``X-Hub-Signature-256`` (HMAC-SHA256 do corpo com a chave do app)."""
    if not assinatura or not assinatura.startswith("sha256="):
        return False
    esperada = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, assinatura.removeprefix("sha256="))


def extrair_mensagens(payload: dict) -> list[MensagemRecebida]:
    """Mensagens de pacientes no payload. Atualizações de status (enviada, lida...) são ignoradas."""
    mensagens = []
    for entrada in payload.get("entry", []):
        for mudanca in entrada.get("changes", []):
            valor = mudanca.get("value", {})
            nomes = {
                contato.get("wa_id"): contato.get("profile", {}).get("name")
                for contato in valor.get("contacts", [])
            }
            for msg in valor.get("messages", []):
                tipo = msg.get("type", "")
                mensagens.append(MensagemRecebida(
                    id=msg["id"],
                    telefone=msg["from"],
                    tipo=tipo,
                    texto=_texto(msg, tipo),
                    nome_perfil=nomes.get(msg["from"]),
                ))
    return mensagens


def _texto(msg: dict, tipo: str) -> str | None:
    if tipo == "text":
        return msg.get("text", {}).get("body")
    if tipo == "button":  # resposta a botão de template
        return msg.get("button", {}).get("text")
    if tipo == "interactive":  # resposta a botões/listas
        interativo = msg.get("interactive", {})
        resposta = interativo.get("button_reply") or interativo.get("list_reply") or {}
        return resposta.get("title")
    return None
