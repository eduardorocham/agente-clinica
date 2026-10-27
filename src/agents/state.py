from typing import Annotated, NotRequired, TypedDict

from langgraph.graph.message import add_messages


class EstadoAgente(TypedDict):
    messages: Annotated[list, add_messages]
    # Preenchidos pelo canal de entrada (ex.: webhook do WhatsApp), nunca pelo LLM
    canal: NotRequired[str | None]
    telefone_paciente: NotRequired[str | None]
    nome_perfil: NotRequired[str | None]
