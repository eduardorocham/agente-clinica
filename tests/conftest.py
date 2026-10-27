"""Ambiente isolado para os testes: agenda em memória e LLM falso. As variáveis
precisam ser definidas antes de importar ``src.config`` (variáveis de ambiente
têm precedência sobre o ``.env``)."""

import os

os.environ.update({
    "GEMINI_API_KEY": "teste",
    "CALENDARIO_BACKEND": "memoria",
    "FUSO_HORARIO": "America/Sao_Paulo",
    "LANGSMITH_TRACING": "false",
    "WHATSAPP_ACCESS_TOKEN": "token-teste",
    "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
    "WHATSAPP_VERIFY_TOKEN": "verifica-teste",
    "WHATSAPP_APP_SECRET": "segredo-teste",
})

import pytest  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from src.agents import graph  # noqa: E402
from src.calendario import CalendarioEmMemoria, obter_calendario  # noqa: E402


class LLMRoteirizado:
    """Devolve as respostas na ordem e guarda o que recebeu em cada chamada."""

    def __init__(self, *respostas: AIMessage) -> None:
        self.respostas = list(respostas)
        self.historicos: list[list] = []
        self.entradas: list[dict] = []

    def __call__(self, entrada: dict) -> AIMessage:
        self.entradas.append(entrada)
        self.historicos.append(list(entrada["messages"]))
        return self.respostas.pop(0)


@pytest.fixture
def anyio_backend():
    """Testes ``@pytest.mark.anyio`` rodam só no asyncio (plugin de pytest do anyio)."""
    return "asyncio"


@pytest.fixture
def calendario() -> CalendarioEmMemoria:
    """Agenda vazia, a mesma que as tools recebem de ``obter_calendario()``."""
    obter_calendario.cache_clear()
    yield obter_calendario()
    obter_calendario.cache_clear()


@pytest.fixture
def app_grafo():
    return graph.compilar_grafo(InMemorySaver())


@pytest.fixture
def roteirizar(monkeypatch):
    """Troca o LLM pelas respostas dadas, em ordem (o resto do grafo é o de produção)."""
    def _roteirizar(*respostas: AIMessage) -> LLMRoteirizado:
        llm = LLMRoteirizado(*respostas)
        monkeypatch.setattr(graph, "cadeia_agente", RunnableLambda(llm))
        return llm
    return _roteirizar
