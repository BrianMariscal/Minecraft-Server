"""Reglas sobre nombres de jugadores, whitelist y admins.

Lógica pura: recibe listas y devuelve listas. El que las guarda en
settings.yml es `infra.archivos`, y el que se las dice al servidor es
`infra.rcon`.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from mc_admin.errores import ErrorDeConfig

if TYPE_CHECKING:
    from mc_admin.config import Settings

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


# --------------------------------------------------------------------------- #
#  UUIDs: con lo que de verdad compara el servidor
# --------------------------------------------------------------------------- #
#
#  La whitelist, los ops y LuckPerms identifican a cada quien por UUID, no por
#  nombre. Con un servidor no premium hay dos clases de UUID:
#
#  - Java: el "offline", que sale del nombre. Es el mismo cálculo que hace el
#    servidor, así que se puede saber antes de que la persona entre.
#  - Bedrock: Floodgate usa el XUID de la cuenta de Xbox. Un
#    `whitelist add .Gamer_Tag` guardaría el UUID offline de ese nombre, que
#    NO es el que trae el jugador, y el servidor lo sacaría aunque aparezca en
#    la lista.


def uuid_offline(nombre: str) -> str:
    """El UUID que el servidor le da a un jugador de Java no premium.

    Igual que `UUIDUtil.createOfflinePlayerUUID` de Minecraft: un UUID v3
    sobre "OfflinePlayer:<nombre>".
    """
    resumen = bytearray(hashlib.md5(f"OfflinePlayer:{nombre}".encode()).digest())  # noqa: S324
    resumen[6] = (resumen[6] & 0x0F) | 0x30
    resumen[8] = (resumen[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(resumen)))


def uuid_floodgate(xuid: int) -> str:
    """El UUID que Floodgate le da a un jugador de Bedrock: su XUID en hex."""
    hexa = f"{xuid:016x}"
    return f"00000000-0000-0000-{hexa[:4]}-{hexa[4:]}"


def validar_xuid(texto: str) -> int:
    """Lee un XUID de Xbox (un número de 16 dígitos más o menos).

    Raises:
        ErrorDeConfig: si no es un número que pueda ser un XUID.
    """
    limpio = texto.strip()
    if not limpio.isdigit() or not 0 < int(limpio) < 2**64:
        raise ErrorDeConfig(
            f"'{texto}' no es un XUID",
            pista="Es un número largo, como 1234567890123456. Ve docs/administrar.md.",
        )
    return int(limpio)


@dataclass(frozen=True, slots=True)
class EntradaWhitelist:
    nombre: str
    uuid: str

    def a_json(self) -> dict[str, str]:
        return {"uuid": self.uuid, "name": self.nombre}


def entradas_whitelist(
    java: list[str],
    admins: list[str],
    bedrock: list[str],
    xuids: dict[str, int],
    prefijo_bedrock: str,
) -> tuple[list[EntradaWhitelist], list[str]]:
    """Todo `whitelist.json`, calculado desde settings.yml.

    Los admins entran solos: no tiene sentido ser admin y no poder entrar.
    Devuelve también los de Bedrock que no tienen XUID todavía; esos no se
    pueden meter (su UUID sale del XUID).
    """
    entradas: list[EntradaWhitelist] = []
    vistos: set[str] = set()
    for nombre in [*java, *admins]:
        if nombre.lower() in vistos:
            continue
        vistos.add(nombre.lower())
        entradas.append(EntradaWhitelist(nombre, uuid_offline(nombre)))

    sin_xuid: list[str] = []
    xuid_por_nombre = {k.lower(): v for k, v in xuids.items()}
    for gamertag in bedrock:
        normal = normalizar_gamertag(gamertag)
        xuid = xuid_por_nombre.get(normal.lower())
        if xuid is None:
            sin_xuid.append(normal)
            continue
        entradas.append(
            EntradaWhitelist(nombre_con_prefijo(normal, prefijo_bedrock), uuid_floodgate(xuid))
        )
    return entradas, sin_xuid


def admins_con_uuid(settings: Settings) -> list[dict[str, str]]:
    """Todos los admins con el UUID con el que los reconoce el servidor.

    Los de Java con su UUID offline; los de Bedrock con el de Floodgate (si
    ya tienen XUID: sin él no hay UUID que dar).
    """
    admins = [{"nombre": n, "uuid": uuid_offline(n)} for n in settings.admins]
    xuids = {k.lower(): v for k, v in settings.whitelist.xuid.items()}
    prefijo = settings.seguridad.prefijo_bedrock
    for gamertag in settings.admins_bedrock:
        normal = normalizar_gamertag(gamertag)
        xuid = xuids.get(normal.lower())
        if xuid is not None:
            admins.append(
                {"nombre": nombre_con_prefijo(normal, prefijo), "uuid": uuid_floodgate(xuid)}
            )
    return admins
