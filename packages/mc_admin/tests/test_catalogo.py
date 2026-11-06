"""Catálogo de versiones: la fuente correcta para cada tipo de artefacto."""

from __future__ import annotations

from typing import Any, cast

import httpx

from mc_admin.core.manifest import Destino
from mc_admin.core.versiones import Cambio, Comparacion
from mc_admin.infra import catalogo


class Respuesta:
    def __init__(self, datos: Any) -> None:
        self._datos = datos

    def raise_for_status(self) -> None:
        return

    def json(self) -> Any:
        return self._datos


class ClienteFalso:
    def __init__(self, respuestas: dict[str, Any]) -> None:
        self.respuestas = respuestas
        self.pedidas: list[str] = []

    def get(self, url: str) -> Respuesta:
        self.pedidas.append(url)
        return Respuesta(self.respuestas[url])


def _version(
    numero: str,
    loaders: list[str],
    fecha: str,
    *,
    mc: str = "26.1.2",
    canal: str = "release",
) -> dict[str, Any]:
    return {
        "version_number": numero,
        "loaders": loaders,
        "game_versions": [mc],
        "date_published": fecha,
        "version_type": canal,
    }


def _buscar(
    versiones: list[dict[str, Any]],
    *,
    destino: Destino = Destino.PLUGINS,
) -> tuple[Comparacion, ClienteFalso]:
    cliente = ClienteFalso({f"{catalogo.MODRINTH}/project/abc/version": versiones})
    resultado = catalogo.buscar_novedades(
        "Prueba",
        "1.0.0",
        "https://cdn.modrinth.com/data/abc/versions/xyz/Prueba.jar",
        "26.1.2",
        cast(httpx.Client, cliente),
        destino,
    )
    return resultado, cliente


class TestFiltroPorLoader:
    def test_un_plugin_no_sube_a_neoforge(self) -> None:
        resultado, _ = _buscar(
            [
                _version("9.0.0-neoforge", ["neoforge"], "2026-10-20"),
                _version("1.1.0-paper", ["paper"], "2026-10-10"),
            ]
        )
        assert resultado.disponible == "1.1.0-paper"

    def test_un_datapack_no_sube_a_loader_de_mod(self) -> None:
        resultado, _ = _buscar(
            [
                _version("9.0.0-forge", ["forge"], "2026-10-20"),
                _version("1.1.0-pack", ["datapack"], "2026-10-10"),
            ],
            destino=Destino.DATAPACKS,
        )
        assert resultado.disponible == "1.1.0-pack"

    def test_si_solo_hay_otro_loader_no_propone_nada(self) -> None:
        resultado, _ = _buscar([_version("9.0.0-neoforge", ["neoforge"], "2026-10-20")])
        assert resultado.disponible is None
        assert resultado.cambio is Cambio.DESCONOCIDO
        assert "no encontré" in resultado.nota

    def test_sin_loaders_declarados_se_acepta(self) -> None:
        resultado, _ = _buscar([_version("1.1.0", [], "2026-10-10")])
        assert resultado.disponible == "1.1.0"

    def test_los_loaders_de_plugin_compartidos_cuentan(self) -> None:
        resultado, _ = _buscar(
            [
                _version("9.0.0-forge", ["forge"], "2026-10-20"),
                _version("1.1.0-bukkit", ["bukkit"], "2026-10-10"),
            ]
        )
        assert resultado.disponible == "1.1.0-bukkit"

    def test_solo_mira_versiones_de_nuestro_minecraft(self) -> None:
        resultado, _ = _buscar(
            [
                _version("2.0.0", ["paper"], "2026-10-20", mc="26.2"),
                _version("1.1.0", ["paper"], "2026-10-10"),
            ]
        )
        assert resultado.disponible == "1.1.0"
