import logging

from langchain_core.tools import tool

from src.calendario import obter_calendario
from src.services import agenda_service

logger = logging.getLogger(__name__)

# Erros de domínio (AgenteError) propagam e viram ToolMessage no ToolNode (ver graph.py)


@tool
def consultar_horarios_disponiveis(medico_id: str, data_inicial: str, dias: int = 1) -> dict:
    """Consulta na agenda os horários livres de um médico.

    Args:
        medico_id: Código do médico (ex.: MED-01).
        data_inicial: Primeiro dia da consulta, no formato AAAA-MM-DD.
        dias: Quantos dias consultar a partir de data_inicial (1 a 7).
    """
    logger.info(
        "consultar_horarios_disponiveis: medico_id=%s, data_inicial=%s, dias=%s",
        medico_id, data_inicial, dias,
    )
    horarios = agenda_service.horarios_disponiveis(obter_calendario(), medico_id, data_inicial, dias)
    return horarios.model_dump(mode="json")


@tool
def agendar_consulta(
    medico_id: str,
    data_hora: str,
    nome_paciente: str,
    telefone: str,
    convenio: str,
) -> dict:
    """Marca uma consulta na agenda da clínica. Use só depois que o paciente confirmar os dados.

    Args:
        medico_id: Código do médico (ex.: MED-01).
        data_hora: Início da consulta no formato AAAA-MM-DDTHH:MM, um dos horários livres.
        nome_paciente: Nome completo do paciente.
        telefone: Telefone com DDD.
        convenio: Nome do convênio ou "Particular".
    """
    logger.info("agendar_consulta: medico_id=%s, data_hora=%s", medico_id, data_hora)
    consulta = agenda_service.agendar_consulta(
        obter_calendario(), medico_id, data_hora, nome_paciente, telefone, convenio
    )
    return consulta.model_dump(mode="json")


TOOLS = [consultar_horarios_disponiveis, agendar_consulta]
