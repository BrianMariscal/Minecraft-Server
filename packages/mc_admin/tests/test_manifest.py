"""El manifest: sha256 bien formados, rutas seguras y sin choques."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mc_admin.core.manifest import Destino, Manifest
from mc_admin.errores import ErrorDeConfig

SHA_VALIDO = "a" * 64


class TestManifestReal:
    """Contra el manifest.yml que de verdad se versiona."""

    @pytest.fixture
    def manifest(self, proyecto: Path) -> Manifest:
        return Manifest.desde_archivo(proyecto / "minecraft" / "manifest.yml")

    def test_carga(self, manifest: Manifest) -> None:
        assert manifest.compatible_con == "26.1.2"
        assert len(manifest.plugins) >= 18
        assert "discordsrv" not in manifest.plugins
        assert len(manifest.datapacks) == 5

    def test_todos_traen_sha256_de_64_hex(self, manifest: Manifest) -> None:
        for _, a in manifest.artefactos:
            assert len(a.sha256) == 64
            assert all(c in "0123456789abcdef" for c in a.sha256)

    def test_todas_las_urls_son_https(self, manifest: Manifest) -> None:
        for _, a in manifest.artefactos:
            assert a.url.startswith("https://")

    def test_ningun_archivo_se_pisa(self, manifest: Manifest) -> None:
        assert manifest.archivos_repetidos() == []

    def test_cuadra_con_la_version_del_proyecto(self, manifest: Manifest, proyecto: Path) -> None:
        settings = yaml.safe_load((proyecto / "settings.yml").read_text(encoding="utf-8"))
        assert manifest.validar_contra(settings["versiones"]["minecraft"]) == []

    def test_avisa_si_la_version_no_cuadra(self, manifest: Manifest) -> None:
        problemas = manifest.validar_contra("26.3")
        assert len(problemas) == 1
        assert "mc update" in problemas[0]

    def test_cada_artefacto_explica_para_que_es(self, manifest: Manifest) -> None:
        """Una nota vacía es un plugin que nadie se acuerda por qué está."""
        sin_nota = [a.nombre for _, a in manifest.artefactos if not a.nota.strip()]
        assert sin_nota == []

    def test_los_datapacks_van_dentro_del_mundo(self, manifest: Manifest) -> None:
        """Si no, Minecraft no los ve y genera un mundo vanilla."""
        for destino, a in manifest.artefactos:
            if destino is Destino.DATAPACKS:
                assert a.ruta_destino(destino).startswith("world/datapacks/")

    def test_el_addon_de_floodgate_va_en_su_carpeta(self, manifest: Manifest) -> None:
        sqlite = manifest.plugins["floodgate_sqlite"]
        assert sqlite.ruta_destino(Destino.PLUGINS) == (
            "plugins/floodgate/floodgate-sqlite-database.jar"
        )

    def test_vanilla_tweaks_cuadra(self, manifest: Manifest) -> None:
        vt = manifest.vanilla_tweaks
        assert vt is not None
        assert vt.coherente() == []
        assert vt.total_packs_seleccionados == len(vt.packs)

    def test_estan_las_piezas_que_el_arranque_real_demostro_necesarias(
        self, manifest: Manifest
    ) -> None:
        """Vault para el chat por grupo; PacketEvents para AuthMe."""
        nombres = {a.nombre for _, a in manifest.artefactos}
        assert "VaultUnlocked" in nombres
        assert "PacketEvents" in nombres


class TestValidacion:
    def escribir(self, tmp_path: Path, datos: dict) -> Path:
        ruta = tmp_path / "manifest.yml"
        ruta.write_text(yaml.safe_dump(datos), encoding="utf-8")
        return ruta

    def base(self, **cambios) -> dict:
        plugin = {
            "nombre": "Cosa",
            "version": "1.0",
            "archivo": "cosa.jar",
            "url": "https://ejemplo.com/cosa.jar",
            "sha256": SHA_VALIDO,
        }
        plugin.update(cambios)
        return {"compatible_con": "26.1.2", "plugins": {"cosa": plugin}}

    def test_sha256_corto(self, tmp_path: Path) -> None:
        ruta = self.escribir(tmp_path, self.base(sha256="abc"))
        with pytest.raises(ErrorDeConfig, match="64 caracteres hexadecimales"):
            Manifest.desde_archivo(ruta)

    def test_sha256_en_mayusculas_se_normaliza(self, tmp_path: Path) -> None:
        ruta = self.escribir(tmp_path, self.base(sha256="A" * 64))
        m = Manifest.desde_archivo(ruta)
        assert m.plugins["cosa"].sha256 == "a" * 64

    def test_url_http_se_rechaza(self, tmp_path: Path) -> None:
        ruta = self.escribir(tmp_path, self.base(url="http://ejemplo.com/x.jar"))
        with pytest.raises(ErrorDeConfig):
            Manifest.desde_archivo(ruta)

    @pytest.mark.parametrize("archivo", ["../fuera.jar", "sub/cosa.jar", "..\\x.jar"])
    def test_un_archivo_con_ruta_se_rechaza(self, tmp_path: Path, archivo: str) -> None:
        """Sin esto, un manifest podría escribir fuera de la carpeta de datos."""
        ruta = self.escribir(tmp_path, self.base(archivo=archivo))
        with pytest.raises(ErrorDeConfig, match="no puede traer rutas"):
            Manifest.desde_archivo(ruta)

    @pytest.mark.parametrize("sub", ["../fuera", "/absoluta", "a/../../b"])
    def test_una_subcarpeta_que_escapa_se_rechaza(self, tmp_path: Path, sub: str) -> None:
        ruta = self.escribir(tmp_path, self.base(subcarpeta=sub))
        with pytest.raises(ErrorDeConfig, match="relativa sin"):
            Manifest.desde_archivo(ruta)

    def test_dos_plugins_al_mismo_archivo_se_rechazan(self, tmp_path: Path) -> None:
        datos = self.base()
        datos["plugins"]["otra"] = dict(datos["plugins"]["cosa"], nombre="Otra")
        ruta = self.escribir(tmp_path, datos)
        with pytest.raises(ErrorDeConfig, match="mismo archivo"):
            Manifest.desde_archivo(ruta)

    def test_el_mismo_archivo_en_subcarpetas_distintas_sí_se_permite(self, tmp_path: Path) -> None:
        datos = self.base()
        datos["plugins"]["otra"] = dict(
            datos["plugins"]["cosa"], nombre="Otra", subcarpeta="floodgate"
        )
        ruta = self.escribir(tmp_path, datos)
        assert Manifest.desde_archivo(ruta).archivos_repetidos() == []

    def test_sin_archivo(self, tmp_path: Path) -> None:
        with pytest.raises(ErrorDeConfig, match="no encontré el manifest"):
            Manifest.desde_archivo(tmp_path / "no-existe.yml")
