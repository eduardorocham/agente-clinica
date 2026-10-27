"""Atendimento pelo WhatsApp: liga as mensagens do webhook ao agente e devolve a resposta.

- A Meta pode entregar a mesma mensagem mais de uma vez: cada id é processado uma vez só.
- Mensagens do mesmo paciente são atendidas em ordem, uma de cada vez (senão duas
  execuções do grafo disputariam o mesmo histórico).
- Cada número de telefone tem uma conversa; depois de ``sessao`` sem mensagens, a
  próxima começa uma conversa nova, com histórico limpo.
"""

import asyncio
import logging
import time
import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Callable
from datetime import timedelta

from langgraph.graph.state import CompiledStateGraph

from src.errors import AgenteError
from src.services import chat_service
from src.whatsapp import MensagemRecebida, WhatsAppCliente

logger = logging.getLogger(__name__)

MENSAGEM_SO_TEXTO = (
    "Por enquanto só consigo ler mensagens de texto. 🙂 "
    "Pode me escrever como posso ajudar?"
)
MENSAGEM_ERRO = (
    "Desculpe, tive um problema para responder agora. "
    "Tente novamente em instantes ou ligue para a clínica."
)
_MAX_IDS_PROCESSADOS = 5000


class AtendimentoWhatsApp:
    def __init__(
        self,
        grafo: CompiledStateGraph,
        cliente: WhatsAppCliente,
        sessao: timedelta,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._grafo = grafo
        self._cliente = cliente
        self._sessao = sessao.total_seconds()
        self._relogio = relogio
        self._ids_processados: OrderedDict[str, None] = OrderedDict()
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._conversas: dict[str, tuple[str, float]] = {}  # telefone -> (conversa_id, última mensagem)

    def registrar(self, mensagem_id: str) -> bool:
        """Registra o id da mensagem; ``False`` se ela já tinha chegado antes (reentrega da Meta)."""
        if mensagem_id in self._ids_processados:
            logger.info("whatsapp: mensagem repetida ignorada (id=%s)", mensagem_id)
            return False
        self._ids_processados[mensagem_id] = None
        if len(self._ids_processados) > _MAX_IDS_PROCESSADOS:
            self._ids_processados.popitem(last=False)
        return True

    async def atender(self, mensagem: MensagemRecebida) -> None:
        """Responde uma mensagem do paciente. Roda em background: nunca propaga exceção."""
        try:
            async with self._locks[mensagem.telefone]:
                await self._atender(mensagem)
        except Exception:
            logger.exception("whatsapp: falha inesperada ao atender mensagem (id=%s)", mensagem.id)

    async def _atender(self, mensagem: MensagemRecebida) -> None:
        await self._cliente.marcar_como_lida(mensagem.id)

        if not (mensagem.texto or "").strip():
            logger.info("whatsapp: mensagem do tipo %r não suportada", mensagem.tipo)
            await self._responder(mensagem.telefone, MENSAGEM_SO_TEXTO)
            return

        try:
            saida = await chat_service.conversar(
                self._grafo,
                mensagem.texto,
                self._conversa_do_paciente(mensagem.telefone),
                dados_canal={
                    "canal": "whatsapp",
                    "telefone_paciente": mensagem.telefone,
                    "nome_perfil": mensagem.nome_perfil,
                },
            )
            resposta = saida.resposta
        except AgenteError as erro:
            # mensagens de AgenteError são escritas para o paciente (ver src/errors.py)
            resposta = erro.mensagem
        except Exception:
            logger.exception("whatsapp: falha inesperada no agente")
            resposta = MENSAGEM_ERRO

        await self._responder(mensagem.telefone, resposta or MENSAGEM_ERRO)

    async def _responder(self, telefone: str, texto: str) -> None:
        try:
            await self._cliente.enviar_texto(telefone, texto)
        except AgenteError:
            pass  # já logado pelo cliente, com o motivo devolvido pela Graph API

    def _conversa_do_paciente(self, telefone: str) -> str:
        agora = self._relogio()
        conversa_id, ultima = self._conversas.get(telefone, (None, 0.0))
        if conversa_id is None or agora - ultima > self._sessao:
            conversa_id = f"whatsapp:{telefone}:{uuid.uuid4().hex[:8]}"
            logger.info("whatsapp: nova conversa para ...%s (%s)", telefone[-4:], conversa_id)
        self._conversas[telefone] = (conversa_id, agora)
        return conversa_id
