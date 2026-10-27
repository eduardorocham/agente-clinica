import logging
from functools import lru_cache

from src.calendario.base import Calendario, EventoCriado, Intervalo, NovoEvento
from src.calendario.memoria import CalendarioEmMemoria
from src.config import settings

logger = logging.getLogger(__name__)


@lru_cache
def obter_calendario() -> Calendario:
    """Agenda configurada por CALENDARIO_BACKEND (google | memoria), criada uma vez só."""
    backend = settings.calendario_backend.lower().strip()

    if backend == "memoria":
        logger.info("calendario: usando agenda em memória (não persiste entre reinícios)")
        return CalendarioEmMemoria()

    if backend == "google":
        from src.calendario.google import GoogleCalendar, carregar_credenciais

        credenciais = carregar_credenciais(
            settings.google_credentials_file, settings.google_token_file
        )
        logger.info("calendario: usando Google Calendar (calendar_id=%s)", settings.google_calendar_id)
        return GoogleCalendar(settings.google_calendar_id, credenciais, settings.fuso)

    raise ValueError(f"CALENDARIO_BACKEND desconhecido: '{backend}'. Use 'google' ou 'memoria'.")


__all__ = [
    "Calendario",
    "CalendarioEmMemoria",
    "EventoCriado",
    "Intervalo",
    "NovoEvento",
    "obter_calendario",
]
