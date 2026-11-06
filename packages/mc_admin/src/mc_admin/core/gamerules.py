"""Gamerules del servidor.

OJO con las versiones: en Minecraft 26.x las gamerules cambiaron de nombre y
de lugar. Lo que todas las guías de internet llaman `playersSleepingPercentage`
aquí se llama `players_sleeping_percentage`, y ya no viven en level.dat sino
en `world/dimensions/<dimensión>/data/minecraft/game_rules.dat`.

Verificado contra un Paper 26.1.2 real: con el nombre viejo el servidor
contesta "Incorrect argument for command" y la regla NO se aplica, sin otro
aviso. Por eso los nombres de aquí salieron de leer el game_rules.dat que
generó el servidor, no de la documentación.

Otra consecuencia del cambio: las gamerules ahora son POR DIMENSIÓN. Una regla
puesta desde la consola aplica al overworld. Las que necesiten valer también en
el Nether o el End hay que ponerlas con `execute in <dimensión> run gamerule`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Dimension(StrEnum):
    OVERWORLD = "minecraft:overworld"
    NETHER = "minecraft:the_nether"
    END = "minecraft:the_end"


@dataclass(frozen=True, slots=True)
class Regla:
    """Una gamerule que queremos dejar puesta."""

    nombre: str
    valor: str
    porque: str
    dimensiones: tuple[Dimension, ...] = (Dimension.OVERWORLD,)

    def comandos(self) -> list[str]:
        """Los comandos de consola que la dejan puesta."""
        return [
            f"execute in {d.value} run gamerule {self.nombre} {self.valor}"
            for d in self.dimensiones
        ]


TODAS_LAS_DIMENSIONES = (Dimension.OVERWORLD, Dimension.NETHER, Dimension.END)


def reglas_para(*, dormir_con_un_jugador: bool) -> list[Regla]:
    """Las gamerules que pone este servidor, y por qué cada una.

    Son POCAS por diseño: todo lo demás se queda como vanilla, que es lo que
    la gente espera al entrar a un servidor de supervivencia.
    """
    reglas: list[Regla] = []

    if dormir_con_un_jugador:
        reglas.append(
            Regla(
                nombre="players_sleeping_percentage",
                valor="1",
                porque=(
                    "Con 1% basta que UNA persona se duerma para que amanezca. "
                    "El default es 100, o sea que tendrían que dormirse los 15. "
                    "Solo aplica al overworld, que es donde se duerme."
                ),
            )
        )

    # Los mensajes de muerte se quedan encendidos: son vanilla y cada cliente
    # los traduce a su idioma.
    reglas.append(
        Regla(
            nombre="show_death_messages",
            valor="true",
            porque="Vanilla. Cada cliente los traduce a su idioma.",
            dimensiones=TODAS_LAS_DIMENSIONES,
        )
    )

    # mob_griefing tiene que seguir encendido o se rompen cosas que sí
    # queremos: los aldeanos no cosechan (adiós granjas de aldeanos), los
    # creepers no rompen bloques y las granjas de TNT dejan de funcionar.
    # El griefing de endermans lo quitamos con el datapack de Vanilla Tweaks,
    # que es quirúrgico en vez de apagarlo todo.
    reglas.append(
        Regla(
            nombre="mob_griefing",
            valor="true",
            porque=(
                "Si se apaga, los aldeanos dejan de cosechar y se caen las "
                "granjas de aldeanos y de TNT. Lo de los endermans se arregla "
                "con el datapack anti enderman grief, que es más fino."
            ),
            dimensiones=TODAS_LAS_DIMENSIONES,
        )
    )

    # Las raids tienen que poder ocurrir: son un requisito del proyecto.
    reglas.append(
        Regla(
            nombre="raids",
            valor="true",
            porque="Las granjas de raids necesitan que las raids sucedan.",
            dimensiones=TODAS_LAS_DIMENSIONES,
        )
    )
    reglas.append(
        Regla(
            nombre="spawn_patrols",
            valor="true",
            porque="Sin patrullas de saqueadores no hay forma de conseguir el mal augurio.",
        )
    )

    return reglas


def comandos_de(reglas: list[Regla]) -> list[str]:
    """Aplana todas las reglas a una lista de comandos de consola."""
    return [c for r in reglas for c in r.comandos()]
