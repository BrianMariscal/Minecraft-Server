"""Punto de entrada de `mc`.

Junta todos los comandos y configura el logging. La ayuda y los mensajes
están en español de México a propósito: esto lo va a usar la banda, no un
administrador de sistemas.
"""

from __future__ import annotations

import logging

import typer

from mc_admin import __version__
from mc_admin.cli import build as cli_build
from mc_admin.cli import consola
from mc_admin.cli import doctor as cli_doctor
from mc_admin.cli import jugadores as cli_jugadores
from mc_admin.cli import mundo as cli_mundo
from mc_admin.cli import respaldos as cli_respaldos
from mc_admin.cli import servidor as cli_servidor
from mc_admin.cli import setup as cli_setup
from mc_admin.cli import update as cli_update
from mc_admin.infra import registro

app = typer.Typer(
    name="mc",
    help="Administra el servidor de Minecraft HD.",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version(valor: bool) -> None:
    if valor:
        consola.consola.print(f"mc {__version__}")
        raise typer.Exit()


@app.callback()
def principal(
    verboso: int = typer.Option(
        0,
        "--verboso",
        "-v",
        count=True,
        help="Más detalle en el log. -v para info, -vv para todo.",
    ),
    version: bool = typer.Option(  # noqa: ARG001 — lo consume el callback
        False, "--version", callback=_version, is_eager=True, help="Enseña la versión."
    ),
) -> None:
    """Administra el servidor de Minecraft HD."""
    nivel = {0: logging.WARNING, 1: logging.INFO}.get(verboso, logging.DEBUG)
    registro.configurar(nivel)


# --- Preparar el servidor -------------------------------------------------- #
app.command("setup", help="Revisa el entorno y te pide los datos que faltan.")(cli_setup.setup)
app.add_typer(
    cli_build.app,
    name="build",
    help="Descarga los plugins verificando su sha256 y genera las configs.",
)

# --- Día a día ------------------------------------------------------------- #
app.command("start", help="Enciende el servidor.")(cli_servidor.start)
app.command("stop", help="Apaga el servidor guardando el mundo.")(cli_servidor.stop)
app.command("restart", help="Reinicia el servidor.")(cli_servidor.restart)
app.command("status", help="Cómo está el servidor y quién anda conectado.")(cli_servidor.status)
app.command("logs", help="Muestra los logs.")(cli_servidor.logs)
app.command("console", help="Consola interactiva del servidor por RCON.")(cli_servidor.console)

# --- Jugadores -------------------------------------------------------------- #
app.add_typer(cli_jugadores.whitelist_app, name="whitelist")
app.add_typer(cli_jugadores.admin_app, name="admin")

# --- Respaldos --------------------------------------------------------------- #
app.add_typer(cli_respaldos.app, name="backup")

# --- Mundo -------------------------------------------------------------------- #
app.command("pregen", help="Pregenera el mapa con Chunky.")(cli_mundo.pregen)
app.add_typer(cli_mundo.app, name="world")

# --- Mantenimiento ------------------------------------------------------------ #
app.command("update", help="Revisa si hay versiones nuevas de los plugins.")(cli_update.update)
app.command("doctor", help="Diagnóstico: puertos, RAM, disco, TPS y traducciones.")(
    cli_doctor.doctor
)


if __name__ == "__main__":  # pragma: no cover
    app()
