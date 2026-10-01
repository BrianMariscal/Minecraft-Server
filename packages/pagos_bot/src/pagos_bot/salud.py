"""Healthcheck del contenedor.

El bot deja una marca de tiempo cada minuto mientras está conectado a
Discord. Este módulo la lee: si está vieja, el contenedor se reporta enfermo
y Docker lo reinicia.

Se corre como `python -m pagos_bot.salud` desde el healthcheck del compose.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Si la marca tiene más de esto, algo se atoró.
MAXIMA_EDAD_SEGUNDOS = 180


def ruta_de_la_marca() -> Path:
    """Junto a la base de datos, que es el volumen que sí persiste."""
    db = Path(os.environ.get("PAGOS_DB", "/datos/pagos.sqlite"))
    return db.parent / "vivo.txt"


def tocar(ruta: Path | None = None) -> None:
    """Deja la marca de que seguimos vivos."""
    destino = ruta or ruta_de_la_marca()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(str(time.time()), encoding="utf-8")


def esta_vivo(ruta: Path | None = None, ahora: float | None = None) -> bool:
    """¿La marca es reciente?"""
    origen = ruta or ruta_de_la_marca()
    try:
        ultima = float(origen.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    return (ahora or time.time()) - ultima < MAXIMA_EDAD_SEGUNDOS


def main() -> int:
    if esta_vivo():
        return 0
    print("el bot no ha dado señales de vida", file=sys.stderr)  # noqa: T201
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
