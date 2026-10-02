"""Hablar con la consola del servidor por RCON.

RCON es la puerta de servicio del servidor: por ahí mandamos comandos sin
entrar al juego. Vive solo en la red interna de Docker, nunca expuesta a
internet (ver docs/vps.md).
"""

from __future__ import annotations

import re
import socket
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass

from mcrcon import MCRcon

from mc_admin.errores import ErrorDeRcon
from mc_admin.infra.registro import obtener

log = obtener("rcon")

TIMEOUT = 10
# Un pregen o un save-all pueden tardar; estos comandos aguantan más.
TIMEOUT_LARGO = 120

# Paper contesta "TPS from last 1m, 5m, 15m: 20.0, 19.98, 19.95" con colores.
#
# OJO: NO se pueden tomar los números en orden de aparición. Los "1m, 5m, 15m"
# del encabezado son números también, así que el primero que aparece es el 1
# de "1m" y leeríamos 1 TPS con el servidor perfecto. Hay que cortar en el
# ":" y tomar los números de DESPUÉS.
_RE_TPS = re.compile(r"(\d+\.\d+|\d+)")
_RE_CODIGOS_COLOR = re.compile(r"§.")


def limpiar(texto: str) -> str:
    """Quita los códigos de color § de una respuesta del servidor."""
    return _RE_CODIGOS_COLOR.sub("", texto).strip()


@dataclass(frozen=True, slots=True)
class Conexion:
    """Dónde y con qué contraseña nos conectamos."""

    host: str
    puerto: int
    password: str

    def __repr__(self) -> str:
        """Nunca imprimimos la contraseña, ni en un traceback."""
        return f"Conexion(host={self.host!r}, puerto={self.puerto})"

    __str__ = __repr__


@contextmanager
def abrir(conexion: Conexion, timeout: int = TIMEOUT) -> Iterator[MCRcon]:
    """Abre una sesión RCON y la cierra siempre al salir.

    Raises:
        ErrorDeRcon: si el servidor no contesta o la contraseña está mal.
    """
    if not conexion.password:
        raise ErrorDeRcon(
            "no hay contraseña de RCON configurada",
            pista="Corre `mc setup` para generar RCON_PASSWORD en .env.",
        )

    cliente = MCRcon(conexion.host, conexion.password, port=conexion.puerto, timeout=timeout)
    try:
        cliente.connect()
    except (ConnectionRefusedError, TimeoutError) as exc:
        raise ErrorDeRcon(
            f"el servidor no contesta en {conexion.host}:{conexion.puerto}",
            pista="¿Está encendido? Revisa con `mc status` y arranca con `mc start`.",
        ) from exc
    except socket.gaierror as exc:
        raise ErrorDeRcon(
            f"no pude resolver el nombre '{conexion.host}'",
            pista="Si corres `mc` fuera de Docker, el host debe ser 127.0.0.1.",
        ) from exc
    except Exception as exc:
        mensaje = str(exc).lower()
        if "authentic" in mensaje or "password" in mensaje or "login" in mensaje:
            raise ErrorDeRcon(
                "el servidor rechazó la contraseña de RCON",
                pista=(
                    "RCON_PASSWORD en .env y la del servidor no coinciden. "
                    "Corre `mc build` y `mc restart` para resincronizarlas."
                ),
            ) from exc
        raise ErrorDeRcon(f"no pude conectarme por RCON: {exc}") from exc

    try:
        yield cliente
    finally:
        # Cerrar nunca debe tumbar nada: si el socket ya murió, da igual.
        with suppress(Exception):
            cliente.disconnect()


def mandar(conexion: Conexion, comando: str, timeout: int = TIMEOUT) -> str:
    """Manda un comando y devuelve la respuesta ya sin códigos de color."""
    with abrir(conexion, timeout) as cliente:
        log.debug("rcon> %s", comando)
        try:
            respuesta = cliente.command(comando)
        except Exception as exc:
            raise ErrorDeRcon(f"falló el comando '{comando}': {exc}") from exc
    return limpiar(respuesta or "")


def mandar_varios(conexion: Conexion, comandos: list[str], timeout: int = TIMEOUT) -> list[str]:
    """Manda varios comandos en una sola conexión.

    Reusar la conexión importa: abrir RCON por cada nombre de la whitelist
    sería lentísimo con 15 jugadores.
    """
    respuestas: list[str] = []
    with abrir(conexion, timeout) as cliente:
        for comando in comandos:
            log.debug("rcon> %s", comando)
            try:
                respuestas.append(limpiar(cliente.command(comando) or ""))
            except Exception as exc:
                raise ErrorDeRcon(f"falló el comando '{comando}': {exc}") from exc
    return respuestas


def leer_tps(conexion: Conexion) -> float | None:
    """Pregunta los TPS al servidor. None si no se pudo.

    Devuelve el promedio del último minuto, que es el que de verdad dice si
    el servidor va mal AHORA.
    """
    try:
        respuesta = mandar(conexion, "tps")
    except ErrorDeRcon:
        return None

    # Nos quedamos con lo que va después del ":", para no confundir el
    # "1m, 5m, 15m" del encabezado con los TPS.
    cola = respuesta.split(":", 1)[1] if ":" in respuesta else respuesta
    numeros = _RE_TPS.findall(cola)
    if not numeros:
        return None
    try:
        # El tope de 20 es por si Paper reporta 20.01 por redondeo.
        return min(float(numeros[0]), 20.0)
    except ValueError:  # pragma: no cover
        return None


def esta_vivo(conexion: Conexion) -> bool:
    """¿Contesta el servidor por RCON?"""
    try:
        mandar(conexion, "list", timeout=5)
    except ErrorDeRcon:
        return False
    return True


def jugadores_conectados(conexion: Conexion) -> tuple[int, int, list[str]]:
    """Lee `list`: devuelve (conectados, máximo, nombres)."""
    respuesta = mandar(conexion, "list")
    # "There are 2 of a max of 15 players online: Pepe, .Lupita"
    numeros = re.findall(r"\d+", respuesta)
    conectados = int(numeros[0]) if numeros else 0
    maximo = int(numeros[1]) if len(numeros) > 1 else 0
    nombres: list[str] = []
    if ":" in respuesta:
        cola = respuesta.split(":", 1)[1].strip()
        nombres = [n.strip() for n in cola.split(",") if n.strip()]
    return conectados, maximo, nombres
