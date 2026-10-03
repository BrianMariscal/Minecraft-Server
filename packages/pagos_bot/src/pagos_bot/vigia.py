"""El vigía: avisa en Discord si el servidor de Minecraft deja de contestar.

Es opcional: solo corre si pones ALERTAS_CANAL_ID en .env. Cada minuto
intenta abrir una conexión al puerto de Minecraft dentro de la red de
Docker. Con eso basta para saber si el servidor está arriba; no hace falta
hablar el protocolo de Minecraft.

Para no dar falsas alarmas:

- No avisa nada hasta haber visto el servidor arriba al menos una vez.
  Después de un `mc restart` el bot arranca antes que Minecraft, y el primer
  arranque genera mundo durante minutos: eso no es una caída.
- Avisa después de varias fallas SEGUIDAS, no por un parpadeo.
- Avisa una vez cuando se cae y una vez cuando vuelve. Nada de spam.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from enum import StrEnum

# Cuántos minutos seguidos sin contestar antes de avisar. Un reinicio normal
# del servidor tarda menos que esto.
FALLAS_PARA_AVISAR = 5
TIMEOUT_CONEXION = 5.0


class Cambio(StrEnum):
    SE_CAYO = "se_cayo"
    VOLVIO = "volvio"


@dataclass(slots=True)
class EstadoDelVigia:
    """Lógica pura: recibe 'contestó / no contestó' y dice si hay que avisar."""

    fallas_para_avisar: int = FALLAS_PARA_AVISAR
    visto_arriba: bool = False
    fallas_seguidas: int = 0
    avisado: bool = False

    def registrar(self, contesto: bool) -> Cambio | None:
        if contesto:
            self.visto_arriba = True
            self.fallas_seguidas = 0
            if self.avisado:
                self.avisado = False
                return Cambio.VOLVIO
            return None

        if not self.visto_arriba:
            return None
        self.fallas_seguidas += 1
        if self.fallas_seguidas >= self.fallas_para_avisar and not self.avisado:
            self.avisado = True
            return Cambio.SE_CAYO
        return None


async def contesta(host: str, puerto: int) -> bool:
    """¿Hay alguien escuchando en ese puerto?"""
    try:
        async with asyncio.timeout(TIMEOUT_CONEXION):
            _, escritor = await asyncio.open_connection(host, puerto)
    except (OSError, TimeoutError):
        return False
    escritor.close()
    with contextlib.suppress(OSError):
        await escritor.wait_closed()
    return True


def texto_de(cambio: Cambio, minutos: int) -> str:
    if cambio is Cambio.SE_CAYO:
        return (
            f"⚠️ El servidor de Minecraft no contesta desde hace {minutos} minutos.\n"
            "Si nadie lo apagó a propósito, revisa con `mc status` y `mc logs`."
        )
    return "✅ El servidor de Minecraft ya volvió."
