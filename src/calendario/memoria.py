import threading
import uuid
from datetime import datetime

from src.calendario.base import EventoCriado, Intervalo, NovoEvento


class CalendarioEmMemoria:
    """Agenda em memória, para testes e para rodar a demo sem credenciais do Google."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.eventos: dict[str, tuple[str | None, Intervalo, NovoEvento | None]] = {}

    def bloquear(self, inicio: datetime, fim: datetime, medico_id: str | None = None) -> str:
        """Ocupa um período sem consulta (ex.: feriado). ``medico_id=None`` bloqueia todos."""
        return self._guardar(medico_id, Intervalo(inicio, fim), None)

    def ocupados(self, medico_id: str, inicio: datetime, fim: datetime) -> list[Intervalo]:
        periodo = Intervalo(inicio, fim)
        with self._lock:
            return [
                intervalo
                for dono, intervalo, _ in self.eventos.values()
                if dono in (None, medico_id) and intervalo.sobrepoe(periodo)
            ]

    def criar_evento(self, evento: NovoEvento) -> EventoCriado:
        evento_id = self._guardar(evento.medico_id, Intervalo(evento.inicio, evento.fim), evento)
        return EventoCriado(id=evento_id)

    def _guardar(self, medico_id: str | None, intervalo: Intervalo, evento: NovoEvento | None) -> str:
        evento_id = uuid.uuid4().hex
        with self._lock:
            self.eventos[evento_id] = (medico_id, intervalo, evento)
        return evento_id
