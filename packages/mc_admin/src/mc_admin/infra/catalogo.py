"""Pregunta a Modrinth, GitHub y GeyserMC qué versiones nuevas hay.

Lo usa `mc update`. Cada fuente sabe cómo leer su propia API; el que decide
si conviene actualizar es `core.versiones`, que no sabe de HTTP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from mc_admin.core.versiones import Comparacion, comparar
from mc_admin.infra.descargas import TIMEOUT, USER_AGENT
from mc_admin.infra.registro import obtener

log = obtener("catalogo")

MODRINTH = "https://api.modrinth.com/v2"
GEYSER = "https://download.geysermc.org/v2"
GITHUB = "https://api.github.com"

# De qué URL sale cada artefacto, para saber a quién preguntarle.
_RE_MODRINTH = re.compile(r"cdn\.modrinth\.com/data/([A-Za-z0-9]+)/versions/")
_RE_GEYSER = re.compile(r"download\.geysermc\.org/v2/projects/([a-z]+)/")
_RE_GITHUB = re.compile(r"github\.com/([^/]+)/([^/]+)/releases/download/")


@dataclass(frozen=True, slots=True)
class VersionDisponible:
    """Lo que encontramos allá arriba."""

    version: str
    canal: str
    soporta: tuple[str, ...]


def _modrinth_por_id(cliente: httpx.Client, project_id: str, mc: str) -> VersionDisponible | None:
    """La versión más nueva de un proyecto de Modrinth que soporte `mc`."""
    try:
        r = cliente.get(f"{MODRINTH}/project/{project_id}/version")
        r.raise_for_status()
        versiones: list[dict[str, Any]] = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("no pude preguntarle a Modrinth por %s: %s", project_id, exc)
        return None

    candidatas = [v for v in versiones if mc in v.get("game_versions", [])]
    if not candidatas:
        return None
    # Modrinth las devuelve de la más nueva a la más vieja.
    mejor = max(candidatas, key=lambda v: str(v.get("date_published", "")))
    return VersionDisponible(
        version=str(mejor["version_number"]),
        canal=str(mejor.get("version_type", "release")),
        soporta=tuple(mejor.get("game_versions", [])),
    )


def _geyser(cliente: httpx.Client, proyecto: str) -> VersionDisponible | None:
    """El último build de un proyecto de GeyserMC."""
    try:
        r = cliente.get(f"{GEYSER}/projects/{proyecto}")
        r.raise_for_status()
        ultima = r.json()["versions"][-1]
        r2 = cliente.get(f"{GEYSER}/projects/{proyecto}/versions/{ultima}")
        r2.raise_for_status()
        build = r2.json()["builds"][-1]
    except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
        log.warning("no pude preguntarle a GeyserMC por %s: %s", proyecto, exc)
        return None
    return VersionDisponible(version=f"{ultima}-b{build}", canal="release", soporta=())


def _github(cliente: httpx.Client, duenio: str, repo: str) -> VersionDisponible | None:
    """El último release estable de un repo de GitHub."""
    try:
        r = cliente.get(f"{GITHUB}/repos/{duenio}/{repo}/releases?per_page=10")
        r.raise_for_status()
        releases: list[dict[str, Any]] = r.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("no pude preguntarle a GitHub por %s/%s: %s", duenio, repo, exc)
        return None
    estables = [x for x in releases if not x.get("prerelease")]
    if not estables:
        return None
    return VersionDisponible(
        version=str(estables[0]["tag_name"]).lstrip("v"), canal="release", soporta=()
    )


def buscar_novedades(
    nombre: str, version_actual: str, url: str, mc: str, cliente: httpx.Client
) -> Comparacion:
    """Compara la versión que tenemos contra la más nueva que haya.

    La fuente se deduce de la URL del manifest: así no hay que mantener una
    tabla aparte de "este plugin vive en tal lado".
    """
    disponible: VersionDisponible | None = None

    if m := _RE_MODRINTH.search(url):
        disponible = _modrinth_por_id(cliente, m.group(1), mc)
    elif m := _RE_GEYSER.search(url):
        disponible = _geyser(cliente, m.group(1))
    elif m := _RE_GITHUB.search(url):
        disponible = _github(cliente, m.group(1), m.group(2))
    else:
        # SpigotMC, vanillatweaks.net y demás: no tienen API para esto.
        return Comparacion(
            nombre,
            version_actual,
            None,
            comparar(version_actual, None),
            nota="esta fuente no tiene API de versiones; revísala a mano",
        )

    if disponible is None:
        return Comparacion(
            nombre,
            version_actual,
            None,
            comparar(version_actual, None),
            nota=f"no encontré ninguna versión que soporte Minecraft {mc}",
        )

    return Comparacion(
        nombre=nombre,
        actual=version_actual,
        disponible=disponible.version,
        cambio=comparar(version_actual, disponible.version),
        soporta_minecraft=disponible.soporta,
        canal=disponible.canal,
    )


def crear_cliente() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
