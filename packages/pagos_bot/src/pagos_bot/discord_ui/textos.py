"""Los textos del bot, en español de México.

Todos juntos aquí para poder leerlos de corrido y ver si suenan a persona o
a robot. Regla: corto, directo, como se lo dirías a un amigo en el chat.
Nada de "Estimado usuario" ni "Por favor, proceda a".

Usan el markdown de Discord: `##` y `###` son encabezados, `-#` es el texto
chiquito gris de abajo, y `**` es negrita. El acomodo (tarjetas, separadores
y botones) está en `tarjetas.py`.
"""

from __future__ import annotations

from datetime import date

from pagos_bot.config import PagosConfig
from pagos_bot.domain.calendario import Agenda, Periodo
from pagos_bot.domain.cobro import Cuota, Estado, MesDeCobro
from pagos_bot.domain.dinero import Dinero

# La paleta del servidor: el azul del MOTD y colores tranquilos.
COLOR_NORMAL = 0x4FB0C6
COLOR_LISTO = 0x5BB97F
COLOR_URGENTE = 0xD98C5F
COLOR_PROBLEMA = 0xE06C6C
COLOR_AJUSTES = 0x7A8A8E

ANCHO_BARRA = 14


# --------------------------------------------------------------------------- #
#  Piezas
# --------------------------------------------------------------------------- #


def lista_con_y(cosas: list[str]) -> str:
    """'a', 'a y b', 'a, b y c'."""
    if not cosas:
        return ""
    if len(cosas) == 1:
        return cosas[0]
    return ", ".join(cosas[:-1]) + " y " + cosas[-1]


def menciones(cuotas: list[Cuota] | tuple[Cuota, ...]) -> str:
    return lista_con_y([c.participante.mencion for c in cuotas])


def objetivo(mes: MesDeCobro) -> Dinero:
    """Lo que hay que juntar: el precio del VPS que puso el tesorero."""
    return mes.meta


def barra_de_avance(avance: float, ancho: int = ANCHO_BARRA) -> str:
    """Una barrita con bloques, que se ve pareja en Discord."""
    llenos = round(max(0.0, min(1.0, avance)) * ancho)
    return "█" * llenos + "░" * (ancho - llenos)


def avance(mes: MesDeCobro) -> str:
    """'**$120.00** de $280.00' y la barrita debajo."""
    return (
        f"**{mes.juntado}** de {objetivo(mes)} juntados\n"
        f"`{barra_de_avance(mes.avance)}`  **{mes.avance:.0%}**"
    )


def cuando_vence(mes: MesDeCobro, agenda: Agenda, hoy: date) -> str:
    """La línea chiquita de debajo del título."""
    limite = agenda.fecha_limite(mes.periodo)
    fecha = agenda.fecha_bonita(limite)
    if mes.esta_cubierto:
        return f"Se pagaba el {fecha} · ✅ ya quedó cubierto"
    dias = (limite - hoy).days
    if dias > 1:
        return f"Se paga el **{fecha}** · faltan {dias} días"
    if dias == 1:
        return f"Se paga **mañana**, {fecha}"
    if dias == 0:
        return f"Se paga **hoy**, {fecha}"
    atraso = -dias
    return f"Se pagaba el {fecha} · ⚠️ van {atraso} día{'s' if atraso != 1 else ''} de atraso"


def renglon(cuota: Cuota) -> str:
    return f"{cuota.participante.nombre} · {cuota.monto}"


GRUPOS = (
    (Estado.PAGADO, "✅ Ya pagaron"),
    (Estado.POR_CONFIRMAR, "🕓 Por confirmar"),
    (Estado.PENDIENTE, "❌ Faltan"),
    (Estado.EXENTO, "➖ No les toca"),
)


def grupo(mes: MesDeCobro, estado: Estado, titulo: str) -> str | None:
    """Un bloque '### ✅ Ya pagaron' con su gente. None si está vacío."""
    gente = [c for c in mes.cuotas if c.estado is estado]
    if not gente:
        return None
    return f"### {titulo} ({len(gente)})\n" + "\n".join(renglon(c) for c in gente)


# Para que la tarjeta de /pagos no pase del límite de Discord (4000
# caracteres) ni con un año entero de deudas.
MAX_MESES_ATRASADOS = 6
MAX_NOMBRES_POR_MES = 5


def nombres_cortos(nombres: list[str], maximo: int = MAX_NOMBRES_POR_MES) -> str:
    """'A, B y C', o 'A, B, C, D, E y 3 más' si son muchos."""
    if len(nombres) <= maximo:
        return lista_con_y(nombres)
    return ", ".join(nombres[:maximo]) + f" y {len(nombres) - maximo} más"


def deudas_anteriores(meses: list[MesDeCobro]) -> str:
    """Una línea por mes atrasado, con quién falta. Los más recientes primero."""
    recientes = sorted(meses, key=lambda m: m.periodo, reverse=True)
    lineas = [
        f"**{m.periodo.nombre.capitalize()}**: "
        + nombres_cortos([c.participante.nombre for c in m.faltantes])
        for m in recientes[:MAX_MESES_ATRASADOS]
    ]
    if len(recientes) > MAX_MESES_ATRASADOS:
        resto = len(recientes) - MAX_MESES_ATRASADOS
        lineas.append(f"-# …y {resto} mes{'es' if resto != 1 else ''} más de antes")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- #
#  Lo que se ve
# --------------------------------------------------------------------------- #


def titulo_del_mes(periodo: Periodo) -> str:
    return f"## 💰 Pagos de {periodo.nombre}"


def aviso_previo(mes: MesDeCobro, agenda: Agenda, dias: int) -> str:
    """El de 'ya mero'. Aquí no se señala a nadie."""
    limite = agenda.fecha_bonita(agenda.fecha_limite(mes.periodo))
    cuando = "mañana" if dias == 1 else f"en {dias} días"
    montos = {c.monto.centavos for c in mes.activos}
    cuanto = (
        f"Tocan **{mes.activos[0].monto}** por cabeza."
        if len(montos) == 1 and mes.activos
        else "Cada quien ya sabe cuánto le toca: lo ves con `/pagos`."
    )
    return (
        "### 🔔 Ya casi toca pagar el VPS\n"
        f"El de **{mes.periodo.nombre}** se paga el **{limite}**, o sea {cuando}.\n"
        f"{cuanto}"
    )


def aviso_del_dia(mes: MesDeCobro, agenda: Agenda) -> str:
    """El del mero día. Aquí sí se menciona a quien falta."""
    limite = agenda.fecha_bonita(agenda.fecha_limite(mes.periodo))
    return (
        "### 📅 Hoy se paga el VPS\n"
        f"Hoy, **{limite}**, se paga el de {mes.periodo.nombre}.\n"
        f"Faltan: {menciones(mes.faltantes)}"
    )


def aviso_tardio(mes: MesDeCobro, agenda: Agenda, dias_de_atraso: int) -> str:
    """El 'ya se pasó la fecha'. Insiste, pero sin regañar."""
    limite = agenda.fecha_bonita(agenda.fecha_limite(mes.periodo))
    cuanto = "un día" if dias_de_atraso == 1 else f"{dias_de_atraso} días"
    return (
        "### ⏰ Ya pasó la fecha\n"
        f"Van {cuanto} desde el **{limite}** y todavía falta gente "
        f"con lo de {mes.periodo.nombre}.\n"
        f"Faltan: {menciones(mes.faltantes)}"
    )


def pie_del_boton() -> str:
    return "-# Si ya pagaste, pícale al botón y le aviso al tesorero."


def ya_quedo(mes: MesDeCobro) -> str:
    return (
        f"## 🎉 ¡Ya quedó el VPS de {mes.periodo.nombre}!\n"
        f"Se juntaron **{mes.juntado}**. Gracias, banda. 🫡"
    )


def dijo_que_pago(cuota: Cuota, mes: MesDeCobro, tesorero: str) -> str:
    return (
        f"### 👍 Anotado\n"
        f"Ya le avisé a **{tesorero}** que pagaste **{cuota.monto}** de {mes.periodo.nombre}.\n"
        "-# En cuanto lo confirme, cuenta para el total."
    )


def aviso_al_tesorero(cuota: Cuota, mes: MesDeCobro, tesorero_id: int) -> str:
    return (
        "### 💸 Pago por confirmar\n"
        f"{cuota.participante.mencion} dice que ya pagó **{cuota.monto}** "
        f"de {mes.periodo.nombre}.\n"
        f"<@{tesorero_id}>, cuando te llegue, confírmalo aquí abajo."
    )


def pago_confirmado(cuota: Cuota, mes: MesDeCobro, quien_confirmo: int) -> str:
    return (
        "### ✅ Pago confirmado\n"
        f"{cuota.participante.mencion} pagó **{cuota.monto}** de {mes.periodo.nombre}.\n"
        f"-# Lo confirmó <@{quien_confirmo}>"
    )


def desmarcado(cuota: Cuota, mes: MesDeCobro) -> str:
    return f"↩️ Regresé a **{cuota.participante.nombre}** a pendiente en {mes.periodo.nombre}."


def eximido(cuota: Cuota, mes: MesDeCobro) -> str:
    return f"➖ En {mes.periodo.nombre} ya no le toca pagar a **{cuota.participante.nombre}**."


def no_puedes() -> str:
    return "Eso solo lo puede hacer el tesorero (o quien tenga el rol de admin del cobro)."


def mes_mal_escrito(texto: str) -> str:
    return f"No entendí el mes `{texto}`. Se escribe como `2026-10`."


def boton_viejo() -> str:
    return (
        "Este botón es de antes de una actualización del bot y ya no sabe de quién "
        "era el pago. Confírmalo con `/confirmar`."
    )


def sin_historial() -> str:
    return "Todavía no hay meses anteriores que enseñar."


def resumen_historial(mes: MesDeCobro) -> str:
    estado = "✅ cubierto" if mes.esta_cubierto else "⚠️ quedó debiéndose"
    lineas = [f"### {mes.periodo.nombre.capitalize()} · {estado}"]
    lineas.append(f"**{mes.juntado}** de {objetivo(mes)}")
    faltaron = [c.participante.nombre for c in mes.faltantes]
    if faltaron:
        lineas.append(f"Falta: {nombres_cortos(faltaron)}")
    return "\n".join(lineas)


# --------------------------------------------------------------------------- #
#  Ajustes
# --------------------------------------------------------------------------- #


def ajustes(config: PagosConfig) -> str:
    rol = f"<@&{config.rol_admin_id}>" if config.rol_admin_id else "ninguno (solo el tesorero)"
    reparto = (
        "cada quien su monto"
        if config.reparto.value == "personalizado"
        else "el total dividido entre todos"
    )
    return (
        f"**📅 Día de pago:** el {config.dia_de_pago} de cada mes\n"
        f"**💵 Total del VPS:** {config.total}\n"
        f"**➗ Reparto:** {reparto}\n"
        f"**🔔 Avisos:** {config.avisos.dias_antes} días antes · cada "
        f"{config.avisos.cada_dias_despues} días si se pasa · a las "
        f"{config.hora_aviso:02d}:00\n"
        f"**👤 Tesorero:** {config.tesorero.nombre}\n"
        f"**🛡️ Rol que también administra:** {rol}"
    )


def miembros(config: PagosConfig) -> str:
    gente = config.participantes
    if not gente:
        return "### 👥 Miembros (0)\nNadie todavía. Agrega con `/miembro agregar`."
    personalizado = config.reparto.value == "personalizado"
    lineas = [f"### 👥 Miembros ({len(gente)})"]
    for p in sorted(gente, key=lambda x: x.nombre.lower()):
        monto = f" · {Dinero.de_pesos(p.monto_mxn)}" if personalizado and p.monto_mxn else ""
        lineas.append(f"{p.nombre}{monto}")
    return "\n".join(lineas)


def descuadre(config: PagosConfig) -> str | None:
    diferencia = config.descuadre
    if diferencia is None:
        return None
    cuanto = Dinero(abs(diferencia.centavos))
    if diferencia.es_positivo:
        return f"-# ⚠️ Las cuotas suman {cuanto} más que el total del VPS."
    return f"-# ⚠️ Las cuotas no alcanzan: faltan {cuanto} para el total del VPS."


def ayuda_de_ajustes() -> str:
    return (
        "-# `/miembro agregar` · `/miembro quitar` · `/miembro monto` · `/miembro nombre`\n"
        "-# `/ajustes dia` · `/ajustes total` · `/ajustes reparto` · `/ajustes avisos` · "
        "`/ajustes hora` · `/ajustes tesorero` · `/ajustes rol`"
    )
