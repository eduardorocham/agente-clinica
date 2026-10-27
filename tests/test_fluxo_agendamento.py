"""Fluxo de agendamento de ponta a ponta no grafo real, com o LLM roteirizado.

Cada teste define as respostas que o "LLM" vai dar, em ordem. O resto (roteador,
ToolNode, tools, service e agenda em memória) é o código de produção. O LLM
roteirizado e o grafo vêm do conftest.py.
"""

import json
import uuid
from datetime import datetime, timedelta

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from src.config import settings
from src.services import chat_service

pytestmark = pytest.mark.anyio


def proxima_segunda() -> str:
    hoje = datetime.now(settings.fuso).date()
    return (hoje + timedelta(days=7 - hoje.weekday())).isoformat()


def chamada(nome, **args) -> dict:
    return {"name": nome, "args": args, "id": f"call_{uuid.uuid4().hex[:8]}"}


def pede(*tool_calls) -> AIMessage:
    return AIMessage(content="", tool_calls=list(tool_calls))


def responde(texto="Pronto!") -> AIMessage:
    return AIMessage(content=texto)


def tool_messages(llm) -> list[dict]:
    """Conteúdo (JSON) das ToolMessages vistas pelo LLM na última chamada."""
    return [json.loads(m.content) for m in llm.historicos[-1] if isinstance(m, ToolMessage)]


async def test_consulta_horarios_e_agenda(app_grafo, roteirizar, calendario):
    segunda = proxima_segunda()
    dados = {"nome_paciente": "João da Silva", "telefone": "11912345678", "convenio": "Amil"}

    roteirizar(
        pede(chamada("consultar_horarios_disponiveis", medico_id="MED-01", data_inicial=segunda)),
        responde("Tenho 08:00, 08:30... Qual prefere?"),
    )
    primeira = await chat_service.conversar(app_grafo, "Quero clínico geral na segunda")
    assert primeira.resposta == "Tenho 08:00, 08:30... Qual prefere?"

    llm = roteirizar(
        pede(chamada("agendar_consulta", medico_id="MED-01", data_hora=f"{segunda}T08:30", **dados)),
        responde("Consulta marcada!"),
    )
    segunda_msg = await chat_service.conversar(app_grafo, "08:30, pode confirmar", primeira.conversa_id)

    assert segunda_msg.resposta == "Consulta marcada!"
    # o histórico da conversa foi mantido entre as mensagens
    [horarios, agendada] = tool_messages(llm)
    assert horarios["dias"][0]["horarios_livres"][:2] == ["08:00", "08:30"]
    assert agendada["medico"] == "Dra. Helena Martins"
    assert agendada["inicio"].startswith(f"{segunda}T08:30")
    [(medico_id, intervalo, _)] = calendario.eventos.values()
    assert medico_id == "MED-01" and intervalo.inicio.isoformat().startswith(f"{segunda}T08:30")


async def test_erro_da_tool_volta_ao_llm(app_grafo, roteirizar, calendario):
    segunda = proxima_segunda()
    llm = roteirizar(
        pede(chamada(
            "agendar_consulta", medico_id="MED-01", data_hora=f"{segunda}T13:00",
            nome_paciente="João da Silva", telefone="11912345678", convenio="Amil",
        )),
        responde("Esse horário não existe, veja outros."),
    )

    saida = await chat_service.conversar(app_grafo, "Marca às 13h")

    assert saida.resposta == "Esse horário não existe, veja outros."
    [erro] = tool_messages(llm)
    assert erro["tipo"] == "AgenteValidationError"
    assert calendario.eventos == {}


async def test_argumentos_invalidos_do_llm(app_grafo, roteirizar, calendario):
    llm = roteirizar(
        pede(chamada("consultar_horarios_disponiveis", medico_id="MED-01")),  # falta data_inicial
        responde("Para qual dia?"),
    )
    await chat_service.conversar(app_grafo, "Horários da Dra. Helena")
    assert tool_messages(llm)[0]["tipo"] == "ArgumentosInvalidos"
