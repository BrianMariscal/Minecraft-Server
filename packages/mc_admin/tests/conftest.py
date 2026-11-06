"""Piezas compartidas por los tests de la CLI."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from mc_admin.infra.archivos import actualizar_settings

# La raíz del proyecto real: de ahí copiamos settings.example.yml y las
# plantillas, para que los tests prueben los archivos REALES y no una
# maqueta que se desincroniza.
RAIZ_REAL = Path(__file__).resolve().parents[3]


@pytest.fixture
def proyecto(tmp_path: Path) -> Iterator[Path]:
    """Una copia del proyecto en un directorio temporal.

    Copiamos lo que se versiona (settings.example.yml, manifest.yml,
    templates y traducciones) para que un cambio en esos archivos haga
    fallar los tests si rompe algo.
    """
    destino = tmp_path / "proyecto"
    destino.mkdir()
    shutil.copy(RAIZ_REAL / "settings.example.yml", destino / "settings.yml")
    shutil.copy(RAIZ_REAL / ".env.example", destino / ".env.example")
    shutil.copytree(RAIZ_REAL / "minecraft", destino / "minecraft", dirs_exist_ok=True)
    # El ejemplo trae datos ficticios; los tests parten sin nadie.
    actualizar_settings(
        destino,
        {
            "admins": [],
            "admins_bedrock": [],
            "whitelist.java": [],
            "whitelist.bedrock": [],
            "whitelist.xuid": {},
        },
    )
    yield destino


@pytest.fixture
def env_lleno(proyecto: Path) -> Path:
    """Un .env con todo lleno, para probar el camino felíz."""
    (proyecto / ".env").write_text(
        "RCON_PASSWORD=contrasenaDePrueba\n"
        "PAGOS_BOT_TOKEN=otroTokenDePrueba\n"
        "PAGOS_GUILD_ID=222\n"
        "PAGOS_CANAL_ID=333\n",
        encoding="utf-8",
    )
    return proyecto
