"""La única capa que escribe a la terminal.

Todo lo que ve el usuario pasa por aquí: así el resto del código puede
loguear sin pelearse con Rich, y los tests no capturan salida.
"""

from __future__ import annotations

from typing import NoReturn

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.theme import Theme

from mc_admin.errores import ErrorMc, OperacionCancelada

# Paleta sobria, a juego con el MOTD del servidor.
TEMA = Theme(
    {
        "ok": "bold green",
        "aviso": "bold yellow",
        "mal": "bold red",
        "dato": "cyan",
        "tenue": "dim",
        "titulo": "bold cyan",
    }
)

consola = Console(theme=TEMA)
# Los errores van a stderr, para poder hacer `mc status > archivo` sin que se
# mezclen con la salida buena.
consola_error = Console(theme=TEMA, stderr=True)


def titulo(texto: str) -> None:
    consola.print(f"\n[titulo]{texto}[/titulo]")


def ok(texto: str) -> None:
    consola.print(f"[ok]✓[/ok] {texto}")


def aviso(texto: str) -> None:
    consola.print(f"[aviso]![/aviso] {texto}")


def mal(texto: str) -> None:
    consola.print(f"[mal]✗[/mal] {texto}")


def info(texto: str) -> None:
    consola.print(f"  {texto}")


def tenue(texto: str) -> None:
    consola.print(f"[tenue]{texto}[/tenue]")


def paso(texto: str) -> None:
    """Un paso dentro de una operación larga."""
    consola.print(f"[dato]→[/dato] {texto}")


def tabla(titulo_tabla: str, columnas: list[str]) -> Table:
    """Una tabla con el estilo del proyecto."""
    t = Table(
        title=titulo_tabla,
        title_style="titulo",
        header_style="dato",
        box=None,
        pad_edge=False,
    )
    for c in columnas:
        t.add_column(c)
    return t


def mostrar_error(exc: ErrorMc) -> None:
    """Imprime un ErrorMc bonito, sin traceback."""
    cuerpo = exc.mensaje
    if exc.pista:
        cuerpo += f"\n\n[tenue]{exc.pista}[/tenue]"
    consola_error.print(
        Panel(cuerpo, title="[mal]Algo salió mal[/mal]", border_style="red", expand=False)
    )


def salir_con_error(exc: ErrorMc) -> NoReturn:
    """Muestra el error y termina con el código que corresponde."""
    if isinstance(exc, OperacionCancelada):
        consola.print(f"[aviso]{exc.mensaje}[/aviso]")
        raise typer.Exit(code=0)
    mostrar_error(exc)
    raise typer.Exit(code=1)


def confirmar(pregunta: str, *, por_defecto: bool = False) -> bool:
    """Pregunta sí o no."""
    return typer.confirm(pregunta, default=por_defecto)


def confirmar_doble(pregunta: str, palabra: str) -> bool:
    """Confirmación de dos pasos para lo que no tiene vuelta atrás.

    Primero un sí/no, y luego hay que teclear una palabra exacta. Es a
    propósito molesto: es lo que separa "regenerar el mundo" de
    "perdí el mundo".
    """
    if not typer.confirm(pregunta, default=False):
        return False
    consola.print(f"\n[aviso]Para confirmar, escribe exactamente:[/aviso] [dato]{palabra}[/dato]")
    escrito = typer.prompt("  ")
    if escrito.strip() != palabra:
        consola.print("[tenue]No coincide. No se tocó nada.[/tenue]")
        return False
    return True
