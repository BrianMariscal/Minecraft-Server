"""Fechas del ciclo de pagos.

Todo con zoneinfo, nunca con datetime "ingenuo". El caso que más se rompe en
estos bots es el día de pago 31 en un mes de 30 días (o febrero): aquí se
resuelve usando el último día del mes.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Self
from zoneinfo import ZoneInfo

MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


def dia_de_pago_real(anio: int, mes: int, dia_pedido: int) -> int:
    """El día de pago que existe en ese mes.

    Si pides el 31 y el mes tiene 30, te da 30. Si pides el 31 en febrero,
    te da 28 (o 29 en bisiesto).
    """
    ultimo = calendar.monthrange(anio, mes)[1]
    return min(dia_pedido, ultimo)


def fecha_de_pago(anio: int, mes: int, dia_pedido: int) -> date:
    """La fecha exacta en que toca pagar ese mes."""
    return date(anio, mes, dia_de_pago_real(anio, mes, dia_pedido))


@dataclass(frozen=True, order=True, slots=True)
class Periodo:
    """Un mes de cobro. Es la unidad de todo el bot."""

    anio: int
    mes: int

    def __post_init__(self) -> None:
        if not 1 <= self.mes <= 12:
            msg = f"el mes {self.mes} no existe"
            raise ValueError(msg)

    @classmethod
    def de_fecha(cls, momento: datetime | date) -> Self:
        return cls(momento.year, momento.month)

    @property
    def clave(self) -> str:
        """Identificador estable para la base de datos: '2026-10'."""
        return f"{self.anio:04d}-{self.mes:02d}"

    @classmethod
    def de_clave(cls, clave: str) -> Self:
        """Lee '2026-10'.

        Raises:
            ValueError: si la clave está mal escrita.
        """
        try:
            anio, mes = clave.split("-")
            return cls(int(anio), int(mes))
        except (ValueError, AttributeError) as exc:
            msg = f"'{clave}' no es un periodo válido; se escribe como 2026-10"
            raise ValueError(msg) from exc

    @property
    def nombre(self) -> str:
        """Como se lo decimos a la gente: 'octubre de 2026'."""
        return f"{MESES_ES[self.mes - 1]} de {self.anio}"

    def siguiente(self) -> Periodo:
        return Periodo(self.anio + 1, 1) if self.mes == 12 else Periodo(self.anio, self.mes + 1)

    def anterior(self) -> Periodo:
        return Periodo(self.anio - 1, 12) if self.mes == 1 else Periodo(self.anio, self.mes - 1)

    def fecha_de_pago(self, dia_pedido: int) -> date:
        return fecha_de_pago(self.anio, self.mes, dia_pedido)


@dataclass(frozen=True, slots=True)
class Agenda:
    """Decide qué aviso toca mandar hoy, si es que toca alguno."""

    dia_de_pago: int
    dias_antes: int
    cada_dias_despues: int
    zona: ZoneInfo

    def hoy(self, ahora: datetime | None = None) -> date:
        return (ahora or datetime.now(self.zona)).astimezone(self.zona).date()

    def periodo_actual(self, ahora: datetime | None = None) -> Periodo:
        return Periodo.de_fecha(self.hoy(ahora))

    def fecha_limite(self, periodo: Periodo) -> date:
        return periodo.fecha_de_pago(self.dia_de_pago)

    def dias_para_pagar(self, periodo: Periodo, ahora: datetime | None = None) -> int:
        """Cuántos días faltan. Negativo si ya se pasó la fecha."""
        return (self.fecha_limite(periodo) - self.hoy(ahora)).days

    def toca_aviso_previo(self, periodo: Periodo, ahora: datetime | None = None) -> bool:
        """El aviso de 'faltan X días'."""
        return self.dias_para_pagar(periodo, ahora) == self.dias_antes

    def toca_aviso_del_dia(self, periodo: Periodo, ahora: datetime | None = None) -> bool:
        """El recordatorio del mero día de pago."""
        return self.dias_para_pagar(periodo, ahora) == 0

    def toca_recordatorio_tardio(self, periodo: Periodo, ahora: datetime | None = None) -> bool:
        """El 'ya se pasó la fecha', cada N días.

        Empieza N días DESPUÉS de la fecha, no el mismo día (ese ya lo cubre
        `toca_aviso_del_dia`).
        """
        atraso = -self.dias_para_pagar(periodo, ahora)
        return atraso > 0 and atraso % self.cada_dias_despues == 0

    def fecha_bonita(self, cuando: date) -> str:
        """'5 de octubre', como lo diría cualquiera."""
        return f"{cuando.day} de {MESES_ES[cuando.month - 1]}"


def dias_entre(desde: date, hasta: date) -> int:
    return (hasta - desde).days


def sumar_dias(cuando: date, dias: int) -> date:
    return cuando + timedelta(days=dias)
