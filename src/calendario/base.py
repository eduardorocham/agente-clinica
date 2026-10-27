from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class Intervalo:
    inicio: datetime
    fim: datetime

    def sobrepoe(self, outro: "Intervalo") -> bool:
        return self.inicio < outro.fim and outro.inicio < self.fim


@dataclass(frozen=True)
class NovoEvento:
    medico_id: str
    titulo: str
    descricao: str
    inicio: datetime
    fim: datetime


@dataclass(frozen=True)
class EventoCriado:
    id: str
    link: str | None = None


class Calendario(Protocol):
    """Agenda da clínica.

    Um evento pertence a um médico (``medico_id``) ou a ninguém. Eventos sem
    médico — feriados, reformas, bloqueios criados à mão na agenda — ocupam o
    horário de todos os médicos.
    """

    def ocupados(self, medico_id: str, inicio: datetime, fim: datetime) -> list[Intervalo]:
        """Intervalos ocupados do médico que tocam o período ``[inicio, fim)``."""
        ...

    def criar_evento(self, evento: NovoEvento) -> EventoCriado:
        """Cria o evento de uma consulta na agenda."""
        ...
