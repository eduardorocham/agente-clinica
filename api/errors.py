"""Tradução dos erros de domínio (:class:`AgenteError`) em respostas HTTP.

As rotas não capturam erros de domínio nem usam ``HTTPException`` para eles:
apenas deixam a exceção propagar, e os handlers registrados aqui a convertem.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.errors import (
    AgenteConflictError,
    AgenteError,
    AgenteExternalError,
    AgenteNotFoundError,
    AgenteUnavailableError,
    AgenteValidationError,
)

_STATUS_POR_ERRO: tuple[tuple[type[AgenteError], int], ...] = (
    (AgenteValidationError, 400),
    (AgenteNotFoundError, 404),
    (AgenteConflictError, 409),
    (AgenteUnavailableError, 503),
    (AgenteExternalError, 502),
    (AgenteError, 500),
)


def registrar_handlers_de_erro(app: FastAPI) -> None:
    """Registra um handler por classe de :class:`AgenteError`.

    O corpo devolvido é sempre ``{"erro", "tipo"}``, com a mensagem em português
    da própria exceção. O log com o detalhe técnico fica a cargo de quem traduziu
    o erro de infraestrutura; nada aqui é logado.
    """
    for classe, status in _STATUS_POR_ERRO:

        def _handler(request: Request, exc: Exception, _status: int = status) -> JSONResponse:
            corpo = (
                exc.to_dict()
                if isinstance(exc, AgenteError)
                else {"erro": str(exc), "tipo": type(exc).__name__}
            )
            headers = (
                {"Retry-After": str(exc.retry_after)}
                if isinstance(exc, AgenteUnavailableError) and exc.retry_after
                else None
            )
            return JSONResponse(status_code=_status, content=corpo, headers=headers)

        app.add_exception_handler(classe, _handler)
