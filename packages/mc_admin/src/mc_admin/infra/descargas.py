"""Descarga y verificación de plugins y datapacks.

Nada se instala sin que su sha256 coincida. Si no coincide, el archivo se
borra y el build falla: preferimos un servidor que no arranca a un servidor
corriendo un jar que no sabemos de dónde salió.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from mc_admin.core.manifest import Artefacto, VanillaTweaks
from mc_admin.errores import ErrorDeDescarga
from mc_admin.infra.registro import obtener

log = obtener("descargas")

# Nos identificamos: es de buena educación con Modrinth y GeyserMC, y algunos
# ponen límites más estrictos al tráfico sin User-Agent.
USER_AGENT = "mc-admin/1.0 (servidor Minecraft HD)"
TIMEOUT = httpx.Timeout(30.0, read=300.0)
TROZO = 1 << 16


def sha256_de(ruta: Path) -> str:
    """sha256 de un archivo, leído por trozos para no cargarlo en memoria."""
    digest = hashlib.sha256()
    with ruta.open("rb") as f:
        while trozo := f.read(TROZO):
            digest.update(trozo)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class Descarga:
    """Un archivo que ya está en el caché y ya pasó la verificación."""

    artefacto: Artefacto
    ruta: Path
    desde_cache: bool


def _verificar(ruta: Path, esperado: str, nombre: str) -> None:
    """Compara el sha256 y borra el archivo si no cuadra."""
    real = sha256_de(ruta)
    if real != esperado:
        ruta.unlink(missing_ok=True)
        raise ErrorDeDescarga(
            f"el sha256 de {nombre} no coincide.\n  esperaba: {esperado}\n  obtuve:   {real}",
            pista=(
                "O cambiaron el archivo allá arriba, o la descarga se corrompió. "
                "Corre `mc update` para revisar si hay versión nueva; si no, "
                "vuelve a intentar `mc build`."
            ),
        )


def _descargar_a(cliente: httpx.Client, url: str, destino: Path, nombre: str) -> None:
    """Baja una URL a un archivo, escribiendo primero a un temporal.

    Así un Ctrl+C a medias no deja un archivo truncado en el caché que luego
    pase por bueno.
    """
    temporal = destino.with_suffix(destino.suffix + ".parcial")
    try:
        with cliente.stream("GET", url, follow_redirects=True) as respuesta:
            respuesta.raise_for_status()
            with temporal.open("wb") as f:
                for trozo in respuesta.iter_bytes(TROZO):
                    f.write(trozo)
    except httpx.HTTPStatusError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorDeDescarga(
            f"no pude bajar {nombre}: el servidor contestó {exc.response.status_code}",
            pista=f"Revisa que la URL siga viva:\n  {url}",
        ) from exc
    except httpx.HTTPError as exc:
        temporal.unlink(missing_ok=True)
        raise ErrorDeDescarga(
            f"no pude bajar {nombre}: {exc}",
            pista="Revisa tu conexión y vuelve a intentar.",
        ) from exc
    temporal.replace(destino)


def obtener_artefacto(
    artefacto: Artefacto, cache: Path, cliente: httpx.Client | None = None
) -> Descarga:
    """Deja un artefacto verificado en el caché y dice dónde quedó.

    Si ya estaba en el caché con el sha256 correcto, no lo vuelve a bajar: eso
    hace que `mc build` dos veces seguidas sea casi instantáneo.
    """
    cache.mkdir(parents=True, exist_ok=True)
    # Guardamos por sha256 para que dos versiones del mismo plugin convivan.
    destino = cache / f"{artefacto.sha256[:12]}-{artefacto.archivo}"

    if destino.is_file():
        if sha256_de(destino) == artefacto.sha256:
            log.debug("%s ya estaba en el caché", artefacto.nombre)
            return Descarga(artefacto, destino, desde_cache=True)
        log.warning("el caché de %s estaba corrupto, lo vuelvo a bajar", artefacto.nombre)
        destino.unlink()

    propio = cliente is None
    cliente = cliente or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    try:
        log.info("bajando %s %s", artefacto.nombre, artefacto.version)
        _descargar_a(cliente, artefacto.url, destino, artefacto.nombre)
    finally:
        if propio:
            cliente.close()

    _verificar(destino, artefacto.sha256, f"{artefacto.nombre} {artefacto.version}")
    return Descarga(artefacto, destino, desde_cache=False)


def obtener_vanilla_tweaks(
    vt: VanillaTweaks, cache: Path, cliente: httpx.Client | None = None
) -> list[tuple[str, Path]]:
    """Pide el ZIP a vanillatweaks.net y saca los datapacks verificados.

    vanillatweaks.net no da URLs fijas: hay que mandarle un POST con la lista
    de packs y te contesta con un link de id aleatorio. El ZIP contenedor no
    es estable byte a byte, así que no se verifica entero: se verifica cada
    datapack de adentro contra el sha256 del manifest. La clave del caché
    incluye versión, selección y esos hashes, para no reusar un ZIP viejo
    después de actualizar el manifest.

    Returns:
        Una lista de (nombre del datapack, ruta del zip ya verificado).
    """
    cache.mkdir(parents=True, exist_ok=True)
    clave = vt.clave_de_cache
    zip_cache = cache / f"vt-{clave}.zip"

    if not zip_cache.is_file():
        propio = cliente is None
        cliente = cliente or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        try:
            log.info("pidiéndole a vanillatweaks.net %d packs", len(vt.packs))
            try:
                respuesta = cliente.post(
                    vt.url,
                    data={
                        "packs": json.dumps(vt.seleccion, separators=(",", ":")),
                        "version": vt.version_mc,
                    },
                )
                respuesta.raise_for_status()
                datos = respuesta.json()
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                raise ErrorDeDescarga(
                    f"vanillatweaks.net no me contestó bien: {exc}",
                    pista="Puede estar caído. Intenta otra vez en un rato.",
                ) from exc

            if datos.get("status") != "success" or not datos.get("link"):
                raise ErrorDeDescarga(
                    f"vanillatweaks.net rechazó la selección de packs: {datos}",
                    pista=(
                        "Lo más probable es que cambiaron el nombre de un pack o "
                        "ya no existe para Minecraft " + vt.version_mc + ". "
                        "Revisa minecraft/manifest.yml."
                    ),
                )
            url_zip = f"https://vanillatweaks.net{datos['link']}"
            _descargar_a(cliente, url_zip, zip_cache, "el ZIP de Vanilla Tweaks")
        finally:
            if propio:
                cliente.close()

    return _extraer_packs(vt, zip_cache, cache, clave)


def _extraer_packs(
    vt: VanillaTweaks, zip_cache: Path, cache: Path, clave: str
) -> list[tuple[str, Path]]:
    """Saca cada datapack del ZIP contenedor y verifica su sha256."""
    salida = cache / f"vt-{clave}"
    salida.mkdir(parents=True, exist_ok=True)
    esperados = {p.archivo: p.sha256 for p in vt.packs}

    with tempfile.TemporaryDirectory() as tmp:
        try:
            with zipfile.ZipFile(zip_cache) as z:
                dentro = [n for n in z.namelist() if n.endswith(".zip")]
                z.extractall(tmp)
        except zipfile.BadZipFile as exc:
            zip_cache.unlink(missing_ok=True)
            raise ErrorDeDescarga(
                "el ZIP de Vanilla Tweaks llegó corrupto",
                pista="Vuelve a correr `mc build`.",
            ) from exc

        if faltan := sorted(set(esperados) - set(dentro)):
            raise ErrorDeDescarga(
                "el ZIP de Vanilla Tweaks no trae los packs que esperaba:\n  • "
                + "\n  • ".join(faltan),
                pista=(
                    "Casi seguro Vanilla Tweaks publicó una versión nueva de esos "
                    "packs. Corre `mc update` para refrescar manifest.yml."
                ),
            )

        resultado: list[tuple[str, Path]] = []
        for nombre, sha in esperados.items():
            origen = Path(tmp) / nombre
            _verificar(origen, sha, f"el datapack '{nombre}'")
            destino = salida / nombre
            shutil.copy2(origen, destino)
            resultado.append((nombre, destino))

    return resultado


def crear_cliente() -> httpx.Client:
    """Un cliente HTTP compartido, para no abrir una conexión por archivo."""
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
