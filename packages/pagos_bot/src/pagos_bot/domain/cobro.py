"""El estado de un mes de cobro: quién pagó, quién debe y cuánto falta.

Lógica pura. No sabe de Discord ni de SQLite: recibe datos y contesta
preguntas. Todo esto se prueba con pytest sin levantar nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.dinero import Dinero, repartir, sumar


class Estado(StrEnum):
    """En qué va cada quien este mes."""

    PENDIENTE = "pendiente"
    POR_CONFIRMAR = "por_confirmar"
    PAGADO = "pagado"
    # Alguien a quien se le perdonó el mes (no estuvo, se salió, lo que sea).
    EXENTO = "exento"

    @property
    def emoji(self) -> str:
        return {
            Estado.PENDIENTE: "❌",
            Estado.POR_CONFIRMAR: "🕓",
            Estado.PAGADO: "✅",
            Estado.EXENTO: "➖",
        }[self]

    @property
    def texto(self) -> str:
        return {
            Estado.PENDIENTE: "falta",
            Estado.POR_CONFIRMAR: "por confirmar",
            Estado.PAGADO: "pagado",
            Estado.EXENTO: "no le toca",
        }[self]


class Reparto(StrEnum):
    IGUALES = "iguales"
    PERSONALIZADO = "personalizado"


@dataclass(frozen=True, slots=True)
class Participante:
    """Alguien que coopera para el VPS."""

    nombre: str
    discord_id: int
    # Solo con reparto personalizado; con "iguales" se calcula.
    monto_fijo: Dinero | None = None

    @property
    def mencion(self) -> str:
        """Como se le menciona en Discord."""
        return f"<@{self.discord_id}>"


@dataclass(frozen=True, slots=True)
class Cuota:
    """Lo que le toca a una persona este mes y cómo va."""

    participante: Participante
    monto: Dinero
    estado: Estado = Estado.PENDIENTE
    # Cuándo dijo que pagó y cuándo se lo confirmaron.
    dijo_que_pago: datetime | None = None
    confirmado: datetime | None = None

    @property
    def cuenta_para_el_total(self) -> bool:
        """Los exentos no suman al total que hay que juntar."""
        return self.estado is not Estado.EXENTO

    @property
    def ya_entro(self) -> bool:
        """¿Ese dinero ya se puede dar por recibido?"""
        return self.estado is Estado.PAGADO

    @property
    def falta(self) -> bool:
        return self.estado in (Estado.PENDIENTE, Estado.POR_CONFIRMAR)

    def marcar(self, estado: Estado, cuando: datetime) -> Cuota:
        """Devuelve una copia con el estado nuevo. No muta nada."""
        if estado is Estado.POR_CONFIRMAR:
            return replace(self, estado=estado, dijo_que_pago=cuando)
        if estado is Estado.PAGADO:
            return replace(
                self,
                estado=estado,
                confirmado=cuando,
                dijo_que_pago=self.dijo_que_pago or cuando,
            )
        return replace(self, estado=estado, dijo_que_pago=None, confirmado=None)


@dataclass(frozen=True, slots=True)
class MesDeCobro:
    """Un mes completo: quién debe cuánto y cómo va la cosa."""

    periodo: Periodo
    total: Dinero
    cuotas: tuple[Cuota, ...] = field(default_factory=tuple)

    # -- lectura ----------------------------------------------------------- #

    @property
    def activos(self) -> list[Cuota]:
        """Los que sí tienen que pagar este mes."""
        return [c for c in self.cuotas if c.cuenta_para_el_total]

    @property
    def pagados(self) -> list[Cuota]:
        return [c for c in self.cuotas if c.estado is Estado.PAGADO]

    @property
    def por_confirmar(self) -> list[Cuota]:
        return [c for c in self.cuotas if c.estado is Estado.POR_CONFIRMAR]

    @property
    def pendientes(self) -> list[Cuota]:
        return [c for c in self.cuotas if c.estado is Estado.PENDIENTE]

    @property
    def faltantes(self) -> list[Cuota]:
        """A quiénes hay que mencionar en los recordatorios.

        Incluye a los que dijeron que ya pagaron pero nadie les ha
        confirmado: si el tesorero no lo vio, el dinero no está.
        """
        return [c for c in self.cuotas if c.falta]

    @property
    def juntado(self) -> Dinero:
        """Lo que de verdad ya entró (solo lo confirmado)."""
        return sumar([c.monto for c in self.pagados])

    @property
    def por_juntar(self) -> Dinero:
        """Lo que falta para cubrir el VPS."""
        return sumar([c.monto for c in self.activos]) - self.juntado

    @property
    def esta_cubierto(self) -> bool:
        """¿Ya está pagado el VPS de este mes?"""
        return bool(self.activos) and all(c.ya_entro for c in self.activos)

    @property
    def avance(self) -> float:
        """De 0.0 a 1.0, para la barrita del embed."""
        objetivo = sumar([c.monto for c in self.activos])
        if not objetivo.es_positivo:
            return 1.0
        return min(1.0, self.juntado.centavos / objetivo.centavos)

    def cuota_de(self, discord_id: int) -> Cuota | None:
        return next((c for c in self.cuotas if c.participante.discord_id == discord_id), None)

    # -- cambios ----------------------------------------------------------- #

    def con_estado(self, discord_id: int, estado: Estado, cuando: datetime) -> MesDeCobro:
        """Devuelve un mes nuevo con esa persona en ese estado."""
        nuevas = tuple(
            c.marcar(estado, cuando) if c.participante.discord_id == discord_id else c
            for c in self.cuotas
        )
        return replace(self, cuotas=nuevas)


def abrir_mes(
    periodo: Periodo,
    total: Dinero,
    participantes: list[Participante],
    reparto: Reparto,
) -> MesDeCobro:
    """Arma un mes nuevo con todos en pendiente.

    Con reparto `iguales`, el total se divide sin perder centavos. Con
    `personalizado`, cada quien paga lo suyo y el total de settings.yml se
    usa nada más como referencia.

    Raises:
        ValueError: si no hay participantes, o si falta algún monto fijo.
    """
    if not participantes:
        msg = "no hay participantes: revisa la sección `pagos` de settings.yml"
        raise ValueError(msg)

    if reparto is Reparto.IGUALES:
        montos = repartir(total, len(participantes))
    else:
        sin_monto = [p.nombre for p in participantes if p.monto_fijo is None]
        if sin_monto:
            msg = (
                "con reparto personalizado cada quien necesita su monto_mxn. "
                f"Les falta a: {', '.join(sin_monto)}"
            )
            raise ValueError(msg)
        montos = [p.monto_fijo for p in participantes if p.monto_fijo is not None]

    cuotas = tuple(
        Cuota(participante=p, monto=m) for p, m in zip(participantes, montos, strict=True)
    )
    return MesDeCobro(periodo=periodo, total=total, cuotas=cuotas)
