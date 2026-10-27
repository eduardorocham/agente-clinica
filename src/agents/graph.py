import json
import logging
import time
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolInvocationError

from src.agents.state import EstadoAgente
from src.agents.tools import TOOLS
from src.config import settings
from src.errors import AgenteError, AgenteExternalError, AgenteUnavailableError
from src.llm import (
    LLM_RETRY_POLICY,
    get_chat_model,
    is_quota_exhausted,
    segundos_ate_reset_da_quota,
)
from src.prompts import descrever_canal, prompt_atendimento

logger = logging.getLogger(__name__)

llm = get_chat_model().bind_tools(TOOLS)
cadeia_agente = prompt_atendimento | llm


async def chamar_agente(state: EstadoAgente):
    logger.info(
        "chamar_agente: invocando LLM (model=%s, qtd_mensagens=%d)",
        settings.gemini_model, len(state["messages"]),
    )
    inicio = time.perf_counter()
    try:
        resposta = await cadeia_agente.ainvoke({
            "messages": state["messages"],
            "canal": descrever_canal(
                state.get("canal"), state.get("telefone_paciente"), state.get("nome_perfil")
            ),
        })
    except Exception as erro:
        # Retentativas ficam a cargo da RetryPolicy do nó (ver add_node abaixo),
        # que inspeciona a causa original deste AgenteExternalError. Quota esgotada
        # não é repetida e vira AgenteUnavailableError (503 + Retry-After na API).
        logger.exception("chamar_agente: falha ao invocar LLM")
        if is_quota_exhausted(erro):
            raise AgenteUnavailableError(
                "O serviço de IA atingiu o limite de uso e está indisponível no momento. "
                "Tente novamente mais tarde.",
                retry_after=segundos_ate_reset_da_quota(),
            ) from erro
        raise AgenteExternalError(
            "Não foi possível processar sua mensagem no momento. Tente novamente."
        ) from erro
    duracao = time.perf_counter() - inicio

    tool_calls = getattr(resposta, "tool_calls", None) or []
    logger.info(
        "chamar_agente: resposta do LLM recebida (duracao=%.2fs, tool_calls=%s, tokens=%s)",
        duracao,
        [call["name"] for call in tool_calls],
        getattr(resposta, "usage_metadata", None),
    )
    return {"messages": [resposta]}


def decidir_proximo_passo(state: EstadoAgente):
    ultima = state["messages"][-1]
    if not ultima.tool_calls:
        logger.info("decidir_proximo_passo: finalizando fluxo")
        return "finalizar"
    logger.info("decidir_proximo_passo: seguindo para ferramentas (%s)", [c["name"] for c in ultima.tool_calls])
    return "ferramentas"


def _erro_para_tool_message(erro: AgenteError | ToolInvocationError) -> str:
    """Converte um erro levantado por uma tool em conteúdo de ToolMessage.

    O ToolNode infere pela anotação quais erros são tratados aqui: erros de domínio
    (``AgenteError``, incluindo falha do Google Calendar) e argumentos inválidos
    gerados pelo LLM (``ToolInvocationError``). O LLM recebe ``{"erro", "tipo"}``
    (mesmo corpo da API REST) e pode corrigir a chamada ou explicar o problema ao
    paciente. Qualquer outra exceção é bug e propaga.
    """
    if isinstance(erro, ToolInvocationError):
        logger.warning("ferramentas: LLM chamou %s com argumentos inválidos", erro.tool_name)
        return json.dumps({"erro": erro.message, "tipo": "ArgumentosInvalidos"}, ensure_ascii=False)
    logger.info("ferramentas: tool retornou erro de domínio (%s)", type(erro).__name__)
    return json.dumps(erro.to_dict(), ensure_ascii=False)


ferramentas_node = ToolNode(TOOLS, handle_tool_errors=_erro_para_tool_message)

grafo = StateGraph(EstadoAgente)
grafo.add_node("agente", chamar_agente, retry_policy=LLM_RETRY_POLICY)
grafo.add_node("ferramentas", ferramentas_node)

grafo.set_entry_point("agente")
grafo.add_conditional_edges(
    "agente",
    decidir_proximo_passo,
    {"ferramentas": "ferramentas", "finalizar": END},
)
grafo.add_edge("ferramentas", "agente")


def compilar_grafo(checkpointer: BaseCheckpointSaver[Any]) -> CompiledStateGraph:
    """Compila o grafo com o checkpointer que guarda o histórico de cada conversa.

    As tools (síncronas, com chamadas HTTP ao Google Calendar) rodam no thread
    pool do LangGraph, sem bloquear o event loop.
    """
    return grafo.compile(checkpointer=checkpointer)
