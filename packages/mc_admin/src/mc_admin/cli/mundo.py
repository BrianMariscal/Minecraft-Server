"""`mc pregen` y `mc world reset`: generar y regenerar el mundo."""

from __future__ import annotations

import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.errores import ErrorDeRcon, ErrorMc, OperacionCancelada
from mc_admin.infra import rcon

app = typer.Typer(help="El mundo: pregenerar y regenerar.")


def pregen(
    radio: int = typer.Option(
        None, "--radio", "-r", help="Radio en bloques. Por defecto, el de settings.yml."
    ),
) -> None:
    """Pregenera el mapa con Chunky, para que no haya tirones al explorar."""
    try:
        ctx = Contexto.cargar()
        r = radio if radio is not None else ctx.settings.mundo.radio_pregen

        if not rcon.esta_vivo(ctx.conexion_rcon):
            raise ErrorDeRcon(
                "el servidor tiene que estar encendido para pregenerar",
                "Arranca con `mc start` y espera a que diga listo.",
            )

        # Una estimación honesta: con estos datapacks un radio de 3000 da un
        # mundo de varios GB y tarda horas.
        chunks = int((2 * r / 16) ** 2)
        gb = (r**2) / 450_000
        consola.titulo(f"Pregenerar radio {r}")
        consola.info(
            f"Son como [dato]{chunks:,}[/dato] chunks, unos [dato]{gb:.1f} GB[/dato] de mundo."
        )
        consola.aviso("Esto tarda HORAS y va a traer el servidor cargado todo ese rato.")
        consola.tenue("  Puedes seguirlo con `mc logs -f` y pararlo con `/chunky cancel`.")

        if not consola.confirmar("\n¿Le damos?", por_defecto=False):
            raise OperacionCancelada()

        consola.paso("Arrancando Chunky...")
        rcon.mandar_varios(
            ctx.conexion_rcon,
            [
                "chunky world world",
                "chunky center 0 0",
                "chunky radius " + str(r),
                "chunky start",
            ],
        )
        consola.ok("Chunky corriendo")
        consola.tenue(
            "\n  Míralo con: mc logs -f\n  Para pararlo:  mc console  y luego  chunky pause"
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@app.command("reset")
def world_reset(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Solo di qué pasaría."),
) -> None:
    """Regenera el mundo desde cero. Hace respaldo antes y pide doble confirmación."""
    try:
        ctx = Contexto.cargar()
        datos = ctx.carpeta_datos
        mundos = [datos / n for n in ("world", "world_nether", "world_the_end")]
        existentes = [m for m in mundos if m.is_dir()]

        consola.titulo("Regenerar el mundo")
        if not existentes:
            consola.aviso("no hay ningún mundo todavía; esto no haría nada.")
            return

        total = sum(f.stat().st_size for m in existentes for f in m.rglob("*") if f.is_file())
        consola.info("Se van a BORRAR estas carpetas:")
        for m in existentes:
            consola.info(f"  [mal]{m.relative_to(ctx.raiz)}[/mal]")
        consola.info(f"\nEn total [dato]{total / 1024**3:.2f} GB[/dato] de mundo.")
        consola.aviso("Se pierden todas las construcciones, cofres y granjas.")
        consola.tenue(
            "  Lo que NO se pierde: las casas de /sethome apuntan a coordenadas\n"
            "  que ya no van a existir, así que también conviene borrarlas."
        )

        if dry_run:
            consola.tenue("\n  --dry-run: no se tocó nada.")
            return

        if not consola.confirmar_doble("\n¿De verdad quieres borrar el mundo?", "BORRAR EL MUNDO"):
            raise OperacionCancelada()

        # Respaldo ANTES de tocar nada. Si esto falla, no seguimos.
        consola.paso("Haciendo un respaldo antes, por si acaso...")
        from mc_admin.cli import respaldos as cli_respaldos

        ruta_respaldo = cli_respaldos.crear_respaldo(ctx, etiqueta="antes-de-reset")
        consola.ok(f"respaldo en {ruta_respaldo.relative_to(ctx.raiz)}")

        if rcon.esta_vivo(ctx.conexion_rcon):
            consola.paso("Apagando el servidor...")
            ctx.compose.apagar()

        consola.paso("Borrando los mundos...")
        for m in existentes:
            shutil.rmtree(m)
            consola.info(f"  borrado {m.name}")

        consola.ok("listo: el mundo se regenera solo en el próximo arranque")
        consola.tenue(
            "\n  La semilla nueva es aleatoria (servidor.semilla está vacío).\n"
            "  Arranca con `mc start` y luego pregenera con `mc pregen`."
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def _ahora(ctx: Contexto) -> datetime:
    return datetime.now(ZoneInfo(ctx.settings.pagos.zona_horaria))
