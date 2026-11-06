"""`mc doctor`: diagnóstico del servidor."""

from __future__ import annotations

from pathlib import Path

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import diagnostico as diag
from mc_admin.core import traducciones as trad
from mc_admin.core.compose import reemplazar_bloque
from mc_admin.core.diagnostico import Nivel, Reporte
from mc_admin.errores import ErrorMc
from mc_admin.infra import archivos, puertos, rcon

COLOR = {Nivel.BIEN: "ok", Nivel.AVISO: "aviso", Nivel.MAL: "mal"}
SIMBOLO = {Nivel.BIEN: "✓", Nivel.AVISO: "!", Nivel.MAL: "✗"}


def _revisar_traducciones(ctx: Contexto) -> list[trad.LineaSospechosa]:
    """Busca mensajes en inglés en las configs generadas y en las traducciones."""
    rutas: list[Path] = []
    for carpeta in (ctx.carpeta_generados, ctx.carpeta_traducciones):
        if carpeta.is_dir():
            rutas.extend(
                p
                for p in carpeta.rglob("*")
                if p.is_file() and p.suffix in {".yml", ".yaml", ".properties", ".txt", ".conf"}
            )
    return trad.revisar_archivos(rutas, ctx.raiz)


def doctor(
    traducciones: bool = typer.Option(
        False, "--traducciones", "-t", help="Enseña línea por línea lo que sigue en inglés."
    ),
) -> None:
    """Revisa puertos, RAM, disco, TPS, versiones y traducciones."""
    try:
        ctx = Contexto.cargar()
        consola.titulo(f"Revisando {ctx.settings.servidor.nombre}")

        sospechosas = _revisar_traducciones(ctx)

        if traducciones:
            if not sospechosas:
                consola.ok("no encontré ningún mensaje que siga en inglés")
                return
            consola.aviso(f"{len(sospechosas)} línea(s) parecen seguir en inglés:\n")
            for s in sospechosas[:60]:
                consola.consola.print(f"  [dato]{s.ubicacion}[/dato]")
                consola.consola.print(f"    {s.texto}")
                consola.tenue(f"    palabras: {', '.join(s.palabras)}")
            if len(sospechosas) > 60:
                consola.tenue(f"\n  ...y {len(sospechosas) - 60} más.")
            return

        reporte = Reporte()

        # --- Entorno ----------------------------------------------------- #
        disponible, version = ctx.compose.disponible()
        reporte.agregar(diag.revisar_docker(disponible, version))
        reporte.agregar(
            diag.revisar_memoria(archivos.ram_total_gb(), ctx.settings.recursos.memoria)
        )
        reporte.agregar(
            diag.revisar_disco(archivos.espacio_libre_gb(ctx.raiz), ctx.settings.mundo.radio_pregen)
        )

        # --- Puertos ------------------------------------------------------ #
        p = ctx.settings.puertos
        ocupados = puertos.ocupados([p.java, p.bedrock], [p.bedrock, p.bedrock_webrtc])
        servidor = ctx.compose.estado_de("minecraft") if disponible else None
        for h in diag.revisar_puertos(
            ocupados,
            {"Java": p.java, "Bedrock": p.bedrock, "Bedrock WebRTC": p.bedrock_webrtc},
            servidor_encendido=servidor is not None and servidor.corriendo,
        ):
            reporte.agregar(h)

        # --- Configuración ------------------------------------------------ #
        reporte.agregar(
            diag.revisar_version_manifest(
                ctx.settings.versiones.minecraft, ctx.manifest.compatible_con
            )
        )
        reporte.agregar(
            diag.revisar_secretos(ctx.secretos.faltantes_para(pagos=ctx.settings.pagos.activo))
        )
        reporte.agregar(diag.revisar_logo(ctx.ruta_logo.is_file(), ctx.settings.servidor.logo))
        ruta_env = ctx.raiz / ".env"
        env_actual = ruta_env.read_text(encoding="utf-8") if ruta_env.is_file() else ""
        reporte.agregar(
            diag.revisar_compose(reemplazar_bloque(env_actual, ctx.bloque_compose()) == env_actual)
        )
        reporte.agregar(diag.revisar_traducciones(len(sospechosas)))

        # --- En vivo ------------------------------------------------------ #
        reporte.agregar(diag.revisar_tps(rcon.leer_tps(ctx.conexion_rcon)))

        # --- Pendientes --------------------------------------------------- #
        for h in diag.revisar_pendientes_de_llenar(
            ctx.settings.pagos.pendiente_de_llenar,
            len(ctx.settings.admins),
            len(ctx.settings.whitelist.java) + len(ctx.settings.whitelist.bedrock),
        ):
            reporte.agregar(h)

        # --- Imprimir ----------------------------------------------------- #
        for h in reporte.hallazgos:
            color = COLOR[h.nivel]
            consola.consola.print(
                f"[{color}]{SIMBOLO[h.nivel]}[/{color}] [dato]{h.titulo}[/dato]: {h.detalle}"
            )
            if h.pista:
                consola.tenue(f"    {h.pista}")

        consola.titulo("Resumen")
        consola.info(reporte.resumen())

        if reporte.hay_problemas:
            raise typer.Exit(code=1)

    except ErrorMc as exc:
        consola.salir_con_error(exc)
