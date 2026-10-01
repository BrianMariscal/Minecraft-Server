"""Arranque del bot de pagos.

Si algo de la configuración está mal, truena aquí con un mensaje claro en
lugar de arrancar a medias. Si falla Discord o la base de datos en pleno
vuelo, lo anota y sigue: un bot caído no le cobra a nadie.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from contextlib import suppress
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from pagos_bot import salud
from pagos_bot.config import Entorno, ErrorDeConfig, PagosConfig, cargar_pagos
from pagos_bot.discord_ui import botones, comandos
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.scheduler import Recordatorios
from pagos_bot.services.cobros import ServicioDeCobros

RUTA_SETTINGS = Path(os.environ.get("PAGOS_SETTINGS", "/app/settings.yml"))

log = logging.getLogger("pagos")


def configurar_log() -> None:
    """Logging con niveles. Nunca se loguea el token."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # discord.py es muy hablador en INFO.
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


class BotDePagos(discord.Client):
    """El bot.

    Hereda de discord.Client y no de commands.Bot a propósito: solo usamos
    comandos slash y botones, así que no hace falta la maquinaria de
    comandos de prefijo. De paso nos evita el aviso de discord.py sobre el
    intent privilegiado de contenido de mensajes, que no tenemos por qué
    pedirle a Discord.
    """

    def __init__(self, config: PagosConfig, entorno: Entorno, servicio: ServicioDeCobros) -> None:
        # Solo los intents que de verdad usamos.
        super().__init__(intents=discord.Intents.default())
        self.config = config
        self.entorno = entorno
        self.servicio = servicio
        self.tree = app_commands.CommandTree(self)
        self.recordatorios: Recordatorios | None = None

    async def setup_hook(self) -> None:
        comandos.registrar(self.tree, self.servicio)

        # Vistas persistentes: los botones de mensajes viejos siguen
        # funcionando después de un reinicio.
        self.add_view(botones.BotonYaPague(self.servicio))

        # Los comandos se sincronizan solo con nuestro servidor: así
        # aparecen al instante en vez de tardar hasta una hora.
        guild = discord.Object(id=self.entorno.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

        self.marcar_vivo.start()

    async def on_ready(self) -> None:
        log.info("conectado como %s", self.user)
        if self.config.esta_sin_llenar:
            log.warning(
                "la sección `pagos` de settings.yml todavía trae CAMBIAME; "
                "no voy a poder abrir el mes hasta que la llenes"
            )
        if self.recordatorios is None:
            self.recordatorios = Recordatorios(self.servicio, self, self.entorno.canal_id)
            self.recordatorios.arrancar()

    @tasks.loop(minutes=1)
    async def marcar_vivo(self) -> None:
        """Para el healthcheck del contenedor."""
        try:
            salud.tocar()
        except OSError:
            log.warning("no pude escribir la marca de salud", exc_info=True)

    @marcar_vivo.before_loop
    async def _esperar_conexion(self) -> None:
        await self.wait_until_ready()

    async def close(self) -> None:
        if self.recordatorios is not None:
            self.recordatorios.parar()
        await super().close()


async def arrancar() -> int:
    configurar_log()

    try:
        config = cargar_pagos(RUTA_SETTINGS)
        entorno = Entorno.desde_entorno()
    except ErrorDeConfig as exc:
        # Sin traceback a propósito: el mensaje de ErrorDeConfig ya dice
        # qué está mal y dónde. Un traceback aquí solo asusta.
        log.error("no puedo arrancar:\n%s", exc)  # noqa: TRY400
        return 1

    if not config.activo:
        log.info("pagos.activo está en false en settings.yml; no hay nada que hacer")
        return 0

    repo = RepositorioPagos(entorno.ruta_db)
    servicio = ServicioDeCobros(config, repo)
    bot = BotDePagos(config, entorno, servicio)

    # Ctrl+C y el SIGTERM de Docker cierran limpio.
    bucle = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        # Windows no soporta add_signal_handler; ahí Ctrl+C igual funciona.
        with suppress(NotImplementedError):
            bucle.add_signal_handler(s, lambda: asyncio.create_task(bot.close()))

    try:
        await bot.start(entorno.token)
    except discord.LoginFailure:
        # Cerramos nosotros la sesión HTTP: si no, aiohttp se queja de un
        # conector sin cerrar y ensucia el log justo cuando el usuario está
        # tratando de leer por qué falló.
        await bot.close()
        # El traceback de discord.py no agrega nada: el problema es el token.
        log.error(  # noqa: TRY400
            "Discord rechazó el token. Revisa PAGOS_BOT_TOKEN en .env.\n"
            "Acuérdate que es un bot DISTINTO al de DiscordSRV. Ver docs/bot-pagos.md."
        )
        return 1
    except discord.PrivilegedIntentsRequired:
        log.error(  # noqa: TRY400
            "Discord pide prender intents privilegiados para este bot.\n"
            "En el Developer Portal > Bot, prende 'Server Members Intent'."
        )
        return 1
    finally:
        repo.cerrar()
    return 0


def run() -> None:
    """Punto de entrada del contenedor."""
    try:
        sys.exit(asyncio.run(arrancar()))
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    run()
