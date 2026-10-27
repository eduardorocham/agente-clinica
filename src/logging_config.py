import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configura o logging da aplicação (idempotente)."""
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
