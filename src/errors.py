"""Hierarquia de exceções do agente da clínica.

Todas as mensagens são escritas em português e podem ser exibidas ao paciente:
nunca carregam segredo ou detalhe interno. As exceções derivam de
``AgenteError``, permitindo que as interfaces (API REST e tools do agente)
capturem o tipo base e ainda distingam a causa quando necessário.

Cada interface traduz os erros na sua borda:
- API REST: exception handlers em :mod:`api.errors` (``{"erro", "tipo"}`` + status HTTP).
- Tools do LangGraph: ``handle_tool_errors`` do ``ToolNode`` devolve o mesmo
  ``{"erro", "tipo"}`` ao LLM como ``ToolMessage``.
"""

from __future__ import annotations


class AgenteError(Exception):
    """Erro base de toda a aplicação.

    Args:
        mensagem: Descrição do erro em português.
    """

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem

    def to_dict(self) -> dict[str, str]:
        """Corpo público do erro, compartilhado pela API REST e pelas tools.

        Returns:
            ``{"erro": <mensagem>, "tipo": <nome da classe>}``.
        """
        return {"erro": self.mensagem, "tipo": type(self).__name__}


class AgenteValidationError(AgenteError):
    """Dados de entrada inválidos segundo as regras do domínio (equivalente a HTTP 400)."""


class AgenteNotFoundError(AgenteError):
    """Recurso não encontrado (equivalente a HTTP 404)."""


class AgenteConflictError(AgenteError):
    """Operação incompatível com o estado atual do recurso (equivalente a HTTP 409)."""


class AgenteExternalError(AgenteError):
    """Falha de uma dependência externa, como o LLM ou o Google Calendar (equivalente a HTTP 502)."""


class AgenteUnavailableError(AgenteExternalError):
    """Dependência externa indisponível por um período conhecido, como a quota do
    provider LLM esgotada (equivalente a HTTP 503).

    Args:
        mensagem: Descrição do erro em português.
        retry_after: Segundos até o serviço voltar, se conhecido (vira ``Retry-After``).
    """

    def __init__(self, mensagem: str, retry_after: int | None = None) -> None:
        super().__init__(mensagem)
        self.retry_after = retry_after
