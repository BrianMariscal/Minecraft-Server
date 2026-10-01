"""El esquema de la base de datos y sus migraciones.

Esquema versionado a mano en vez de Alembic: son tres tablas y el bot corre
solo en este proyecto. Alembic sería más máquina de la que hace falta, y
una dependencia más que mantener.

Para cambiar el esquema: agrega una migración nueva al final de MIGRACIONES.
NUNCA edites una que ya se publicó; en la base de datos de alguien ya corrió.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable

VERSION_ACTUAL = 1


def _v1(cx: sqlite3.Connection) -> None:
    """Esquema inicial: periodos, cuotas y avisos ya mandados."""
    cx.executescript(
        """
        -- Un renglón por mes de cobro.
        CREATE TABLE periodos (
            clave          TEXT PRIMARY KEY,   -- '2026-10'
            total_centavos INTEGER NOT NULL,
            reparto        TEXT NOT NULL,
            abierto_en     TEXT NOT NULL,      -- ISO 8601 con zona
            cerrado_en     TEXT                -- cuando todos pagaron
        );

        -- Lo que le toca a cada quien en cada mes.
        -- El dinero SIEMPRE en centavos como entero: un float pierde
        -- centavos al sumar.
        CREATE TABLE cuotas (
            periodo         TEXT NOT NULL REFERENCES periodos(clave) ON DELETE CASCADE,
            discord_id      INTEGER NOT NULL,
            nombre          TEXT NOT NULL,
            monto_centavos  INTEGER NOT NULL,
            estado          TEXT NOT NULL,
            dijo_que_pago   TEXT,
            confirmado      TEXT,
            PRIMARY KEY (periodo, discord_id)
        );

        -- Qué avisos ya se mandaron, para no repetirlos si el bot se
        -- reinicia. Es lo que hace los recordatorios idempotentes.
        CREATE TABLE avisos (
            periodo   TEXT NOT NULL REFERENCES periodos(clave) ON DELETE CASCADE,
            tipo      TEXT NOT NULL,   -- previo | dia | tardio
            dia       TEXT NOT NULL,   -- la fecha local en que se mandó
            mandado_en TEXT NOT NULL,
            PRIMARY KEY (periodo, tipo, dia)
        );

        CREATE INDEX idx_cuotas_estado ON cuotas(periodo, estado);
        """
    )


MIGRACIONES: list[tuple[int, Callable[[sqlite3.Connection], None]]] = [
    (1, _v1),
]


def version_de(cx: sqlite3.Connection) -> int:
    """Qué versión de esquema tiene esta base de datos."""
    return int(cx.execute("PRAGMA user_version").fetchone()[0])


def migrar(cx: sqlite3.Connection) -> int:
    """Aplica las migraciones que falten. Devuelve la versión final.

    Es idempotente: si ya está al día, no hace nada.
    """
    actual = version_de(cx)
    for version, aplicar in MIGRACIONES:
        if version <= actual:
            continue
        with cx:
            aplicar(cx)
            # PRAGMA no acepta parámetros, y `version` viene de esta misma
            # lista de constantes, nunca del usuario.
            cx.execute(f"PRAGMA user_version = {int(version)}")
        actual = version
    return actual
