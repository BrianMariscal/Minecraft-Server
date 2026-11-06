"""Copias consistentes y revisión de bases SQLite.

Una base en modo WAL guarda lo último que se escribió en `-wal`, no en el
archivo principal. Copiar los archivos mientras el servidor escribe puede
dejar una copia que no abre. Por eso se usa la API de respaldo de SQLite, que
entrega una foto consistente aunque el proceso siga trabajando.

También se encarga de detectar qué archivos de una carpeta son SQLite, para
que el respaldo sepa cuáles necesita fotografiar y cuáles puede copiar tal
cual.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

# Los archivos que acompañan a una base en modo WAL.
SUFIJOS_WAL = ("-wal", "-shm")

# Extensiones que puede usar una base SQLite. LuckPerms usa H2 y termina en
# `.mv.db`; ese formato no lo abre este módulo y se copia como archivo normal.
SUFIJOS_BASE = (".sqlite", ".sqlite3", ".db")
SUFIJOS_OTROS = (".mv.db", ".h2.db")

_CABECERA = b"SQLite format 3\x00"


def es_sqlite(ruta: Path) -> bool:
    """¿El archivo empieza con la cabecera de SQLite?"""
    try:
        with ruta.open("rb") as archivo:
            return archivo.read(len(_CABECERA)) == _CABECERA
    except OSError:
        return False


def bases_en(carpeta: Path) -> list[Path]:
    """Bases SQLite dentro de `carpeta`, como rutas relativas y ordenadas.

    Solo mira archivos con extensión de base y comprueba la cabecera: así no
    confunde el H2 de LuckPerms ni un `.db` de otro formato con SQLite.
    """
    encontradas: list[Path] = []
    for ruta in sorted(carpeta.rglob("*")):
        if not ruta.is_file() or ruta.name.endswith(SUFIJOS_OTROS):
            continue
        if ruta.suffix.lower() not in SUFIJOS_BASE:
            continue
        if es_sqlite(ruta):
            encontradas.append(ruta.relative_to(carpeta))
    return encontradas


def copia_consistente(origen: Path, destino: Path) -> None:
    """Copia `origen` a `destino` con la API de respaldo de SQLite.

    La copia incluye lo que esté pendiente en el `-wal` de origen y deja un
    solo archivo, sin acompañantes.

    Raises:
        sqlite3.Error: si la base de origen no se puede leer.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    borrar_con_wal(destino)
    # Sin mode=ro: una base en WAL abierta de solo lectura falla si no existe
    # su -shm (por ejemplo, con el proceso apagado). La API de respaldo solo
    # lee páginas; no modifica datos.
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


def borrar_wal(ruta: Path) -> None:
    """Borra los archivos `-wal` y `-shm` de una base."""
    for sufijo in SUFIJOS_WAL:
        ruta.with_name(ruta.name + sufijo).unlink(missing_ok=True)


def borrar_con_wal(ruta: Path) -> None:
    """Borra la base y sus archivos `-wal` y `-shm`.

    Antes de restaurar hace falta: un `-wal` viejo que se quede junto a la base
    restaurada se le aplicaría encima y la dejaría inconsistente.
    """
    ruta.unlink(missing_ok=True)
    borrar_wal(ruta)


def consolidar_en_sitio(ruta: Path) -> None:
    """Deja `ruta` como un solo archivo sano, sin `-wal` ni `-shm`.

    Se usa al restaurar respaldos viejos, que copiaban la base viva con sus
    acompañantes. La API de respaldo lee base y WAL juntos y escribe una foto
    limpia; después se reemplaza el archivo original y se borran los
    acompañantes.

    Raises:
        sqlite3.Error: si la base no se puede leer o la foto no pasa la
            revisión de integridad.
    """
    temporal = ruta.with_name(f".{ruta.name}.consolidando")
    try:
        copia_consistente(ruta, temporal)
        if not esta_sana(temporal):
            msg = f"la base {ruta} no pasó la revisión de integridad"
            raise sqlite3.DatabaseError(msg)
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)
    borrar_wal(ruta)
