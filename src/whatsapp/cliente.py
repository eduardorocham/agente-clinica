"""Envio de mensagens pela WhatsApp Cloud API (Graph API da Meta)."""

import logging
import re

import httpx

from src.errors import AgenteExternalError

logger = logging.getLogger(__name__)

LIMITE_CARACTERES = 4096  # tamanho máximo do corpo de uma mensagem de texto
_GRAPH_URL = "https://graph.facebook.com"


def para_whatsapp(texto: str) -> str:
    """Adapta o markdown que o LLM costuma gerar à formatação do WhatsApp."""
    texto = re.sub(r"\*\*(.+?)\*\*", r"*\1*", texto)  # **negrito** -> *negrito*
    texto = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", texto, flags=re.MULTILINE)  # títulos
    return texto.strip()


def dividir(texto: str, limite: int = LIMITE_CARACTERES) -> list[str]:
    """Quebra textos longos em partes de até ``limite`` caracteres, de preferência entre parágrafos."""
    partes = []
    while len(texto) > limite:
        corte = texto.rfind("\n", 0, limite)
        if corte <= 0:
            corte = texto.rfind(" ", 0, limite)
        if corte <= 0:
            corte = limite
        partes.append(texto[:corte].rstrip())
        texto = texto[corte:].lstrip()
    return [*partes, texto] if texto else partes


class WhatsAppCliente:
    def __init__(self, access_token: str, phone_number_id: str, api_version: str) -> None:
        self._http = httpx.AsyncClient(
            base_url=f"{_GRAPH_URL}/{api_version}/{phone_number_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )

    async def enviar_texto(self, telefone: str, texto: str) -> None:
        """Envia a resposta ao paciente (dividida se passar do limite do WhatsApp).

        Raises:
            AgenteExternalError: Se a Graph API recusar ou estiver inacessível.
        """
        for parte in dividir(para_whatsapp(texto)):
            await self._post({
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": telefone,
                "type": "text",
                "text": {"preview_url": False, "body": parte},
            })
        logger.info("whatsapp: resposta enviada para ...%s", telefone[-4:])

    async def marcar_como_lida(self, mensagem_id: str) -> None:
        """Marca a mensagem como lida (tique azul) e mostra "digitando..." ao paciente.

        É só cosmético: falhas são logadas e ignoradas.
        """
        try:
            await self._post({
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": mensagem_id,
                "typing_indicator": {"type": "text"},
            })
        except AgenteExternalError:
            logger.warning("whatsapp: não foi possível marcar a mensagem como lida")

    async def fechar(self) -> None:
        await self._http.aclose()

    async def _post(self, corpo: dict) -> None:
        try:
            resposta = await self._http.post("/messages", json=corpo)
            resposta.raise_for_status()
        except httpx.HTTPStatusError as erro:
            # o corpo de erro da Graph API explica o motivo (token expirado, número fora da janela de 24h...)
            logger.error(
                "whatsapp: Graph API respondeu %s: %s",
                erro.response.status_code, erro.response.text[:500],
            )
            raise AgenteExternalError("Não foi possível enviar a mensagem pelo WhatsApp.") from erro
        except httpx.HTTPError as erro:
            logger.exception("whatsapp: falha de rede ao chamar a Graph API")
            raise AgenteExternalError("Não foi possível enviar a mensagem pelo WhatsApp.") from erro
