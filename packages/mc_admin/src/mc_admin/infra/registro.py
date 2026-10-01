"""Configuración del logging de `mc`.

Regla del proyecto: la lógica loguea, nunca imprime. La capa CLI es la única
que escribe a la terminal (con Rich). Y nunca, por ningún motivo, se loguea un
secreto: para eso está el filtro de abajo.
"""

from __future__ import annotations

import logging
import re
from typing import Final

NOMBRE_LOGGER: Final = "mc"

# Patrones de cosas que jamás deben aparecer en un log, aunque alguien las
# pase por error dentro de un mensaje.
_PATRONES_SECRETOS: Final = (
    # Token de bot de Discord: tres bloques base64 separados por puntos.
    re.compile(r"\b[A-Za-z0-9_-]{24,28}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,40}\b"),
    # Cualquier asignación tipo PASSWORD=... o token: ...
    re.compile(
        r"\b(password|passwd|token|secret|rcon_password)\b\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
)
REEMPLAZO: Final = "***"


class FiltroSecretos(logging.Filter):
    """Tacha secretos del mensaje antes de que llegue a cualquier handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensaje = record.getMessage()
        limpio = mensaje
        for patron in _PATRONES_SECRETOS:
            limpio = patron.sub(
                lambda m: f"{m.group(1)}={REEMPLAZO}" if m.lastindex else REEMPLAZO,
                limpio,
            )
        if limpio != mensaje:
            # Reescribimos el mensaje ya formateado y soltamos los args para
            # que no se vuelva a interpolar el original.
            record.msg = limpio
            record.args = ()
        return True


def configurar(nivel: int = logging.WARNING, archivo: str | None = None) -> logging.Logger:
    """Prepara el logger de `mc`.

    Args:
        nivel: logging.DEBUG con -vv, INFO con -v, WARNING normal.
        archivo: si lo pasas, además escribe a ese archivo.
    """
    logger = logging.getLogger(NOMBRE_LOGGER)
    logger.setLevel(nivel)
    logger.handlers.clear()
    # No propagamos al root: si no, Rich y logging se pelean por la terminal.
    logger.propagate = False

    formato = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    filtro = FiltroSecretos()

    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    consola.addFilter(filtro)
    logger.addHandler(consola)

    if archivo:
        aldisco = logging.FileHandler(archivo, encoding="utf-8")
        aldisco.setFormatter(formato)
        aldisco.addFilter(filtro)
        logger.addHandler(aldisco)

    return logger


def obtener(sufijo: str = "") -> logging.Logger:
    """Devuelve el logger del módulo que lo pide: `mc.descargas`, etc."""
    return logging.getLogger(f"{NOMBRE_LOGGER}.{sufijo}" if sufijo else NOMBRE_LOGGER)
