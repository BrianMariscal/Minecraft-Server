"""Copiar y revisar la base de datos del bot de pagos sin corromperla.

La base corre en modo WAL: lo último que se escribió puede vivir todavía en
`pagos.sqlite-wal` y no en `pagos.sqlite`. Copiar los archivos a lo bruto
mientras el bot escribe puede dejar una copia que no abre. Por eso aquí se
usa la API de respaldo de SQLite, que da una foto consistente aunque el bot
siga corriendo.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

# Los archivos que acompañan a una base en modo WAL.
SUFIJOS_WAL = ("-wal", "-shm")


def copia_consistente(origen: Path, destino: Path) -> None:
    """Copia `origen` a `destino` con la API de respaldo de SQLite.

    Raises:
        sqlite3.Error: si la base de origen no se puede leer.
    """
    destino.unlink(missing_ok=True)
    # Sin mode=ro a propósito: una base en WAL abierta de solo lectura
    # truena si no existe ya su -shm (por ejemplo, con el bot apagado). La
    # API de respaldo solo lee las páginas; no cambia ningún dato.
    with (
        closing(sqlite3.connect(origen)) as fuente,
        closing(sqlite3.connect(destino)) as copia,
    ):
        fuente.backup(copia)


def esta_sana(ruta: Path) -> bool:
    """¿La base abre y pasa `PRAGMA integrity_check`?"""
    if not ruta.is_file():
        return False
    try:
        with closing(sqlite3.connect(ruta)) as cx:
            fila = cx.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error:
        return False
    return bool(fila) and fila[0] == "ok"


def borrar_con_wal(ruta: Path) -> None:
    """Borra la base y sus archivos -wal y -shm.

    Antes de restaurar hace falta: un -wal viejo que se quede junto a la base
    restaurada se le aplicaría encima y la dejaría hecha un revoltijo.
    """
    ruta.unlink(missing_ok=True)
    for sufijo in SUFIJOS_WAL:
        ruta.with_name(ruta.name + sufijo).unlink(missing_ok=True)
