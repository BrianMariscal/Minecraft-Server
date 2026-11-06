"""Comparación de versiones para `mc update`.

Pura: le pasas qué tienes y qué hay disponible, y te dice qué cambiaría. Quien
pregunta a Modrinth, GitHub y GeyserMC es `infra.descargas`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Cambio(StrEnum):
    IGUAL = "igual"
    SUBE = "sube"
    BAJA = "baja"
    DESCONOCIDO = "desconocido"


@dataclass(frozen=True, slots=True)
class Comparacion:
    """Qué pasaría con un artefacto si aplicáramos la actualización."""

    nombre: str
    actual: str
    disponible: str | None
    cambio: Cambio
    # Versiones de Minecraft que declara soportar la versión disponible.
    soporta_minecraft: tuple[str, ...] = ()
    # Canal de la versión disponible: release, beta o alpha.
    canal: str = "release"
    nota: str = ""

    @property
    def vale_la_pena(self) -> bool:
        """¿Hay algo que aplicar?"""
        return self.cambio is Cambio.SUBE

    @property
    def es_seguro(self) -> bool:
        """Solo recomendamos saltos a canal `release`."""
        return self.canal == "release"


def _partes(version: str) -> tuple[int | str, ...]:
    """Parte una versión en trozos comparables.

    Aguanta las formas raras que usan estos proyectos:
    "2.11.3-b1247", "v5.5.71-bukkit", "5.28-paper", "26.1-datapack".
    Los números se comparan como números; lo demás como texto.
    """
    limpia = version.lower().removeprefix("v")
    trozos = re.split(r"[.\-+_]", limpia)
    salida: list[int | str] = []
    for t in trozos:
        if not t:
            continue
        # "b1247" -> 1247, para que b1248 sea mayor que b1247.
        numero = re.fullmatch(r"[a-z]*(\d+)", t)
        salida.append(int(numero.group(1)) if numero else t)
    return tuple(salida)


def comparar(actual: str, disponible: str | None) -> Cambio:
    """Decide si `disponible` es más nueva que `actual`."""
    if disponible is None:
        return Cambio.DESCONOCIDO
    if actual == disponible:
        return Cambio.IGUAL

    a, b = _partes(actual), _partes(disponible)
    for pa, pb in zip(a, b, strict=False):
        if pa == pb:
            continue
        # Un número siempre gana a un texto: 2.11.3 > 2.11.beta
        if isinstance(pa, int) and isinstance(pb, int):
            return Cambio.SUBE if pb > pa else Cambio.BAJA
        if isinstance(pa, int) != isinstance(pb, int):
            return Cambio.SUBE if isinstance(pb, int) else Cambio.BAJA
        return Cambio.SUBE if str(pb) > str(pa) else Cambio.BAJA

    # Mismo prefijo: gana la que tenga más trozos (2.11.3.1 > 2.11.3).
    if len(b) > len(a):
        return Cambio.SUBE
    if len(b) < len(a):
        return Cambio.BAJA
    return Cambio.IGUAL


def resumir(comparaciones: list[Comparacion], version_minecraft: str) -> str:
    """Una línea diciendo qué se puede actualizar."""
    suben = [c for c in comparaciones if c.vale_la_pena]
    if not suben:
        return "Todo está en la versión más nueva que soporta Minecraft " + version_minecraft + "."

    seguros = [c for c in suben if c.es_seguro]
    riesgosos = [c for c in suben if not c.es_seguro]
    partes = [f"{len(seguros)} actualización(es) en canal estable"]
    if riesgosos:
        partes.append(f"{len(riesgosos)} solo en beta o alpha")
    return "Hay " + " y ".join(partes) + "."


def filtrar_compatibles(
    comparaciones: list[Comparacion], version_minecraft: str
) -> tuple[list[Comparacion], list[Comparacion]]:
    """Separa lo que sí soporta nuestra versión de Minecraft de lo que no.

    Devuelve (aplicables, descartadas). Nunca proponemos subir un plugin a una
    versión que ya no soporta el Minecraft que corremos: así es como se rompe
    un servidor de un día para otro.
    """
    aplicables: list[Comparacion] = []
    descartadas: list[Comparacion] = []
    for c in comparaciones:
        if not c.vale_la_pena:
            continue
        # Si no sabemos qué soporta, no arriesgamos.
        if c.soporta_minecraft and version_minecraft not in c.soporta_minecraft:
            descartadas.append(c)
        else:
            aplicables.append(c)
    return aplicables, descartadas
