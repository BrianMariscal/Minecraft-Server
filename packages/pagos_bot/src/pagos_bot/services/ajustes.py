"""Cambiar la configuración del cobro desde Discord, sin tocar archivos.

La configuración vive en la base de datos del bot (tabla `ajustes`). La
sección `pagos` de settings.yml solo se usa la PRIMERA vez, para llenarla;
de ahí en adelante manda lo que se cambie con los comandos del tesorero.

Cada cambio se valida completo con PagosConfig antes de guardarse: si el
resultado no es una configuración válida, no se guarda nada.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError

from pagos_bot.config import PagosConfig
from pagos_bot.domain.cobro import Estado, Reparto
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.services.cobros import ErrorDeCobro, ServicioDeCobros

log = logging.getLogger("pagos.ajustes")

CLAVE_CONFIG = "config"


def cargar_config(repo: RepositorioPagos, de_settings: PagosConfig) -> tuple[PagosConfig, bool]:
    """La configuración que manda: la guardada, o la de settings.yml la 1a vez.

    Devuelve (config, venía_de_la_base). `activo` y `zona_horaria` siempre
    salen de settings.yml: son del servidor, no del cobro.
    """
    guardada = repo.leer_ajuste(CLAVE_CONFIG)
    if guardada is None:
        repo.guardar_ajuste(CLAVE_CONFIG, de_settings.model_dump_json())
        return de_settings, False
    try:
        config = PagosConfig.model_validate_json(guardada)
    except ValidationError:
        log.exception("la configuración guardada no es válida; uso la de settings.yml")
        return de_settings, False
    return (
        config.model_copy(
            update={"activo": de_settings.activo, "zona_horaria": de_settings.zona_horaria}
        ),
        True,
    )


def leer_monto(texto: str) -> Decimal:
    """'40', '$40.50', '40,50' -> Decimal. Truena con un mensaje claro."""
    limpio = texto.strip().replace("$", "").replace(" ", "").replace(",", ".")
    try:
        monto = Decimal(limpio)
    except InvalidOperation as exc:
        msg = f"`{texto}` no es una cantidad. Escríbela como `40` o `40.50`."
        raise ErrorDeCobro(msg) from exc
    if monto <= 0 or monto != monto.quantize(Decimal("0.01")):
        msg = f"`{texto}` no sirve: tiene que ser mayor que cero y con máximo dos decimales."
        raise ErrorDeCobro(msg)
    return monto


class ServicioDeAjustes:
    """Todo lo que el tesorero puede cambiar desde Discord."""

    def __init__(self, cobros: ServicioDeCobros) -> None:
        self.cobros = cobros

    @property
    def config(self) -> PagosConfig:
        return self.cobros.config

    def _guardar(self, **cambios: Any) -> PagosConfig:
        """Valida la config con los cambios y, si sirve, la aplica y la guarda."""
        datos = self.config.model_dump(mode="json")
        datos.update(cambios)
        try:
            nueva = PagosConfig.model_validate(datos)
        except ValidationError as exc:
            detalle = "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
            msg = f"ese cambio no se puede: {detalle}"
            raise ErrorDeCobro(msg) from exc
        self.cobros.aplicar_config(nueva)
        self.cobros.repo.guardar_ajuste(CLAVE_CONFIG, nueva.model_dump_json())
        return nueva

    def _participantes(self) -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in self.config.participantes]

    # -- miembros ---------------------------------------------------------- #

    def agregar_miembro(self, discord_id: int, nombre: str, monto: str | None) -> Dinero:
        """Mete a alguien a la banda. Entra también al mes en curso.

        Devuelve lo que le toca pagar.
        """
        if any(p.discord_id == discord_id for p in self.config.participantes):
            msg = f"**{nombre}** ya está en la lista."
            raise ErrorDeCobro(msg)
        personalizado = self.config.reparto is Reparto.PERSONALIZADO
        if personalizado and monto is None:
            msg = "con reparto personalizado hay que decir cuánto paga (`monto`)."
            raise ErrorDeCobro(msg)
        nuevo: dict[str, Any] = {"nombre": nombre[:32], "discord_id": discord_id}
        if monto is not None:
            nuevo["monto_mxn"] = str(leer_monto(monto))
        self._guardar(participantes=[*self._participantes(), nuevo])

        # El mes en curso lo recoge solo (ServicioDeCobros._sincronizar_gente).
        mes = self.cobros.mes_actual()
        cuota = mes.cuota_de(discord_id)
        return cuota.monto if cuota else Dinero.cero()

    def quitar_miembro(self, discord_id: int) -> str:
        """Saca a alguien de la banda. Devuelve qué pasó con su mes en curso.

        Si este mes ya pagó, ese dinero se queda contado. Si no, queda como
        "no le toca": no se le va a perseguir por un mes en el que ya no está.
        """
        quien = next((p for p in self.config.participantes if p.discord_id == discord_id), None)
        if quien is None:
            msg = "esa persona no está en la lista."
            raise ErrorDeCobro(msg)
        mes = self.cobros.mes_actual()
        self._guardar(
            participantes=[
                p.model_dump(mode="json")
                for p in self.config.participantes
                if p.discord_id != discord_id
            ]
        )
        cuota = mes.cuota_de(discord_id)
        if cuota is None or cuota.estado in (Estado.PAGADO, Estado.EXENTO):
            return "ya no se le cobra a partir del mes que viene"
        self.cobros.eximir(discord_id)
        return "este mes ya no se le cobra"

    def cambiar_monto(self, discord_id: int, monto: str, *, este_mes: bool) -> Dinero:
        """Cambia lo que paga alguien. Con `este_mes`, también el mes en curso."""
        if self.config.reparto is not Reparto.PERSONALIZADO:
            msg = (
                "con reparto `iguales` el monto sale de dividir el total. "
                "Cambia el total con `/ajustes total`, o pasa a reparto personalizado."
            )
            raise ErrorDeCobro(msg)
        valor = leer_monto(monto)
        participantes = self._participantes()
        for p in participantes:
            if p["discord_id"] == discord_id:
                p["monto_mxn"] = str(valor)
                break
        else:
            msg = "esa persona no está en la lista."
            raise ErrorDeCobro(msg)
        self._guardar(participantes=participantes)
        if este_mes:
            self.cobros.cambiar_monto_del_mes(discord_id, Dinero.de_pesos(valor))
        return Dinero.de_pesos(valor)

    def renombrar(self, discord_id: int, nombre: str) -> None:
        participantes = self._participantes()
        for p in participantes:
            if p["discord_id"] == discord_id:
                p["nombre"] = nombre.strip()[:32]
                break
        else:
            msg = "esa persona no está en la lista."
            raise ErrorDeCobro(msg)
        self._guardar(participantes=participantes)

    # -- el cobro ---------------------------------------------------------- #

    def cambiar_dia(self, dia: int) -> None:
        self._guardar(dia_de_pago=dia)

    def cambiar_total(self, monto: str) -> Dinero:
        """El precio del VPS. Aplica desde ya, también al mes en curso."""
        valor = leer_monto(monto)
        self._guardar(monto_total_mxn=str(valor))
        total = Dinero.de_pesos(valor)
        self.cobros.cambiar_precio_de_meses_abiertos(total)
        return total

    def cambiar_reparto(self, reparto: Reparto) -> None:
        if reparto is Reparto.PERSONALIZADO:
            sin = [p.nombre for p in self.config.participantes if p.monto_mxn is None]
            if sin:
                msg = (
                    "para pasar a reparto personalizado, primero ponle monto a: "
                    + ", ".join(sin)
                    + " (`/miembro monto`)."
                )
                raise ErrorDeCobro(msg)
        self._guardar(reparto=reparto.value)

    def cambiar_avisos(self, dias_antes: int, cada_dias_despues: int) -> None:
        self._guardar(avisos={"dias_antes": dias_antes, "cada_dias_despues": cada_dias_despues})

    def cambiar_hora(self, hora: int) -> None:
        self._guardar(hora_aviso=hora)

    def cambiar_tesorero(self, discord_id: int, nombre: str) -> None:
        self._guardar(tesorero={"nombre": nombre[:32], "discord_id": discord_id})

    def cambiar_rol_admin(self, rol_id: int) -> None:
        self._guardar(rol_admin_id=rol_id)
