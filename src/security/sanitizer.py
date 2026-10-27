import logging
import re

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = re.compile(
    r"(ignore\s+previous|ignore\s+above|system\s*:|<\|system\|>|\[INST\]|</)",
    re.IGNORECASE,
)


def sanitize_input(text: str) -> str:
    resultado, qtd = _INJECTION_PATTERNS.subn("", text)
    if qtd:
        logger.warning(
            "sanitize_input: %d padrão(ões) de possível prompt injection removido(s)", qtd
        )
    return resultado.strip()
