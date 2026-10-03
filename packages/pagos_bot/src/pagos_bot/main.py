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
import sqlite3
import sys
import time
from contextlib import suppress
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import tasks

from pagos_bot import salud, vigia
from pagos_bot.config import Entorno, ErrorDeConfig, PagosConfig, cargar_pagos
from pagos_bot.discord_ui import botones, comandos
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.scheduler import Recordatorios
from pagos_bot.services.ajustes import cargar_config
from pagos_bot.services.cobros import ErrorDeCobro, ServicioDeCobros

RUTA_SETTINGS = Path(os.environ.get("PAGOS_SETTINGS", "/app/settings.yml"))

log = logging.getLogger("pagos")

# Si lleva este tiempo sin Discord, el bot se sale con error para que Docker
# lo levante de cero. discord.py reconecta solo casi siempre; esto es para
# cuando se queda atorado. Docker NO reinicia un contenedor solo porque su
# healthcheck falle, así que el bot tiene que caerse él mismo.
MAXIMO_SIN_DISCORD_SEGUNDOS = 15 * 60

# Ver canales, Enviar mensajes, Insertar enlaces y Leer el historial: nada más.
PERMISOS_DEL_BOT = 84992

# La foto de la base que usa `mc backup restore` si la principal sale dañada.
NOMBRE_DE_LA_FOTO = "pagos.copia.sqlite"


def configurar_log() -> None:
    """Logging con niveles. Nunca se loguea el token."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # discord.py es muy hablador en INFO.
    logging.getLogger("discord").setLevel(logging.WARNING)
    # Avisa en cada arranque que no hay soporte de voz; no usamos voz.
    logging.getLogger("discord.client").setLevel(logging.ERROR)
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
        # monotonic() de cuando se perdió Discord; None = conectado.
        self._sin_discord_desde: float | None = None
        self.codigo_de_salida = 0
        self._vigia = vigia.EstadoDelVigia()
        self._comandos_registrados = False

    async def setup_hook(self) -> None:
        comandos.registrar(self.tree, self.servicio)

        # Los botones se reconocen por su custom_id: los de mensajes viejos
        # siguen funcionando después de un reinicio.
        self.add_dynamic_items(*botones.BOTONES_DINAMICOS)

        # Los comandos se sincronizan solo con nuestro servidor: así
        # aparecen al instante en vez de tardar hasta una hora.
        self.tree.copy_global_to(guild=discord.Object(id=self.entorno.guild_id))
        await self._registrar_comandos()

        self.marcar_vivo.start()
        self.foto_de_la_base.start()
        if self.entorno.alertas_canal_id:
            self.vigilar_minecraft.start()
            log.info(
                "vigilando el servidor de Minecraft en %s:%s",
                self.entorno.minecraft_host,
                self.entorno.minecraft_puerto,
            )

    async def _registrar_comandos(self) -> bool:
        """Registra los comandos slash en el servidor. False si no se pudo.

        Si el bot todavía no está invitado al servidor, Discord contesta
        "Missing Access". No tronamos por eso: lo decimos claro y se vuelve
        a intentar solo en cuanto lo inviten (on_guild_join).
        """
        try:
            await self.tree.sync(guild=discord.Object(id=self.entorno.guild_id))
        except discord.HTTPException as exc:
            app = self.application_id or "<id de la aplicación>"
            log.error(  # noqa: TRY400 — el traceback no dice nada útil
                "no pude registrar los comandos en el servidor %s (%s). ¿Ya invitaste "
                "al bot? https://discord.com/oauth2/authorize?client_id=%s"
                "&scope=bot+applications.commands&permissions=%s",
                self.entorno.guild_id,
                exc.text or exc.status,
                app,
                PERMISOS_DEL_BOT,
            )
            return False
        self._comandos_registrados = True
        return True

    async def on_guild_join(self, guild: discord.Guild) -> None:
        log.info("me invitaron a %s", guild.name)
        if guild.id == self.entorno.guild_id and not self._comandos_registrados:
            await self._registrar_comandos()
            log.info("comandos registrados en %s", guild.name)

    async def on_ready(self) -> None:
        self._sin_discord_desde = None
        log.info("conectado como %s", self.user)
        if (diferencia := self.config.descuadre) is not None:
            log.info(
                "las cuotas suman %s %s que el precio del VPS (%s); la meta es el precio",
                Dinero(abs(diferencia.centavos)),
                "más" if diferencia.es_positivo else "menos",
                self.config.total,
            )
        if self.config.esta_sin_llenar:
            log.warning(
                "la sección `pagos` de settings.yml todavía trae CAMBIAME; "
                "no voy a poder abrir el mes hasta que la llenes"
            )
        if self.recordatorios is None:
            self.recordatorios = Recordatorios(self.servicio, self, self.entorno.canal_id)
            self.recordatorios.arrancar()

    async def on_resumed(self) -> None:
        self._sin_discord_desde = None

    async def on_disconnect(self) -> None:
        if self._sin_discord_desde is None:
            self._sin_discord_desde = time.monotonic()

    @tasks.loop(minutes=1)
    async def marcar_vivo(self) -> None:
        """Para el healthcheck del contenedor, y el perro guardián.

        Solo marca vivo si de verdad hay conexión con Discord. Y si lleva
        demasiado sin ella, se sale para que Docker lo reinicie.
        """
        if self._sin_discord_desde is None:
            try:
                salud.tocar()
            except OSError:
                log.warning("no pude escribir la marca de salud", exc_info=True)
            return

        sin_discord = time.monotonic() - self._sin_discord_desde
        if sin_discord >= MAXIMO_SIN_DISCORD_SEGUNDOS:
            log.error(
                "llevo %d minutos sin Discord; me salgo para que Docker me reinicie",
                sin_discord // 60,
            )
            self.codigo_de_salida = 1
            await self.close()

    @tasks.loop(hours=1)
    async def foto_de_la_base(self) -> None:
        """Una copia consistente de la base, para los respaldos."""
        destino = self.entorno.ruta_db.with_name(NOMBRE_DE_LA_FOTO)
        try:
            self.servicio.repo.copiar_a(destino)
        except (OSError, sqlite3.Error):
            log.warning("no pude sacar la foto de la base de datos", exc_info=True)

    @tasks.loop(minutes=1)
    async def vigilar_minecraft(self) -> None:
        """Avisa en el canal de alertas si el servidor se cae o vuelve."""
        contesto = await vigia.contesta(self.entorno.minecraft_host, self.entorno.minecraft_puerto)
        cambio = self._vigia.registrar(contesto)
        if cambio is None or self.entorno.alertas_canal_id is None:
            return
        log.info("el servidor de Minecraft: %s", cambio)
        canal = self.get_channel(self.entorno.alertas_canal_id)
        if not isinstance(canal, discord.abc.Messageable):
            log.error("no encuentro el canal de alertas %s", self.entorno.alertas_canal_id)
            return
        try:
            await canal.send(vigia.texto_de(cambio, self._vigia.fallas_para_avisar))
        except discord.DiscordException:
            log.exception("no pude mandar la alerta")

    @vigilar_minecraft.before_loop
    async def _esperar_para_vigilar(self) -> None:
        await self.wait_until_ready()

    @marcar_vivo.before_loop
    async def _esperar_conexion(self) -> None:
        await self.wait_until_ready()

    async def close(self) -> None:
        if self.recordatorios is not None:
            self.recordatorios.parar()
        for ciclo in (self.marcar_vivo, self.foto_de_la_base, self.vigilar_minecraft):
            ciclo.cancel()
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
    config, de_la_base = cargar_config(repo, config)
    if de_la_base:
        log.info(
            "uso la configuración del cobro guardada en la base (se cambia desde "
            "Discord con /ajustes y /miembro; la sección pagos de settings.yml "
            "solo se usó la primera vez)"
        )
    else:
        log.info("primera vez: guardé la sección pagos de settings.yml en la base")
    servicio = ServicioDeCobros(config, repo)
    # Que el mes en curso tenga el precio del VPS que está en la configuración
    # (por si se cambió con una versión que no lo aplicaba al mes abierto).
    with suppress(ErrorDeCobro):
        servicio.cambiar_precio_de_meses_abiertos(config.total)
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
            "Discord rechazó el token. Revisa PAGOS_BOT_TOKEN en .env.\nVer docs/bot-pagos.md."
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
    return bot.codigo_de_salida


def run() -> None:
    """Punto de entrada del contenedor."""
    try:
        sys.exit(asyncio.run(arrancar()))
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(0)


if __name__ == "__main__":  # pragma: no cover
    run()
