"""Los comandos slash del bot.

Se registran como funciones sueltas en el CommandTree, no como un Cog. Es a
propósito: el bot SOLO usa comandos slash y botones, así que no necesita la
maquinaria de comandos de prefijo de `commands.Bot` (que además hace que
discord.py avise de que falta el intent privilegiado de contenido de
mensajes, un permiso que no tenemos por qué pedirle a Discord).

Cada comando cierra sobre `servicio`: así no hay estado global.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from pagos_bot.discord_ui import botones, embeds, textos
from pagos_bot.services.cobros import ErrorDeCobro, ServicioDeCobros

log = logging.getLogger("pagos.comandos")


async def _responder_problema(interaccion: discord.Interaction, texto: str) -> None:
    """Un error se le dice SOLO a quien lo provocó, no a todo el canal."""
    await interaccion.response.send_message(embed=embeds.problema(texto), ephemeral=True)


def registrar(tree: app_commands.CommandTree, servicio: ServicioDeCobros) -> None:
    """Cuelga todos los comandos del árbol del bot."""

    def puede_administrar(interaccion: discord.Interaction) -> bool:
        roles = [r.id for r in getattr(interaccion.user, "roles", [])]
        return servicio.config.puede_administrar(interaccion.user.id, roles)

    async def avisarle_al_tesorero(
        interaccion: discord.Interaction, discord_id: int, mes: object
    ) -> None:
        """Manda al canal el aviso con el botón para confirmar."""
        from pagos_bot.domain.cobro import MesDeCobro

        if not isinstance(mes, MesDeCobro):  # pragma: no cover
            return
        cuota = mes.cuota_de(discord_id)
        if cuota is None:  # pragma: no cover
            return
        canal = interaccion.channel
        if isinstance(canal, discord.abc.Messageable):
            await canal.send(
                content=f"<@{servicio.config.tesorero.discord_id}>",
                embed=embeds.aviso(textos.aviso_al_tesorero(cuota, mes)),
                view=botones.BotonConfirmar(servicio, discord_id),
            )

    # -- para todos --------------------------------------------------------- #

    @tree.command(name="pagos", description="Cómo va el pago del VPS este mes.")
    async def pagos(interaccion: discord.Interaction) -> None:
        try:
            mes = servicio.mes_actual()
        except ErrorDeCobro as exc:
            await _responder_problema(interaccion, str(exc))
            return
        await interaccion.response.send_message(
            embed=embeds.estado_del_mes(mes, servicio.agenda),
            view=botones.BotonYaPague(servicio),
        )

    @tree.command(name="pague", description="Avisa que ya pagaste tu parte.")
    async def pague(interaccion: discord.Interaction) -> None:
        try:
            mes = servicio.dijo_que_pago(interaccion.user.id)
        except ErrorDeCobro as exc:
            await _responder_problema(interaccion, str(exc))
            return
        cuota = mes.cuota_de(interaccion.user.id)
        if cuota is None:  # pragma: no cover
            return
        tesorero = f"<@{servicio.config.tesorero.discord_id}>"
        await interaccion.response.send_message(
            textos.dijo_que_pago(cuota, tesorero), ephemeral=True
        )
        await avisarle_al_tesorero(interaccion, interaccion.user.id, mes)

    @tree.command(name="historial", description="Los meses anteriores.")
    async def historial(interaccion: discord.Interaction) -> None:
        await interaccion.response.send_message(embed=embeds.historial(servicio.historial()))

    # -- solo el tesorero (o el rol de admin) -------------------------------- #

    @tree.command(name="confirmar", description="Confirma que alguien ya pagó.")
    @app_commands.describe(quien="A quién le llegó el pago.")
    async def confirmar(interaccion: discord.Interaction, quien: discord.User) -> None:
        if not puede_administrar(interaccion):
            await _responder_problema(interaccion, textos.no_puedes())
            return
        try:
            mes = servicio.confirmar(quien.id)
        except ErrorDeCobro as exc:
            await _responder_problema(interaccion, str(exc))
            return
        cuota = mes.cuota_de(quien.id)
        if cuota is None:  # pragma: no cover
            return
        await interaccion.response.send_message(textos.confirmado(cuota))
        if mes.esta_cubierto:
            canal = interaccion.channel
            if isinstance(canal, discord.abc.Messageable):
                await canal.send(embed=embeds.ya_quedo(mes))

    @tree.command(name="desmarcar", description="Regresa a alguien a pendiente.")
    @app_commands.describe(quien="A quién.")
    async def desmarcar(interaccion: discord.Interaction, quien: discord.User) -> None:
        if not puede_administrar(interaccion):
            await _responder_problema(interaccion, textos.no_puedes())
            return
        try:
            mes = servicio.desmarcar(quien.id)
        except ErrorDeCobro as exc:
            await _responder_problema(interaccion, str(exc))
            return
        cuota = mes.cuota_de(quien.id)
        if cuota is not None:
            await interaccion.response.send_message(textos.desmarcado(cuota))

    @tree.command(name="eximir", description="Quita a alguien del cobro de este mes.")
    @app_commands.describe(quien="A quién no le toca pagar este mes.")
    async def eximir(interaccion: discord.Interaction, quien: discord.User) -> None:
        if not puede_administrar(interaccion):
            await _responder_problema(interaccion, textos.no_puedes())
            return
        try:
            mes = servicio.eximir(quien.id)
        except ErrorDeCobro as exc:
            await _responder_problema(interaccion, str(exc))
            return
        cuota = mes.cuota_de(quien.id)
        if cuota is not None:
            await interaccion.response.send_message(textos.eximido(cuota))
        if mes.esta_cubierto:
            canal = interaccion.channel
            if isinstance(canal, discord.abc.Messageable):
                await canal.send(embed=embeds.ya_quedo(mes))

    log.info("registré %d comandos slash", len(tree.get_commands()))
