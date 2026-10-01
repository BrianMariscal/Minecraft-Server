"""Los embeds que manda el bot. Limpios y legibles, sin adornos de más."""

from __future__ import annotations

import discord

from pagos_bot.discord_ui import textos
from pagos_bot.domain.calendario import Agenda
from pagos_bot.domain.cobro import Estado, MesDeCobro


def estado_del_mes(mes: MesDeCobro, agenda: Agenda) -> discord.Embed:
    """El embed de /pagos: quién va cómo y cuánto falta."""
    color = textos.COLOR_LISTO if mes.esta_cubierto else textos.COLOR_NORMAL
    limite = agenda.fecha_limite(mes.periodo)

    embed = discord.Embed(
        title=textos.titulo_del_mes(mes.periodo),
        description=textos.resumen_de_dinero(mes),
        colour=color,
    )

    # Agrupamos por estado para que se lea de un vistazo quién falta.
    for estado, titulo in (
        (Estado.PAGADO, "✅ Ya pagaron"),
        (Estado.POR_CONFIRMAR, "🕓 Por confirmar"),
        (Estado.PENDIENTE, "❌ Faltan"),
        (Estado.EXENTO, "➖ No les toca"),
    ):
        delgrupo = [c for c in mes.cuotas if c.estado is estado]
        if not delgrupo:
            continue
        embed.add_field(
            name=titulo,
            value="\n".join(textos.renglon_de_cuota(c) for c in delgrupo),
            inline=False,
        )

    barra = textos.barra_de_avance(mes.avance)
    embed.add_field(name="​", value=f"`{barra}` {mes.avance:.0%}", inline=False)
    embed.set_footer(text=f"Se paga el {agenda.fecha_bonita(limite)}")
    return embed


def historial(meses: list[MesDeCobro]) -> discord.Embed:
    """El embed de /historial."""
    embed = discord.Embed(title="Meses anteriores", colour=textos.COLOR_NORMAL)
    if not meses:
        embed.description = textos.sin_historial()
        return embed

    for mes in meses:
        pagaron = [c.participante.nombre for c in mes.pagados]
        faltaron = [c.participante.nombre for c in mes.faltantes]
        lineas = [textos.resumen_de_dinero(mes)]
        if pagaron:
            lineas.append("✅ " + ", ".join(pagaron))
        if faltaron:
            lineas.append("❌ " + ", ".join(faltaron))
        embed.add_field(name=mes.periodo.nombre.capitalize(), value="\n".join(lineas), inline=False)
    return embed


def aviso(texto: str, *, urgente: bool = False) -> discord.Embed:
    """Un recordatorio."""
    return discord.Embed(
        description=texto,
        colour=textos.COLOR_URGENTE if urgente else textos.COLOR_NORMAL,
    )


def ya_quedo(mes: MesDeCobro) -> discord.Embed:
    return discord.Embed(description=textos.ya_quedo(mes), colour=textos.COLOR_LISTO)


def problema(texto: str) -> discord.Embed:
    """Algo salió mal, dicho sin dramatismo."""
    return discord.Embed(description=texto, colour=textos.COLOR_URGENTE)
