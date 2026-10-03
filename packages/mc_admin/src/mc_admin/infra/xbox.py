"""Buscar el XUID de un gamertag de Xbox.

Se lo preguntamos a la API global de GeyserMC, la misma que usa Floodgate
para `fwhitelist`. Solo conoce a quien ya entró alguna vez a un servidor con
Geyser; si no lo conoce, el XUID se consigue a mano (docs/administrar.md).
"""

from __future__ import annotations

import httpx

from mc_admin.infra.registro import obtener

log = obtener("xbox")

URL = "https://api.geysermc.org/v2/xbox/xuid/{gamertag}"
TIMEOUT = 10.0


def buscar_xuid(gamertag: str) -> int | None:
    """El XUID de ese gamertag, o None si la API no lo conoce (o no contesta)."""
    try:
        respuesta = httpx.get(URL.format(gamertag=gamertag), timeout=TIMEOUT)
    except httpx.HTTPError:
        log.debug("no pude hablar con la API de GeyserMC", exc_info=True)
        return None
    if respuesta.status_code != 200:
        return None
    try:
        xuid = respuesta.json().get("xuid")
    except ValueError:
        return None
    return int(xuid) if isinstance(xuid, int | str) and str(xuid).isdigit() else None
