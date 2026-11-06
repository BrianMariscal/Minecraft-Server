"""`mc backup`: crear, listar, verificar, podar y restaurar respaldos."""

from __future__ import annotations

import fcntl
import hashlib
import io
import json
import shutil
import sqlite3
import tarfile
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import respaldos as core
from mc_admin.errores import ErrorDeRcon, ErrorDeRespaldo, ErrorMc, OperacionCancelada
from mc_admin.infra import rcon, sqlite

app = typer.Typer(help="Respaldos del mundo y de las configs.")

# Lo que no tiene caso guardar: se vuelve a bajar o a generar solo.
# `pagos-datos` dentro de data/ es solo el punto de montaje del contenedor;
# la base real vive en la raíz del proyecto y se agrega aparte.
EXCLUIR = ("cache", "logs", "libraries", "versions", "pagos-datos")

CARPETA_PAGOS = "pagos-datos"
BASE_PAGOS = "pagos.sqlite"
# La foto que el bot saca cada hora con la API de respaldo de SQLite.
COPIA_PAGOS = "pagos.copia.sqlite"

ARCHIVO_INFO = "BACKUP_INFO.json"
ARCHIVO_ESTADO = "estado.json"
ARCHIVO_BLOQUEO = ".bloqueo"
SUFIJO_SHA256 = ".sha256"
SUFIJO_JSON = ".json"


def _zona(ctx: Contexto) -> ZoneInfo:
    return ZoneInfo(ctx.settings.pagos.zona_horaria)


def _ahora(ctx: Contexto) -> datetime:
    return datetime.now(_zona(ctx))


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


def _sha256(ruta: Path) -> str:
    """Hash de un archivo, leído por bloques para no cargarlo en memoria."""
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def _escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe JSON de forma atómica: nadie ve un archivo a medias."""
    temporal = ruta.with_name(f".{ruta.name}.tmp")
    try:
        temporal.write_text(
            json.dumps(datos, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporal.replace(ruta)
    finally:
        temporal.unlink(missing_ok=True)


def _leer_json(ruta: Path) -> dict[str, Any] | None:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) else None


def _ruta_estado(ctx: Contexto) -> Path:
    return ctx.carpeta_respaldos / ARCHIVO_ESTADO


def _registrar_exito(
    ctx: Contexto,
    destino: Path,
    *,
    marca: str,
    duracion: float,
    bases: list[str],
    servidor_vivo: bool,
    sha256: str,
) -> None:
    estado = _leer_json(_ruta_estado(ctx)) or {}
    estado["ultimo"] = {
        "archivo": destino.name,
        "id": marca,
        "momento": _ahora(ctx).isoformat(),
        "bytes": destino.stat().st_size,
        "sha256": sha256,
        "duracion_segundos": round(duracion, 2),
        "bases_sqlite": bases,
        "servidor_vivo": servidor_vivo,
    }
    estado["ultimo_error"] = None
    _escribir_json(_ruta_estado(ctx), estado)


def _registrar_error(ctx: Contexto, mensaje: str) -> None:
    estado = _leer_json(_ruta_estado(ctx)) or {}
    estado["ultimo_error"] = {"momento": _ahora(ctx).isoformat(), "mensaje": mensaje}
    _escribir_json(_ruta_estado(ctx), estado)


@contextmanager
def _bloqueo(carpeta: Path) -> Iterator[None]:
    """Impide que dos respaldos se ejecuten a la vez sobre la misma carpeta."""
    carpeta.mkdir(parents=True, exist_ok=True)
    with (carpeta / ARCHIVO_BLOQUEO).open("a+", encoding="utf-8") as archivo:
        try:
            fcntl.flock(archivo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ErrorDeRespaldo(
                "ya hay otro respaldo en curso",
                pista="Espera a que termine o revisa `mc backup status`.",
            ) from exc
        try:
            yield
        finally:
            fcntl.flock(archivo, fcntl.LOCK_UN)


def _bases_para_foto(ctx: Contexto) -> list[tuple[Path, Path]]:
    """Pares (ruta dentro del tar, archivo real) que hay que fotografiar.

    Incluye las bases SQLite que encuentre en data/ y las dos del bot de
    pagos. Las que no son SQLite se copian como archivo normal.
    """
    pares: list[tuple[Path, Path]] = [
        (rel, ctx.carpeta_datos / rel) for rel in sqlite.bases_en(ctx.carpeta_datos)
    ]
    for nombre in (BASE_PAGOS, COPIA_PAGOS):
        ruta = ctx.raiz / CARPETA_PAGOS / nombre
        if ruta.is_file():
            pares.append((Path(CARPETA_PAGOS) / nombre, ruta))
    return pares


def _info_respaldo(
    ctx: Contexto,
    *,
    marca: str,
    etiqueta: str,
    creado: datetime,
    servidor_vivo: bool,
    archivos: int,
    bases: list[str],
) -> dict[str, Any]:
    return {
        "formato": 1,
        "id": marca,
        "etiqueta": etiqueta,
        "creado": creado.isoformat(),
        "zona": str(_zona(ctx)),
        "minecraft": ctx.settings.versiones.minecraft,
        "servidor_vivo": servidor_vivo,
        "archivos": archivos,
        "bases_sqlite": bases,
        "herramienta": "mc backup",
    }


def _sin_basura(info: tarfile.TarInfo, excluidas: set[str]) -> tarfile.TarInfo | None:
    """Filtro de tar: deja fuera lo que no sirve restaurar."""
    nombre = info.name.removeprefix("./")
    if nombre in excluidas or nombre.endswith(sqlite.SUFIJOS_WAL):
        return None
    partes = Path(nombre).parts
    if any(p in ("cache", "logs", "libraries", "versions") for p in partes):
        return None
    if nombre.endswith(".jar"):
        return None
    return info


def crear_respaldo(ctx: Contexto, etiqueta: str = "world") -> Path:
    """Hace un respaldo en caliente, sin apagar el servidor.

    Le dice al servidor que deje de escribir al disco (`save-off`), lo obliga
    a guardar lo que trae en memoria (`save-all flush`), copia, y luego lo
    deja seguir (`save-on`). Las bases SQLite se copian con la API de respaldo
    para que no importe que el servidor siga escribiendo.
    """
    ctx.carpeta_respaldos.mkdir(parents=True, exist_ok=True)
    creado = _ahora(ctx)
    marca = creado.strftime(core.FORMATO_MARCA)
    destino = ctx.carpeta_respaldos / f"{etiqueta}-{marca}.tgz"
    if destino.exists():
        raise ErrorDeRespaldo(
            f"ya existe un respaldo con la marca {marca}",
            pista="Espera un segundo y vuelve a intentarlo.",
        )

    with _bloqueo(ctx.carpeta_respaldos):
        return _crear_respaldo_bloqueado(ctx, etiqueta=etiqueta, marca=marca, creado=creado)


def _crear_respaldo_bloqueado(
    ctx: Contexto, *, etiqueta: str, marca: str, creado: datetime
) -> Path:
    destino = ctx.carpeta_respaldos / f"{etiqueta}-{marca}.tgz"
    parcial = ctx.carpeta_respaldos / f".{destino.name}.parcial"
    parcial.unlink(missing_ok=True)
    inicio = time.monotonic()
    servidor_vivo = rcon.esta_vivo(ctx.conexion_rcon)
    bases = _bases_para_foto(ctx)
    bases_tar = [str(rel) for rel, _ in bases]
    excluidas = {str(rel) for rel, _ in bases}
    archivos = 0

    if servidor_vivo:
        rcon.mandar_varios(
            ctx.conexion_rcon, ["save-off", "save-all flush"], timeout=rcon.TIMEOUT_LARGO
        )
    try:
        with tarfile.open(parcial, "w:gz") as tar:
            for elemento in sorted(ctx.carpeta_datos.iterdir()):
                rel = elemento.name
                if rel in EXCLUIR or rel.endswith(".jar"):
                    continue
                tar.add(
                    elemento,
                    arcname=rel,
                    filter=lambda info: _sin_basura(info, excluidas),
                )

            # Las bases vivas no se copian tal cual: se pide a SQLite una foto
            # consistente y esa foto es la que entra al tar.
            with tempfile.TemporaryDirectory(prefix="mc-backup-") as temporal:
                for ruta_rel, origen in bases:
                    copia = Path(temporal) / ruta_rel
                    sqlite.copia_consistente(origen, copia)
                    tar.add(copia, arcname=str(ruta_rel))

            tar.add(ctx.raiz / "settings.yml", arcname="settings.yml")

            archivos = sum(1 for m in tar.getmembers() if m.isfile())
            info = _info_respaldo(
                ctx,
                marca=marca,
                etiqueta=etiqueta,
                creado=creado,
                servidor_vivo=servidor_vivo,
                archivos=archivos,
                bases=bases_tar,
            )
            datos = json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
            miembro = tarfile.TarInfo(ARCHIVO_INFO)
            miembro.size = len(datos)
            miembro.mtime = int(creado.timestamp())
            tar.addfile(miembro, io.BytesIO(datos))

        parcial.replace(destino)
    except (OSError, sqlite3.Error, tarfile.TarError) as exc:
        parcial.unlink(missing_ok=True)
        _registrar_error(ctx, f"no se pudo escribir el respaldo: {exc}")
        raise ErrorDeRespaldo(f"no pude escribir el respaldo: {exc}") from exc
    except Exception as exc:
        parcial.unlink(missing_ok=True)
        _registrar_error(ctx, f"error inesperado al respaldar: {exc}")
        raise
    finally:
        if servidor_vivo:
            try:
                rcon.mandar(ctx.conexion_rcon, "save-on")
            except ErrorDeRcon:  # pragma: no cover
                consola.mal(
                    "No pude volver a activar el guardado automático. "
                    "Entra con `mc console` y escribe `save-on`."
                )

    sha256 = _sha256(destino)
    info = _info_respaldo(
        ctx,
        marca=marca,
        etiqueta=etiqueta,
        creado=creado,
        servidor_vivo=servidor_vivo,
        archivos=archivos,
        bases=bases_tar,
    )
    info["sha256"] = sha256
    info["bytes"] = destino.stat().st_size
    _escribir_json(destino.with_name(destino.name + SUFIJO_JSON), info)
    destino.with_name(destino.name + SUFIJO_SHA256).write_text(
        f"{sha256}  {destino.name}\n", encoding="utf-8"
    )
    _registrar_exito(
        ctx,
        destino,
        marca=marca,
        duracion=time.monotonic() - inicio,
        bases=bases_tar,
        servidor_vivo=servidor_vivo,
        sha256=sha256,
    )
    return destino


def _restaurar_base_de_pagos(ctx: Contexto, tar: tarfile.TarFile) -> None:
    """Saca del respaldo la base del bot de pagos y la deja sana.

    Los respaldos viejos copiaban la base viva con su `-wal` y su `-shm`.
    Aquí se extraen a un temporal y se consolidan con la API de SQLite: al
    destino llega un solo archivo, sin acompañantes viejos que se le apliquen
    encima. Si la base principal no abre, se usa la foto horaria del bot.
    """
    miembros = [m for m in tar.getmembers() if _nombre(m).startswith(CARPETA_PAGOS + "/")]
    if not miembros:
        return

    carpeta = ctx.raiz / CARPETA_PAGOS
    carpeta.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mc-pagos-") as temporal:
        tar.extractall(temporal, members=miembros, filter="data")
        origen = Path(temporal) / CARPETA_PAGOS
        base = carpeta / BASE_PAGOS

        for nombre, mensaje in (
            (BASE_PAGOS, "restauré también la base de datos del bot de pagos"),
            (
                COPIA_PAGOS,
                "la base del bot de pagos del respaldo venía dañada; usé la foto "
                "que el bot saca cada hora (puede faltarle lo de la última hora)",
            ),
        ):
            candidato = origen / nombre
            if not candidato.is_file() or not sqlite.esta_sana(candidato):
                continue
            sqlite.borrar_con_wal(base)
            sqlite.copia_consistente(candidato, base)
            consola.info(f"  {mensaje}")
            return

        consola.mal(
            "la base del bot de pagos del respaldo no abre. Prueba con otro respaldo: "
            "mc backup restore <id>"
        )


def _nombre(miembro: tarfile.TarInfo) -> str:
    """El nombre sin el `./` que le ponen los respaldos de itzg/mc-backup."""
    return miembro.name.removeprefix("./")


def _consolidar_bases_extraidas(ctx: Contexto, tar: tarfile.TarFile) -> None:
    """Deja las bases restauradas sin WAL viejo.

    En respaldos viejos la base y su `-wal` vienen del mismo instante, pero
    quedan como dos archivos. Al consolidarlos se garantiza que el servidor
    arranque leyendo una sola foto coherente.
    """
    nombres = {
        _nombre(m)
        for m in tar.getmembers()
        if m.isfile()
        and _nombre(m).endswith((".db", ".sqlite", ".sqlite3"))
        and not _nombre(m).endswith((".mv.db", ".h2.db"))
    }
    for nombre in sorted(nombres):
        ruta = ctx.carpeta_datos / nombre
        if not ruta.is_file() or not sqlite.es_sqlite(ruta):
            continue
        try:
            sqlite.consolidar_en_sitio(ruta)
        except sqlite3.Error as exc:
            consola.aviso(f"la base {nombre} del respaldo no se pudo consolidar: {exc}")


def _problemas_de(ruta: Path) -> list[str]:
    """Revisa un archivo de respaldo sin tocar el servidor."""
    problemas: list[str] = []
    sidecar = ruta.with_name(ruta.name + SUFIJO_SHA256)
    # Los respaldos anteriores a este motor no tienen sidecar. Se verifican
    # igual por dentro; solo se compara el hash cuando existe el archivo.
    if sidecar.is_file():
        try:
            esperado = sidecar.read_text(encoding="utf-8").split()[0]
        except (OSError, IndexError):
            esperado = ""
        if not esperado or _sha256(ruta) != esperado:
            problemas.append("el sha256 no coincide")

    # Los respaldos del motor anterior no traen BACKUP_INFO.json ni sidecar.
    # Se verifican igual por dentro; solo exigimos la ficha a los nuevos,
    # que son los que tienen su .json al lado.
    tiene_ficha = sidecar.with_name(ruta.name + SUFIJO_JSON).is_file()

    try:
        with tarfile.open(ruta) as tar:
            nombres = {_nombre(m) for m in tar.getmembers()}
            if "world/level.dat" not in nombres:
                problemas.append("falta world/level.dat")
            if tiene_ficha and ARCHIVO_INFO not in nombres:
                problemas.append("falta BACKUP_INFO.json")

            bases = sorted(
                n
                for n in nombres
                if n.endswith((".db", ".sqlite", ".sqlite3"))
                and not n.endswith((".mv.db", ".h2.db"))
            )
            if bases:
                with tempfile.TemporaryDirectory(prefix="mc-verifica-") as temporal:
                    queridos = {n for base in bases for n in (base, base + "-wal", base + "-shm")}
                    miembros = [m for m in tar.getmembers() if _nombre(m) in queridos]
                    tar.extractall(temporal, members=miembros, filter="data")
                    for base in bases:
                        ruta_base = Path(temporal) / base
                        # La extensión no basta: GravesX deja un .trace.db que
                        # es un log de H2 en texto. Solo se revisa lo que trae
                        # la cabecera de SQLite.
                        if not sqlite.es_sqlite(ruta_base):
                            continue
                        if not sqlite.esta_sana(ruta_base):
                            problemas.append(f"la base {base} no pasa integrity_check")
    except (OSError, tarfile.TarError) as exc:
        problemas.append(f"no se pudo abrir el tar: {exc}")
    return problemas


def _segundos_intervalo(texto: str) -> int:
    """Convierte `6h`, `30m` o `1d` a segundos."""
    unidades = {"m": 60, "h": 3600, "d": 86400}
    return int(texto[:-1]) * unidades[texto[-1]]


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


@app.command("verify")
def backup_verify(
    identificador: str | None = typer.Argument(
        None, help="Un id concreto; si se omite, revisa todos."
    ),
) -> None:
    """Revisa checksum, contenido y bases SQLite de los respaldos."""
    try:
        ctx = Contexto.cargar()
        if identificador:
            elegidos = [core.buscar(_leer_respaldos(ctx), identificador)]
        else:
            elegidos = core.ordenar_recientes_primero(_leer_respaldos(ctx))
        if not elegidos:
            consola.aviso("todavía no hay ningún respaldo.")
            return

        fallos = 0
        for r in elegidos:
            archivo = ctx.carpeta_respaldos / r.archivo
            problemas = _problemas_de(archivo)
            if problemas:
                fallos += 1
                consola.mal(f"{r.archivo}: {'; '.join(problemas)}")
            else:
                consola.ok(f"{r.archivo}: correcto")
        if fallos:
            raise ErrorDeRespaldo(
                f"{fallos} de {len(elegidos)} respaldo(s) tienen problemas",
                pista="No borres esos archivos hasta revisar el error con calma.",
            )
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@app.command("prune")
def backup_prune(
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Solo enseña qué borraría."),
) -> None:
    """Borra los respaldos más viejos que la ventana de retención."""
    try:
        ctx = Contexto.cargar()
        sobran = core.cuales_sobran(
            _leer_respaldos(ctx),
            ctx.settings.respaldos.conservar_dias,
            _ahora(ctx),
        )
        if not sobran:
            consola.ok("no hay respaldos fuera de la ventana de retención.")
            return
        for r in sobran:
            archivo = ctx.carpeta_respaldos / r.archivo
            acompanantes = [
                archivo.with_name(archivo.name + SUFIJO_SHA256),
                archivo.with_name(archivo.name + SUFIJO_JSON),
            ]
            if dry_run:
                consola.info(f"borraría {r.archivo} ({r.tamano_legible})")
                continue
            archivo.unlink(missing_ok=True)
            for acompanante in acompanantes:
                acompanante.unlink(missing_ok=True)
            consola.ok(f"borrado {r.archivo}")
        if dry_run:
            consola.tenue("\n  --dry-run: no se borró nada.")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@app.command("status")
def backup_status() -> None:
    """Enseña el último respaldo, su edad y los errores recientes."""
    try:
        ctx = Contexto.cargar()
        encontrados = core.ordenar_recientes_primero(_leer_respaldos(ctx))
        estado = _leer_json(_ruta_estado(ctx)) or {}
        ahora = _ahora(ctx)
        t = consola.tabla("Respaldos", ["Dato", "Valor"])
        t.add_row("Carpeta", str(ctx.carpeta_respaldos))
        t.add_row("Respaldos", str(len(encontrados)))
        t.add_row("Retención", f"{ctx.settings.respaldos.conservar_dias} días")
        t.add_row("Intervalo", ctx.settings.respaldos.intervalo)
        if encontrados:
            ultimo = encontrados[0]
            edad = ahora - ultimo.momento
            horas = edad.total_seconds() / 3600
            t.add_row("Último", f"{ultimo.archivo} ({horas:.1f} h)")
            t.add_row("Tamaño", ultimo.tamano_legible)
        else:
            t.add_row("Último", "ninguno")
        libre = shutil.disk_usage(ctx.raiz).free / 1024**3
        t.add_row("Disco libre", f"{libre:.1f} GB")
        consola.consola.print(t)

        if encontrados:
            proximo = encontrados[0].momento.timestamp() + _segundos_intervalo(
                ctx.settings.respaldos.intervalo
            )
            restante = (proximo - ahora.timestamp()) / 3600
            if restante > 0:
                consola.tenue(f"\n  Próximo respaldo en unas {restante:.1f} h.")
            else:
                consola.aviso("Ya toca un respaldo: el último tiene más de lo configurado.")

        error = estado.get("ultimo_error")
        if isinstance(error, dict):
            consola.mal(f"Último error: {error.get('momento', '?')} — {error.get('mensaje', '')}")
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
        consola.info(f"Del     : {elegido.fecha_bonita(_zona(ctx))}")
        consola.info(f"Tamaño  : {elegido.tamano_legible}")
        consola.aviso("Esto reemplaza el mundo y las configs actuales.")

        if dry_run:
            with tarfile.open(archivo) as tar:
                nombres = tar.getnames()
            consola.info(f"\nTrae [dato]{len(nombres)}[/dato] archivos. Los primeros:")
            for n in nombres[:12]:
                consola.tenue(f"  {n}")
            consola.tenue("\n  --dry-run: no se tocó nada.")
            return

        if not consola.confirmar_doble("\n¿Restaurar y sobrescribir lo actual?", "RESTAURAR"):
            raise OperacionCancelada()

        consola.paso("Primero, un respaldo de lo que hay ahora...")
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
            # Por eso no se hace un extractall pelón.
            #
            # filter="data" evita que una ruta con ".." escriba fuera del destino.
            # Los respaldos de itzg/mc-backup nombran todo con "./" adelante.
            del_servidor = [
                m
                for m in tar.getmembers()
                if not _nombre(m).startswith(("settings.yml", CARPETA_PAGOS))
            ]
            tar.extractall(destino, members=del_servidor, filter="data")
            _consolidar_bases_extraidas(ctx, tar)
            _restaurar_base_de_pagos(ctx, tar)

        # settings.yml del respaldo no se restaura solo: pisar sin avisar una
        # configuración que cambió después sería un error.
        consola.tenue("  (settings.yml no se tocó; está dentro del respaldo si lo necesitas)")

        consola.ok("restaurado")
        consola.tenue(
            f"\n  Si algo salió mal, el respaldo de antes está en:\n"
            f"  {previo.relative_to(ctx.raiz)}\n\n"
            "  Arranca con: mc start"
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)
