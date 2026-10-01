"""Los textos del bot, en español de México.

Todos juntos aquí para poder leerlos de corrido y ver si suenan a persona o
a robot. Regla: corto, directo, como se lo dirías a un amigo en el chat.
Nada de "Estimado usuario" ni "Por favor, proceda a".
"""

from __future__ import annotations

from pagos_bot.domain.calendario import Agenda, Periodo
from pagos_bot.domain.cobro import Cuota, MesDeCobro
from pagos_bot.domain.dinero import Dinero

# Un azul tranquilo, a juego con el MOTD del servidor.
COLOR_NORMAL = 0x4FB0C6
COLOR_LISTO = 0x5BB97F
COLOR_URGENTE = 0xD98C5F


def _lista_de_menciones(cuotas: tuple[Cuota, ...] | list[Cuota]) -> str:
    """Las menciones separadas por comas, con 'y' al final."""
    menciones = [c.participante.mencion for c in cuotas]
    if not menciones:
        return ""
    if len(menciones) == 1:
        return menciones[0]
    return ", ".join(menciones[:-1]) + " y " + menciones[-1]


def aviso_previo(mes: MesDeCobro, agenda: Agenda, dias: int) -> str:
    """El aviso de 'ya mero'. Aquí no se señala a nadie."""
    limite = agenda.fecha_limite(mes.periodo)
    cuanto = mes.activos[0].monto if mes.activos else Dinero.cero()
    todos_igual = len({c.monto.centavos for c in mes.activos}) <= 1
    reparto = f"Tocan {cuanto} por cabeza." if todos_igual else "Cada quien ya sabe cuánto le toca."
    cuando = "mañana" if dias == 1 else f"en {dias} días"
    return (
        f"El VPS se paga el **{agenda.fecha_bonita(limite)}**, o sea {cuando}. "
        f"{reparto}\n"
        f"Si ya lo pagaste, pícale al botón y yo le aviso al tesorero."
    )


def aviso_del_dia(mes: MesDeCobro, agenda: Agenda) -> str:
    """El recordatorio del mero día. Aquí sí se menciona a quien falta."""
    limite = agenda.fecha_limite(mes.periodo)
    return (
        f"Hoy **{agenda.fecha_bonita(limite)}** se paga el VPS.\n"
        f"Faltan: {_lista_de_menciones(mes.faltantes)}\n"
        f"Van {mes.juntado} de {_objetivo(mes)}."
    )


def aviso_tardio(mes: MesDeCobro, agenda: Agenda, dias_de_atraso: int) -> str:
    """El 'ya se pasó la fecha'. Insiste, pero sin regañar."""
    limite = agenda.fecha_limite(mes.periodo)
    cuanto = "un día" if dias_de_atraso == 1 else f"{dias_de_atraso} días"
    return (
        f"Ya pasó {cuanto} del **{agenda.fecha_bonita(limite)}** y todavía falta gente.\n"
        f"{_lista_de_menciones(mes.faltantes)}\n"
        f"Van {mes.juntado} de {_objetivo(mes)}."
    )


def ya_quedo(mes: MesDeCobro) -> str:
    """Cuando todos pagaron."""
    return f"Listo, ya está cubierto el VPS de {mes.periodo.nombre}. Gracias, banda. 🫡"


def dijo_que_pago(cuota: Cuota, tesorero_mencion: str) -> str:
    return (
        f"Va, anoté que ya pagaste tus {cuota.monto}. "
        f"Le avisé a {tesorero_mencion} para que lo confirme."
    )


def aviso_al_tesorero(cuota: Cuota, mes: MesDeCobro) -> str:
    return (
        f"{cuota.participante.mencion} dice que ya pagó sus {cuota.monto} "
        f"de {mes.periodo.nombre}.\n"
        f"Cuando te llegue, confírmalo aquí abajo o con `/confirmar`."
    )


def confirmado(cuota: Cuota) -> str:
    return f"Confirmado: {cuota.participante.mencion} ya pagó sus {cuota.monto}."


def desmarcado(cuota: Cuota) -> str:
    return f"Listo, regresé a {cuota.participante.mencion} a pendiente."


def eximido(cuota: Cuota) -> str:
    return f"Va, este mes no le toca pagar a {cuota.participante.mencion}."


def no_puedes() -> str:
    return "Eso solo lo puede hacer el tesorero."


def _objetivo(mes: MesDeCobro) -> Dinero:
    from pagos_bot.domain.dinero import sumar

    return sumar([c.monto for c in mes.activos])


def barra_de_avance(avance: float, ancho: int = 12) -> str:
    """Una barrita de progreso con bloques, que se ve bien en Discord."""
    llenos = round(avance * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


def titulo_del_mes(periodo: Periodo) -> str:
    return f"Pagos de {periodo.nombre}"


def resumen_de_dinero(mes: MesDeCobro) -> str:
    objetivo = _objetivo(mes)
    if mes.esta_cubierto:
        return f"**{mes.juntado}** de {objetivo} — ya quedó"
    return f"**{mes.juntado}** de {objetivo} · faltan {mes.por_juntar}"


def renglon_de_cuota(cuota: Cuota) -> str:
    return f"{cuota.estado.emoji} **{cuota.participante.nombre}** — {cuota.monto}"


def sin_historial() -> str:
    return "Todavía no hay meses anteriores que enseñar."


def config_sin_llenar() -> str:
    return (
        "La sección `pagos` de `settings.yml` todavía trae **CAMBIAME**.\n"
        "Hay que poner a la banda y al tesorero antes de que yo pueda cobrar.\n"
        "Guía: `docs/bot-pagos.md`"
    )
