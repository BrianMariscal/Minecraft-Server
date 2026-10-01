"""Los botones del bot.

Las vistas son persistentes (`timeout=None` y `custom_id` fijo): así siguen
funcionando aunque el bot se reinicie, que es justo lo que pasa cuando el
VPS se actualiza a media madrugada.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from pagos_bot.discord_ui import embeds, textos
from pagos_bot.services.cobros import ErrorDeCobro

if TYPE_CHECKING:
    from pagos_bot.services.cobros import ServicioDeCobros


class BotonYaPague(discord.ui.View):
    """El botón "Ya pagué" que va pegado a cada recordatorio."""

    def __init__(self, servicio: ServicioDeCobros) -> None:
        # Sin timeout: el mensaje puede quedarse días en el canal.
        super().__init__(timeout=None)
        self.servicio = servicio

    @discord.ui.button(
        label="Ya pagué",
        style=discord.ButtonStyle.success,
        emoji="💸",
        custom_id="pagos:ya_pague",
    )
    async def ya_pague(
        self, interaccion: discord.Interaction, boton: discord.ui.Button[BotonYaPague]
    ) -> None:
        del boton  # lo pide la firma de discord.py
        try:
            mes = self.servicio.dijo_que_pago(interaccion.user.id)
        except ErrorDeCobro as exc:
            await interaccion.response.send_message(embed=embeds.problema(str(exc)), ephemeral=True)
            return

        cuota = mes.cuota_de(interaccion.user.id)
        if cuota is None:  # pragma: no cover — dijo_que_pago ya lo validó
            return

        tesorero = f"<@{self.servicio.config.tesorero.discord_id}>"
        # La confirmación solo la ve quien picó el botón: no llenamos el canal.
        await interaccion.response.send_message(
            textos.dijo_que_pago(cuota, tesorero), ephemeral=True
        )
        # Y al tesorero sí se le avisa en el canal, con su botón para confirmar.
        if interaccion.channel is not None and isinstance(
            interaccion.channel, discord.abc.Messageable
        ):
            await interaccion.channel.send(
                content=tesorero,
                embed=embeds.aviso(textos.aviso_al_tesorero(cuota, mes)),
                view=BotonConfirmar(self.servicio, interaccion.user.id),
            )


class BotonConfirmar(discord.ui.View):
    """El botón con el que el tesorero confirma que sí llegó el dinero."""

    def __init__(self, servicio: ServicioDeCobros, de_quien: int) -> None:
        super().__init__(timeout=None)
        self.servicio = servicio
        self.de_quien = de_quien

    @discord.ui.button(
        label="Sí me llegó",
        style=discord.ButtonStyle.primary,
        emoji="✅",
        custom_id="pagos:confirmar",
    )
    async def confirmar(
        self, interaccion: discord.Interaction, boton: discord.ui.Button[BotonConfirmar]
    ) -> None:
        del boton
        roles = [r.id for r in getattr(interaccion.user, "roles", [])]
        if not self.servicio.config.puede_administrar(interaccion.user.id, roles):
            await interaccion.response.send_message(
                embed=embeds.problema(textos.no_puedes()), ephemeral=True
            )
            return

        try:
            mes = self.servicio.confirmar(self.de_quien)
        except ErrorDeCobro as exc:
            await interaccion.response.send_message(embed=embeds.problema(str(exc)), ephemeral=True)
            return

        cuota = mes.cuota_de(self.de_quien)
        if cuota is None:  # pragma: no cover
            return

        # El botón ya se usó: lo apagamos para que no lo piquen dos veces.
        for hijo in self.children:
            if isinstance(hijo, discord.ui.Button):
                hijo.disabled = True
        await interaccion.response.edit_message(view=self)

        if interaccion.channel is not None and isinstance(
            interaccion.channel, discord.abc.Messageable
        ):
            await interaccion.channel.send(textos.confirmado(cuota))
            if mes.esta_cubierto:
                await interaccion.channel.send(embed=embeds.ya_quedo(mes))
