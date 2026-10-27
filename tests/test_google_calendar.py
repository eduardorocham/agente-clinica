"""Adaptador do Google Calendar com o cliente da API falso (sem rede)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.calendario.base import Intervalo, NovoEvento
from src.calendario.google import GoogleCalendar
from src.config import settings
from src.errors import AgenteExternalError

FZ = settings.fuso
INICIO = datetime(2026, 10, 5, 0, 0, tzinfo=FZ)
FIM = datetime(2026, 10, 6, 0, 0, tzinfo=FZ)


def evento(inicio, fim, medico_id=None, **extra):
    ev = {"start": inicio, "end": fim, **extra}
    if medico_id:
        ev["extendedProperties"] = {"private": {"medico_id": medico_id}}
    return ev


@pytest.fixture
def servico():
    with patch("src.calendario.google.build") as build:
        yield build.return_value


@pytest.fixture
def agenda(servico):
    return GoogleCalendar("clinica@group.calendar.google.com", MagicMock(), FZ)


def test_ocupados_filtra_por_medico_e_pagina(agenda, servico):
    servico.events().list().execute.side_effect = [
        {"items": [
            evento({"dateTime": "2026-10-05T09:00:00-03:00"}, {"dateTime": "2026-10-05T09:30:00-03:00"}, "MED-01"),
            evento({"dateTime": "2026-10-05T10:00:00-03:00"}, {"dateTime": "2026-10-05T10:30:00-03:00"}, "MED-02"),
        ], "nextPageToken": "p2"},
        {"items": [
            # sem médico: bloqueia todos
            evento({"dateTime": "2026-10-05T12:00:00-03:00"}, {"dateTime": "2026-10-05T13:00:00-03:00"}),
            # marcado como "Disponível": não bloqueia
            evento({"dateTime": "2026-10-05T14:00:00-03:00"}, {"dateTime": "2026-10-05T15:00:00-03:00"},
                   transparency="transparent"),
            # dia inteiro
            evento({"date": "2026-10-05"}, {"date": "2026-10-06"}, "MED-01"),
        ]},
    ]

    ocupados = agenda.ocupados("MED-01", INICIO, FIM)

    assert ocupados == [
        Intervalo(datetime(2026, 10, 5, 9, 0, tzinfo=FZ), datetime(2026, 10, 5, 9, 30, tzinfo=FZ)),
        Intervalo(datetime(2026, 10, 5, 12, 0, tzinfo=FZ), datetime(2026, 10, 5, 13, 0, tzinfo=FZ)),
        Intervalo(INICIO, FIM),
    ]
    chamadas = [c.kwargs for c in servico.events().list.call_args_list if c.kwargs]
    assert chamadas[0]["calendarId"] == "clinica@group.calendar.google.com"
    assert chamadas[0]["singleEvents"] is True
    assert [c["pageToken"] for c in chamadas] == [None, "p2"]


def test_criar_evento_grava_medico_nas_propriedades(agenda, servico):
    servico.events().insert().execute.return_value = {"id": "abc", "htmlLink": "https://calendar/abc"}

    criado = agenda.criar_evento(NovoEvento(
        medico_id="MED-01", titulo="Consulta", descricao="Paciente: João",
        inicio=datetime(2026, 10, 5, 9, 0, tzinfo=FZ), fim=datetime(2026, 10, 5, 9, 30, tzinfo=FZ),
    ))

    assert (criado.id, criado.link) == ("abc", "https://calendar/abc")
    corpo = servico.events().insert.call_args.kwargs["body"]
    assert corpo["extendedProperties"] == {"private": {"medico_id": "MED-01"}}
    assert corpo["start"] == {"dateTime": "2026-10-05T09:00:00-03:00", "timeZone": "America/Sao_Paulo"}


def test_falha_da_api_vira_erro_de_dominio(agenda, servico):
    servico.events().list().execute.side_effect = OSError("sem rede")
    with pytest.raises(AgenteExternalError, match="agenda da clínica"):
        agenda.ocupados("MED-01", INICIO, FIM)
