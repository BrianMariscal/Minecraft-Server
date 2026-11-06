"""Los casos de uso del bot.

Aquí se juntan el dominio y el repositorio, pero todavía sin Discord: estas
funciones devuelven datos, no mandan mensajes. Eso lo hace `discord_ui`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pagos_bot.config import PagosConfig
from pagos_bot.domain.auditoria import Actor, RegistroDeAuditoria
from pagos_bot.domain.calendario import Agenda, Periodo
from pagos_bot.domain.cobro import Cuota, Estado, MesDeCobro, abrir_mes
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.pagos_repo import RepositorioPagos


class ErrorDeCobro(Exception):
    """Algo que el usuario puede entender y arreglar."""


# Los tipos de aviso, tal como se guardan en la tabla `avisos`.
AVISO_PREVIO = "previo"
AVISO_DIA = "dia"
AVISO_TARDIO = "tardio"

# Hasta cuántos meses atrás se sigue persiguiendo una deuda.
MESES_QUE_SE_PERSIGUEN = 12


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
        self.repo = repo
        self.aplicar_config(config)

    def aplicar_config(self, config: PagosConfig) -> None:
        """Cambia la configuración en caliente (la usan los comandos del tesorero)."""
        self.config = config
        self.agenda = Agenda(
            dia_de_pago=config.dia_de_pago,
            dias_antes=config.avisos.dias_antes,
            cada_dias_despues=config.avisos.cada_dias_despues,
            zona=config.zona,
        )

    # -- auditoría ---------------------------------------------------------- #

    def auditar(
        self,
        accion: str,
        *,
        actor: Actor | None = None,
        periodo: Periodo | None = None,
        objetivo_id: int | None = None,
        detalle: dict[str, str] | None = None,
    ) -> None:
        """Apunta un movimiento en el libro. Sin actor, es el bot."""
        self.repo.anotar_auditoria(
            RegistroDeAuditoria(
                cuando=self.ahora(),
                actor=actor or Actor.sistema(),
                accion=accion,
                periodo=periodo,
                objetivo_id=objetivo_id,
                detalle=detalle or {},
            )
        )

    def movimientos(self, cuantos: int = 20) -> list[RegistroDeAuditoria]:
        """Los últimos movimientos del cobro, del más nuevo al más viejo."""
        return self.repo.leer_auditoria(cuantos)

    # -- el mes ------------------------------------------------------------ #

    def ahora(self) -> datetime:
        return datetime.now(self.config.zona)

    def periodo_actual(self) -> Periodo:
        return self.agenda.periodo_actual(self.ahora())

    def mes_actual(self) -> MesDeCobro:
        """El mes actual. Si no existe, lo abre.

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

    # -- qué mes -------------------------------------------------------------- #

    def mes_de(self, periodo: Periodo | None) -> MesDeCobro:
        """El mes que pide un comando. None = el actual.

        El actual y el que sigue se abren si hace falta (el que sigue lo
        abre el aviso previo unos días antes). Uno viejo tiene que existir.
        """
        if periodo is None:
            return self.mes_actual()
        actual = self.periodo_actual()
        if periodo in (actual, actual.siguiente()):
            return self.abrir_si_falta(periodo)
        mes = self.repo.leer_mes(periodo)
        if mes is None:
            msg = f"no hay cobro de {periodo.nombre}."
            raise ErrorDeCobro(msg)
        return mes

    def meses_abiertos(self) -> list[MesDeCobro]:
        """Del más viejo al más nuevo: donde se busca qué debe cada quien.

        Trae el actual (aunque ya esté cubierto), los anteriores que
        todavía no se cierran, y el que sigue si el aviso previo ya lo abrió.
        """
        actual = self.mes_actual()
        limite = actual.periodo.siguiente()
        meses: list[MesDeCobro] = []
        for p in sorted(self.repo.periodos_guardados(MESES_QUE_SE_PERSIGUEN + 2)):
            if p > limite:
                continue
            if p == actual.periodo:
                meses.append(actual)
                continue
            if p < actual.periodo and self.repo.esta_cerrado(p):
                continue
            mes = self.repo.leer_mes(p)
            if mes is not None:
                meses.append(mes)
        return meses

    def deudas_anteriores(self) -> list[MesDeCobro]:
        """Los meses ya pasados en los que todavía falta gente."""
        actual = self.periodo_actual()
        return [
            m
            for m in self.meses_abiertos()
            if m.periodo < actual and not m.esta_cubierto and m.faltantes
        ]

    # -- marcar pagos ------------------------------------------------------- #

    def dijo_que_pago(self, discord_id: int, *, actor: Actor | None = None) -> MesDeCobro:
        """Alguien le picó a "Ya pagué" o escribió /pague.

        Se anota en el mes MÁS VIEJO que deba: primero se salda lo atrasado.
        Si ya está al corriente y el aviso previo ya abrió el mes que sigue,
        cuenta como pago adelantado de ese. Sin esto, picarle al botón del
        aviso previo (que sale el 30 por el mes que viene) contestaba "ya
        tienes el mes pagado" y no había forma de avisar el pago.
        """
        suyos = [(m, c) for m in self.meses_abiertos() if (c := m.cuota_de(discord_id)) is not None]
        if not suyos:
            msg = "no estás en la lista de este mes. Dile a un admin que te agregue."
            raise ErrorDeCobro(msg)

        pendiente = next((m for m, c in suyos if c.estado is Estado.PENDIENTE), None)
        if pendiente is not None:
            nuevo = pendiente.con_estado(discord_id, Estado.POR_CONFIRMAR, self.ahora())
            self.repo.guardar_mes(nuevo, self.config.reparto)
            cuota = nuevo.cuota_de(discord_id)
            self.auditar(
                "pago.avisado",
                actor=actor,
                periodo=nuevo.periodo,
                objetivo_id=discord_id,
                detalle={
                    "objetivo": cuota.participante.nombre if cuota else str(discord_id),
                    "monto": str(cuota.monto) if cuota else "",
                },
            )
            return nuevo

        # Nada pendiente. Si ya avisó, no volvemos a etiquetar al tesorero
        # cada vez que le pique al botón.
        esperando = next((m for m, c in suyos if c.estado is Estado.POR_CONFIRMAR), None)
        if esperando is not None:
            msg = (
                f"ya le avisé al tesorero de tu pago de {esperando.periodo.nombre}; "
                "solo falta que lo confirme."
            )
            raise ErrorDeCobro(msg)

        actual = self.periodo_actual()
        cuota_actual = next((c for m, c in suyos if m.periodo == actual), None)
        if cuota_actual is not None and cuota_actual.estado is Estado.EXENTO:
            msg = "este mes no te toca pagar."
            raise ErrorDeCobro(msg)
        msg = "ya tienes el mes pagado y confirmado, no tienes que hacer nada."
        raise ErrorDeCobro(msg)

    def confirmar(
        self,
        discord_id: int,
        periodo: Periodo | None = None,
        *,
        actor: Actor | None = None,
    ) -> MesDeCobro:
        """El tesorero confirma que sí llegó el dinero.

        Sin mes, confirma lo más viejo que esa persona tenga: primero lo que
        dijo que pagó y, si no dijo nada (pago en efectivo), lo más viejo que
        deba.
        """
        mes = self.mes_de(periodo) if periodo is not None else self._mes_a_confirmar(discord_id)
        cuota = mes.cuota_de(discord_id)
        if cuota is None:
            msg = f"esa persona no está en la lista de {mes.periodo.nombre}."
            raise ErrorDeCobro(msg)
        if cuota.estado is Estado.PAGADO:
            msg = f"su pago de {mes.periodo.nombre} ya estaba confirmado."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.PAGADO, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        self._cerrar_si_ya_esta(nuevo)
        self.auditar(
            "pago.confirmado",
            actor=actor,
            periodo=nuevo.periodo,
            objetivo_id=discord_id,
            detalle={
                "objetivo": cuota.participante.nombre,
                "monto": str(cuota.monto),
            },
        )
        return nuevo

    def _mes_a_confirmar(self, discord_id: int) -> MesDeCobro:
        meses = self.meses_abiertos()
        for estado in (Estado.POR_CONFIRMAR, Estado.PENDIENTE):
            for m in meses:
                c = m.cuota_de(discord_id)
                if c is not None and c.estado is estado:
                    return m
        if all(m.cuota_de(discord_id) is None for m in meses):
            msg = "esa persona no está en la lista de este mes."
            raise ErrorDeCobro(msg)
        msg = "esa persona no debe nada: ya está al corriente."
        raise ErrorDeCobro(msg)

    def desmarcar(
        self,
        discord_id: int,
        periodo: Periodo | None = None,
        *,
        actor: Actor | None = None,
    ) -> MesDeCobro:
        """Regresa a alguien a pendiente (se equivocaron, se devolvió el pago...)."""
        mes = self.mes_de(periodo)
        cuota = mes.cuota_de(discord_id)
        if cuota is None:
            msg = f"esa persona no está en la lista de {mes.periodo.nombre}."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.PENDIENTE, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        # Si el mes ya estaba cerrado, ya no: vuelve a faltar alguien.
        self.repo.reabrir(nuevo.periodo)
        self.auditar(
            "pago.desmarcado",
            actor=actor,
            periodo=nuevo.periodo,
            objetivo_id=discord_id,
            detalle={"objetivo": cuota.participante.nombre, "estado_anterior": cuota.estado.value},
        )
        return nuevo

    def eximir(
        self,
        discord_id: int,
        periodo: Periodo | None = None,
        *,
        actor: Actor | None = None,
    ) -> MesDeCobro:
        """Sacar a alguien del mes sin que cuente como que debe."""
        mes = self.mes_de(periodo)
        cuota = mes.cuota_de(discord_id)
        if cuota is None:
            msg = f"esa persona no está en la lista de {mes.periodo.nombre}."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_estado(discord_id, Estado.EXENTO, self.ahora())
        self.repo.guardar_mes(nuevo, self.config.reparto)
        self._cerrar_si_ya_esta(nuevo)
        self.auditar(
            "pago.eximido",
            actor=actor,
            periodo=nuevo.periodo,
            objetivo_id=discord_id,
            detalle={"objetivo": cuota.participante.nombre, "monto": str(cuota.monto)},
        )
        return nuevo

    def cambiar_precio_de_meses_abiertos(
        self, total: Dinero, *, actor: Actor | None = None
    ) -> None:
        """El precio nuevo del VPS aplica al mes en curso y al siguiente.

        Los meses ya pasados conservan el precio que tenían: así el historial
        dice lo que costó en realidad.
        """
        actual = self.mes_actual()
        meses = [actual]
        siguiente = self.repo.leer_mes(actual.periodo.siguiente())
        if siguiente is not None:
            meses.append(siguiente)
        cambiados: list[Periodo] = []
        for mes in meses:
            if mes.total == total:
                continue
            nuevo = mes.con_total(total)
            self.repo.guardar_mes(nuevo, self.config.reparto)
            self._cerrar_si_ya_esta(nuevo)
            cambiados.append(mes.periodo)
        if not cambiados:
            return
        self.auditar(
            "mes.precio",
            actor=actor,
            periodo=actual.periodo,
            detalle={
                "total": str(total),
                "meses": ", ".join(p.clave for p in cambiados),
            },
        )

    def cambiar_monto_del_mes(
        self, discord_id: int, monto: Dinero, *, actor: Actor | None = None
    ) -> MesDeCobro:
        """Cambia lo que le toca a alguien en el mes en curso, si no ha pagado."""
        mes = self.mes_actual()
        cuota = mes.cuota_de(discord_id)
        if cuota is None:
            msg = "esa persona no está en el mes en curso."
            raise ErrorDeCobro(msg)
        if cuota.estado is Estado.PAGADO:
            msg = f"ya pagó {mes.periodo.nombre}; el monto nuevo aplica desde el mes que viene."
            raise ErrorDeCobro(msg)
        nuevo = mes.con_monto(discord_id, monto)
        self.repo.guardar_mes(nuevo, self.config.reparto)
        self.auditar(
            "cuota.monto",
            actor=actor,
            periodo=nuevo.periodo,
            objetivo_id=discord_id,
            detalle={
                "objetivo": cuota.participante.nombre,
                "monto_anterior": str(cuota.monto),
                "monto": str(monto),
            },
        )
        return nuevo

    def _cerrar_si_ya_esta(self, mes: MesDeCobro) -> None:
        if mes.esta_cubierto:
            self.repo.marcar_cerrado(mes.periodo, self.ahora())

    # -- avisos -------------------------------------------------------------- #

    def avisos_que_tocan(self, hoy: date | None = None) -> list[AvisoQueToca]:
        """Los recordatorios que hay que mandar hoy, del más urgente al menos.

        Nunca propone dos veces el mismo aviso del mismo día: antes revisa la
        tabla `avisos`. Por eso reiniciar el bot no vuelve a mencionar a nadie.

        OJO con el aviso previo: puede caer en el MES ANTERIOR al que cobra.
        Con `dia_de_pago: 2` y `dias_antes: 3`, el aviso del periodo de
        noviembre toca el 30 de OCTUBRE, cuando el periodo en curso todavía
        es octubre. Por eso hay que mirar también el periodo siguiente y no
        solo el de hoy; si no, con un día de pago temprano el aviso previo
        no sale nunca.

        Y los meses pasados que nadie terminó de pagar siguen recibiendo su
        recordatorio tardío cada N días: una deuda no se borra porque cambió
        el mes.
        """
        ahora = self.ahora()
        dia = hoy or self.agenda.hoy(ahora)

        avisos: list[AvisoQueToca] = []
        # 1. Lo del periodo en curso, que es lo más urgente.
        if (aviso := self._aviso_del_periodo_en_curso(ahora, dia)) is not None:
            avisos.append(aviso)
        # 2. El aviso previo del periodo que viene.
        if (aviso := self._aviso_previo_del_siguiente(ahora, dia)) is not None:
            avisos.append(aviso)
        # 3. Lo que se quedó debiendo de meses anteriores.
        avisos.extend(self._avisos_de_meses_atrasados(ahora, dia))
        return avisos

    def aviso_que_toca(self, hoy: date | None = None) -> AvisoQueToca | None:
        """El más urgente de `avisos_que_tocan`, o None si hoy no toca nada."""
        return next(iter(self.avisos_que_tocan(hoy)), None)

    def _avisos_de_meses_atrasados(self, ahora: datetime, dia: date) -> list[AvisoQueToca]:
        avisos: list[AvisoQueToca] = []
        for mes in self.deudas_anteriores():
            if not self.agenda.toca_recordatorio_tardio(mes.periodo, ahora):
                continue
            if self.repo.ya_se_mando(mes.periodo, AVISO_TARDIO, dia):
                continue
            avisos.append(
                AvisoQueToca(
                    tipo=AVISO_TARDIO,
                    mes=mes,
                    mencionar=tuple(mes.faltantes),
                    dias_de_atraso=-self.agenda.dias_para_pagar(mes.periodo, ahora),
                )
            )
        return avisos

    def _aviso_del_periodo_en_curso(self, ahora: datetime, dia: date) -> AvisoQueToca | None:
        """El del día de pago, los tardíos, y el previo si cae en este mes."""
        mes = self.mes_actual()
        if mes.esta_cubierto:
            return None

        tipo: str
        mencionar: tuple[Cuota, ...]
        atraso: int

        if self.agenda.toca_aviso_del_dia(mes.periodo, ahora):
            tipo, mencionar, atraso = AVISO_DIA, tuple(mes.faltantes), 0
        elif self.agenda.toca_recordatorio_tardio(mes.periodo, ahora):
            tipo = AVISO_TARDIO
            mencionar = tuple(mes.faltantes)
            atraso = -self.agenda.dias_para_pagar(mes.periodo, ahora)
        elif self.agenda.toca_aviso_previo(mes.periodo, ahora):
            # Solo pasa cuando dia_de_pago > dias_antes.
            tipo, mencionar, atraso = AVISO_PREVIO, (), 0
        else:
            return None

        # Si no falta nadie, no hay a quién recordarle.
        if tipo != AVISO_PREVIO and not mencionar:
            return None

        if self.repo.ya_se_mando(mes.periodo, tipo, dia):
            return None

        return AvisoQueToca(tipo=tipo, mes=mes, mencionar=mencionar, dias_de_atraso=atraso)

    def _aviso_previo_del_siguiente(self, ahora: datetime, dia: date) -> AvisoQueToca | None:
        """El aviso previo cuando el día de pago cae temprano en el mes."""
        siguiente = self.periodo_actual().siguiente()
        if not self.agenda.toca_aviso_previo(siguiente, ahora):
            return None
        if self.repo.ya_se_mando(siguiente, AVISO_PREVIO, dia):
            return None

        # Abrir el mes unos días antes no tiene costo: todos quedan en
        # pendiente y `mes_actual()` lo encuentra ya abierto cuando entre.
        mes = self.abrir_si_falta(siguiente)
        if mes.esta_cubierto:
            return None
        return AvisoQueToca(tipo=AVISO_PREVIO, mes=mes, mencionar=(), dias_de_atraso=0)

    def anotar_que_se_mando(self, aviso: AvisoQueToca, hoy: date | None = None) -> None:
        """Deja constancia para no repetirlo."""
        ahora = self.ahora()
        self.repo.anotar_aviso(aviso.mes.periodo, aviso.tipo, hoy or self.agenda.hoy(ahora), ahora)

    # -- historial ----------------------------------------------------------- #

    def historial(self, cuantos: int = 6) -> list[MesDeCobro]:
        """Los meses anteriores, del más nuevo al más viejo."""
        actual = self.periodo_actual()
        meses: list[MesDeCobro] = []
        for p in self.repo.periodos_guardados(cuantos + 2):
            # `>= actual` y no `== actual`: el aviso previo abre el mes que
            # viene unos días antes, y ese todavía no es "historial".
            if p >= actual:
                continue
            mes = self.repo.leer_mes(p)
            if mes is not None:
                meses.append(mes)
        return meses[:cuantos]
