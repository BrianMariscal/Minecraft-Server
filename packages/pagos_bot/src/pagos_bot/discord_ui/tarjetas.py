"""Cómo se ven los mensajes del bot: tarjetas con el diseño nuevo de Discord.

Cada mensaje es una tarjeta (un `Container` con una franja de color a la
izquierda) armada por secciones: un título, el dato principal, separadores
con aire entre bloques, y los botones abajo, dentro de la misma tarjeta.

Aquí solo se ACOMODA. Lo que dice cada mensaje está en `textos.py`, y los
botones se reciben ya hechos, para que este módulo no dependa de ellos.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import discord
from discord import ui

from pagos_bot.config import PagosConfig
from pagos_bot.discord_ui import textos
from pagos_bot.domain.calendario import Agenda
from pagos_bot.domain.cobro import Cuota, MesDeCobro

# Cualquier pieza de una tarjeta: texto, separador, botón...
Hijo = ui.Item[Any]

# Ningún mensaje del bot avisa a nadie salvo que se diga explícito: el
# estado del mes nombra a toda la banda y no tiene por qué sonarles.
SIN_MENCIONES = discord.AllowedMentions.none()
SOLO_PERSONAS = discord.AllowedMentions(users=True, roles=False, everyone=False)


def _texto(contenido: str) -> ui.TextDisplay[Any]:
    return ui.TextDisplay(contenido)


def _separador(*, grande: bool = False, linea: bool = True) -> ui.Separator[Any]:
    espacio = discord.SeparatorSpacing.large if grande else discord.SeparatorSpacing.small
    return ui.Separator(visible=linea, spacing=espacio)


def _tarjeta(color: int, *hijos: Hijo, botones: list[Hijo] | None = None) -> ui.LayoutView:
    """Una tarjeta con su franja de color y, si hay, una fila de botones abajo."""
    contenido: list[Hijo] = list(hijos)
    if botones:
        contenido += [_separador(linea=False), ui.ActionRow(*botones)]
    vista = ui.LayoutView(timeout=None)
    vista.add_item(ui.Container(*contenido, accent_colour=color))
    return vista


# --------------------------------------------------------------------------- #
#  El mes
# --------------------------------------------------------------------------- #


def estado_del_mes(
    mes: MesDeCobro,
    agenda: Agenda,
    hoy: date,
    *,
    tesorero: str,
    atrasados: list[MesDeCobro],
    botones: list[Hijo],
) -> ui.LayoutView:
    """`/pagos`: cómo va el mes, de un vistazo."""
    color = textos.COLOR_LISTO if mes.esta_cubierto else textos.COLOR_NORMAL
    hijos: list[Hijo] = [
        _texto(f"{textos.titulo_del_mes(mes.periodo)}\n-# {textos.cuando_vence(mes, agenda, hoy)}"),
        _separador(),
        _texto(textos.avance(mes)),
        _separador(grande=True),
    ]
    bloques = [b for e, t in textos.GRUPOS if (b := textos.grupo(mes, e, t)) is not None]
    for i, bloque in enumerate(bloques):
        if i:
            hijos.append(_separador(linea=False))
        hijos.append(_texto(bloque))

    if atrasados:
        hijos += [
            _separador(grande=True),
            _texto("### ⏳ De meses anteriores\n" + textos.deudas_anteriores(atrasados)),
        ]

    hijos += [_separador(), _texto(f"-# Tesorero: {tesorero} · Avisa que pagaste con el botón")]
    return _tarjeta(color, *hijos, botones=botones)


def aviso(texto: str, mes: MesDeCobro, *, urgente: bool, botones: list[Hijo]) -> ui.LayoutView:
    """Los recordatorios: el previo, el del día y los tardíos."""
    color = textos.COLOR_URGENTE if urgente else textos.COLOR_NORMAL
    return _tarjeta(
        color,
        _texto(texto),
        _separador(),
        _texto(textos.avance(mes)),
        _separador(),
        _texto(textos.pie_del_boton()),
        botones=botones,
    )


def ya_quedo(mes: MesDeCobro) -> ui.LayoutView:
    return _tarjeta(textos.COLOR_LISTO, _texto(textos.ya_quedo(mes)))


def historial(meses: list[MesDeCobro]) -> ui.LayoutView:
    hijos: list[Hijo] = [_texto("## 📜 Meses anteriores")]
    if not meses:
        hijos += [_separador(), _texto(textos.sin_historial())]
    for mes in meses:
        hijos += [_separador(), _texto(textos.resumen_historial(mes))]
    return _tarjeta(textos.COLOR_NORMAL, *hijos)


# --------------------------------------------------------------------------- #
#  Pagos
# --------------------------------------------------------------------------- #


def dijo_que_pago(cuota: Cuota, mes: MesDeCobro, tesorero: str) -> ui.LayoutView:
    return _tarjeta(textos.COLOR_LISTO, _texto(textos.dijo_que_pago(cuota, mes, tesorero)))


def aviso_al_tesorero(
    cuota: Cuota, mes: MesDeCobro, tesorero_id: int, *, botones: list[Hijo]
) -> ui.LayoutView:
    return _tarjeta(
        textos.COLOR_URGENTE,
        _texto(textos.aviso_al_tesorero(cuota, mes, tesorero_id)),
        botones=botones,
    )


def pago_confirmado(cuota: Cuota, mes: MesDeCobro, quien_confirmo: int) -> ui.LayoutView:
    return _tarjeta(textos.COLOR_LISTO, _texto(textos.pago_confirmado(cuota, mes, quien_confirmo)))


# --------------------------------------------------------------------------- #
#  Respuestas cortas
# --------------------------------------------------------------------------- #


def listo(texto: str) -> ui.LayoutView:
    """Un cambio que salió bien."""
    return _tarjeta(textos.COLOR_LISTO, _texto(texto))


def problema(texto: str) -> ui.LayoutView:
    """Algo que no se pudo, dicho sin dramatismo."""
    return _tarjeta(
        textos.COLOR_PROBLEMA, _texto(f"**No se pudo.** {texto[:1].upper()}{texto[1:]}")
    )


# --------------------------------------------------------------------------- #
#  Ajustes
# --------------------------------------------------------------------------- #


def ajustes(config: PagosConfig) -> ui.LayoutView:
    """`/ajustes ver`: toda la configuración del cobro en una tarjeta."""
    hijos: list[Hijo] = [
        _texto("## ⚙️ Ajustes del cobro\n-# Los cambian el tesorero y el rol de admin"),
        _separador(),
        _texto(textos.ajustes(config)),
        _separador(grande=True),
        _texto(textos.miembros(config)),
    ]
    hijos += [_separador(), _texto(textos.ayuda_de_ajustes())]
    return _tarjeta(textos.COLOR_AJUSTES, *hijos)
