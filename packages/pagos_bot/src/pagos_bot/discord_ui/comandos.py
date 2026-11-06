"""Los comandos slash del bot.

Dos clases de comandos:

- Para todos: `/pagos`, `/pague`, `/historial`.
- Para el tesorero (o el rol de admin del cobro): confirmar pagos y cambiar
  TODA la configuración del cobro, sin tocar archivos: `/miembro ...` y
  `/ajustes ...`. Discord los esconde a quien no tiene "Gestionar
  servidor" (se puede cambiar en Ajustes del servidor > Integraciones), y
  además el bot revisa que quien los usa sea el tesorero o tenga el rol.

Se registran como funciones sueltas en el CommandTree, no como un Cog: el
bot SOLO usa comandos slash y botones, así que no necesita la maquinaria de
comandos de prefijo de `commands.Bot`.
"""

from __future__ import annotations

import logging
from typing import Literal

import discord
from discord import app_commands

from pagos_bot.discord_ui import botones, tarjetas, textos
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import MesDeCobro, Reparto
from pagos_bot.services.ajustes import ServicioDeAjustes
from pagos_bot.services.cobros import ErrorDeCobro, ServicioDeCobros

log = logging.getLogger("pagos.comandos")

# Quién ve los comandos de administración en la lista de Discord.
SOLO_ADMINS = discord.Permissions(manage_guild=True)


async def _problema(interaccion: discord.Interaction, texto: str) -> None:
    """Un error se le dice SOLO a quien lo provocó, no a todo el canal."""
    await interaccion.response.send_message(view=tarjetas.problema(texto), ephemeral=True)


async def _listo(interaccion: discord.Interaction, texto: str) -> None:
    """Un cambio de ajustes: se anuncia en el canal, para que todos se enteren."""
    await interaccion.response.send_message(
        view=tarjetas.listo(texto), allowed_mentions=tarjetas.SIN_MENCIONES
    )


def _leer_mes(texto: str | None) -> Periodo | None:
    """'2026-10' -> Periodo. None si no se escribió nada."""
    if not texto:
        return None
    try:
        return Periodo.de_clave(texto.strip())
    except ValueError as exc:
        raise ErrorDeCobro(textos.mes_mal_escrito(texto)) from exc


async def _anunciar_si_quedo(interaccion: discord.Interaction, mes: MesDeCobro) -> None:
    if mes.esta_cubierto and isinstance(interaccion.channel, discord.abc.Messageable):
        await interaccion.channel.send(view=tarjetas.ya_quedo(mes))


def registrar(tree: app_commands.CommandTree, servicio: ServicioDeCobros) -> None:
    """Cuelga todos los comandos del árbol del bot."""
    ajustes = ServicioDeAjustes(servicio)

    async def es_admin(interaccion: discord.Interaction) -> bool:
        """True si puede; si no, se lo dice y devuelve False."""
        roles = [r.id for r in getattr(interaccion.user, "roles", [])]
        if servicio.config.puede_administrar(interaccion.user.id, roles):
            return True
        await _problema(interaccion, textos.no_puedes())
        return False

    # ===================================================================== #
    #  Para todos
    # ===================================================================== #

    @tree.command(name="pagos", description="Cómo va el pago del VPS este mes.")
    async def pagos(interaccion: discord.Interaction) -> None:
        try:
            mes = servicio.mes_actual()
            atrasados = servicio.deudas_anteriores()
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await interaccion.response.send_message(
            view=tarjetas.estado_del_mes(
                mes,
                servicio.agenda,
                servicio.agenda.hoy(servicio.ahora()),
                tesorero=servicio.config.tesorero.nombre,
                atrasados=atrasados,
                botones=[botones.BotonYaPague()],
            ),
            allowed_mentions=tarjetas.SIN_MENCIONES,
        )

    @tree.command(name="pague", description="Avisa que ya pagaste tu parte.")
    async def pague(interaccion: discord.Interaction) -> None:
        await botones.ya_pague(interaccion)

    @tree.command(name="historial", description="Los meses anteriores y quién pagó.")
    async def historial(interaccion: discord.Interaction) -> None:
        await interaccion.response.send_message(
            view=tarjetas.historial(servicio.historial()), allowed_mentions=tarjetas.SIN_MENCIONES
        )

    # ===================================================================== #
    #  Pagos: solo el tesorero o el rol de admin
    # ===================================================================== #

    @tree.command(name="confirmar", description="Confirma que te llegó el pago de alguien.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        quien="A quién le llegó el pago.",
        mes="De qué mes, como 2026-10. Si no lo pones, lo más viejo que deba.",
    )
    async def confirmar(
        interaccion: discord.Interaction, quien: discord.User, mes: str | None = None
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            cobro = servicio.confirmar(quien.id, _leer_mes(mes))
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        cuota = cobro.cuota_de(quien.id)
        if cuota is None:  # pragma: no cover
            return
        await interaccion.response.send_message(
            view=tarjetas.pago_confirmado(cuota, cobro, interaccion.user.id),
            allowed_mentions=tarjetas.SIN_MENCIONES,
        )
        await _anunciar_si_quedo(interaccion, cobro)

    @tree.command(name="desmarcar", description="Regresa a alguien a pendiente.")
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(quien="A quién.", mes="De qué mes, como 2026-10. Si no, el actual.")
    async def desmarcar(
        interaccion: discord.Interaction, quien: discord.User, mes: str | None = None
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            cobro = servicio.desmarcar(quien.id, _leer_mes(mes))
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        cuota = cobro.cuota_de(quien.id)
        if cuota is not None:
            await _listo(interaccion, textos.desmarcado(cuota, cobro))

    @tree.command(
        name="eximir", description="Que alguien no pague un mes, sin que cuente que debe."
    )
    @app_commands.default_permissions(manage_guild=True)
    @app_commands.describe(
        quien="A quién no le toca pagar.",
        mes="De qué mes, como 2026-10. Si no, el actual.",
    )
    async def eximir(
        interaccion: discord.Interaction, quien: discord.User, mes: str | None = None
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            cobro = servicio.eximir(quien.id, _leer_mes(mes))
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        cuota = cobro.cuota_de(quien.id)
        if cuota is not None:
            await _listo(interaccion, textos.eximido(cuota, cobro))
        await _anunciar_si_quedo(interaccion, cobro)

    # ===================================================================== #
    #  /miembro: quién está en la banda
    # ===================================================================== #

    miembro = app_commands.Group(
        name="miembro",
        description="Quién coopera para el VPS.",
        default_permissions=SOLO_ADMINS,
        guild_only=True,
    )

    @miembro.command(name="agregar", description="Mete a alguien a la banda que paga el VPS.")
    @app_commands.describe(
        quien="La persona en Discord.",
        monto="Cuánto paga al mes, como 40 o 40.50. Con reparto iguales se ignora.",
        nombre="Cómo aparece en las listas. Si no, su nombre de Discord.",
    )
    async def miembro_agregar(
        interaccion: discord.Interaction,
        quien: discord.Member,
        monto: str | None = None,
        nombre: str | None = None,
    ) -> None:
        if not await es_admin(interaccion):
            return
        etiqueta = (nombre or quien.display_name).strip()
        try:
            cuota = ajustes.agregar_miembro(quien.id, etiqueta, monto)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(
            interaccion,
            f"### 👋 Bienvenido a la banda, {etiqueta}\n"
            f"Le tocan **{cuota}** al mes y ya entra en el cobro de este mes.",
        )

    @miembro.command(name="quitar", description="Saca a alguien de la banda que paga el VPS.")
    @app_commands.describe(quien="La persona en Discord.")
    async def miembro_quitar(interaccion: discord.Interaction, quien: discord.User) -> None:
        if not await es_admin(interaccion):
            return
        try:
            nombre = next(
                (p.nombre for p in servicio.config.participantes if p.discord_id == quien.id),
                quien.display_name,
            )
            que_paso = ajustes.quitar_miembro(quien.id)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(
            interaccion, f"### 👋 {nombre} ya no está en la banda\n{que_paso.capitalize()}."
        )

    @miembro.command(name="monto", description="Cambia cuánto paga alguien al mes.")
    @app_commands.describe(
        quien="La persona en Discord.",
        monto="Lo nuevo, como 40 o 40.50.",
        este_mes="¿También el mes en curso? Si no, desde el que viene.",
    )
    async def miembro_monto(
        interaccion: discord.Interaction,
        quien: discord.User,
        monto: str,
        este_mes: bool = False,
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            nuevo = ajustes.cambiar_monto(quien.id, monto, este_mes=este_mes)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        desde = "desde este mes" if este_mes else "desde el mes que viene"
        await _listo(interaccion, f"💵 Ahora **{quien.display_name}** paga **{nuevo}** {desde}.")

    @miembro.command(name="nombre", description="Cambia cómo aparece alguien en las listas.")
    @app_commands.describe(quien="La persona en Discord.", nombre="El nombre nuevo.")
    async def miembro_nombre(
        interaccion: discord.Interaction, quien: discord.User, nombre: str
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.renombrar(quien.id, nombre)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(interaccion, f"✏️ Listo, ahora aparece como **{nombre.strip()[:32]}**.")

    tree.add_command(miembro)

    # ===================================================================== #
    #  /ajustes: cómo se cobra
    # ===================================================================== #

    grupo_ajustes = app_commands.Group(
        name="ajustes",
        description="Cómo se cobra el VPS.",
        default_permissions=SOLO_ADMINS,
        guild_only=True,
    )

    @grupo_ajustes.command(name="ver", description="Toda la configuración del cobro.")
    async def ajustes_ver(interaccion: discord.Interaction) -> None:
        if not await es_admin(interaccion):
            return
        await interaccion.response.send_message(
            view=tarjetas.ajustes(servicio.config),
            allowed_mentions=tarjetas.SIN_MENCIONES,
            ephemeral=True,
        )

    @grupo_ajustes.command(name="dia", description="El día del mes en que se paga el VPS.")
    @app_commands.describe(dia="Del 1 al 31. Si el mes es más corto, se usa su último día.")
    async def ajustes_dia(
        interaccion: discord.Interaction, dia: app_commands.Range[int, 1, 31]
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_dia(dia)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(interaccion, f"📅 Ahora el VPS se paga el **{dia}** de cada mes.")

    @grupo_ajustes.command(name="total", description="Cuánto cuesta el VPS al mes.")
    @app_commands.describe(monto="El total, como 240 o 240.50.")
    async def ajustes_total(interaccion: discord.Interaction, monto: str) -> None:
        if not await es_admin(interaccion):
            return
        try:
            total = ajustes.cambiar_total(monto)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(
            interaccion,
            f"💵 El VPS cuesta **{total}** al mes. Es la meta desde este mes; "
            "si se junta de más, no pasa nada.",
        )

    @grupo_ajustes.command(name="reparto", description="Cómo se divide el total.")
    @app_commands.describe(
        como="Iguales: el total entre todos. Personalizado: cada quien su monto."
    )
    async def ajustes_reparto(
        interaccion: discord.Interaction, como: Literal["iguales", "personalizado"]
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_reparto(Reparto(como))
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        explicacion = (
            "el total se divide entre todos"
            if como == "iguales"
            else "cada quien paga su monto (`/miembro monto`)"
        )
        await _listo(interaccion, f"➗ Desde el mes que viene, {explicacion}.")

    @grupo_ajustes.command(name="avisos", description="Cuándo manda los recordatorios.")
    @app_commands.describe(
        dias_antes="Cuántos días antes avisa que ya casi toca.",
        cada_dias="Si ya se pasó la fecha, cada cuántos días vuelve a recordar.",
    )
    async def ajustes_avisos(
        interaccion: discord.Interaction,
        dias_antes: app_commands.Range[int, 0, 28],
        cada_dias: app_commands.Range[int, 1, 30],
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_avisos(dias_antes, cada_dias)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(
            interaccion,
            f"🔔 Aviso **{dias_antes} días antes**, y si se pasa la fecha, "
            f"recordatorio **cada {cada_dias} días**.",
        )

    @grupo_ajustes.command(name="hora", description="A qué hora salen los recordatorios.")
    @app_commands.describe(hora="De 0 a 23, hora de México.")
    async def ajustes_hora(
        interaccion: discord.Interaction, hora: app_commands.Range[int, 0, 23]
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_hora(hora)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        recordatorios = getattr(interaccion.client, "recordatorios", None)
        if recordatorios is not None:
            recordatorios.reprogramar()
        await _listo(interaccion, f"⏰ Los recordatorios salen a las **{hora:02d}:00**.")

    @grupo_ajustes.command(name="tesorero", description="Quién recibe el dinero y lo confirma.")
    @app_commands.describe(quien="La persona en Discord.")
    async def ajustes_tesorero(interaccion: discord.Interaction, quien: discord.Member) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_tesorero(quien.id, quien.display_name)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        await _listo(interaccion, f"👤 Ahora el tesorero es **{quien.display_name}**.")

    @grupo_ajustes.command(
        name="rol", description="Un rol que también puede confirmar pagos y cambiar ajustes."
    )
    @app_commands.describe(rol="El rol. Déjalo vacío para que solo el tesorero pueda.")
    async def ajustes_rol(
        interaccion: discord.Interaction, rol: discord.Role | None = None
    ) -> None:
        if not await es_admin(interaccion):
            return
        try:
            ajustes.cambiar_rol_admin(rol.id if rol else 0)
        except ErrorDeCobro as exc:
            await _problema(interaccion, str(exc))
            return
        texto = (
            f"🛡️ Quien tenga **{rol.name}** también puede administrar el cobro."
            if rol
            else "🛡️ Listo: solo el tesorero administra el cobro."
        )
        await _listo(interaccion, texto)

    tree.add_command(grupo_ajustes)

    log.info("registré %d comandos slash", len(tree.get_commands()))
