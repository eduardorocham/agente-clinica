"""
Chat no terminal com o agente da clínica (demo, sem subir a API).

Uso:
  uv run python chat_cli.py
"""

import asyncio
import logging

from langgraph.checkpoint.memory import InMemorySaver

from src.agents.graph import compilar_grafo
from src.calendario import obter_calendario
from src.errors import AgenteError
from src.logging_config import setup_logging
from src.services import chat_service


async def main() -> None:
    obter_calendario()
    grafo = compilar_grafo(InMemorySaver())
    conversa_id = None
    print("Clara — Clínica Vida Plena. Digite 'sair' para encerrar.\n")

    while True:
        mensagem = (await asyncio.to_thread(input, "Você: ")).strip()
        if mensagem.lower() in {"sair", "exit", "quit"}:
            break
        if not mensagem:
            continue
        try:
            saida = await chat_service.conversar(grafo, mensagem, conversa_id)
        except AgenteError as erro:
            print(f"\n[erro] {erro.mensagem}\n")
            continue
        conversa_id = saida.conversa_id
        print(f"\nClara: {saida.resposta}\n")


if __name__ == "__main__":
    setup_logging(level="WARNING")
    logging.getLogger("src").setLevel(logging.INFO)
    asyncio.run(main())
