"""La lógica de `mc build`: qué hay que hacer para dejar el servidor listo.

Pura en el sentido que importa: decide y describe el plan, y la ejecución
(bajar, verificar, escribir) la hacen los adaptadores que le pasas. Así se
puede probar el plan completo sin red ni disco.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Accion(StrEnum):
    """Qué le va a pasar a un archivo."""

    CREAR = "crear"
    ACTUALIZAR = "actualizar"
    SIN_CAMBIO = "sin cambio"
    QUITAR = "quitar"


@dataclass(frozen=True, slots=True)
class PasoDelPlan:
    """Una cosa que `mc build` va a hacer."""

    categoria: str
    nombre: str
    destino: str
    accion: Accion
    detalle: str = ""

    @property
    def cambia_algo(self) -> bool:
        return self.accion is not Accion.SIN_CAMBIO


@dataclass(slots=True)
class PlanDeConstruccion:
    """Todo lo que `mc build` va a hacer, antes de hacerlo.

    Sirve para dos cosas: enseñárselo al usuario con --dry-run, y que la
    ejecución no tenga que decidir nada sobre la marcha.
    """

    pasos: list[PasoDelPlan] = field(default_factory=list)
    problemas: list[str] = field(default_factory=list)

    def agregar(self, paso: PasoDelPlan) -> None:
        self.pasos.append(paso)

    @property
    def cambios(self) -> list[PasoDelPlan]:
        return [p for p in self.pasos if p.cambia_algo]

    @property
    def hay_cambios(self) -> bool:
        return bool(self.cambios)

    def por_categoria(self) -> dict[str, list[PasoDelPlan]]:
        agrupado: dict[str, list[PasoDelPlan]] = {}
        for p in self.pasos:
            agrupado.setdefault(p.categoria, []).append(p)
        return agrupado

    def resumen(self) -> str:
        """Una línea con lo que cambiaría."""
        if not self.hay_cambios:
            return "Todo estaba al día: no hubo nada que cambiar."
        creados = sum(1 for p in self.cambios if p.accion is Accion.CREAR)
        actualizados = sum(1 for p in self.cambios if p.accion is Accion.ACTUALIZAR)
        quitados = sum(1 for p in self.cambios if p.accion is Accion.QUITAR)
        partes: list[str] = []
        if creados:
            partes.append(f"{creados} creado(s)")
        if actualizados:
            partes.append(f"{actualizados} actualizado(s)")
        if quitados:
            partes.append(f"{quitados} quitado(s)")
        return ", ".join(partes) + "."
