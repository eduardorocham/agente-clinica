"""Agenda da clínica no Google Calendar (API v3).

Todas as consultas ficam em uma única agenda (``GOOGLE_CALENDAR_ID``). Cada
evento de consulta guarda o código do médico em
``extendedProperties.private.medico_id``; eventos sem essa propriedade (ex.:
um feriado criado à mão na agenda) bloqueiam o horário de todos os médicos.
"""

import json
import logging
import threading
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.credentials import Credentials
from googleapiclient.discovery import build

from src.calendario.base import EventoCriado, Intervalo, NovoEvento
from src.errors import AgenteExternalError

logger = logging.getLogger(__name__)

ESCOPOS = ["https://www.googleapis.com/auth/calendar.events"]
_PROPRIEDADE_MEDICO = "medico_id"
_ERRO_AGENDA = "Não foi possível acessar a agenda da clínica no momento. Tente novamente."


def carregar_credenciais(arquivo_credenciais: str, arquivo_token: str) -> Credentials:
    """Credenciais a partir do JSON baixado do Google Cloud Console.

    Aceita uma service account (a agenda precisa estar compartilhada com o
    e-mail dela, com permissão de "Fazer alterações nos eventos") ou um cliente
    OAuth do tipo "App para computador" — nesse caso o login abre no navegador
    na primeira execução e o token fica salvo em ``arquivo_token``.
    """
    caminho = Path(arquivo_credenciais)
    if not caminho.exists():
        raise RuntimeError(
            f"Arquivo de credenciais do Google não encontrado: {caminho}. "
            "Configure GOOGLE_CREDENTIALS_FILE ou use CALENDARIO_BACKEND=memoria."
        )
    info = json.loads(caminho.read_text())

    if info.get("type") == "service_account":
        from google.oauth2 import service_account

        logger.info("google_calendar: autenticando com service account (%s)", info.get("client_email"))
        return service_account.Credentials.from_service_account_info(info, scopes=ESCOPOS)

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials as CredenciaisUsuario
    from google_auth_oauthlib.flow import InstalledAppFlow

    token = Path(arquivo_token)
    credenciais = (
        CredenciaisUsuario.from_authorized_user_file(str(token), ESCOPOS) if token.exists() else None
    )
    if credenciais and credenciais.valid:
        return credenciais
    if credenciais and credenciais.expired and credenciais.refresh_token:
        logger.info("google_calendar: renovando token OAuth")
        credenciais.refresh(Request())
    else:
        logger.info("google_calendar: abrindo login OAuth no navegador")
        credenciais = InstalledAppFlow.from_client_config(info, ESCOPOS).run_local_server(port=0)
    token.write_text(credenciais.to_json())
    return credenciais


class GoogleCalendar:
    def __init__(self, calendar_id: str, credenciais: Credentials, fuso: ZoneInfo) -> None:
        self._calendar_id = calendar_id
        self._fuso = fuso
        self._servico = build("calendar", "v3", credentials=credenciais, cache_discovery=False)
        # o cliente HTTP (httplib2) do googleapiclient não é thread-safe e as
        # tools rodam no thread pool do LangGraph
        self._lock = threading.Lock()

    def ocupados(self, medico_id: str, inicio: datetime, fim: datetime) -> list[Intervalo]:
        intervalos = []
        for evento in self._listar_eventos(inicio, fim):
            if evento.get("transparency") == "transparent":  # marcado como "Disponível"
                continue
            dono = evento.get("extendedProperties", {}).get("private", {}).get(_PROPRIEDADE_MEDICO)
            if dono is not None and dono != medico_id:
                continue
            intervalos.append(Intervalo(self._instante(evento["start"]), self._instante(evento["end"])))
        logger.info(
            "google_calendar: %d intervalo(s) ocupado(s) para %s entre %s e %s",
            len(intervalos), medico_id, inicio.isoformat(), fim.isoformat(),
        )
        return intervalos

    def criar_evento(self, evento: NovoEvento) -> EventoCriado:
        corpo = {
            "summary": evento.titulo,
            "description": evento.descricao,
            "start": {"dateTime": evento.inicio.isoformat(), "timeZone": self._fuso.key},
            "end": {"dateTime": evento.fim.isoformat(), "timeZone": self._fuso.key},
            "extendedProperties": {"private": {_PROPRIEDADE_MEDICO: evento.medico_id}},
        }
        try:
            with self._lock:
                criado = self._servico.events().insert(
                    calendarId=self._calendar_id, body=corpo
                ).execute()
        except Exception as erro:
            logger.exception("google_calendar: falha ao criar evento")
            raise AgenteExternalError(_ERRO_AGENDA) from erro
        logger.info("google_calendar: evento criado (id=%s)", criado["id"])
        return EventoCriado(id=criado["id"], link=criado.get("htmlLink"))

    def _listar_eventos(self, inicio: datetime, fim: datetime) -> list[dict]:
        eventos: list[dict] = []
        pagina = None
        try:
            with self._lock:
                while True:
                    resposta = self._servico.events().list(
                        calendarId=self._calendar_id,
                        timeMin=inicio.isoformat(),
                        timeMax=fim.isoformat(),
                        singleEvents=True,  # expande eventos recorrentes
                        orderBy="startTime",
                        pageToken=pagina,
                    ).execute()
                    eventos.extend(resposta.get("items", []))
                    pagina = resposta.get("nextPageToken")
                    if not pagina:
                        return eventos
        except Exception as erro:
            logger.exception("google_calendar: falha ao listar eventos")
            raise AgenteExternalError(_ERRO_AGENDA) from erro

    def _instante(self, campo: dict) -> datetime:
        """Início/fim de um evento; eventos de dia inteiro só têm ``date``."""
        if "dateTime" in campo:
            return datetime.fromisoformat(campo["dateTime"])
        return datetime.combine(date.fromisoformat(campo["date"]), time.min, tzinfo=self._fuso)
