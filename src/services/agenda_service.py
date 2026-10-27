"""Regras de agenda da clínica: horários livres e marcação de consultas.

Horário livre = slot da grade do médico (ver :mod:`src.clinica.dados`) que
ainda não passou e não se sobrepõe a nenhum evento da agenda. Toda regra é
verificada aqui, no servidor: o LLM só escolhe entre os horários devolvidos e
não consegue marcar fora da grade, no passado ou em cima de outra consulta.
"""

import logging
import re
import threading
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from src.calendario import Calendario, Intervalo, NovoEvento
from src.clinica import (
    CLINICA,
    DIAS_DA_SEMANA,
    Medico,
    formatar_reais,
    normalizar_texto,
    obter_medico,
)
from src.config import settings
from src.errors import AgenteConflictError, AgenteValidationError

logger = logging.getLogger(__name__)

MAX_DIAS_POR_CONSULTA = 7
HORIZONTE_AGENDAMENTO_DIAS = 60
PARTICULAR = "Particular"

# conferir se o horário está livre e criar o evento precisa ser atômico, senão
# dois pacientes podem marcar o mesmo horário (vale para um processo só — é uma demo)
_lock_agendamento = threading.Lock()


class DiaDisponivel(BaseModel):
    data: date
    dia_semana: str
    medico_atende: bool
    horarios_livres: list[str]


class HorariosDisponiveis(BaseModel):
    medico_id: str
    medico: str
    especialidade: str
    duracao_consulta_min: int
    dias: list[DiaDisponivel]


class ConsultaAgendada(BaseModel):
    evento_id: str
    medico_id: str
    medico: str
    especialidade: str
    inicio: datetime
    fim: datetime
    paciente: str
    telefone: str
    convenio: str
    valor_consulta: str | None
    link_agenda: str | None = None


def _agora() -> datetime:
    return datetime.now(settings.fuso)


def ler_data(texto: str) -> date:
    try:
        return date.fromisoformat(texto.strip())
    except ValueError:
        raise AgenteValidationError(f"Data inválida: {texto!r}. Use o formato AAAA-MM-DD.") from None


def ler_data_hora(texto: str) -> datetime:
    """Data e hora no fuso da clínica. Sem fuso na entrada, assume o da clínica."""
    try:
        instante = datetime.fromisoformat(texto.strip())
    except ValueError:
        raise AgenteValidationError(
            f"Data/hora inválida: {texto!r}. Use o formato AAAA-MM-DDTHH:MM."
        ) from None
    if instante.tzinfo is None:
        return instante.replace(tzinfo=settings.fuso)
    return instante.astimezone(settings.fuso)


def _slots_do_dia(medico: Medico, dia: date) -> Iterator[Intervalo]:
    duracao = timedelta(minutes=medico.duracao_consulta)
    for faixa in medico.grade.get(dia.weekday(), ()):
        inicio = datetime.combine(dia, faixa.inicio, tzinfo=settings.fuso)
        limite = datetime.combine(dia, faixa.fim, tzinfo=settings.fuso)
        while inicio + duracao <= limite:
            yield Intervalo(inicio, inicio + duracao)
            inicio += duracao


def _validar_periodo(dia: date, agora: datetime) -> None:
    if dia < agora.date():
        raise AgenteValidationError("Não é possível consultar ou agendar em datas passadas.")
    if dia > agora.date() + timedelta(days=HORIZONTE_AGENDAMENTO_DIAS):
        raise AgenteValidationError(
            f"A agenda está aberta apenas para os próximos {HORIZONTE_AGENDAMENTO_DIAS} dias."
        )


def horarios_disponiveis(
    calendario: Calendario,
    medico_id: str,
    data_inicial: str,
    dias: int = 1,
    agora: datetime | None = None,
) -> HorariosDisponiveis:
    """Horários livres do médico a partir de ``data_inicial`` (inclusive), por ``dias`` dias.

    Raises:
        AgenteNotFoundError: Se o médico não existir.
        AgenteValidationError: Se a data for inválida, passada ou além do horizonte.
        AgenteExternalError: Se a agenda estiver inacessível.
    """
    medico = obter_medico(medico_id)
    agora = agora or _agora()
    if not 1 <= dias <= MAX_DIAS_POR_CONSULTA:
        raise AgenteValidationError(f"Consulte entre 1 e {MAX_DIAS_POR_CONSULTA} dias por vez.")
    primeiro_dia = ler_data(data_inicial)
    _validar_periodo(primeiro_dia, agora)

    datas = [primeiro_dia + timedelta(days=i) for i in range(dias)]
    ocupados = calendario.ocupados(
        medico.id,
        datetime.combine(datas[0], time.min, tzinfo=settings.fuso),
        datetime.combine(datas[-1] + timedelta(days=1), time.min, tzinfo=settings.fuso),
    )

    resultado = []
    for dia in datas:
        livres = [
            slot.inicio.strftime("%H:%M")
            for slot in _slots_do_dia(medico, dia)
            if slot.inicio > agora and not any(slot.sobrepoe(o) for o in ocupados)
        ]
        resultado.append(DiaDisponivel(
            data=dia,
            dia_semana=DIAS_DA_SEMANA[dia.weekday()],
            medico_atende=dia.weekday() in medico.grade,
            horarios_livres=livres,
        ))

    logger.info(
        "horarios_disponiveis: %s de %s por %d dia(s) -> %d horário(s) livre(s)",
        medico.id, primeiro_dia, dias, sum(len(d.horarios_livres) for d in resultado),
    )
    return HorariosDisponiveis(
        medico_id=medico.id,
        medico=medico.nome,
        especialidade=medico.especialidade,
        duracao_consulta_min=medico.duracao_consulta,
        dias=resultado,
    )


def _validar_nome(nome: str) -> str:
    nome = " ".join(nome.split())
    if len(nome) < 3:
        raise AgenteValidationError("Informe o nome completo do paciente.")
    return nome


def _validar_telefone(telefone: str) -> str:
    digitos = re.sub(r"\D", "", telefone)
    if not 10 <= len(digitos) <= 13:
        raise AgenteValidationError("Telefone inválido. Informe DDD e número, ex.: (11) 91234-5678.")
    return digitos


def _validar_convenio(convenio: str) -> str:
    aceitos = (*CLINICA["convenios"], PARTICULAR)
    for nome in aceitos:
        if normalizar_texto(nome) == normalizar_texto(convenio):
            return nome
    raise AgenteValidationError(
        f"Convênio {convenio!r} não é aceito. Aceitos: {', '.join(aceitos)}."
    )


def agendar_consulta(
    calendario: Calendario,
    medico_id: str,
    data_hora: str,
    nome_paciente: str,
    telefone: str,
    convenio: str,
    agora: datetime | None = None,
) -> ConsultaAgendada:
    """Marca a consulta na agenda depois de conferir grade, data e disponibilidade.

    Raises:
        AgenteNotFoundError: Se o médico não existir.
        AgenteValidationError: Se algum dado for inválido ou o horário não estiver na grade.
        AgenteConflictError: Se o horário já estiver ocupado.
        AgenteExternalError: Se a agenda estiver inacessível.
    """
    medico = obter_medico(medico_id)
    agora = agora or _agora()
    inicio = ler_data_hora(data_hora)
    nome = _validar_nome(nome_paciente)
    telefone = _validar_telefone(telefone)
    convenio = _validar_convenio(convenio)

    _validar_periodo(inicio.date(), agora)
    if inicio <= agora:
        raise AgenteValidationError("Esse horário já passou. Escolha um horário futuro.")

    slot = next((s for s in _slots_do_dia(medico, inicio.date()) if s.inicio == inicio), None)
    if slot is None:
        raise AgenteValidationError(
            f"{medico.nome} não tem horário de consulta às {inicio:%H:%M} de {inicio:%d/%m/%Y}. "
            "Consulte os horários disponíveis antes de agendar."
        )

    with _lock_agendamento:
        if any(slot.sobrepoe(o) for o in calendario.ocupados(medico.id, slot.inicio, slot.fim)):
            logger.info("agendar_consulta: horário ocupado (%s, %s)", medico.id, slot.inicio)
            raise AgenteConflictError(
                "Esse horário não está mais disponível. Consulte os horários livres novamente."
            )
        evento = calendario.criar_evento(NovoEvento(
            medico_id=medico.id,
            titulo=f"Consulta {medico.especialidade} — {nome} ({medico.nome})",
            descricao=(
                f"Paciente: {nome}\nTelefone: {telefone}\nConvênio: {convenio}\n"
                f"Médico: {medico.nome} ({medico.crm})\nAgendado pelo assistente virtual."
            ),
            inicio=slot.inicio,
            fim=slot.fim,
        ))

    logger.info("agendar_consulta: consulta marcada (%s, %s, evento=%s)", medico.id, slot.inicio, evento.id)
    return ConsultaAgendada(
        evento_id=evento.id,
        medico_id=medico.id,
        medico=medico.nome,
        especialidade=medico.especialidade,
        inicio=slot.inicio,
        fim=slot.fim,
        paciente=nome,
        telefone=telefone,
        convenio=convenio,
        valor_consulta=formatar_reais(medico.valor_consulta) if convenio == PARTICULAR else None,
        link_agenda=evento.link,
    )
