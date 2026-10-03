"""El reloj del bot: revisa una vez al día si toca mandar un recordatorio.

Los avisos son idempotentes: antes de mandar uno, el servicio revisa en la
base de datos si ya se mandó ese mismo aviso hoy. Por eso reiniciar el bot
tres veces el día de pago no menciona a nadie tres veces.
"""

from __future__ import annotations

import logging
from contextlib import suppress

import discord
from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pagos_bot.discord_ui import botones, tarjetas, textos
from pagos_bot.services.cobros import (
    AVISO_DIA,
    AVISO_PREVIO,
    AvisoQueToca,
    ErrorDeCobro,
    ServicioDeCobros,
)

log = logging.getLogger("pagos.scheduler")

# La hora sale de la configuración (`/ajustes hora`, 11 por defecto: ni tan
# temprano que nadie lo vea, ni tan tarde que ya se les haya pasado el día).
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
        # Para no apagar dos veces: `parar()` llega por el manejador de
        # SIGTERM y otra vez por el cierre de discord.py.
        self._parado = False

    def _programar(self) -> None:
        hora = self.servicio.config.hora_aviso
        self.scheduler.add_job(
            self.revisar,
            CronTrigger(hour=hora, minute=MINUTO_DEL_AVISO, timezone=self.servicio.config.zona),
            id="aviso_diario",
            replace_existing=True,
            # Si el bot estuvo caído a la hora exacta, que lo mande al volver
            # dentro de las siguientes 6 horas en lugar de saltárselo.
            misfire_grace_time=6 * 3600,
        )
        log.info(
            "recordatorios programados para las %02d:%02d, hora de %s",
            hora,
            MINUTO_DEL_AVISO,
            self.servicio.config.zona_horaria,
        )

    def arrancar(self) -> None:
        self._programar()
        self.scheduler.start()

    def reprogramar(self) -> None:
        """Después de `/ajustes hora`: el mismo trabajo, a la hora nueva."""
        self._programar()

    def parar(self) -> None:
        """Para el reloj. Se puede llamar varias veces sin que truene.

        Hace falta blindarlo por dos razones:

        1. `parar()` llega dos veces: una por el manejador de SIGTERM que
           pone Docker en cada `mc restart`, y otra por el cierre de
           discord.py.
        2. apscheduler DIFIERE el apagado al event loop
           (`@run_in_event_loop` sobre `_shutdown`). Su `shutdown()` revisa
           `running`, que todavía es True, y encola el apagado; cuando el
           segundo callback corre, el primero ya dejó el estado en STOPPED y
           `SchedulerNotRunningError` sale desde dentro del loop, donde ya no
           lo puede atrapar nadie.

        Sin esto, cada `mc restart` dejaba un traceback de 10 líneas en el
        log del contenedor, con el bot apagándose perfectamente bien.
        """
        if self._parado:
            return
        self._parado = True
        with suppress(SchedulerNotRunningError):
            self.scheduler.shutdown(wait=False)

    async def revisar(self) -> None:
        """¿Toca mandar algo hoy? Si sí, lo manda.

        Puede tocar más de uno el mismo día (el del mes en curso y el de un
        mes que quedó debiéndose). Sale uno por mensaje.

        Si Discord o la base de datos fallan, lo anota en el log y sigue
        vivo: un bot caído no cobra nada.
        """
        try:
            avisos = self.servicio.avisos_que_tocan()
        except ErrorDeCobro as exc:
            log.warning("no pude revisar los avisos: %s", exc)
            return
        except Exception:
            log.exception("error inesperado al revisar los avisos")
            return

        if not avisos:
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

        for aviso in avisos:
            await self._mandar(canal, aviso)

    async def _mandar(self, canal: discord.abc.Messageable, aviso: AvisoQueToca) -> None:
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
                view=tarjetas.aviso(texto, mes, urgente=urgente, botones=[botones.BotonYaPague()]),
                allowed_mentions=tarjetas.SOLO_PERSONAS,
            )
        except discord.DiscordException:
            # No lo anotamos: si falló, que se reintente.
            log.exception("no pude mandar el aviso al canal")
            return

        self.servicio.anotar_que_se_mando(aviso)
        log.info("mandé el aviso '%s' de %s", aviso.tipo, mes.periodo.clave)
