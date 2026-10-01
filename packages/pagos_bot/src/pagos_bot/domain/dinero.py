"""Dinero.

Regla del proyecto: el dinero NUNCA es float. Un float no puede representar
0.10 exacto, y después de sumar quince veces te sobran o te faltan centavos.
Aquí todo se guarda en CENTAVOS como entero, y se muestra con Decimal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

CENTAVOS_POR_PESO = 100


@dataclass(frozen=True, order=True, slots=True)
class Dinero:
    """Una cantidad en pesos mexicanos, guardada en centavos."""

    # Centavos, SIEMPRE entero. mypy es quien lo garantiza: si alguien
    # intenta meter un float aquí, el type check truena antes de correr.
    centavos: int

    # -- construcción ------------------------------------------------------ #

    @classmethod
    def de_pesos(cls, pesos: Decimal | str | int) -> Self:
        """Desde pesos. Redondea al centavo más cercano."""
        d = Decimal(str(pesos))
        centavos = (d * CENTAVOS_POR_PESO).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return cls(int(centavos))

    @classmethod
    def cero(cls) -> Self:
        return cls(0)

    # -- lectura ----------------------------------------------------------- #

    @property
    def pesos(self) -> Decimal:
        """El valor en pesos, exacto."""
        return Decimal(self.centavos) / CENTAVOS_POR_PESO

    def __str__(self) -> str:
        """Como se escribe en México: $1,234.50"""
        return f"${self.pesos:,.2f}"

    # -- aritmética -------------------------------------------------------- #

    def __add__(self, otro: Dinero) -> Dinero:
        return Dinero(self.centavos + otro.centavos)

    def __sub__(self, otro: Dinero) -> Dinero:
        return Dinero(self.centavos - otro.centavos)

    def __mul__(self, veces: int) -> Dinero:
        return Dinero(self.centavos * veces)

    def __bool__(self) -> bool:
        return self.centavos != 0

    @property
    def es_positivo(self) -> bool:
        return self.centavos > 0


def repartir(total: Dinero, entre: int) -> list[Dinero]:
    """Divide un total en partes iguales sin perder ni un centavo.

    $450.00 entre 3 da tres de $150.00. Pero $100.00 entre 3 no da tres de
    $33.33 (eso suma $99.99 y falta un centavo): da $33.34, $33.33 y $33.33.
    Los centavos que sobran se reparten de uno en uno empezando por el
    primero, para que la suma SIEMPRE dé el total exacto.

    Raises:
        ValueError: si `entre` no es al menos 1.
    """
    if entre < 1:
        msg = "hay que repartir entre al menos una persona"
        raise ValueError(msg)

    base, sobra = divmod(total.centavos, entre)
    return [Dinero(base + (1 if i < sobra else 0)) for i in range(entre)]


def sumar(cantidades: list[Dinero]) -> Dinero:
    """Suma una lista de cantidades."""
    return Dinero(sum(c.centavos for c in cantidades))
