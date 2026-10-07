"""`mc backup`: hacer, listar y restaurar respaldos."""

from __future__ import annotations

import shutil
import sqlite3
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import respaldos as core
from mc_admin.errores import ErrorDeRcon, ErrorDeRespaldo, ErrorMc, OperacionCancelada
from mc_admin.infra import rcon, sqlite

app = typer.Typer(help="Respaldos del mundo y de las configs.")

# Lo que no tiene caso guardar: se vuelve a bajar o a generar solo.
# `pagos-datos` dentro de data/ es solo el punto de montaje vacío que usa el
# contenedor de respaldos; la base de verdad se agrega aparte, abajo.
EXCLUIR = ("cache", "logs", "libraries", "versions", "pagos-datos")

CARPETA_PAGOS = "pagos-datos"
BASE_PAGOS = "pagos.sqlite"
# La foto que el bot saca cada hora con la API de respaldo de SQLite.
COPIA_PAGOS = "pagos.copia.sqlite"


def _zona(ctx: Contexto) -> ZoneInfo:
    return ZoneInfo(ctx.settings.pagos.zona_horaria)


def _leer_respaldos(ctx: Contexto) -> list[core.Respaldo]:
    carpeta = ctx.carpeta_respaldos
    if not carpeta.is_dir():
        return []
    zona = _zona(ctx)
    encontrados: list[core.Respaldo] = []
    for archivo in carpeta.iterdir():
        if not archivo.is_file():
            continue
        r = core.interpretar_nombre(archivo.name, archivo.stat().st_size, zona)
        if r is not None:
            encontrados.append(r)
    return encontrados


def crear_respaldo(ctx: Contexto, etiqueta: str = "world") -> Path:
    """Hace un respaldo en caliente, sin apagar el servidor.

    Le dice al servidor que deje de escribir al disco (`save-off`), lo
    obliga a guardar lo que trae en memoria (`save-all flush`), copia, y
    luego lo deja seguir (`save-on`). Nadie se desconecta.
    """
    ctx.carpeta_respaldos.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(_zona(ctx)).strftime(core.FORMATO_MARCA)
    destino = ctx.carpeta_respaldos / f"{etiqueta}-{marca}.tgz"

    servidor_vivo = rcon.esta_vivo(ctx.conexion_rcon)
    if servidor_vivo:
        rcon.mandar_varios(
            ctx.conexion_rcon, ["save-off", "save-all flush"], timeout=rcon.TIMEOUT_LARGO
        )
    try:
        with tarfile.open(destino, "w:gz") as tar:
            for elemento in sorted(ctx.carpeta_datos.iterdir()):
                rel = elemento.name
                if rel in EXCLUIR or rel.endswith(".jar"):
                    continue
                tar.add(elemento, arcname=rel, filter=_sin_basura)
            # La base de datos del bot de pagos también entra, pero copiada con
            # la API de SQLite: el bot puede estar escribiendo en este momento.
            _agregar_base_de_pagos(ctx, tar)
            # Y settings.yml, para saber con qué config se hizo.
            tar.add(ctx.raiz / "settings.yml", arcname="settings.yml")
    except (OSError, sqlite3.Error) as exc:
        destino.unlink(missing_ok=True)
        raise ErrorDeRespaldo(f"no pude escribir el respaldo: {exc}") from exc
    finally:
        if servidor_vivo:
            try:
                rcon.mandar(ctx.conexion_rcon, "save-on")
            except ErrorDeRcon:  # pragma: no cover
                # Dejar el servidor con save-off sería grave: lo avisamos
                # fuerte en vez de tragárnoslo.
                consola.mal(
                    "¡OJO! No pude volver a prender el guardado automático. "
                    "Entra con `mc console` y escribe `save-on`."
                )
    return destino


def _agregar_base_de_pagos(ctx: Contexto, tar: tarfile.TarFile) -> None:
    """Mete al tar una copia consistente de la base del bot de pagos."""
    base = ctx.raiz / CARPETA_PAGOS / BASE_PAGOS
    if not base.is_file():
        return
    with tempfile.TemporaryDirectory() as temporal:
        copia = Path(temporal) / BASE_PAGOS
        sqlite.copia_consistente(base, copia)
        tar.add(copia, arcname=f"{CARPETA_PAGOS}/{BASE_PAGOS}")


def _restaurar_base_de_pagos(ctx: Contexto, tar: tarfile.TarFile) -> None:
    """Saca del respaldo la base del bot de pagos y la deja sana.

    Los respaldos automáticos copian los archivos tal cual (base, -wal y la
    foto horaria del bot). Si la base que salió no pasa la revisión de
    SQLite, usamos la foto.
    """
    de_pagos = [m for m in tar.getmembers() if _nombre(m).startswith(CARPETA_PAGOS + "/")]
    if not de_pagos:
        return

    carpeta = ctx.raiz / CARPETA_PAGOS
    # Lo de ahorita fuera, con su -wal: si se quedara, SQLite se lo aplicaría
    # encima a la base restaurada.
    sqlite.borrar_con_wal(carpeta / BASE_PAGOS)
    sqlite.borrar_con_wal(carpeta / COPIA_PAGOS)
    tar.extractall(ctx.raiz, members=de_pagos, filter="data")

    base = carpeta / BASE_PAGOS
    if sqlite.esta_sana(base):
        consola.info("  restauré también la base de datos del bot de pagos")
        return
    copia = carpeta / COPIA_PAGOS
    if sqlite.esta_sana(copia):
        sqlite.borrar_con_wal(base)
        shutil.copy2(copia, base)
        consola.aviso(
            "la base del bot de pagos del respaldo venía dañada; usé la foto que "
            "el bot saca cada hora (puede faltarle lo de la última hora)"
        )
        return
    consola.mal(
        "la base del bot de pagos del respaldo no abre. Prueba con otro respaldo: "
        "mc backup restore <id>"
    )


def _nombre(miembro: tarfile.TarInfo) -> str:
    """El nombre sin el `./` que le ponen los respaldos de itzg/mc-backup."""
    return miembro.name.removeprefix("./")


def _sin_basura(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    """Filtro de tar: deja fuera lo que no sirve restaurar."""
    partes = Path(info.name).parts
    if any(p in ("cache", "logs", "libraries", "versions") for p in partes):
        return None
    if info.name.endswith(".jar"):
        return None
    return info


@app.command("now")
def backup_now() -> None:
    """Hace un respaldo ya, sin apagar el servidor."""
    try:
        ctx = Contexto.cargar()
        if not ctx.carpeta_datos.is_dir():
            raise ErrorDeRespaldo("no hay carpeta data/ que respaldar", "Corre `mc build` primero.")
        consola.paso("Haciendo el respaldo (el servidor sigue encendido)...")
        destino = crear_respaldo(ctx)
        tamano = destino.stat().st_size
        consola.ok(f"listo: {destino.name} ({tamano / 1024**2:.1f} MB)")
        consola.tenue(f"  {destino.relative_to(ctx.raiz)}")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@app.command("list")
def backup_list() -> None:
    """Enseña los respaldos que hay."""
    try:
        ctx = Contexto.cargar()
        encontrados = core.ordenar_recientes_primero(_leer_respaldos(ctx))
        if not encontrados:
            consola.aviso("todavía no hay ningún respaldo.")
            consola.tenue("  Haz uno con: mc backup now")
            return

        zona = _zona(ctx)
        t = consola.tabla("Respaldos", ["id", "Cuándo", "Tamaño"])
        for r in encontrados:
            t.add_row(r.id, r.fecha_bonita(zona), r.tamano_legible)
        consola.consola.print(t)
        consola.tenue(
            f"\n  {len(encontrados)} respaldo(s), se conservan "
            f"{ctx.settings.respaldos.conservar_dias} días.\n"
            f"  Restaurar: mc backup restore {encontrados[0].id}  (o `ultimo`)"
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@app.command("restore")
def backup_restore(
    identificador: str = typer.Argument(..., help="El id del respaldo, o `ultimo`."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Solo di qué pasaría."),
) -> None:
    """Restaura un respaldo. Hace otro respaldo antes y pide doble confirmación."""
    try:
        ctx = Contexto.cargar()
        elegido = core.buscar(_leer_respaldos(ctx), identificador)
        archivo = ctx.carpeta_respaldos / elegido.archivo

        consola.titulo("Restaurar un respaldo")
        consola.info(f"Respaldo: [dato]{elegido.archivo}[/dato]")
        consola.info(f"Del      : {elegido.fecha_bonita(_zona(ctx))}")
        consola.info(f"Tamaño   : {elegido.tamano_legible}")
        consola.aviso("Esto reemplaza el mundo y las configs de ahorita.")

        if dry_run:
            with tarfile.open(archivo) as tar:
                nombres = tar.getnames()
            consola.info(f"\nTrae [dato]{len(nombres)}[/dato] archivos. Los primeros:")
            for n in nombres[:12]:
                consola.tenue(f"  {n}")
            consola.tenue("\n  --dry-run: no se tocó nada.")
            return

        if not consola.confirmar_doble("\n¿Restaurar y sobrescribir lo de ahorita?", "RESTAURAR"):
            raise OperacionCancelada()

        consola.paso("Primero, un respaldo de lo que hay ahorita...")
        previo = crear_respaldo(ctx, etiqueta="antes-de-restaurar")
        consola.ok(f"guardado en {previo.name}")

        consola.paso("Apagando el servidor...")
        try:
            ctx.compose.apagar()
        except ErrorMc:
            consola.tenue("  (ya estaba apagado)")

        consola.paso("Restaurando...")
        destino = ctx.carpeta_datos
        for n in ("world", "world_nether", "world_the_end"):
            carpeta_vieja = destino / n
            if carpeta_vieja.is_dir():
                shutil.rmtree(carpeta_vieja)

        with tarfile.open(archivo) as tar:
            # El respaldo trae tres cosas distintas que NO van al mismo lugar:
            #   settings.yml  -> la raíz del proyecto (y solo si lo pides)
            #   pagos-datos/  -> la raíz del proyecto
            #   todo lo demás -> data/
            # Por eso no hacemos un extractall pelón.
            #
            # filter="data" es lo que evita que una ruta con ".." dentro del
            # tar escriba fuera de la carpeta destino.
            # Ojo: los respaldos de itzg/mc-backup nombran todo con "./"
            # adelante ("./pagos-datos/..."); los de `mc backup now`, no.
            del_servidor = [
                m
                for m in tar.getmembers()
                if not _nombre(m).startswith(("settings.yml", CARPETA_PAGOS))
            ]
            tar.extractall(destino, members=del_servidor, filter="data")
            _restaurar_base_de_pagos(ctx, tar)

        # settings.yml del respaldo NO se restaura solo: si cambiaste la
        # config a propósito, pisártela sin avisar sería una grosería.
        # Queda dentro del .tgz por si lo quieres consultar.
        consola.tenue("  (settings.yml NO se tocó; está dentro del respaldo si lo necesitas)")

        consola.ok("restaurado")
        consola.tenue(
            f"\n  Si algo salió mal, el respaldo de antes está en:\n"
            f"  {previo.relative_to(ctx.raiz)}\n\n"
            "  Arranca con: mc start"
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)
