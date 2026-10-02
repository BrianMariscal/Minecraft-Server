"""Ayudas compartidas por los tests.

Va en su propio módulo y no en conftest.py porque conftest no es importable:
pytest lo carga solo, pero no se puede hacer `from conftest import ...`.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

ZONA = ZoneInfo("America/Mexico_City")


def momento(dia: int, mes: int = 10, anio: int = 2026, hora: int = 11) -> datetime:
    """Un instante concreto en la zona de México.

    Los tests nunca usan `datetime.now()`: así no cambian de resultado según
    el día en que se corran.
    """
    return datetime(anio, mes, dia, hora, 0, tzinfo=ZONA)
