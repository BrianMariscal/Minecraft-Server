"""`mc alert` y `mc monitor`: avisos operativos por Discord."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime

import typer

from mc_admin.cli import consola
from mc_admin.cli import respaldos as cli_respaldos
from mc_admin.contexto import Contexto
from mc_admin.errores import ErrorDeEntorno, ErrorMc
from mc_admin.infra import alertas

ARCHIVO_MONITOR = ".monitor.json"


def _texto(titulo: str, lineas: list[str]) -> str:
    return f"**{titulo}**\n" + "\n".join(f"- {linea}" for linea in lineas)


def _toca_avisar(ctx: Contexto, huella: str, repetir_horas: float) -> bool:
    """Evita mandar la misma alerta cada hora mientras el problema siga."""
    ruta = ctx.carpeta_respaldos / ARCHIVO_MONITOR
    previo = cli_respaldos._leer_json(ruta) or {}
    if previo.get("huella") != huella:
        return True
    momento = previo.get("momento")
    if not isinstance(momento, str):
        return True
    try:
        anterior = datetime.fromisoformat(momento)
    except ValueError:
        return True
    edad = (cli_respaldos._ahora(ctx) - anterior).total_seconds() / 3600
    return edad >= repetir_horas


def _recordar(ctx: Contexto, huella: str) -> None:
    cli_respaldos._escribir_json(
        ctx.carpeta_respaldos / ARCHIVO_MONITOR,
        {"huella": huella, "momento": cli_respaldos._ahora(ctx).isoformat()},
    )


def alert(
    mensaje: str = typer.Argument(..., help="Texto de la alerta."),
    titulo: str = typer.Option("Minecraft HD", "--titulo", "-t", help="Título del aviso."),
    seco: bool = typer.Option(False, "--seco", help="Solo imprime el texto; no manda nada."),
) -> None:
    """Manda una alerta al canal de Discord configurado."""
    try:
        ctx = Contexto.cargar()
        texto = _texto(titulo, [mensaje])
        if seco:
            consola.info(texto)
            return
        if not alertas.enviar(ctx.secretos, texto):
            raise ErrorDeEntorno(
                "no pude mandar la alerta a Discord",
                pista=(
                    "Revisa PAGOS_BOT_TOKEN, ALERTAS_CANAL_ID (o PAGOS_CANAL_ID) "
                    "y la conexión del VPS."
                ),
            )
        consola.ok("alerta enviada")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def monitor(
    horas_max: float = typer.Option(8.0, "--horas-max", help="Horas sin respaldo antes de avisar."),
    disco_minimo_gb: float = typer.Option(
        15.0, "--disco-minimo-gb", help="GB libres por debajo de los cuales avisar."
    ),
    repetir_horas: float = typer.Option(
        6.0, "--repetir-horas", help="Horas antes de repetir la misma alerta."
    ),
) -> None:
    """Revisa respaldo, disco y servidor; avisa por Discord si algo falla."""
    try:
        ctx = Contexto.cargar()
        problemas: list[str] = []

        respaldos = cli_respaldos._leer_respaldos(ctx)
        if not respaldos:
            problemas.append("no hay ningún respaldo guardado")
        else:
            ultimo = max(respaldos, key=lambda r: r.momento)
            edad = (cli_respaldos._ahora(ctx) - ultimo.momento).total_seconds() / 3600
            if edad > horas_max:
                problemas.append(
                    f"el último respaldo tiene {edad:.1f} h; el límite es {horas_max:.1f} h"
                )

        libre = shutil.disk_usage(ctx.raiz).free / 1024**3
        if libre < disco_minimo_gb:
            problemas.append(f"quedan {libre:.1f} GB libres; el mínimo es {disco_minimo_gb:.1f} GB")

        try:
            servidor = ctx.compose.estado_de("minecraft")
            if servidor is None or not servidor.corriendo:
                problemas.append("el contenedor de Minecraft no está corriendo")
            elif not servidor.sano:
                problemas.append(f"el contenedor de Minecraft está {servidor.descripcion}")
        except ErrorMc as exc:
            problemas.append(f"no pude revisar Docker: {exc.mensaje}")

        if not problemas:
            (ctx.carpeta_respaldos / ARCHIVO_MONITOR).unlink(missing_ok=True)
            consola.ok("respaldo, disco y servidor en orden.")
            return

        texto = _texto("Minecraft HD", problemas)
        huella = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]
        if not _toca_avisar(ctx, huella, repetir_horas):
            consola.tenue("El problema sigue, pero ya se avisó hace poco.")
        elif alertas.enviar(ctx.secretos, texto):
            _recordar(ctx, huella)
            consola.ok("alerta enviada")
        else:
            consola.mal("hay problemas y no pude mandar la alerta a Discord")
        raise typer.Exit(code=1)
    except ErrorMc as exc:
        consola.salir_con_error(exc)
