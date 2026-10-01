"""Modelo de `minecraft/manifest.yml`: qué se descarga y con qué sha256.

Lógica pura: valida y describe. No baja nada (eso es `infra.descargas`) ni
toca el disco (eso es `infra.archivos`).
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
)

from mc_admin.errores import ErrorDeConfig

_RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _normalizar_sha256(valor: str) -> str:
    """Valida un sha256 y lo pasa a minúsculas."""
    if not _RE_SHA256.match(valor.lower()):
        msg = f"'{valor}' no es un sha256: deben ser 64 caracteres hexadecimales"
        raise ValueError(msg)
    return valor.lower()


# Tipo reutilizable: cualquier campo sha256 del manifest usa esto.
Sha256 = Annotated[str, AfterValidator(_normalizar_sha256)]


class Destino(StrEnum):
    """Dónde vive cada cosa dentro de la carpeta de datos del servidor."""

    PLUGINS = "plugins"
    DATAPACKS = "datapacks"


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Artefacto(_Base):
    """Un jar o un zip que hay que bajar y verificar."""

    nombre: str = Field(min_length=1)
    version: str = Field(min_length=1)
    archivo: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")
    sha256: Sha256
    nota: str = ""

    @field_validator("archivo")
    @classmethod
    def _sin_rutas(cls, v: str) -> str:
        """Un `archivo` con / o .. podría escribir fuera de su carpeta."""
        if "/" in v or "\\" in v or ".." in v:
            msg = f"el nombre de archivo '{v}' no puede traer rutas ni '..'"
            raise ValueError(msg)
        return v


class PackVanillaTweaks(_Base):
    """Un datapack individual dentro del ZIP que arma vanillatweaks.net."""

    archivo: str = Field(min_length=1)
    sha256: Sha256
    nota: str = ""


class VanillaTweaks(_Base):
    """Vanilla Tweaks no da URLs fijas; hay que pedirle el ZIP por POST.

    El ZIP que devuelve sí es reproducible byte a byte para la misma selección,
    así que podemos fijar su sha256 igual que cualquier otro artefacto.
    """

    version_mc: str = Field(pattern=r"^\d+(\.\d+){0,2}$")
    url: str = Field(pattern=r"^https://")
    seleccion: dict[str, list[str]]
    sha256_zip: Sha256
    packs: list[PackVanillaTweaks] = Field(min_length=1)

    @field_validator("seleccion")
    @classmethod
    def _seleccion_no_vacia(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        if not v or not any(v.values()):
            msg = "vanilla_tweaks.seleccion está vacía: no hay nada que bajar"
            raise ValueError(msg)
        return v

    @property
    def total_packs_seleccionados(self) -> int:
        return sum(len(p) for p in self.seleccion.values())

    def coherente(self) -> list[str]:
        """Revisa que `packs` y `seleccion` hablen del mismo número de packs."""
        problemas: list[str] = []
        if self.total_packs_seleccionados != len(self.packs):
            problemas.append(
                f"vanilla_tweaks.seleccion pide {self.total_packs_seleccionados} packs "
                f"pero vanilla_tweaks.packs lista {len(self.packs)} sha256"
            )
        return problemas


class Manifest(_Base):
    """manifest.yml completo."""

    compatible_con: str = Field(pattern=r"^\d+(\.\d+){0,2}$")
    plugins: dict[str, Artefacto] = Field(min_length=1)
    datapacks: dict[str, Artefacto] = Field(default_factory=dict)
    vanilla_tweaks: VanillaTweaks | None = None

    @property
    def artefactos(self) -> list[tuple[Destino, Artefacto]]:
        """Todos los artefactos con URL fija, con su carpeta destino."""
        return [
            *((Destino.PLUGINS, a) for a in self.plugins.values()),
            *((Destino.DATAPACKS, a) for a in self.datapacks.values()),
        ]

    def validar_contra(self, version_minecraft: str) -> list[str]:
        """Avisa si el manifest se verificó contra otra versión de Minecraft."""
        problemas: list[str] = []
        if self.compatible_con != version_minecraft:
            problemas.append(
                f"manifest.yml se verificó contra Minecraft {self.compatible_con} pero "
                f"settings.yml pide {version_minecraft}. Corre `mc update` para "
                "revisar las versiones de los plugins antes de arrancar"
            )
        if self.vanilla_tweaks is not None:
            problemas.extend(self.vanilla_tweaks.coherente())
        return problemas

    def archivos_repetidos(self) -> list[str]:
        """Dos artefactos con el mismo nombre de archivo se pisarían."""
        vistos: dict[tuple[Destino, str], list[str]] = {}
        for destino, a in self.artefactos:
            vistos.setdefault((destino, a.archivo), []).append(a.nombre)
        return [
            f"{len(nombres)} artefactos escriben el mismo archivo {destino}/{archivo}: "
            f"{', '.join(nombres)}"
            for (destino, archivo), nombres in vistos.items()
            if len(nombres) > 1
        ]

    @classmethod
    def desde_archivo(cls, ruta: Path) -> Self:
        """Lee y valida manifest.yml."""
        if not ruta.is_file():
            raise ErrorDeConfig(
                f"no encontré el manifest en {ruta}",
                pista="Debe existir minecraft/manifest.yml con los plugins y datapacks.",
            )
        try:
            crudo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ErrorDeConfig(f"manifest.yml no es YAML válido: {exc}") from exc
        if not isinstance(crudo, dict):
            raise ErrorDeConfig("manifest.yml está vacío o no es un mapa de claves")
        try:
            manifest = cls.model_validate(crudo)
        except ValidationError as exc:
            lineas = [
                "  • "
                + ".".join(str(p) for p in e["loc"])
                + ": "
                + e["msg"].removeprefix("Value error, ")
                for e in exc.errors()
            ]
            raise ErrorDeConfig("manifest.yml tiene errores:\n" + "\n".join(lineas)) from exc

        if repetidos := manifest.archivos_repetidos():
            raise ErrorDeConfig(
                "manifest.yml tiene choques de archivos:\n  • " + "\n  • ".join(repetidos)
            )
        return manifest
