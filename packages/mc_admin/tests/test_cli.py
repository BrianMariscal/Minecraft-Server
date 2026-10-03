"""Los comandos de `mc` de punta a punta, con Docker y RCON simulados.

Aquí vivía el bug más grave del proyecto: `mc` hablaba con RCON en
127.0.0.1:25575 y el compose nunca publicaba ese puerto, así que whitelist,
gamerules y el save-all antes de apagar fallaban callados. Los tests de la
lógica pura no lo podían ver; estos recorren el comando completo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mc_admin.cli.main import app
from mc_admin.core import compose as core_compose
from mc_admin.infra import rcon
from mc_admin.infra.docker import Compose

runner = CliRunner()


class Registro:
    """Lo que `mc` le pidió a Docker y a RCON, en orden."""

    def __init__(self) -> None:
        self.pasos: list[str] = []
        self.rcon: list[str] = []


@pytest.fixture
def registro(env_lleno: Path, monkeypatch: pytest.MonkeyPatch) -> Registro:
    reg = Registro()
    monkeypatch.chdir(env_lleno)
    (env_lleno / "data").mkdir()
    (env_lleno / "data" / "server.properties").write_text("ya construido")

    def arrancar(self: Compose, servicios: list[str] | None = None) -> None:
        reg.pasos.append("up")

    def apagar(self: Compose, servicios: list[str] | None = None) -> None:
        reg.pasos.append("down")

    def mandar(_c: Any, comando: str, timeout: int = 10) -> str:
        reg.rcon.append(comando)
        return ""

    def mandar_varios(_c: Any, comandos: list[str], timeout: int = 10) -> list[str]:
        reg.rcon.extend(comandos)
        return [""] * len(comandos)

    monkeypatch.setattr(Compose, "arrancar", arrancar)
    monkeypatch.setattr(Compose, "apagar", apagar)
    monkeypatch.setattr(rcon, "esta_vivo", lambda _c: True)
    monkeypatch.setattr(rcon, "mandar", mandar)
    monkeypatch.setattr(rcon, "mandar_varios", mandar_varios)
    return reg


def _correr(*argumentos: str) -> Any:
    resultado = runner.invoke(app, list(argumentos))
    assert resultado.exit_code == 0, resultado.output
    return resultado


class TestStart:
    def test_arranca_y_aplica_la_configuracion(self, registro: Registro) -> None:
        _correr("start")
        assert registro.pasos == ["up"]
        assert any("gamerule " in c for c in registro.rcon)

    def test_pone_las_variables_de_compose_en_el_env(
        self, registro: Registro, env_lleno: Path
    ) -> None:
        _correr("start")
        texto = (env_lleno / ".env").read_text(encoding="utf-8")
        assert core_compose.INICIO_BLOQUE in texto
        assert "MC_PUERTO_RCON=25575" in texto
        # Y los secretos siguen ahí.
        assert "RCON_PASSWORD=contrasenaDePrueba" in texto

    def test_sin_build_no_arranca(self, registro: Registro, env_lleno: Path) -> None:
        (env_lleno / "data" / "server.properties").unlink()
        resultado = runner.invoke(app, ["start"])
        assert resultado.exit_code == 1
        assert "mc build" in resultado.output
        assert registro.pasos == []


class TestStop:
    def test_guarda_a_disco_antes_de_apagar(self, registro: Registro) -> None:
        _correr("stop")
        assert registro.rcon == ["save-all flush"]
        assert registro.pasos == ["down"]


class TestRestart:
    def test_guarda_apaga_y_vuelve_a_aplicar_todo(self, registro: Registro) -> None:
        """No es `compose restart`: ese no se entera de cambios en .env."""
        _correr("restart")
        assert registro.pasos == ["down", "up"]
        assert registro.rcon[0] == "save-all flush"
        assert any("gamerule " in c for c in registro.rcon[1:])

    def test_si_falta_un_secreto_no_apaga_nada(self, registro: Registro, env_lleno: Path) -> None:
        env = env_lleno / ".env"
        env.write_text(
            env.read_text(encoding="utf-8").replace("RCON_PASSWORD=contrasenaDePrueba", ""),
            encoding="utf-8",
        )
        resultado = runner.invoke(app, ["restart"])
        assert resultado.exit_code == 1
        assert registro.pasos == []


class TestBuildDryRun:
    def test_no_toca_nada(self, env_lleno: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(env_lleno)
        antes = (env_lleno / ".env").read_text(encoding="utf-8")
        resultado = _correr("build", "--dry-run")
        assert "Docker Compose" in resultado.output
        assert "Nada de esto se hizo" in resultado.output
        assert (env_lleno / ".env").read_text(encoding="utf-8") == antes
        assert not (env_lleno / "data").exists()


class TestWhitelist:
    def _whitelist(self, raiz: Path) -> Any:
        import json

        return json.loads((raiz / "data" / "whitelist.json").read_text(encoding="utf-8"))

    def test_java_con_el_uuid_offline(self, registro: Registro, env_lleno: Path) -> None:
        resultado = _correr("whitelist", "add", "Pepe")
        assert "whitelist reload" in registro.rcon
        assert self._whitelist(env_lleno) == [
            {"uuid": "6eed0e07-3df7-3e33-9aa2-baa999bb44ee", "name": "Pepe"}
        ]
        assert "/register" in resultado.output

    def test_bedrock_con_xuid_a_mano(self, registro: Registro, env_lleno: Path) -> None:
        resultado = _correr(
            "whitelist", "add", "Gamer Tag", "--bedrock", "--xuid", "1234567890123456"
        )
        assert "/register" not in resultado.output
        assert self._whitelist(env_lleno) == [
            {"uuid": "00000000-0000-0000-0004-62d53c8abac0", "name": ".Gamer_Tag"}
        ]
        settings = (env_lleno / "settings.yml").read_text(encoding="utf-8")
        assert "Gamer_Tag: 1234567890123456" in settings

    def test_bedrock_busca_el_xuid_solo(
        self, registro: Registro, env_lleno: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mc_admin.infra import xbox

        monkeypatch.setattr(xbox, "buscar_xuid", lambda _g: 1234567890123456)
        _correr("whitelist", "add", "Gamer Tag", "--bedrock")
        assert self._whitelist(env_lleno)[0]["name"] == ".Gamer_Tag"

    def test_bedrock_sin_xuid_explica_como_conseguirlo(
        self, registro: Registro, env_lleno: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from mc_admin.infra import xbox

        monkeypatch.setattr(xbox, "buscar_xuid", lambda _g: None)
        resultado = runner.invoke(app, ["whitelist", "add", "Gamer Tag", "--bedrock"])
        assert resultado.exit_code == 1
        assert "--xuid" in resultado.output
        # Y no lo dejó a medias en settings.yml.
        assert "Gamer_Tag" not in (env_lleno / "settings.yml").read_text(encoding="utf-8")

    def test_quitar_lo_saca_del_archivo_y_del_servidor(
        self, registro: Registro, env_lleno: Path
    ) -> None:
        _correr("whitelist", "add", "Pepe")
        _correr("whitelist", "remove", "Pepe")
        assert self._whitelist(env_lleno) == []
        assert any(c.startswith("kick Pepe") for c in registro.rcon)


class TestAdmins:
    def test_un_admin_entra_solo_a_la_whitelist(self, registro: Registro, env_lleno: Path) -> None:
        import json

        _correr("admin", "add", "Zorro")
        lista = json.loads((env_lleno / "data" / "whitelist.json").read_text(encoding="utf-8"))
        assert lista == [{"uuid": "94c56451-ca97-328d-a577-186e0ba6ebd3", "name": "Zorro"}]

    def test_luckperms_por_uuid(self, registro: Registro) -> None:
        """Por nombre, LuckPerms no encuentra a quien nunca ha entrado."""
        _correr("admin", "add", "Zorro")
        assert "lp user 94c56451-ca97-328d-a577-186e0ba6ebd3 parent add admin" in registro.rcon
        assert "op Zorro" in registro.rcon

    def test_el_guion_de_grupos_se_regenera_solo(self, registro: Registro, env_lleno: Path) -> None:
        _correr("admin", "add", "Zorro")
        guion = env_lleno / "minecraft" / "generated" / "mensajes" / "luckperms-grupos.txt"
        assert "lp user 94c56451-ca97-328d-a577-186e0ba6ebd3 parent add admin" in guion.read_text(
            encoding="utf-8"
        )

    def test_a_un_admin_no_se_le_saca_de_la_whitelist(self, registro: Registro) -> None:
        _correr("admin", "add", "Zorro")
        resultado = runner.invoke(app, ["whitelist", "remove", "Zorro"])
        assert resultado.exit_code == 1
        assert "admin remove" in resultado.output

    def test_quitar_admin_lo_deja_como_jugador(self, registro: Registro, env_lleno: Path) -> None:
        _correr("admin", "add", "Zorro")
        _correr("admin", "remove", "Zorro")
        assert "deop Zorro" in registro.rcon
        assert "lp user 94c56451-ca97-328d-a577-186e0ba6ebd3 parent remove admin" in registro.rcon
        settings = (env_lleno / "settings.yml").read_text(encoding="utf-8")
        assert "admins: []" in settings
        assert "- Zorro" in settings


class TestAdminsBedrock:
    UUID = "00000000-0000-0000-0004-62d53c8abac0"  # XUID 1234567890123456

    def test_entra_a_la_whitelist_y_al_grupo_por_uuid(
        self, registro: Registro, env_lleno: Path
    ) -> None:
        import json

        _correr("admin", "add", "AdminBedrock", "--bedrock", "--xuid", "1234567890123456")
        lista = json.loads((env_lleno / "data" / "whitelist.json").read_text(encoding="utf-8"))
        assert lista == [{"uuid": self.UUID, "name": ".AdminBedrock"}]
        assert f"lp user {self.UUID} parent add admin" in registro.rcon
        # `op` con un UUID lo toma como nombre: no se debe mandar.
        assert not [c for c in registro.rcon if c.startswith("op ") and "0000" in c]
        guion = env_lleno / "minecraft" / "generated" / "mensajes" / "luckperms-grupos.txt"
        assert f"lp user {self.UUID} parent add admin" in guion.read_text(encoding="utf-8")

    def test_no_se_le_saca_de_la_whitelist_sin_quitarle_el_admin(self, registro: Registro) -> None:
        _correr("admin", "add", "AdminBedrock", "--bedrock", "--xuid", "1234567890123456")
        resultado = runner.invoke(app, ["whitelist", "remove", "AdminBedrock", "--bedrock"])
        assert resultado.exit_code == 1

    def test_quitar_admin_lo_deja_como_jugador(self, registro: Registro, env_lleno: Path) -> None:
        import json

        _correr("admin", "add", "AdminBedrock", "--bedrock", "--xuid", "1234567890123456")
        _correr("admin", "remove", "AdminBedrock", "--bedrock")
        assert f"lp user {self.UUID} parent remove admin" in registro.rcon
        lista = json.loads((env_lleno / "data" / "whitelist.json").read_text(encoding="utf-8"))
        assert lista == [{"uuid": self.UUID, "name": ".AdminBedrock"}]
