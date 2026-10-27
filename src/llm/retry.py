from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from langgraph.types import RetryPolicy

_TRANSIENT_MARKERS = (
    "503",
    "429",
    "internal error",  # 500 INTERNAL intermitente da Gemini API
    "unavailable",
    "resource_exhausted",
    "rate limit",
    "timeout",
    "connection",
)

# Quotas que não voltam em segundos: a diária do Gemini (quotaId
# "...PerDay...") e o saldo esgotado da OpenAI. Chegam como 429, mas repetir
# só gasta tempo e mais chamadas.
_QUOTA_EXHAUSTED_MARKERS = (
    "perday",
    "insufficient_quota",
)

# A quota diária do Gemini reinicia à meia-noite do horário do Pacífico.
_FUSO_RESET_QUOTA = ZoneInfo("America/Los_Angeles")


def _cadeia(exc: BaseException):
    """Percorre a exceção e sua cadeia de ``__cause__``.

    O nó do agente embrulha a exceção original do provider em um erro de
    domínio antes de propagá-la, então a causa real fica mais abaixo.
    """
    atual: BaseException | None = exc
    while atual is not None:
        yield atual
        atual = atual.__cause__


def is_quota_exhausted(exc: BaseException) -> bool:
    """Indica se o erro do LLM é quota esgotada que não se resolve em segundos."""
    return any(
        marker in str(erro).lower()
        for erro in _cadeia(exc)
        for marker in _QUOTA_EXHAUSTED_MARKERS
    )


def is_transient_error(exc: BaseException) -> bool:
    """Indica se o erro do LLM é transitório (rate limit, timeout, 5xx).

    Quota esgotada (ver :func:`is_quota_exhausted`) também chega como 429, mas
    não é transitória e não deve ser repetida.
    """
    if is_quota_exhausted(exc):
        return False
    return any(
        marker in str(erro).lower()
        for erro in _cadeia(exc)
        for marker in _TRANSIENT_MARKERS
    )


def segundos_ate_reset_da_quota(agora: datetime | None = None) -> int:
    """Segundos até a próxima meia-noite do Pacífico, quando a quota diária reinicia."""
    agora = (agora or datetime.now(_FUSO_RESET_QUOTA)).astimezone(_FUSO_RESET_QUOTA)
    proxima_meia_noite = datetime.combine(
        agora.date() + timedelta(days=1), datetime.min.time(), tzinfo=_FUSO_RESET_QUOTA
    )
    # Subtrai em UTC: no mesmo fuso o Python ignora a troca de horário de verão.
    delta = proxima_meia_noite.astimezone(timezone.utc) - agora.astimezone(timezone.utc)
    return max(1, int(delta.total_seconds()))


# Mesmo orçamento do retry manual anterior: 3 tentativas, esperas de ~2s e ~4s
# (mais jitter). Declarada no add_node do grafo; o LangGraph loga cada retentativa.
# É a única camada de retry: o retry interno dos SDKs fica desligado em provider.py.
LLM_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    initial_interval=2.0,
    backoff_factor=2.0,
    retry_on=is_transient_error,
)
