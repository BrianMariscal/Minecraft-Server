"""Quién movió el dinero y cuándo.

El registro es de solo agregar: nunca se edita ni se borra un renglón. Así,
si alguien confirma un pago por error, queda la huella de quién lo hizo y
después se ve el movimiento contrario (desmarcar), no un hueco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pagos_bot.domain.calendario import Periodo


@dataclass(frozen=True, slots=True)
class Actor:
    """Quien ejecuta una acción.

    El bot usa `Actor.sistema()` cuando actúa solo (por ejemplo, al arrancar
    y poner al día el precio del mes). Las acciones humanas llevan el ID y
    el nombre de Discord de quien las hizo.
    """

    discord_id: int
    nombre: str

    @classmethod
    def sistema(cls) -> Actor:
        return cls(discord_id=0, nombre="sistema")


@dataclass(frozen=True, slots=True)
class RegistroDeAuditoria:
    """Un renglón del libro de movimientos del cobro."""

    cuando: datetime
    actor: Actor
    accion: str
    periodo: Periodo | None = None
    objetivo_id: int | None = None
    # Valores ya listos para mostrar: nombre, monto, ajuste...
    detalle: dict[str, str] = field(default_factory=dict)
