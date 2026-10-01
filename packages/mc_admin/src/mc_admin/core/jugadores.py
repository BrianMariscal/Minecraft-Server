"""Reglas sobre nombres de jugadores, whitelist y admins.

Lógica pura: recibe listas y devuelve listas. El que las guarda en
settings.yml es `infra.archivos`, y el que se las dice al servidor es
`infra.rcon`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from mc_admin.errores import ErrorDeConfig

# Nombre válido de Minecraft Java: 3 a 16, letras, números y guion bajo.
RE_NOMBRE_JAVA = re.compile(r"^[A-Za-z0-9_]{3,16}$")
# Un gamertag de Xbox puede traer espacios y llegar a 15 caracteres.
# Floodgate los reemplaza por guion bajo y les pone el prefijo configurado.
RE_GAMERTAG = re.compile(r"^[A-Za-z0-9 _]{1,16}$")


class Plataforma(StrEnum):
    JAVA = "java"
    BEDROCK = "bedrock"


def normalizar_gamertag(gamertag: str) -> str:
    """Convierte un gamertag de Xbox al nombre que Floodgate le va a dar.

    Floodgate cambia los espacios por guion bajo. Lo replicamos para que la
    whitelist tenga exactamente el nombre que el servidor va a ver.
    """
    return gamertag.strip().replace(" ", "_")


def nombre_con_prefijo(nombre: str, prefijo: str) -> str:
    """Pone el prefijo de Floodgate si no lo trae ya."""
    if not prefijo or nombre.startswith(prefijo):
        return nombre
    return f"{prefijo}{nombre}"


def validar(nombre: str, plataforma: Plataforma) -> str:
    """Valida un nombre y lo devuelve normalizado.

    Raises:
        ErrorDeConfig: si el nombre no sirve para esa plataforma.
    """
    limpio = nombre.strip()
    if not limpio:
        raise ErrorDeConfig("el nombre del jugador viene vacío")

    if plataforma is Plataforma.JAVA:
        if not RE_NOMBRE_JAVA.match(limpio):
            raise ErrorDeConfig(
                f"'{limpio}' no es un nombre válido de Minecraft Java",
                pista=(
                    "Deben ser de 3 a 16 caracteres: letras, números y guion bajo. "
                    "Si es alguien de Bedrock, usa --bedrock."
                ),
            )
        return limpio

    if limpio.startswith("."):
        raise ErrorDeConfig(
            f"quita el punto de '{limpio}'",
            pista="El prefijo de Floodgate lo pone `mc`; tú dame el gamertag tal cual.",
        )
    if not RE_GAMERTAG.match(limpio):
        raise ErrorDeConfig(
            f"'{limpio}' no parece un gamertag de Xbox",
            pista="Hasta 16 caracteres: letras, números, espacios y guion bajo.",
        )
    return normalizar_gamertag(limpio)


@dataclass(frozen=True, slots=True)
class CambioEnLista:
    """Resultado de agregar o quitar a alguien de una lista.

    `cambio` en False significa que ya estaba (o ya no estaba) y no hubo nada
    que hacer: así `mc whitelist add` dos veces no truena ni duplica.
    """

    lista: tuple[str, ...]
    cambio: bool
    mensaje: str


def agregar(lista: list[str], nombre: str, plataforma: Plataforma) -> CambioEnLista:
    """Agrega un nombre a una lista, sin duplicar. Idempotente."""
    limpio = validar(nombre, plataforma)
    # Comparamos sin distinguir mayúsculas: Minecraft tampoco distingue.
    minusculas = {n.lower() for n in lista}
    if limpio.lower() in minusculas:
        return CambioEnLista(tuple(lista), False, f"{limpio} ya estaba en la lista.")
    nueva = sorted([*lista, limpio], key=str.lower)
    return CambioEnLista(tuple(nueva), True, f"Agregué a {limpio}.")


def quitar(lista: list[str], nombre: str, plataforma: Plataforma) -> CambioEnLista:
    """Quita un nombre de una lista. Idempotente."""
    limpio = validar(nombre, plataforma)
    nueva = [n for n in lista if n.lower() != limpio.lower()]
    if len(nueva) == len(lista):
        return CambioEnLista(tuple(lista), False, f"{limpio} no estaba en la lista.")
    return CambioEnLista(tuple(nueva), True, f"Quité a {limpio}.")


def nombres_para_el_servidor(
    java: list[str], bedrock: list[str], prefijo_bedrock: str
) -> list[str]:
    """Arma la lista completa de nombres que hay que meterle al servidor.

    Los de Java van tal cual; los de Bedrock con el prefijo de Floodgate.
    """
    return [
        *java,
        *(nombre_con_prefijo(normalizar_gamertag(n), prefijo_bedrock) for n in bedrock),
    ]
