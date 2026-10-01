"""El estado compartido que cargan todos los comandos de `mc`.

Lo arma una sola vez el callback de Typer y lo reciben los subcomandos, para
no releer settings.yml y .env en cada uno.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from mc_admin.config import Secretos, Settings, cargar_secretos, cargar_settings, encontrar_raiz
from mc_admin.core.manifest import Manifest
from mc_admin.infra import archivos
from mc_admin.infra.docker import Compose
from mc_admin.infra.rcon import Conexion


# Sin slots=True a propósito: `cached_property` necesita un __dict__ donde
# guardar lo que ya calculó, y slots se lo quita.
@dataclass
class Contexto:
    """Todo lo que un comando necesita saber del proyecto."""

    raiz: Path
    settings: Settings
    secretos: Secretos
    # `mc` corre fuera de Docker, así que alcanza RCON por el puerto publicado
    # en la máquina, no por el nombre del servicio.
    host_rcon: str = "127.0.0.1"

    @classmethod
    def cargar(cls, raiz: Path | None = None) -> Contexto:
        """Encuentra la raíz del proyecto y lee su configuración."""
        base = raiz or encontrar_raiz()
        return cls(
            raiz=base,
            settings=cargar_settings(base),
            secretos=cargar_secretos(base),
        )

    @cached_property
    def compose(self) -> Compose:
        return Compose(self.raiz)

    @cached_property
    def manifest(self) -> Manifest:
        return Manifest.desde_archivo(self.raiz / archivos.ARCHIVO_MANIFEST)

    @cached_property
    def conexion_rcon(self) -> Conexion:
        return Conexion(
            host=self.host_rcon,
            puerto=self.settings.puertos.rcon,
            password=self.secretos.rcon_password,
        )

    # -- rutas útiles ------------------------------------------------------ #

    @property
    def carpeta_datos(self) -> Path:
        return self.raiz / archivos.CARPETA_DATOS

    @property
    def carpeta_generados(self) -> Path:
        return self.raiz / archivos.CARPETA_GENERADOS

    @property
    def carpeta_templates(self) -> Path:
        return self.raiz / archivos.CARPETA_TEMPLATES

    @property
    def carpeta_traducciones(self) -> Path:
        return self.raiz / "minecraft/translations/es_mx"

    @property
    def carpeta_cache(self) -> Path:
        return self.raiz / archivos.CARPETA_CACHE

    @property
    def carpeta_respaldos(self) -> Path:
        return self.raiz / archivos.CARPETA_RESPALDOS

    @property
    def ruta_logo(self) -> Path:
        return self.raiz / self.settings.servidor.logo
