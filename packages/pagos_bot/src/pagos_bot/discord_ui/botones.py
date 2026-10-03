"""Los botones del bot.

Todos son `DynamicItem`: discord.py los reconoce por su `custom_id` y los
reconstruye aunque el bot se haya reiniciado, que es justo lo que pasa en
cada `mc restart`. Así un botón de un aviso de hace una semana sigue jalando.

- "Ya pagué" es igual en todos los mensajes: `pagos:ya_pague`.
- "Sí me llegó" tiene que saber DE QUIÉN y DE QUÉ MES es el pago, y eso va
  escrito en su `custom_id`: `pagos:confirmar:<discord_id>:<2026-10>`.
"""

from __future__ import annotations

import re
from typing import Any, Self

import discord

from pagos_bot.discord_ui import tarjetas, textos
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import Cuota, MesDeCobro
from pagos_bot.services.cobros import ErrorDeCobro, ServicioDeCobros

ID_YA_PAGUE = "pagos:ya_pague"
PLANTILLA_CONFIRMAR = r"pagos:confirmar:(?P<quien>[0-9]+):(?P<periodo>[0-9]{4}-[0-9]{2})"

Boton = discord.ui.DynamicItem[discord.ui.Button[Any]]


def id_confirmar(de_quien: int, periodo: Periodo) -> str:
    """El custom_id del botón "Sí me llegó" de ese pago."""
    return f"pagos:confirmar:{de_quien}:{periodo.clave}"


def servicio_de(interaccion: discord.Interaction) -> ServicioDeCobros:
    """El servicio vive en el bot; un botón solo recibe la interacción."""
    servicio = getattr(interaccion.client, "servicio", None)
    if not isinstance(servicio, ServicioDeCobros):  # pragma: no cover — bug nuestro
        msg = "el cliente de Discord no trae el servicio de cobros"
        raise TypeError(msg)
    return servicio


async def avisar_al_tesorero(
    canal: discord.abc.Messageable,
    servicio: ServicioDeCobros,
    cuota: Cuota,
    mes: MesDeCobro,
) -> None:
    """Manda al canal la tarjeta para el tesorero, con su botón para confirmar."""
    await canal.send(
        view=tarjetas.aviso_al_tesorero(
            cuota,
            mes,
            servicio.config.tesorero.discord_id,
            botones=[BotonConfirmar(cuota.participante.discord_id, mes.periodo)],
        ),
        allowed_mentions=tarjetas.SOLO_PERSONAS,
    )


async def ya_pague(interaccion: discord.Interaction) -> None:
    """Lo que pasa al picar "Ya pagué" o al escribir /pague."""
    servicio = servicio_de(interaccion)
    try:
        mes = servicio.dijo_que_pago(interaccion.user.id)
    except ErrorDeCobro as exc:
        await interaccion.response.send_message(view=tarjetas.problema(str(exc)), ephemeral=True)
        return

    cuota = mes.cuota_de(interaccion.user.id)
    if cuota is None:  # pragma: no cover — dijo_que_pago ya lo validó
        return

    # La confirmación solo la ve quien picó el botón: no llenamos el canal.
    await interaccion.response.send_message(
        view=tarjetas.dijo_que_pago(cuota, mes, servicio.config.tesorero.nombre), ephemeral=True
    )
    if isinstance(interaccion.channel, discord.abc.Messageable):
        await avisar_al_tesorero(interaccion.channel, servicio, cuota, mes)


class BotonYaPague(Boton, template=ID_YA_PAGUE):
    """El botón "Ya pagué" que va en cada recordatorio y en /pagos."""

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Ya pagué",
                style=discord.ButtonStyle.success,
                emoji="💸",
                custom_id=ID_YA_PAGUE,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> Self:
        del interaction, item, match
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await ya_pague(interaction)


class BotonConfirmar(Boton, template=PLANTILLA_CONFIRMAR):
    """El botón con el que el tesorero confirma que sí llegó el dinero."""

    def __init__(self, de_quien: int, periodo: Periodo) -> None:
        super().__init__(
            discord.ui.Button(
                label="Sí me llegó",
                style=discord.ButtonStyle.primary,
                emoji="✅",
                custom_id=id_confirmar(de_quien, periodo),
            )
        )
        self.de_quien = de_quien
        self.periodo = periodo

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> Self:
        del interaction, item
        return cls(int(match["quien"]), Periodo.de_clave(match["periodo"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        servicio = servicio_de(interaction)
        roles = [r.id for r in getattr(interaction.user, "roles", [])]
        if not servicio.config.puede_administrar(interaction.user.id, roles):
            await interaction.response.send_message(
                view=tarjetas.problema(textos.no_puedes()), ephemeral=True
            )
            return

        try:
            mes = servicio.confirmar(self.de_quien, self.periodo)
        except ErrorDeCobro as exc:
            await interaction.response.send_message(
                view=tarjetas.problema(str(exc)), ephemeral=True
            )
            return

        cuota = mes.cuota_de(self.de_quien)
        if cuota is None:  # pragma: no cover — confirmar ya lo validó
            return

        # La tarjeta se transforma en "Pago confirmado": sin botón que volver a picar.
        await interaction.response.edit_message(
            view=tarjetas.pago_confirmado(cuota, mes, interaction.user.id),
            allowed_mentions=tarjetas.SIN_MENCIONES,
        )
        if mes.esta_cubierto and isinstance(interaction.channel, discord.abc.Messageable):
            await interaction.channel.send(view=tarjetas.ya_quedo(mes))


class BotonConfirmarViejo(Boton, template=r"pagos:confirmar"):
    """Los "Sí me llegó" de antes de la versión 1.1, que no saben de quién son."""

    def __init__(self) -> None:
        super().__init__(discord.ui.Button(label="Sí me llegó", custom_id="pagos:confirmar"))

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> Self:
        del interaction, item, match
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            view=tarjetas.problema(textos.boton_viejo()), ephemeral=True
        )


# Lo que hay que registrar en el cliente al arrancar.
BOTONES_DINAMICOS = (BotonYaPague, BotonConfirmar, BotonConfirmarViejo)
