"""settings.yml -> variables de docker-compose, y el bloque que va en .env.

Esto es lo que hace que "lo único que editas es settings.yml" sea verdad:
antes la memoria, la versión, los puertos y los respaldos estaban escritos a
mano en el compose y cambiarlos en settings.yml no hacía nada.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from mc_admin.config import Settings, cargar_settings
from mc_admin.core import compose as core
from mc_admin.infra import archivos
from mc_admin.infra.docker import Compose

RAIZ_REAL = Path(__file__).resolve().parents[3]


def _settings(proyecto: Path, **cambios: Any) -> Settings:
    """settings.yml real, con algunas claves cambiadas."""
    ruta = proyecto / "settings.yml"
    datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    for clave, valor in cambios.items():
        nodo = datos
        *camino, hoja = clave.split(".")
        for parte in camino:
            nodo = nodo.setdefault(parte, {})
        nodo[hoja] = valor
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return cargar_settings(proyecto)


def _variables(settings: Settings) -> dict[str, str]:
    return core.variables(settings, uid=1001, gid=1002)


class TestMemoria:
    @pytest.mark.parametrize(("texto", "mb"), [("6G", 6144), ("5632M", 5632), ("1g", 1024)])
    def test_memoria_en_mb(self, texto: str, mb: int) -> None:
        assert core.memoria_en_mb(texto) == mb

    def test_el_limite_deja_aire_fuera_del_heap(self) -> None:
        """Con límite = heap, el kernel mataba a Java al primer pico."""
        assert core.limite_del_contenedor("6G") == "7680m"


class TestVariables:
    def test_salen_de_settings(self, proyecto: Path) -> None:
        v = _variables(
            _settings(
                proyecto,
                **{
                    "recursos.memoria": "5G",
                    "puertos.java": 25570,
                    "puertos.bedrock_webrtc": 19134,
                },
            )
        )
        assert v["MC_MEMORIA"] == "5G"
        assert v["MC_MEMORIA_LIMITE"] == "6656m"
        assert v["MC_PUERTO_JAVA"] == "25570"
        assert v["MC_PUERTO_BEDROCK_WEBRTC"] == "19134"
        assert v["MC_UID"] == "1001"
        assert v["MC_GID"] == "1002"

    def test_versiones_e_imagenes(self, proyecto: Path) -> None:
        s = cargar_settings(proyecto)
        v = _variables(s)
        assert v["MC_VERSION"] == s.versiones.minecraft
        assert v["MC_IMAGEN"] == s.versiones.imagen_servidor

    def test_el_bot_de_pagos_es_un_perfil(self, proyecto: Path) -> None:
        prendido = _variables(_settings(proyecto, **{"pagos.activo": True}))
        assert prendido["COMPOSE_PROFILES"] == "pagos"

    def test_sin_bot_no_queda_ningun_perfil(self, proyecto: Path) -> None:
        """Con el bot apagado, Docker no debe quedarse reiniciándolo en bucle."""
        apagado = _variables(_settings(proyecto, **{"pagos.activo": False}))
        assert apagado["COMPOSE_PROFILES"] == ""


class TestBloque:
    def test_se_agrega_al_final_sin_tocar_lo_demas(self) -> None:
        env = "# mis secretos\nRCON_PASSWORD=abc\n"
        nuevo = core.reemplazar_bloque(env, core.bloque({"MC_MEMORIA": "6G"}))
        assert nuevo.startswith("# mis secretos\nRCON_PASSWORD=abc\n\n")
        assert "MC_MEMORIA=6G" in nuevo
        assert nuevo.endswith(core.FIN_BLOQUE + "\n")

    def test_reemplaza_el_bloque_anterior(self) -> None:
        env = core.reemplazar_bloque("A=1\n", core.bloque({"MC_MEMORIA": "6G"}))
        env += "B=2\n"
        nuevo = core.reemplazar_bloque(env, core.bloque({"MC_MEMORIA": "4G"}))
        assert "MC_MEMORIA=4G" in nuevo
        assert "MC_MEMORIA=6G" not in nuevo
        assert nuevo.count(core.INICIO_BLOQUE) == 1
        # Lo que estaba antes y después del bloque se queda.
        assert nuevo.startswith("A=1\n")
        assert "B=2" in nuevo

    def test_es_idempotente(self) -> None:
        bloque = core.bloque({"X": "1"})
        una = core.reemplazar_bloque("A=1\n", bloque)
        assert core.reemplazar_bloque(una, bloque) == una

    def test_env_vacio(self) -> None:
        assert core.reemplazar_bloque("", core.bloque({"X": "1"})).startswith(core.INICIO_BLOQUE)


class TestEscribirEnElEnv:
    def test_sin_env_lo_crea_desde_el_ejemplo(self, proyecto: Path) -> None:
        assert archivos.escribir_bloque_compose(proyecto, core.bloque({"MC_X": "1"}))
        texto = (proyecto / ".env").read_text(encoding="utf-8")
        assert "RCON_PASSWORD=" in texto  # vino del .env.example
        assert "MC_X=1" in texto

    def test_conserva_los_secretos_y_deja_permisos_600(self, env_lleno: Path) -> None:
        archivos.escribir_bloque_compose(env_lleno, core.bloque({"MC_X": "1"}))
        ruta = env_lleno / ".env"
        assert "RCON_PASSWORD=contrasenaDePrueba" in ruta.read_text(encoding="utf-8")
        assert stat.S_IMODE(ruta.stat().st_mode) == 0o600

    def test_dice_si_cambio(self, env_lleno: Path) -> None:
        assert archivos.escribir_bloque_compose(env_lleno, core.bloque({"MC_X": "1"}))
        assert not archivos.escribir_bloque_compose(env_lleno, core.bloque({"MC_X": "1"}))

    def test_los_secretos_se_siguen_leyendo(self, env_lleno: Path) -> None:
        from mc_admin.config import cargar_secretos

        archivos.escribir_bloque_compose(env_lleno, core.bloque({"MC_X": "1"}))
        assert cargar_secretos(env_lleno, usar_entorno=False).rcon_password == (
            "contrasenaDePrueba"
        )


class TestCarpetas:
    def test_crea_el_punto_de_montaje_de_pagos(self, proyecto: Path) -> None:
        """Sin data/pagos-datos, el contenedor de respaldos no arranca."""
        archivos.asegurar_carpetas(proyecto)
        assert (proyecto / "data" / "pagos-datos").is_dir()
        assert (proyecto / "pagos-datos").is_dir()


class TestElComposeDeVerdad:
    """Que docker-compose.yml use las variables que calculamos, y no otras."""

    @pytest.fixture
    def texto(self) -> str:
        return (RAIZ_REAL / "docker-compose.yml").read_text(encoding="utf-8")

    def test_usa_todas_las_variables_mc(self, proyecto: Path, texto: str) -> None:
        s = cargar_settings(proyecto)
        for clave in _variables(s):
            if clave == "COMPOSE_PROFILES":
                continue  # la lee Compose mismo, no el archivo
            assert f"${{{clave}" in texto, f"docker-compose.yml no usa {clave}"

    def test_rcon_solo_en_localhost(self, texto: str) -> None:
        assert '"127.0.0.1:${MC_PUERTO_RCON:-25575}:${MC_PUERTO_RCON:-25575}/tcp"' in texto

    def test_le_da_tiempo_de_apagarse(self, texto: str) -> None:
        assert "stop_grace_period: 2m" in texto

    def test_la_base_del_bot_sigue_en_su_carpeta(self, texto: str) -> None:
        assert "./pagos-datos:/datos" in texto


class CorridaFalsa:
    def __init__(self) -> None:
        self.comandos: list[list[str]] = []

    def __call__(self, comando: list[str], **kwargs: Any) -> Any:
        self.comandos.append(comando)
        return subprocess.CompletedProcess(comando, 0, stdout="", stderr="")


class TestArrancarYApagar:
    @pytest.fixture
    def compose(self, proyecto: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Compose, Any]:
        c = Compose(proyecto)
        c._binario = ["docker", "compose"]
        corrida = CorridaFalsa()
        monkeypatch.setattr(subprocess, "run", corrida)
        return c, corrida

    def test_arrancar_reconstruye_y_recrea(self, compose: tuple[Compose, Any]) -> None:
        """`up --build`: si cambió el código del bot, se usa el nuevo."""
        c, corrida = compose
        c.arrancar()
        assert corrida.comandos[-1] == [
            "docker",
            "compose",
            "up",
            "-d",
            "--build",
            "--remove-orphans",
        ]

    def test_apagar_alcanza_todos_los_perfiles(self, compose: tuple[Compose, Any]) -> None:
        """Si algo se apagó en settings.yml, su contenedor también se tiene que bajar."""
        c, corrida = compose
        c.apagar()
        assert corrida.comandos[-1] == [
            "docker",
            "compose",
            "--profile",
            "pagos",
            "down",
        ]
