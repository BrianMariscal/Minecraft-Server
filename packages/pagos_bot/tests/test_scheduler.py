"""El reloj del bot: que apagarlo dos veces no truene."""

from __future__ import annotations

from typing import Any, cast

import discord
import pytest
from apscheduler.schedulers import SchedulerNotRunningError

from pagos_bot.scheduler import Recordatorios
from pagos_bot.services.cobros import ServicioDeCobros


class SchedulerFalso:
    """Un doble de AsyncIOScheduler que imita su peculiaridad.

    Lo importante es reproducir que apscheduler DIFIERE el apagado al event
    loop (`@run_in_event_loop` sobre `_shutdown`):

      - `shutdown()` revisa `running` y, si está corriendo, ENCOLA el
        trabajo. No para nada todavía, así que `running` sigue en True.
      - Cuando el event loop corre lo encolado, `_shutdown` llama al
        apagado de verdad, que truena si ya estaba parado.

    Por eso un segundo `shutdown()` pasa el primer chequeo sin problema y la
    excepción sale después, desde dentro del loop, donde ya no la atrapa
    nadie. Un doble que pusiera `running = False` de inmediato NO
    reproduciría el bug, y el test pasaría con el código roto.
    """

    def __init__(self) -> None:
        self.running = False
        self.trabajos: list[Any] = []
        # Lo que quedó encolado en el event loop, sin correr todavía.
        self.encolados: list[bool] = []
        self.apagados = 0

    def add_job(self, *args: Any, **kwargs: Any) -> None:
        self.trabajos.append((args, kwargs))

    def start(self) -> None:
        self.running = True

    def shutdown(self, wait: bool = True) -> None:
        if not self.running:
            raise SchedulerNotRunningError
        self.encolados.append(wait)

    def correr_el_loop(self) -> None:
        """Procesa lo encolado, como haría el event loop al cerrarse."""
        while self.encolados:
            self.encolados.pop(0)
            if not self.running:
                # Esto es lo que aparecía como un traceback de 10 líneas.
                raise SchedulerNotRunningError
            self.running = False
            self.apagados += 1


class ClienteFalso:
    def get_channel(self, _id: int) -> None:
        return None


@pytest.fixture
def recordatorios(servicio: ServicioDeCobros) -> Recordatorios:
    # El doble no hereda de discord.Client a propósito: solo usamos
    # get_channel, y heredar arrastraría toda la maquinaria de la librería.
    r = Recordatorios(servicio, cast("discord.Client", ClienteFalso()), canal_id=123)
    r.scheduler = SchedulerFalso()
    return r


class TestApagado:
    def test_apagar_dos_veces_no_truena(self, recordatorios: Recordatorios) -> None:
        """Docker manda SIGTERM en cada `mc restart` y discord.py también
        cierra, así que `parar()` llega dos veces. Antes eso dejaba un
        traceback de 10 líneas en el log con el bot apagándose bien.
        """
        recordatorios.arrancar()
        recordatorios.parar()
        recordatorios.parar()
        recordatorios.parar()
        # Aquí es donde explotaba, no en las llamadas de arriba.
        recordatorios.scheduler.correr_el_loop()

    def test_solo_se_apaga_una_vez_de_verdad(self, recordatorios: Recordatorios) -> None:
        recordatorios.arrancar()
        recordatorios.parar()
        recordatorios.parar()
        recordatorios.scheduler.correr_el_loop()
        assert recordatorios.scheduler.apagados == 1

    def test_apagar_sin_haber_arrancado_no_truena(self, recordatorios: Recordatorios) -> None:
        recordatorios.parar()
        recordatorios.scheduler.correr_el_loop()

    def test_el_doble_si_reproduce_el_bug(self) -> None:
        """Comprobación del propio doble: sin la guarda, truena.

        Si este test deja de fallar al quitar la guarda, el doble se quedó
        corto y los de arriba no están probando nada.
        """
        s = SchedulerFalso()
        s.start()
        s.shutdown(wait=False)  # como el código roto: dos veces seguidas
        s.shutdown(wait=False)
        with pytest.raises(SchedulerNotRunningError):
            s.correr_el_loop()


class TestArranque:
    def test_programa_el_aviso_diario(self, recordatorios: Recordatorios) -> None:
        recordatorios.arrancar()
        trabajos = recordatorios.scheduler.trabajos
        assert len(trabajos) == 1
        _, kwargs = trabajos[0]
        assert kwargs["id"] == "aviso_diario"
        # Si el VPS estuvo caído a la hora exacta, que lo mande al volver.
        assert kwargs["misfire_grace_time"] > 0
