"""Todo lo que toca el disco: escribir configs, copiar jars, editar settings.yml."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from mc_admin.core.plantillas import ArchivoGenerado
from mc_admin.errores import ErrorDeConfig, ErrorDeEntorno
from mc_admin.infra.registro import obtener

log = obtener("archivos")

# Rutas relativas a la raíz del proyecto.
CARPETA_GENERADOS = Path("minecraft/generated")
CARPETA_TEMPLATES = Path("minecraft/templates")
CARPETA_CACHE = Path(".cache/descargas")
CARPETA_DATOS = Path("data")
CARPETA_RESPALDOS = Path("backups")
CARPETA_PAGOS = Path("pagos-datos")
ARCHIVO_MANIFEST = Path("minecraft/manifest.yml")


@dataclass(frozen=True, slots=True)
class Escritura:
    """Qué pasó al escribir un archivo. Lo usa `mc build --dry-run`."""

    ruta: Path
    cambio: bool
    creado: bool


def escribir_si_cambio(ruta: Path, contenido: str, *, dry_run: bool = False) -> Escritura:
    """Escribe un archivo solo si su contenido es distinto.

    No reescribir lo que no cambió hace que `mc build` sea idempotente de
    verdad: no tocamos la fecha de archivos que están iguales, así que Docker
    no ve cambios donde no hay.
    """
    existia = ruta.is_file()
    if existia and ruta.read_text(encoding="utf-8") == contenido:
        return Escritura(ruta, cambio=False, creado=False)

    if not dry_run:
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            # Escribimos a un temporal en la misma carpeta y luego renombramos:
            # un corte de luz a media escritura no deja una config a medias.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=ruta.parent, delete=False, suffix=".tmp"
            ) as tmp:
                tmp.write(contenido)
                temporal = Path(tmp.name)
            temporal.replace(ruta)
        except PermissionError as exc:
            raise ErrorDeEntorno(
                f"no me dejan escribir en {ruta}",
                pista=(
                    "Casi siempre es que los archivos quedaron del usuario del "
                    "contenedor. Arréglalo con:\n"
                    "    sudo chown -R $USER:$USER data pagos-datos\n"
                    "y corre `mc build`, que pone tu UID y GID en .env."
                ),
            ) from exc
        except OSError as exc:
            raise ErrorDeEntorno(f"no pude escribir {ruta}: {exc}") from exc

    return Escritura(ruta, cambio=True, creado=not existia)


def escribir_generados(
    raiz: Path, generados: list[ArchivoGenerado], *, dry_run: bool = False
) -> list[Escritura]:
    """Vuelca las configs renderizadas a minecraft/generated/."""
    base = raiz / CARPETA_GENERADOS
    return [
        escribir_si_cambio(base / g.ruta_relativa, g.contenido, dry_run=dry_run) for g in generados
    ]


def copiar_si_cambio(origen: Path, destino: Path, *, dry_run: bool = False) -> Escritura:
    """Copia un archivo solo si el destino no existe o es distinto en tamaño.

    Para jars comparamos tamaño en lugar de hash: el hash del origen ya se
    verificó al descargar, y comparar 47 MB byte a byte en cada build no vale
    la pena.
    """
    existia = destino.is_file()
    if existia and destino.stat().st_size == origen.stat().st_size:
        return Escritura(destino, cambio=False, creado=False)
    if not dry_run:
        try:
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origen, destino)
        except PermissionError as exc:
            raise ErrorDeEntorno(
                f"no me dejan copiar a {destino}",
                pista=(
                    "Casi siempre es que los archivos quedaron del usuario del "
                    "contenedor. Arréglalo con:\n"
                    "    sudo chown -R $USER:$USER data"
                ),
            ) from exc
        except OSError as exc:
            raise ErrorDeEntorno(f"no pude copiar a {destino}: {exc}") from exc
    return Escritura(destino, cambio=True, creado=not existia)


def limpiar_jars_viejos(carpeta: Path, esperados: set[str], *, dry_run: bool = False) -> list[Path]:
    """Borra jars de la carpeta de plugins que ya no están en el manifest.

    Sin esto, bajarle de versión a un plugin dejaría los dos jars y el
    servidor cargaría quién sabe cuál.
    """
    if not carpeta.is_dir():
        return []
    sobrantes = [j for j in sorted(carpeta.glob("*.jar")) if j.name not in esperados]
    if not dry_run:
        for jar in sobrantes:
            log.info("quito el jar que ya no está en el manifest: %s", jar.name)
            jar.unlink()
    return sobrantes


def espacio_libre_gb(ruta: Path) -> float | None:
    """GB libres en el sistema de archivos donde vive `ruta`."""
    try:
        objetivo = ruta if ruta.exists() else ruta.parent
        return shutil.disk_usage(objetivo).free / (1024**3)
    except OSError:
        return None


def ram_total_gb() -> float | None:
    """RAM total de la máquina, leída de /proc/meminfo (Linux)."""
    meminfo = Path("/proc/meminfo")
    if not meminfo.is_file():
        return None
    try:
        for linea in meminfo.read_text(encoding="utf-8").splitlines():
            if linea.startswith("MemTotal:"):
                kb = int(linea.split()[1])
                return kb / (1024**2)
    except (OSError, ValueError, IndexError):
        return None
    return None


def actualizar_settings(raiz: Path, cambios: dict[str, list[str] | dict[str, int]]) -> None:
    """Reescribe claves de settings.yml conservando comentarios y formato.

    settings.yml está documentado a propósito, así que no podemos cargarlo y
    volcarlo con PyYAML (tira los comentarios). ruamel.yaml hace round-trip
    de verdad: lee, nos deja cambiar el valor y lo vuelve a escribir con sus
    comentarios y su indentación intactos.

    `cambios` usa rutas con punto: "admins", "whitelist.java".
    """
    ruta = raiz / "settings.yml"
    yaml_rt = YAML()
    yaml_rt.preserve_quotes = True
    # settings.yml indenta las listas dos espacios bajo su clave.
    yaml_rt.indent(mapping=2, sequence=4, offset=2)

    with ruta.open(encoding="utf-8") as f:
        doc = yaml_rt.load(f)

    for ruta_clave, valor in cambios.items():
        partes = ruta_clave.split(".")
        nodo = doc
        for parte in partes[:-1]:
            if parte not in nodo:
                msg = f"settings.yml no tiene la sección '{parte}'"
                raise ErrorDeConfig(msg)
            nodo = nodo[parte]
        hoja = partes[-1]
        if hoja not in nodo:
            msg = f"settings.yml no tiene la clave '{ruta_clave}'"
            raise ErrorDeConfig(msg)
        # Lista nueva ordenada sin distinguir mayúsculas, como la deja `core`.
        nodo[hoja] = CommentedMap(valor) if isinstance(valor, dict) else CommentedSeq(valor)

    flujo = io.StringIO()
    yaml_rt.dump(doc, flujo)
    texto = flujo.getvalue()

    # Red de seguridad: si la edición dejó el YAML inválido, no guardamos.
    try:
        yaml.safe_load(texto)
    except yaml.YAMLError as exc:  # pragma: no cover — sería un bug nuestro
        raise ErrorDeConfig(
            f"al editar settings.yml lo dejé inválido, no guardé nada: {exc}"
        ) from exc

    escribir_si_cambio(ruta, texto)


def escribir_whitelist(carpeta_datos: Path, entradas: list[dict[str, str]]) -> bool:
    """Escribe data/whitelist.json completo. True si cambió algo.

    El servidor lo vuelve a leer con `whitelist reload`. Lo escribimos
    nosotros, y no con `whitelist add`, porque así podemos poner el UUID
    correcto de cada quien (ver core.jugadores) y quien se borra de
    settings.yml se borra también de aquí.
    """
    contenido = json.dumps(entradas, indent=2, ensure_ascii=False) + "\n"
    return escribir_si_cambio(carpeta_datos / "whitelist.json", contenido).cambio


def asegurar_carpetas(raiz: Path) -> None:
    """Crea las carpetas de runtime si no existen. Idempotente."""
    for carpeta in (
        CARPETA_GENERADOS,
        CARPETA_CACHE,
        CARPETA_DATOS,
        CARPETA_RESPALDOS,
        CARPETA_PAGOS,
        # El contenedor de respaldos monta pagos-datos/ ENCIMA de esta carpeta
        # para que la base del bot entre a cada respaldo. Si no existiera,
        # Docker intentaría crearla dentro de un montaje de solo lectura y
        # el contenedor no arrancaría.
        CARPETA_DATOS / CARPETA_PAGOS,
    ):
        destino = raiz / carpeta
        try:
            destino.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ErrorDeEntorno(
                f"no pude crear la carpeta {destino}: {exc}",
                pista="Revisa los permisos de la carpeta del proyecto.",
            ) from exc


def _texto_base_del_env(raiz: Path) -> str:
    """Lo que hay en .env, o .env.example si todavía no existe."""
    ruta = raiz / ".env"
    if ruta.is_file():
        return ruta.read_text(encoding="utf-8")
    ejemplo = raiz / ".env.example"
    if not ejemplo.is_file():
        raise ErrorDeConfig(
            "no existe .env ni .env.example",
            pista="Recupera .env.example con git checkout .env.example",
        )
    return ejemplo.read_text(encoding="utf-8")


def _guardar_env(raiz: Path, texto: str) -> bool:
    """Escribe .env con permisos 600. Devuelve True si cambió algo."""
    ruta = raiz / ".env"
    escritura = escribir_si_cambio(ruta, texto)
    # .env trae secretos: que solo lo lea su dueño.
    os.chmod(ruta, 0o600)  # noqa: PTH101 — Path.chmod no acepta follow_symlinks aquí
    return escritura.cambio


def escribir_bloque_compose(raiz: Path, bloque: str) -> bool:
    """Pone en .env el bloque de variables que `mc build` saca de settings.yml.

    Devuelve True si el bloque cambió (y hace falta recrear contenedores).
    """
    from mc_admin.core.compose import reemplazar_bloque

    return _guardar_env(raiz, reemplazar_bloque(_texto_base_del_env(raiz), bloque))


def escribir_env(raiz: Path, valores: dict[str, str]) -> None:
    """Crea o actualiza .env conservando lo que ya estaba y los comentarios."""
    base = _texto_base_del_env(raiz)

    lineas = base.splitlines()
    pendientes = dict(valores)
    for i, linea in enumerate(lineas):
        if "=" not in linea or linea.lstrip().startswith("#"):
            continue
        clave = linea.split("=", 1)[0].strip()
        if clave in pendientes:
            lineas[i] = f"{clave}={pendientes.pop(clave)}"
    # Lo que no existía en el archivo lo agregamos al final.
    if pendientes:
        lineas.append("")
        lineas.extend(f"{k}={v}" for k, v in pendientes.items())

    _guardar_env(raiz, "\n".join(lineas) + "\n")
