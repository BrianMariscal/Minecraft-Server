"""`mc update`: revisa si hay versiones nuevas y te enseña qué cambiaría."""

from __future__ import annotations

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core.versiones import Cambio, Comparacion, filtrar_compatibles, resumir
from mc_admin.errores import ErrorMc, OperacionCancelada
from mc_admin.infra import catalogo


def _color_de(c: Comparacion) -> str:
    if c.cambio is Cambio.SUBE:
        return "ok" if c.es_seguro else "aviso"
    if c.cambio is Cambio.DESCONOCIDO:
        return "tenue"
    return "tenue"


def update(
    aplicar: bool = typer.Option(
        False, "--aplicar", help="Después de enseñarte qué cambia, pregunta si lo aplico."
    ),
) -> None:
    """Revisa versiones nuevas de los plugins, te dice qué cambiaría y solo aplica si confirmas."""
    try:
        ctx = Contexto.cargar()
        mc = ctx.settings.versiones.minecraft
        manifest = ctx.manifest

        consola.titulo(f"Buscando versiones nuevas para Minecraft {mc}")
        consola.tenue("  Esto le pregunta a Modrinth, GitHub y GeyserMC. Tarda tantito.\n")

        comparaciones: list[Comparacion] = []
        artefactos = manifest.artefactos
        with catalogo.crear_cliente() as cliente:
            for i, (_, a) in enumerate(artefactos, start=1):
                consola.consola.print(
                    f"[tenue]  {i:>2}/{len(artefactos)}  revisando {a.nombre}...[/tenue]",
                    end="\r",
                )
                comparaciones.append(
                    catalogo.buscar_novedades(a.nombre, a.version, a.url, mc, cliente)
                )
        consola.consola.print(" " * 60, end="\r")

        aplicables, descartadas = filtrar_compatibles(comparaciones, mc)

        # --- Lo que sí se puede subir ------------------------------------ #
        if aplicables:
            consola.titulo("Hay versión nueva")
            t = consola.tabla("", ["Plugin", "Ahorita", "Nueva", "Canal"])
            for c in sorted(aplicables, key=lambda x: x.nombre):
                color = _color_de(c)
                t.add_row(
                    c.nombre,
                    c.actual,
                    f"[{color}]{c.disponible}[/{color}]",
                    c.canal if c.es_seguro else f"[aviso]{c.canal}[/aviso]",
                )
            consola.consola.print(t)

        # --- Lo que NO conviene ------------------------------------------ #
        if descartadas:
            consola.titulo("Hay versión nueva, pero NO para nuestro Minecraft")
            consola.tenue(
                f"  Estas ya no soportan Minecraft {mc}. Subirlas rompería el\n"
                "  servidor, así que no te las propongo.\n"
            )
            for c in sorted(descartadas, key=lambda x: x.nombre):
                consola.info(f"[tenue]{c.nombre}: {c.actual} → {c.disponible}[/tenue]")

        # --- Lo que no se pudo revisar ----------------------------------- #
        sin_revisar = [c for c in comparaciones if c.cambio is Cambio.DESCONOCIDO]
        if sin_revisar:
            consola.titulo("No se pudieron revisar solos")
            for c in sin_revisar:
                consola.info(f"[tenue]{c.nombre} ({c.actual}): {c.nota}[/tenue]")

        consola.titulo("Resumen")
        consola.info(resumir(comparaciones, mc))

        if not aplicables:
            return

        consola.tenue(
            "\n  `mc update` NO edita manifest.yml solo: cada versión nueva hay que\n"
            "  bajarla y recalcularle el sha256, y eso conviene hacerlo viendo\n"
            "  el changelog de cada plugin.\n"
            "\n  Para subir uno:\n"
            "    1. Edita minecraft/manifest.yml con la versión y la URL nuevas.\n"
            "    2. Corre `mc build`: va a fallar diciéndote el sha256 real.\n"
            "    3. Pega ese sha256 en el manifest y vuelve a correr `mc build`.\n"
            "    4. `mc restart` y revisa `mc logs`.\n"
            "\n  Haz un respaldo antes: mc backup now"
        )

        if aplicar and not consola.confirmar(
            "\n¿Quieres que te abra manifest.yml para editarlo?", por_defecto=False
        ):
            raise OperacionCancelada()

    except ErrorMc as exc:
        consola.salir_con_error(exc)
