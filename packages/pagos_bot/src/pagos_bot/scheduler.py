"""El reloj del bot: revisa una vez al día si toca mandar un recordatorio.

Los avisos son idempotentes: antes de mandar uno, el servicio revisa en la
base de datos si ya se mandó ese mismo aviso hoy. Por eso reiniciar el bot
tres veces el día de pago no menciona a nadie tres veces.
"""

from __future__ import annotations

import logging

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pagos_bot.discord_ui import botones, embeds, textos
from pagos_bot.services.cobros import (
    AVISO_DIA,
    AVISO_PREVIO,
    ErrorDeCobro,
    ServicioDeCobros,
)

log = logging.getLogger("pagos.scheduler")

# A las 11 de la mañana, hora de México. Ni tan temprano que nadie lo vea,
# ni tan tarde que ya se les haya pasado el día.
HORA_DEL_AVISO = 11
MINUTO_DEL_AVISO = 0


class Recordatorios:
    """Manda los avisos de pago a su hora."""

    def __init__(
        self,
        servicio: ServicioDeCobros,
        cliente: discord.Client,
        canal_id: int,
    ) -> None:
        self.servicio = servicio
        self.cliente = cliente
        self.canal_id = canal_id
        self.scheduler = AsyncIOScheduler(timezone=servicio.config.zona)

    def arrancar(self) -> None:
        self.scheduler.add_job(
            self.revisar,
            CronTrigger(
                hour=HORA_DEL_AVISO,
                minute=MINUTO_DEL_AVISO,
                timezone=self.servicio.config.zona,
            ),
            id="aviso_diario",
            replace_existing=True,
            # Si el bot estuvo caído a la hora exacta, que lo mande al volver
            # dentro de las siguientes 6 horas en lugar de saltárselo.
            misfire_grace_time=6 * 3600,
        )
        self.scheduler.start()
        log.info(
            "recordatorios programados para las %02d:%02d, hora de %s",
            HORA_DEL_AVISO,
            MINUTO_DEL_AVISO,
            self.servicio.config.zona_horaria,
        )

    def parar(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def revisar(self) -> None:
        """¿Toca mandar algo hoy? Si sí, lo manda.

        Si Discord o la base de datos fallan, lo anota en el log y sigue
        vivo: un bot caído no cobra nada.
        """
        try:
            aviso = self.servicio.aviso_que_toca()
        except ErrorDeCobro as exc:
            log.warning("no pude revisar los avisos: %s", exc)
            return
        except Exception:
            log.exception("error inesperado al revisar los avisos")
            return

        if aviso is None:
            log.debug("hoy no toca ningún aviso")
            return

        canal = self.cliente.get_channel(self.canal_id)
        if not isinstance(canal, discord.abc.Messageable):
            log.error(
                "no encuentro el canal %s. Revisa PAGOS_CANAL_ID en .env y que "
                "el bot tenga permiso de verlo.",
                self.canal_id,
            )
            return

        agenda = self.servicio.agenda
        mes = aviso.mes

        if aviso.tipo == AVISO_PREVIO:
            texto = textos.aviso_previo(mes, agenda, agenda.dias_antes)
            urgente = False
        elif aviso.tipo == AVISO_DIA:
            texto = textos.aviso_del_dia(mes, agenda)
            urgente = False
        else:
            texto = textos.aviso_tardio(mes, agenda, aviso.dias_de_atraso)
            urgente = True

        try:
            await canal.send(
                embed=embeds.aviso(texto, urgente=urgente),
                view=botones.BotonYaPague(self.servicio),
            )
        except discord.DiscordException:
            # No anotamos el aviso: si falló, que se reintente.
            log.exception("no pude mandar el aviso al canal")
            return

        self.servicio.anotar_que_se_mando(aviso)
        log.info("mandé el aviso '%s' de %s", aviso.tipo, mes.periodo.clave)
