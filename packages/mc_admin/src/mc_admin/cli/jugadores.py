"""`mc whitelist` y `mc admin`: quién puede entrar y quién manda."""

from __future__ import annotations

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import jugadores as core
from mc_admin.core.jugadores import Plataforma
from mc_admin.errores import ErrorDeRcon, ErrorMc
from mc_admin.infra import archivos, rcon

whitelist_app = typer.Typer(help="Quién puede entrar al servidor.")
admin_app = typer.Typer(help="Quién tiene permisos de administración.")


def _avisar_al_servidor(ctx: Contexto, comandos: list[str]) -> bool:
    """Le dice al servidor los cambios, si está encendido.

    Si está apagado no pasa nada: `mc build` y `mc start` vuelven a aplicar
    todo desde settings.yml.
    """
    try:
        rcon.mandar_varios(ctx.conexion_rcon, comandos)
    except ErrorDeRcon:
        return False
    return True


# --------------------------------------------------------------------------- #
#  Whitelist
# --------------------------------------------------------------------------- #


@whitelist_app.command("add")
def whitelist_add(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
) -> None:
    """Agrega a alguien a la whitelist."""
    try:
        ctx = Contexto.cargar()
        plataforma = Plataforma.BEDROCK if bedrock else Plataforma.JAVA
        lista = list(ctx.settings.whitelist.bedrock if bedrock else ctx.settings.whitelist.java)
        cambio = core.agregar(lista, jugador, plataforma)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        clave = "whitelist.bedrock" if bedrock else "whitelist.java"
        archivos.actualizar_settings(ctx.raiz, {clave: list(cambio.lista)})

        nombre_real = core.validar(jugador, plataforma)
        if bedrock:
            nombre_real = core.nombre_con_prefijo(
                nombre_real, ctx.settings.seguridad.prefijo_bedrock
            )
        consola.ok(cambio.mensaje)
        if bedrock:
            consola.tenue(f"  En el servidor se llama: {nombre_real}")

        if _avisar_al_servidor(ctx, [f"whitelist add {nombre_real}"]):
            consola.ok("ya quedó también en el servidor encendido")
        else:
            consola.tenue("  (el servidor está apagado; se aplica al arrancar)")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@whitelist_app.command("remove")
def whitelist_remove(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
) -> None:
    """Saca a alguien de la whitelist."""
    try:
        ctx = Contexto.cargar()
        plataforma = Plataforma.BEDROCK if bedrock else Plataforma.JAVA
        lista = list(ctx.settings.whitelist.bedrock if bedrock else ctx.settings.whitelist.java)
        cambio = core.quitar(lista, jugador, plataforma)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        clave = "whitelist.bedrock" if bedrock else "whitelist.java"
        archivos.actualizar_settings(ctx.raiz, {clave: list(cambio.lista)})

        nombre_real = core.validar(jugador, plataforma)
        if bedrock:
            nombre_real = core.nombre_con_prefijo(
                nombre_real, ctx.settings.seguridad.prefijo_bedrock
            )
        consola.ok(cambio.mensaje)
        if _avisar_al_servidor(ctx, [f"whitelist remove {nombre_real}"]):
            consola.ok("ya quedó también en el servidor encendido")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@whitelist_app.command("list")
def whitelist_list() -> None:
    """Enseña quién está en la whitelist."""
    try:
        ctx = Contexto.cargar()
        w = ctx.settings.whitelist
        if not w.java and not w.bedrock:
            consola.aviso("la whitelist está vacía: nadie puede entrar.")
            consola.tenue("  Agrega gente con: mc whitelist add Pepe")
            return

        t = consola.tabla("Whitelist", ["Jugador", "Plataforma", "Nombre en el servidor"])
        for n in w.java:
            t.add_row(n, "Java", n)
        prefijo = ctx.settings.seguridad.prefijo_bedrock
        for n in w.bedrock:
            t.add_row(n, "Bedrock", core.nombre_con_prefijo(core.normalizar_gamertag(n), prefijo))
        consola.consola.print(t)
        total = len(w.java) + len(w.bedrock)
        consola.tenue(f"\n  Total: {total} de {ctx.settings.servidor.max_jugadores} lugares")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


# --------------------------------------------------------------------------- #
#  Admins
# --------------------------------------------------------------------------- #


@admin_app.command("add")
def admin_add(jugador: str = typer.Argument(..., help="Nombre de Minecraft Java.")) -> None:
    """Hace admin a alguien: grupo `admin` de LuckPerms y op."""
    try:
        ctx = Contexto.cargar()
        cambio = core.agregar(list(ctx.settings.admins), jugador, Plataforma.JAVA)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        archivos.actualizar_settings(ctx.raiz, {"admins": list(cambio.lista)})
        nombre = core.validar(jugador, Plataforma.JAVA)
        consola.ok(cambio.mensaje)

        if _avisar_al_servidor(ctx, [f"lp user {nombre} parent add admin", f"op {nombre}"]):
            consola.ok("ya quedó también en el servidor encendido")
        else:
            consola.tenue("  (el servidor está apagado; se aplica al arrancar)")
        consola.tenue("  Corre `mc build` para que quede en el guion de grupos.")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@admin_app.command("remove")
def admin_remove(jugador: str = typer.Argument(..., help="Nombre de Minecraft Java.")) -> None:
    """Le quita el admin a alguien."""
    try:
        ctx = Contexto.cargar()
        cambio = core.quitar(list(ctx.settings.admins), jugador, Plataforma.JAVA)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        archivos.actualizar_settings(ctx.raiz, {"admins": list(cambio.lista)})
        nombre = core.validar(jugador, Plataforma.JAVA)
        consola.ok(cambio.mensaje)
        if _avisar_al_servidor(ctx, [f"lp user {nombre} parent remove admin", f"deop {nombre}"]):
            consola.ok("ya quedó también en el servidor encendido")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@admin_app.command("list")
def admin_list() -> None:
    """Enseña quiénes son admins."""
    try:
        ctx = Contexto.cargar()
        if not ctx.settings.admins:
            consola.aviso("no hay ningún admin configurado.")
            consola.tenue("  Agrégate con: mc admin add TuNombre")
            return
        consola.titulo("Admins")
        for n in ctx.settings.admins:
            consola.info(f"[dato]{n}[/dato]")
    except ErrorMc as exc:
        consola.salir_con_error(exc)
