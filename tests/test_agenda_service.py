"""Regras de horários livres e agendamento, com a agenda em memória e um "agora" fixo.

Grade usada: Dra. Helena Martins (MED-01), Clínica Geral, consultas de 30 min,
segunda 08:00–12:00. 2026-10-05 é uma segunda-feira.
"""

from datetime import datetime

import pytest

from src.config import settings
from src.errors import AgenteConflictError, AgenteNotFoundError, AgenteValidationError
from src.services import agenda_service

FZ = settings.fuso
AGORA = datetime(2026, 10, 1, 10, 0, tzinfo=FZ)  # quinta-feira
SEGUNDA = "2026-10-05"
SLOTS_SEGUNDA = [f"{h:02d}:{m:02d}" for h in range(8, 12) for m in (0, 30)]


def livres(calendario, medico_id="MED-01", data=SEGUNDA, dias=1, agora=AGORA):
    resultado = agenda_service.horarios_disponiveis(calendario, medico_id, data, dias, agora=agora)
    return [d.horarios_livres for d in resultado.dias]


def agendar(calendario, data_hora=f"{SEGUNDA}T09:00", medico_id="MED-01", agora=AGORA, **dados):
    dados = {"nome_paciente": "João da Silva", "telefone": "(11) 91234-5678", "convenio": "Unimed", **dados}
    return agenda_service.agendar_consulta(calendario, medico_id, data_hora, agora=agora, **dados)


def test_agenda_vazia_devolve_toda_a_grade(calendario):
    assert livres(calendario) == [SLOTS_SEGUNDA]


def test_dia_sem_atendimento_vem_vazio_e_marcado(calendario):
    resultado = agenda_service.horarios_disponiveis(calendario, "MED-01", "2026-10-06", agora=AGORA)
    assert resultado.dias[0].medico_atende is False
    assert resultado.dias[0].horarios_livres == []


def test_varios_dias(calendario):
    # segunda a quarta: Helena atende segunda e quarta, não terça
    assert livres(calendario, dias=3) == [SLOTS_SEGUNDA, [], SLOTS_SEGUNDA]


def test_consulta_marcada_ocupa_o_horario(calendario):
    agendar(calendario, f"{SEGUNDA}T09:00")
    assert "09:00" not in livres(calendario)[0]
    assert "08:30" in livres(calendario)[0] and "09:30" in livres(calendario)[0]


def test_evento_de_outro_medico_nao_bloqueia(calendario):
    calendario.bloquear(
        datetime(2026, 10, 5, 8, tzinfo=FZ), datetime(2026, 10, 5, 12, tzinfo=FZ), medico_id="MED-03"
    )
    assert livres(calendario) == [SLOTS_SEGUNDA]


def test_evento_sem_medico_bloqueia_todos(calendario):
    # ex.: "Reunião geral" criada à mão na agenda, das 10:15 às 11:00
    calendario.bloquear(datetime(2026, 10, 5, 10, 15, tzinfo=FZ), datetime(2026, 10, 5, 11, tzinfo=FZ))
    assert livres(calendario)[0] == ["08:00", "08:30", "09:00", "09:30", "11:00", "11:30"]


def test_horarios_que_ja_passaram_nao_aparecem(calendario):
    agora = datetime(2026, 10, 5, 10, 0, tzinfo=FZ)
    assert livres(calendario, agora=agora) == [["10:30", "11:00", "11:30"]]


@pytest.mark.parametrize("data, mensagem", [
    ("2026-09-30", "passadas"),
    ("2027-01-15", "próximos 60 dias"),
    ("05/10/2026", "AAAA-MM-DD"),
])
def test_datas_invalidas(calendario, data, mensagem):
    with pytest.raises(AgenteValidationError, match=mensagem):
        livres(calendario, data=data)


def test_medico_inexistente(calendario):
    with pytest.raises(AgenteNotFoundError):
        livres(calendario, medico_id="MED-99")


def test_agendar_cria_evento_na_agenda(calendario):
    consulta = agendar(calendario, convenio="particular", medico_id="med-01")

    medico_id, intervalo, evento = calendario.eventos[consulta.evento_id]
    assert medico_id == "MED-01"
    assert intervalo.inicio == datetime(2026, 10, 5, 9, 0, tzinfo=FZ)
    assert intervalo.fim == datetime(2026, 10, 5, 9, 30, tzinfo=FZ)
    assert "João da Silva" in evento.titulo and "11912345678" in evento.descricao
    assert consulta.convenio == "Particular"
    assert consulta.valor_consulta == "R$ 250,00"


def test_agendar_horario_ocupado(calendario):
    agendar(calendario)
    with pytest.raises(AgenteConflictError):
        agendar(calendario, nome_paciente="Maria Souza")
    assert len(calendario.eventos) == 1


def test_agendar_em_cima_de_bloqueio_parcial(calendario):
    calendario.bloquear(datetime(2026, 10, 5, 9, 15, tzinfo=FZ), datetime(2026, 10, 5, 9, 20, tzinfo=FZ))
    with pytest.raises(AgenteConflictError):
        agendar(calendario)


@pytest.mark.parametrize("data_hora", [
    f"{SEGUNDA}T09:10",  # fora do passo da grade
    f"{SEGUNDA}T13:00",  # fora da faixa
    "2026-10-06T09:00",  # terça: Helena não atende
])
def test_agendar_fora_da_grade(calendario, data_hora):
    with pytest.raises(AgenteValidationError, match="não tem horário"):
        agendar(calendario, data_hora)
    assert calendario.eventos == {}


def test_agendar_no_passado(calendario):
    with pytest.raises(AgenteValidationError, match="já passou"):
        agendar(calendario, agora=datetime(2026, 10, 5, 9, 0, tzinfo=FZ))


def test_agendar_com_fuso_explicito(calendario):
    # 12:00 UTC = 09:00 em São Paulo
    consulta = agendar(calendario, f"{SEGUNDA}T12:00:00+00:00")
    assert consulta.inicio == datetime(2026, 10, 5, 9, 0, tzinfo=FZ)


@pytest.mark.parametrize("dados, mensagem", [
    ({"convenio": "Plano X"}, "não é aceito"),
    ({"telefone": "1234"}, "Telefone inválido"),
    ({"nome_paciente": " J "}, "nome completo"),
])
def test_agendar_dados_invalidos(calendario, dados, mensagem):
    with pytest.raises(AgenteValidationError, match=mensagem):
        agendar(calendario, **dados)
    assert calendario.eventos == {}
