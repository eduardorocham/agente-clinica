"""
Agente de atendimento da clínica (LangGraph + FastAPI)
Entrypoint

Uso:
  uv run python main.py
"""

import uvicorn

from src.logging_config import setup_logging

if __name__ == "__main__":
    setup_logging()
    uvicorn.run("api.routes:app", host="0.0.0.0", port=8000, reload=True)
