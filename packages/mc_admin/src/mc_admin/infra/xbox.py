"""Buscar el XUID de un gamertag de Xbox.

Primero se lo preguntamos a la API global de GeyserMC, la misma que usa
Floodgate para `fwhitelist`, pero esa solo conoce a quien ya entró alguna vez
a un servidor con Geyser. Si no lo conoce, probamos con playerdb.co, que
consulta a Xbox directamente. Si ninguna contesta, el XUID se consigue a mano
(docs/administrar.md).
"""

from __future__ import annotations

import httpx

from mc_admin.infra.registro import obtener

log = obtener("xbox")

URL = "https://api.geysermc.org/v2/xbox/xuid/{gamertag}"
# playerdb no encuentra gamertags con espacios ("Jugador Bedrock 2"), pero sí sin
# ellos ("JugadorBedrock2"): Xbox los ignora al buscar.
URL_PLAYERDB = "https://playerdb.co/api/player/xbox/{gamertag}"
TIMEOUT = 10.0


def buscar_xuid(gamertag: str) -> int | None:
    """El XUID de ese gamertag, o None si nadie lo conoce (o no contestan)."""
    return _desde_geyser(gamertag) or _desde_playerdb(gamertag)


def _a_xuid(valor: object) -> int | None:
    return int(valor) if isinstance(valor, int | str) and str(valor).isdigit() else None


def _desde_geyser(gamertag: str) -> int | None:
    try:
        respuesta = httpx.get(URL.format(gamertag=gamertag), timeout=TIMEOUT)
    except httpx.HTTPError:
        log.debug("no pude hablar con la API de GeyserMC", exc_info=True)
        return None
    if respuesta.status_code != 200:
        return None
    try:
        return _a_xuid(respuesta.json().get("xuid"))
    except ValueError:
        return None


def _sin_espacios(texto: str) -> str:
    return texto.replace(" ", "").replace("_", "").lower()


def _desde_playerdb(gamertag: str) -> int | None:
    buscado = gamertag.replace(" ", "").replace("_", "")
    try:
        respuesta = httpx.get(
            URL_PLAYERDB.format(gamertag=buscado),
            timeout=TIMEOUT,
            # playerdb pide identificarse; sin User-Agent puede rechazarnos.
            headers={"User-Agent": "minecraft-hd (mc whitelist)"},
        )
    except httpx.HTTPError:
        log.debug("no pude hablar con playerdb.co", exc_info=True)
        return None
    if respuesta.status_code != 200:
        return None
    try:
        jugador = respuesta.json().get("data", {}).get("player", {})
    except (ValueError, AttributeError):
        return None
    if not isinstance(jugador, dict):
        return None
    # Que sea la misma cuenta y no una parecida.
    nombre = jugador.get("username")
    if not isinstance(nombre, str) or _sin_espacios(nombre) != _sin_espacios(gamertag):
        return None
    return _a_xuid(jugador.get("id"))
