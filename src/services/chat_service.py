import logging
import uuid

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel

from src.security import sanitize_input

logger = logging.getLogger(__name__)


class ConversaOut(BaseModel):
    conversa_id: str
    resposta: str


async def conversar(
    app_grafo: CompiledStateGraph,
    mensagem: str,
    conversa_id: str | None = None,
    dados_canal: dict | None = None,
) -> ConversaOut:
    """Envia a mensagem do paciente ao agente, criando a conversa se necessário.

    O histórico fica no checkpointer em memória, indexado por ``conversa_id``:
    some quando o processo reinicia (é uma demo). ``dados_canal`` (``canal``,
    ``telefone_paciente``, ``nome_perfil``) vai para o estado do grafo e o
    agente usa no prompt.

    Raises:
        AgenteExternalError: Se o LLM falhar (após retries).
    """
    nova_conversa = conversa_id is None
    conversa_id = conversa_id or str(uuid.uuid4())

    logger.info(
        "chat_service.conversar: recebendo mensagem (conversa_id=%s, nova_conversa=%s, tamanho=%d)",
        conversa_id, nova_conversa, len(mensagem),
    )

    mensagem_sanitizada = sanitize_input(mensagem)
    if mensagem_sanitizada != mensagem.strip():
        logger.warning(
            "chat_service.conversar: mensagem sanitizada por possível prompt injection (conversa_id=%s)",
            conversa_id,
        )

    resultado = await app_grafo.ainvoke(
        {"messages": [HumanMessage(content=mensagem_sanitizada)], **(dados_canal or {})},
        config={"configurable": {"thread_id": conversa_id}},
    )

    logger.info("chat_service.conversar: fluxo concluído (conversa_id=%s)", conversa_id)
    return ConversaOut(conversa_id=conversa_id, resposta=resultado["messages"][-1].text)
