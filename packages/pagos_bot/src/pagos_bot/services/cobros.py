"""Los casos de uso del bot.

Aquí se juntan el dominio y el repositorio, pero todavía sin Discord: estas
funciones devuelven datos, no mandan mensajes. Eso lo hace `discord_ui`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pagos_bot.config import PagosConfig
from pagos_bot.domain.calendario import Agenda, Periodo
from pagos_bot.domain.cobro import Cuota, Estado, MesDeCobro, abrir_mes
from pagos_bot.repository.pagos_repo import RepositorioPagos


class ErrorDeCobro(Exception):
    """Algo que el usuario puede entender y arreglar."""


# Los tipos de aviso, tal como se guardan en la tabla `avisos`.
AVISO_PREVIO = "previo"
AVISO_DIA = "dia"
AVISO_TARDIO = "tardio"


@dataclass(frozen=True, slots=True)
class AvisoQueToca:
    """Un recordatorio que hay que mandar."""

    tipo: str
    mes: MesDeCobro
    # A quién mencionar. En el aviso previo va vacío: ahí no se señala a nadie.
    mencionar: tuple[Cuota, ...]
    dias_de_atraso: int = 0


class ServicioDeCobros:
    """Todo lo que el bot sabe hacer con los pagos."""

    def __init__(self, config: PagosConfig, repo: RepositorioPagos) -> None:
        self.config = config
        self.repo = repo
        self.agenda = Agenda(
            dia_de_pago=config.dia_de_pago,
            dias_antes=config.avisos.dias_antes,
            cada_dias_despues=config.avisos.cada_dias_despues,
            zona=config.zona,
        )

    # -- el mes ------------------------------------------------------------ #

    def ahora(self) -> datetime:
        return datetime.now(self.config.zona)

    def periodo_actual(self) -> Periodo:
        return self.agenda.periodo_actual(self.ahora())

    def mes_actual(self) -> MesDeCobro:
        """El mes de ahorita. Si no existe, lo abre.

        Esto es lo que hace que "cada mes arranca un periodo nuevo
        automáticamente": nadie tiene que acordarse de nada.
        """
        return self.abrir_si_falta(self.periodo_actual())

    def abrir_si_falta(self, periodo: Periodo) -> MesDeCobro:
        """Devuelve el mes, abriéndolo si todavía no existía."""
        existente = self.repo.leer_mes(periodo)
        if existente is not None:
            return self._sincronizar_gente(existente)

        if self.config.esta_sin_llenar:
            msg = (
                "la sección `pagos` de settings.yml todavía trae CAMBIAME.\n"
                "Pon a la banda y al tesorero. Guía: docs/bot-pagos.md"
            )
            raise ErrorDeCobro(msg)

        try:
            mes = abrir_mes(periodo, self.config.total, self.config.gente, self.config.reparto)
        except ValueError as exc:
            raise ErrorDeCobro(str(exc)) from exc

        self.repo.guardar_mes(mes, self.config.reparto)
        return mes

    def _sincronizar_gente(self, mes: MesDeCobro) -> MesDeCobro:
        """Mete a quien se haya agregado a settings.yml después de abrir el mes.

        A quien se quitó de settings.yml NO lo borramos del mes que ya corre:
        si ya pagó, ese dinero cuenta, y borrarlo descuadraría el total.
        """
        conocidos = {c.participante.discord_id for c in mes.cuotas}
        nuevos = [p for p in self.config.gente if p.discord_id not in conocidos]
        if not nuevos:
            return mes

        try:
            plantilla = abrir_mes(
                mes.periodo, self.config.total, self.config.gente, self.config.reparto
            )
        except ValueError:  # pragma: no cover — ya validado al abrir
            return mes

        por_id = {c.participante.discord_id: c for c in plantilla.cuotas}
        agregadas = tuple(por_id[p.discord_id] for p in nuevos if p.discord_id in por_id)
        actualizado = MesDeCobro(
            periodo=mes.periodo, total=mes.total, cuotas=mes.cuotas + agregadas
        )
        self.repo.guardar_mes(actualizado, self.config.reparto)
        return actualizado

    # -- marcar pagos ------------------------------------------------------- #

    def dijo_que_pago(self, discord_id: int) -> MesDeCobro:
        """Alguien le picó a "Ya pagué" o escribió /pague."""
        mes = self.mes_actual()
        cuota = mes.cuota_de(discord_id)
        if cuota is None:
            msg = "no estás en la lista de este mes. Dile a un admin que te agregue."
            raise ErrorDeCobro(msg)
        if cuota.estado is Estado.PAGADO:
            msg = "ya tienes el mes pagado y confirmado, no tienes que hacer nada."
            raise ErrorDeCobro(msg)
        if cuota.estado is Estado.EXENTO:
            msg = "este mes no te toca pagar."
            raise ErrorDeCobro(msg)

        nuevo = mes.con_estado(discord_id, Estado.POR_CONFIRMAR, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        return nuevo

    def confirmar(self, discord_id: int) -> MesDeCobro:
        """El tesorero confirma que sí llegó el dinero."""
        mes = self.mes_actual()
        if mes.cuota_de(discord_id) is None:
            msg = "esa persona no está en la lista de este mes."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.PAGADO, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        self._cerrar_si_ya_esta(nuevo)
        return nuevo

    def desmarcar(self, discord_id: int) -> MesDeCobro:
        """Regresa a alguien a pendiente (se equivocaron, se devolvió el pago...)."""
        mes = self.mes_actual()
        if mes.cuota_de(discord_id) is None:
            msg = "esa persona no está en la lista de este mes."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.PENDIENTE, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        return nuevo

    def eximir(self, discord_id: int) -> MesDeCobro:
        """Sacar a alguien del mes sin que cuente como que debe."""
        mes = self.mes_actual()
        if mes.cuota_de(discord_id) is None:
            msg = "esa persona no está en la lista de este mes."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.EXENTO, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        self._cerrar_si_ya_esta(nuevo)
        return nuevo

    def _cerrar_si_ya_esta(self, mes: MesDeCobro) -> None:
        if mes.esta_cubierto:
            self.repo.marcar_cerrado(mes.periodo, self.ahora())

    # -- avisos -------------------------------------------------------------- #

    def aviso_que_toca(self, hoy: date | None = None) -> AvisoQueToca | None:
        """Qué recordatorio hay que mandar hoy, si es que alguno.

        Nunca devuelve dos veces el mismo aviso del mismo día: antes de
        proponerlo revisa la tabla `avisos`. Por eso reiniciar el bot no
        vuelve a mencionar a nadie.
        """
        ahora = self.ahora()
        dia = hoy or self.agenda.hoy(ahora)
        mes = self.mes_actual()

        if mes.esta_cubierto:
            return None

        tipo: str
        mencionar: tuple[Cuota, ...]
        atraso: int

        if self.agenda.toca_aviso_previo(mes.periodo, ahora):
            # En el aviso previo no se menciona a nadie: todavía no deben nada.
            tipo, mencionar, atraso = AVISO_PREVIO, (), 0
        elif self.agenda.toca_aviso_del_dia(mes.periodo, ahora):
            tipo, mencionar, atraso = AVISO_DIA, tuple(mes.faltantes), 0
        elif self.agenda.toca_recordatorio_tardio(mes.periodo, ahora):
            tipo = AVISO_TARDIO
            mencionar = tuple(mes.faltantes)
            atraso = -self.agenda.dias_para_pagar(mes.periodo, ahora)
        else:
            return None

        # Si no falta nadie, no hay a quién recordarle.
        if tipo != AVISO_PREVIO and not mencionar:
            return None

        if self.repo.ya_se_mando(mes.periodo, tipo, dia):
            return None

        return AvisoQueToca(tipo=tipo, mes=mes, mencionar=mencionar, dias_de_atraso=atraso)

    def anotar_que_se_mando(self, aviso: AvisoQueToca, hoy: date | None = None) -> None:
        """Deja constancia para no repetirlo."""
        ahora = self.ahora()
        self.repo.anotar_aviso(aviso.mes.periodo, aviso.tipo, hoy or self.agenda.hoy(ahora), ahora)

    # -- historial ----------------------------------------------------------- #

    def historial(self, cuantos: int = 6) -> list[MesDeCobro]:
        """Los meses anteriores, del más nuevo al más viejo."""
        actual = self.periodo_actual()
        meses: list[MesDeCobro] = []
        for p in self.repo.periodos_guardados(cuantos + 1):
            if p == actual:
                continue
            mes = self.repo.leer_mes(p)
            if mes is not None:
                meses.append(mes)
        return meses[:cuantos]
