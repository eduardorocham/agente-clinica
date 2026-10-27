"""Dados fictícios da clínica usados na demo: informações gerais e corpo clínico.

A grade de cada médico define quando ele atende. O que já está marcado vem do
Google Calendar; os horários livres são a grade menos os eventos da agenda
(ver :mod:`src.services.agenda_service`).
"""

import unicodedata
from dataclasses import dataclass
from datetime import time
from decimal import Decimal

from src.errors import AgenteNotFoundError

SEG, TER, QUA, QUI, SEX, SAB, DOM = range(7)
DIAS_DA_SEMANA = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)


@dataclass(frozen=True)
class Faixa:
    inicio: time
    fim: time


@dataclass(frozen=True)
class Medico:
    id: str
    nome: str
    especialidade: str
    crm: str
    duracao_consulta: int  # minutos
    valor_consulta: Decimal
    grade: dict[int, tuple[Faixa, ...]]  # dia da semana (0 = segunda) -> faixas de atendimento

    def descrever_grade(self) -> str:
        """Ex.: ``segunda-feira 08:00–12:00; quarta-feira 08:00–12:00``."""
        return "; ".join(
            f"{DIAS_DA_SEMANA[dia]} " + ", ".join(
                f"{faixa.inicio:%H:%M}–{faixa.fim:%H:%M}" for faixa in faixas
            )
            for dia, faixas in sorted(self.grade.items())
        )


def _faixa(inicio: str, fim: str) -> Faixa:
    return Faixa(time.fromisoformat(inicio), time.fromisoformat(fim))


CLINICA = {
    "nome": "Clínica Vida Plena",
    "endereco": "Av. das Palmeiras, 1500, sala 302 — Jardim Primavera, São Paulo/SP",
    "telefone": "(11) 4002-8922",
    "whatsapp": "(11) 98765-4321",
    "funcionamento": "segunda a sexta das 08:00 às 18:00; sábado das 08:00 às 12:00",
    "convenios": ("Unimed", "Bradesco Saúde", "SulAmérica", "Amil"),
    "orientacoes": (
        "Chegar com 15 minutos de antecedência, com documento com foto e carteirinha do convênio.",
        "Cancelamentos e remarcações pelo telefone ou WhatsApp com 24 horas de antecedência.",
        "Pagamento particular por Pix, cartão de débito ou crédito (até 3x).",
    ),
}

MEDICOS: dict[str, Medico] = {
    medico.id: medico
    for medico in (
        Medico(
            id="MED-01", nome="Dra. Helena Martins", especialidade="Clínica Geral",
            crm="CRM-SP 123456", duracao_consulta=30, valor_consulta=Decimal("250.00"),
            grade={
                SEG: (_faixa("08:00", "12:00"),),
                QUA: (_faixa("08:00", "12:00"),),
                SEX: (_faixa("08:00", "12:00"), _faixa("14:00", "17:00")),
            },
        ),
        Medico(
            id="MED-02", nome="Dr. Rafael Albuquerque", especialidade="Cardiologia",
            crm="CRM-SP 234567", duracao_consulta=40, valor_consulta=Decimal("380.00"),
            grade={
                TER: (_faixa("13:00", "18:00"),),
                QUI: (_faixa("13:00", "18:00"),),
            },
        ),
        Medico(
            id="MED-03", nome="Dra. Camila Nogueira", especialidade="Dermatologia",
            crm="CRM-SP 345678", duracao_consulta=30, valor_consulta=Decimal("320.00"),
            grade={
                SEG: (_faixa("14:00", "18:00"),),
                TER: (_faixa("09:00", "12:00"),),
                QUI: (_faixa("09:00", "12:00"), _faixa("14:00", "17:00")),
            },
        ),
        Medico(
            id="MED-04", nome="Dr. Paulo Mendes", especialidade="Pediatria",
            crm="CRM-SP 456789", duracao_consulta=30, valor_consulta=Decimal("280.00"),
            grade={dia: (_faixa("14:00", "18:00"),) for dia in (SEG, TER, QUA, QUI, SEX)},
        ),
        Medico(
            id="MED-05", nome="Dra. Beatriz Lima", especialidade="Ortopedia",
            crm="CRM-SP 567890", duracao_consulta=45, valor_consulta=Decimal("350.00"),
            grade={
                QUA: (_faixa("13:00", "18:15"),),
                SAB: (_faixa("08:00", "12:30"),),
            },
        ),
    )
}


def normalizar_texto(texto: str) -> str:
    """Minúsculas e sem acentos, para comparar entradas do paciente."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def formatar_reais(valor: Decimal) -> str:
    """Ex.: ``Decimal("1250.5")`` -> ``R$ 1.250,50``."""
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def obter_medico(medico_id: str) -> Medico:
    """Busca o médico pelo código (ex.: MED-01).

    Raises:
        AgenteNotFoundError: Se o código não existir.
    """
    medico = MEDICOS.get(medico_id.strip().upper())
    if medico is None:
        raise AgenteNotFoundError(
            f"Médico {medico_id!r} não encontrado. Códigos válidos: {', '.join(MEDICOS)}."
        )
    return medico
