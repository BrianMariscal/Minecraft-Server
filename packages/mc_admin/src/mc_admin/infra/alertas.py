"""Envío de alertas al canal de Discord configurado.

Usa el mismo bot del proyecto, así que no hace falta un webhook aparte. Si
`ALERTAS_CANAL_ID` está vacío se usa `PAGOS_CANAL_ID`: es preferible que la
alerta llegue al canal de pagos a que se quede solo en el journal.
"""

from __future__ import annotations

import httpx

from mc_admin.config import Secretos
from mc_admin.infra.registro import obtener

log = obtener("alertas")

API = "https://discord.com/api/v10"
MAX_LARGO = 1900


def canal(secretos: Secretos) -> str:
    """El canal que recibe las alertas, o cadena vacía si no hay ninguno."""
    return secretos.alertas_canal_id or secretos.pagos_canal_id


def enviar(secretos: Secretos, texto: str) -> bool:
    """Manda `texto` al canal de alertas. Devuelve si se pudo."""
    destino = canal(secretos)
    if not destino or not secretos.pagos_bot_token:
        log.warning("no hay canal o token para mandar la alerta")
        return False

    try:
        respuesta = httpx.post(
            f"{API}/channels/{destino}/messages",
            headers={"Authorization": f"Bot {secretos.pagos_bot_token}"},
            json={"content": texto[:MAX_LARGO]},
            timeout=15,
        )
        respuesta.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("no pude mandar la alerta a Discord: %s", exc)
        return False
    return True
