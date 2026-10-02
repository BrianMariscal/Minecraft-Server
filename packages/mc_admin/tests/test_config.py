"""settings.yml y .env: que validen de verdad y expliquen el error."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from mc_admin.config import cargar_secretos, cargar_settings, encontrar_raiz
from mc_admin.errores import ErrorDeConfig


def editar(proyecto: Path, cambios: dict[str, Any]) -> None:
    """Cambia settings.yml de forma anidada: {'seguridad': {'whitelist': False}}."""
    ruta = proyecto / "settings.yml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))

    def aplicar(nodo: dict[str, Any], cambio: dict[str, Any]) -> None:
        for k, v in cambio.items():
            if isinstance(v, dict) and isinstance(nodo.get(k), dict):
                aplicar(nodo[k], v)
            else:
                nodo[k] = v

    aplicar(datos, cambios)
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")


class TestCargarSettings:
    def test_el_settings_real_del_proyecto_es_valido(self, proyecto: Path) -> None:
        """Si este test falla, el settings.yml que se versiona está roto."""
        s = cargar_settings(proyecto)
        assert s.servidor.nombre == "Minecraft HD"
        assert s.versiones.minecraft == "26.1.2"

    def test_sin_archivo(self, tmp_path: Path) -> None:
        with pytest.raises(ErrorDeConfig, match=r"no encontré settings\.yml"):
            cargar_settings(tmp_path)

    def test_yaml_roto(self, proyecto: Path) -> None:
        (proyecto / "settings.yml").write_text("esto: [no\n  cierra", encoding="utf-8")
        with pytest.raises(ErrorDeConfig, match="no es YAML válido"):
            cargar_settings(proyecto)

    def test_el_error_dice_qué_clave_está_mal(self, proyecto: Path) -> None:
        editar(proyecto, {"rendimiento": {"view_distance": 99}})
        with pytest.raises(ErrorDeConfig, match=r"rendimiento\.view_distance"):
            cargar_settings(proyecto)

    def test_una_clave_de_más_se_detecta(self, proyecto: Path) -> None:
        """Un typo no debe pasar en silencio."""
        editar(proyecto, {"servidor": {"nombrre": "typo"}})
        with pytest.raises(ErrorDeConfig, match="nombrre"):
            cargar_settings(proyecto)


class TestReglasDeNegocio:
    def test_no_premium_sin_whitelist_se_rechaza(self, proyecto: Path) -> None:
        """Un servidor abierto y sin whitelist es tomado en días."""
        editar(proyecto, {"seguridad": {"whitelist": False}})
        with pytest.raises(ErrorDeConfig, match="necesitas"):
            cargar_settings(proyecto)

    def test_simulacion_mayor_que_vista_se_rechaza(self, proyecto: Path) -> None:
        editar(proyecto, {"rendimiento": {"view_distance": 8, "simulation_distance": 10}})
        with pytest.raises(ErrorDeConfig, match="simulation_distance"):
            cargar_settings(proyecto)

    def test_imagen_con_latest_se_rechaza(self, proyecto: Path) -> None:
        """Las versiones se fijan: un tag móvil cambia el server al reiniciar."""
        editar(proyecto, {"versiones": {"imagen_servidor": "itzg/minecraft-server:latest"}})
        with pytest.raises(ErrorDeConfig, match="tag móvil"):
            cargar_settings(proyecto)

    def test_puertos_repetidos_se_rechazan(self, proyecto: Path) -> None:
        editar(proyecto, {"puertos": {"bluemap": 25565}})
        with pytest.raises(ErrorDeConfig, match="puertos repetidos"):
            cargar_settings(proyecto)

    def test_zona_horaria_inventada_se_rechaza(self, proyecto: Path) -> None:
        editar(proyecto, {"pagos": {"zona_horaria": "America/Chilangolandia"}})
        with pytest.raises(ErrorDeConfig, match="no existe"):
            cargar_settings(proyecto)

    def test_formato_de_chat_sin_marcadores_se_rechaza(self, proyecto: Path) -> None:
        editar(proyecto, {"chat": {"formato_default": "solo texto"}})
        with pytest.raises(ErrorDeConfig, match="marcadores"):
            cargar_settings(proyecto)

    def test_bedrock_con_punto_se_rechaza(self, proyecto: Path) -> None:
        """El prefijo de Floodgate lo pone `mc`, no el usuario."""
        editar(proyecto, {"whitelist": {"bedrock": [".Pepe"]}})
        with pytest.raises(ErrorDeConfig, match="quita el punto"):
            cargar_settings(proyecto)

    def test_nombre_de_admin_invalido_se_rechaza(self, proyecto: Path) -> None:
        editar(proyecto, {"admins": ["no"]})
        with pytest.raises(ErrorDeConfig, match="no son nombres válidos"):
            cargar_settings(proyecto)

    def test_reparto_personalizado_sin_montos_se_rechaza(self, proyecto: Path) -> None:
        editar(proyecto, {"pagos": {"reparto": "personalizado"}})
        with pytest.raises(ErrorDeConfig, match="monto_mxn"):
            cargar_settings(proyecto)


class TestSecretos:
    def test_sin_env_todo_vacio(self, proyecto: Path) -> None:
        s = cargar_secretos(proyecto, usar_entorno=False)
        assert s.rcon_password == ""
        assert "RCON_PASSWORD" in s.faltantes_para(discord=False, pagos=False)

    def test_con_env_lleno_no_falta_nada(self, env_lleno: Path) -> None:
        s = cargar_secretos(env_lleno, usar_entorno=False)
        assert s.faltantes_para(discord=True, pagos=True) == []

    def test_nunca_se_imprimen_los_valores(self, env_lleno: Path) -> None:
        """Un traceback o un log jamás debe filtrar el token."""
        s = cargar_secretos(env_lleno, usar_entorno=False)
        texto = f"{s!r} {s!s}"
        assert "tokenDePrueba" not in texto
        assert "contrasenaDePrueba" not in texto
        assert "rcon_password" in texto  # sí dice QUÉ está lleno

    def test_solo_pide_lo_que_esta_activo(self, proyecto: Path) -> None:
        s = cargar_secretos(proyecto, usar_entorno=False)
        faltan = s.faltantes_para(discord=False, pagos=False)
        assert faltan == ["RCON_PASSWORD"]

    def test_env_mal_escrito_truena_diciendo_la_linea(self, proyecto: Path) -> None:
        (proyecto / ".env").write_text("RCON_PASSWORD=x\nesto esta mal\n", encoding="utf-8")
        with pytest.raises(ErrorDeConfig, match="línea 2"):
            cargar_secretos(proyecto, usar_entorno=False)

    def test_variables_de_mas_no_tumban_la_carga(self, proyecto: Path) -> None:
        (proyecto / ".env").write_text("RCON_PASSWORD=x\nALGO_RARO=y\n", encoding="utf-8")
        s = cargar_secretos(proyecto, usar_entorno=False)
        assert s.rcon_password == "x"


class TestEncontrarRaiz:
    def test_encuentra_desde_una_subcarpeta(self, proyecto: Path) -> None:
        hondo = proyecto / "minecraft" / "templates"
        assert encontrar_raiz(hondo) == proyecto.resolve()

    def test_truena_si_no_hay_proyecto(self, tmp_path: Path) -> None:
        with pytest.raises(ErrorDeConfig, match=r"no encontré settings\.yml"):
            encontrar_raiz(tmp_path)
