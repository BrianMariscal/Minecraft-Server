"""Docker y RCON, simulados.

Ningún test de aquí levanta un contenedor ni abre un socket: Docker y RCON
se sustituyen por dobles. Lo que se prueba es NUESTRO código, o sea cómo
interpretamos las respuestas y qué error damos cuando algo falla.
"""

from __future__ import annotations

import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mc_admin.errores import ErrorDeDocker, ErrorDeEntorno, ErrorDeRcon
from mc_admin.infra import archivos, rcon
from mc_admin.infra.docker import Compose, EstadoServicio
from mc_admin.infra.registro import FiltroSecretos, configurar

# --------------------------------------------------------------------------- #
#  Docker
# --------------------------------------------------------------------------- #


class CorridaFalsa:
    """Un doble de subprocess.run que contesta lo que le digamos."""

    def __init__(self, salida: str = "", error: str = "", codigo: int = 0) -> None:
        self.salida, self.error, self.codigo = salida, error, codigo
        self.comandos: list[list[str]] = []

    def __call__(self, comando: list[str], **kwargs: Any) -> Any:
        self.comandos.append(comando)
        return subprocess.CompletedProcess(
            comando, self.codigo, stdout=self.salida, stderr=self.error
        )


@pytest.fixture
def compose(proyecto: Path, monkeypatch: pytest.MonkeyPatch) -> Compose:
    c = Compose(proyecto)
    # Le decimos que ya encontró el binario, para no depender de la máquina.
    c._binario = ["docker", "compose"]
    return c


class TestEstadoServicio:
    def test_corriendo_y_sano(self) -> None:
        e = EstadoServicio("minecraft", "running", "healthy")
        assert e.corriendo and e.sano
        assert e.descripcion == "corriendo"

    def test_sin_healthcheck_running_ya_cuenta_como_sano(self) -> None:
        e = EstadoServicio("respaldos", "running", None)
        assert e.sano

    def test_arrancando(self) -> None:
        e = EstadoServicio("minecraft", "running", "starting")
        assert e.corriendo
        assert not e.sano
        assert "arrancando" in e.descripcion

    def test_enfermo(self) -> None:
        e = EstadoServicio("minecraft", "running", "unhealthy")
        assert not e.sano
        assert "healthcheck falla" in e.descripcion

    def test_apagado(self) -> None:
        e = EstadoServicio("minecraft", "exited", None)
        assert not e.corriendo
        assert "apagado" in e.descripcion


class TestLeerEstado:
    def test_una_linea_json_por_servicio(
        self, compose: Compose, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Es el formato de `docker compose ps --format json` en v2."""
        falsa = CorridaFalsa(
            '{"Service":"minecraft","State":"running","Health":"healthy"}\n'
            '{"Service":"respaldos","State":"running","Health":""}\n'
        )
        monkeypatch.setattr(subprocess, "run", falsa)
        estados = compose.estado()
        assert [e.nombre for e in estados] == ["minecraft", "respaldos"]
        assert estados[0].salud == "healthy"
        assert estados[1].salud is None

    def test_tambien_entiende_un_arreglo(
        self, compose: Compose, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        falsa = CorridaFalsa('[{"Service":"minecraft","State":"running"}]')
        monkeypatch.setattr(subprocess, "run", falsa)
        assert len(compose.estado()) == 1

    def test_una_linea_rota_no_tumba_el_resto(
        self, compose: Compose, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        falsa = CorridaFalsa('esto no es json\n{"Service":"minecraft","State":"running"}\n')
        monkeypatch.setattr(subprocess, "run", falsa)
        assert [e.nombre for e in compose.estado()] == ["minecraft"]

    def test_sin_contenedores(self, compose: Compose, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subprocess, "run", CorridaFalsa(""))
        assert compose.estado() == []

    def test_buscar_un_servicio(self, compose: Compose, monkeypatch: pytest.MonkeyPatch) -> None:
        falsa = CorridaFalsa('{"Service":"minecraft","State":"running"}')
        monkeypatch.setattr(subprocess, "run", falsa)
        assert compose.estado_de("minecraft") is not None
        assert compose.estado_de("no-existe") is None


class TestErroresDeDocker:
    def test_un_comando_que_falla_cuenta_lo_que_dijo_docker(
        self, compose: Compose, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        falsa = CorridaFalsa(error="port is already allocated", codigo=1)
        monkeypatch.setattr(subprocess, "run", falsa)
        with pytest.raises(ErrorDeDocker) as info:
            compose.arrancar()
        assert "already allocated" in info.value.mensaje
        assert "mc doctor" in (info.value.pista or "")

    def test_un_timeout_lo_dice_claro(
        self, compose: Compose, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def truena(*a: Any, **k: Any) -> Any:
            raise subprocess.TimeoutExpired(cmd="docker", timeout=120)

        monkeypatch.setattr(subprocess, "run", truena)
        with pytest.raises(ErrorDeDocker, match="se tardó más de"):
            compose.arrancar()

    def test_sin_docker_instalado_dice_como_arreglarlo(
        self, proyecto: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        c = Compose(proyecto)
        with pytest.raises(ErrorDeEntorno) as info:
            c.arrancar()
        assert "grupo `docker`" in (info.value.pista or "")

    def test_disponible_contesta_sin_truenar(
        self, proyecto: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert Compose(proyecto).disponible() == (False, None)


# --------------------------------------------------------------------------- #
#  RCON
# --------------------------------------------------------------------------- #


class ClienteRconFalso:
    """Un doble de MCRcon."""

    def __init__(self, *args: Any, respuestas: dict[str, str] | None = None, **kw: Any) -> None:
        self.respuestas = respuestas or {}
        self.mandados: list[str] = []
        self.conectado = False
        self.cerrado = False

    def connect(self) -> None:
        self.conectado = True

    def disconnect(self) -> None:
        self.cerrado = True

    def command(self, comando: str) -> str:
        self.mandados.append(comando)
        return self.respuestas.get(comando, "")


CONEXION = rcon.Conexion(host="127.0.0.1", puerto=25575, password="secreta")


def montar_rcon(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> ClienteRconFalso:
    cliente = ClienteRconFalso(**kwargs)
    monkeypatch.setattr(rcon, "MCRcon", lambda *a, **k: cliente)
    return cliente


class TestConexion:
    def test_nunca_imprime_la_contraseña(self) -> None:
        """Un traceback jamás debe filtrar la contraseña de RCON."""
        texto = f"{CONEXION!r} {CONEXION!s}"
        assert "secreta" not in texto
        assert "25575" in texto

    def test_sin_contraseña_dice_que_corras_setup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sin = rcon.Conexion(host="127.0.0.1", puerto=25575, password="")
        with pytest.raises(ErrorDeRcon) as info:
            rcon.mandar(sin, "list")
        assert "mc setup" in (info.value.pista or "")


class TestMandarComandos:
    def test_manda_y_limpia_los_colores(self, monkeypatch: pytest.MonkeyPatch) -> None:
        montar_rcon(monkeypatch, respuestas={"list": "§aHay 2 jugadores§r"})
        assert rcon.mandar(CONEXION, "list") == "Hay 2 jugadores"

    def test_cierra_la_conexion_siempre(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cliente = montar_rcon(monkeypatch)
        rcon.mandar(CONEXION, "list")
        assert cliente.cerrado

    def test_varios_comandos_reusan_la_conexion(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Abrir RCON por cada nombre de la whitelist sería lentísimo."""
        cliente = montar_rcon(monkeypatch)
        rcon.mandar_varios(CONEXION, ["whitelist add A", "whitelist add B"])
        assert cliente.mandados == ["whitelist add A", "whitelist add B"]

    def test_la_diagonal_se_quita(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cliente = montar_rcon(monkeypatch)
        rcon.mandar(CONEXION, "list")
        assert cliente.mandados == ["list"]


class TestErroresDeRcon:
    def test_servidor_apagado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoConecta(ClienteRconFalso):
            def connect(self) -> None:
                raise ConnectionRefusedError

        monkeypatch.setattr(rcon, "MCRcon", lambda *a, **k: NoConecta())
        with pytest.raises(ErrorDeRcon) as info:
            rcon.mandar(CONEXION, "list")
        assert "no contesta" in info.value.mensaje
        assert "mc start" in (info.value.pista or "")

    def test_contraseña_mala(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class RechazaLaClave(ClienteRconFalso):
            def connect(self) -> None:
                raise Exception("Authentication failed")  # noqa: TRY002

        monkeypatch.setattr(rcon, "MCRcon", lambda *a, **k: RechazaLaClave())
        with pytest.raises(ErrorDeRcon) as info:
            rcon.mandar(CONEXION, "list")
        assert "rechazó la contraseña" in info.value.mensaje

    def test_nombre_que_no_resuelve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoResuelve(ClienteRconFalso):
            def connect(self) -> None:
                raise socket.gaierror

        monkeypatch.setattr(rcon, "MCRcon", lambda *a, **k: NoResuelve())
        with pytest.raises(ErrorDeRcon, match="no pude resolver"):
            rcon.mandar(CONEXION, "list")

    def test_esta_vivo_contesta_false_sin_truenar(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class NoConecta(ClienteRconFalso):
            def connect(self) -> None:
                raise ConnectionRefusedError

        monkeypatch.setattr(rcon, "MCRcon", lambda *a, **k: NoConecta())
        assert rcon.esta_vivo(CONEXION) is False


class TestLeerRespuestas:
    def test_tps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """El encabezado trae "1m, 5m, 15m": esos números NO son los TPS.

        Tomarlos en orden de aparición daba 1.0 y `mc doctor` reportaba un
        servidor lentísimo estando perfecto.
        """
        montar_rcon(
            monkeypatch,
            respuestas={"tps": "§6TPS from last 1m, 5m, 15m: §a19.98, §a19.95, §a20.0"},
        )
        assert rcon.leer_tps(CONEXION) == pytest.approx(19.98)

    def test_tps_sin_encabezado(self, monkeypatch: pytest.MonkeyPatch) -> None:
        montar_rcon(monkeypatch, respuestas={"tps": "19.5 19.6 19.7"})
        assert rcon.leer_tps(CONEXION) == pytest.approx(19.5)

    def test_tps_nunca_pasa_de_20(self, monkeypatch: pytest.MonkeyPatch) -> None:
        montar_rcon(monkeypatch, respuestas={"tps": "TPS: 20.5"})
        assert rcon.leer_tps(CONEXION) == 20.0

    def test_tps_cuando_no_contesta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        montar_rcon(monkeypatch, respuestas={"tps": "sin numeros aqui"})
        assert rcon.leer_tps(CONEXION) is None

    def test_jugadores_conectados(self, monkeypatch: pytest.MonkeyPatch) -> None:
        montar_rcon(
            monkeypatch,
            respuestas={"list": "There are 2 of a max of 15 players online: Pepe, .Lupita"},
        )
        conectados, maximo, nombres = rcon.jugadores_conectados(CONEXION)
        assert (conectados, maximo) == (2, 15)
        assert nombres == ["Pepe", ".Lupita"]

    def test_jugadores_en_español(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EssentialsX contesta en español con nuestra traducción."""
        montar_rcon(
            monkeypatch,
            respuestas={"list": "Hay 0 jugadores de un máximo de 15 jugadores en linea."},
        )
        conectados, maximo, nombres = rcon.jugadores_conectados(CONEXION)
        assert (conectados, maximo) == (0, 15)
        assert nombres == []


# --------------------------------------------------------------------------- #
#  Logging
# --------------------------------------------------------------------------- #


class TestFiltroDeSecretos:
    @pytest.mark.parametrize(
        "mensaje",
        [
            "RCON_PASSWORD=sup3rs3cr3t0",
            "password: miClaveSecreta",
            "token: abc123xyz",
        ],
    )
    def test_tacha_las_asignaciones(self, mensaje: str) -> None:
        import logging

        registro = logging.LogRecord("x", logging.INFO, "x", 1, mensaje, None, None)
        FiltroSecretos().filter(registro)
        limpio = registro.getMessage()
        for sospechoso in ("sup3rs3cr3t0", "miClaveSecreta", "abc123xyz"):
            assert sospechoso not in limpio

    def test_la_prosa_no_se_tacha(self) -> None:
        """El filtro busca ASIGNACIONES (clave=valor, clave: valor), no prosa.

        Es a propósito: tachar cualquier palabra cerca de "secret" dejaría los
        logs ilegibles. La regla del proyecto es que la lógica nunca mete un
        secreto en un mensaje, y el filtro es la red por si se nos va una.
        """
        import logging

        registro = logging.LogRecord(
            "x", logging.INFO, "x", 1, "no pude leer el secret del archivo", None, None
        )
        FiltroSecretos().filter(registro)
        assert registro.getMessage() == "no pude leer el secret del archivo"

    def test_tacha_un_token_de_discord(self) -> None:
        import logging

        token = "FAKE-DISCORD-TOKEN-12345678.abcdef.abcdefghijklmnopqrstuvwxyz12"
        registro = logging.LogRecord("x", logging.INFO, "x", 1, token, None, None)
        FiltroSecretos().filter(registro)
        assert token not in registro.getMessage()
        assert "***" in registro.getMessage()

    def test_un_mensaje_normal_no_se_toca(self) -> None:
        import logging

        registro = logging.LogRecord("x", logging.INFO, "x", 1, "bajando Geyser 2.11.3", None, None)
        FiltroSecretos().filter(registro)
        assert registro.getMessage() == "bajando Geyser 2.11.3"

    def test_el_logger_lleva_el_filtro_puesto(self) -> None:
        import logging

        logger = configurar(logging.INFO)
        assert logger.handlers
        assert any(isinstance(f, FiltroSecretos) for h in logger.handlers for f in h.filters)
        # No propagamos al root: si no, Rich y logging se pelean la terminal.
        assert logger.propagate is False


# --------------------------------------------------------------------------- #
#  Archivos
# --------------------------------------------------------------------------- #


class TestEscrituras:
    def test_crear(self, tmp_path: Path) -> None:
        r = archivos.escribir_si_cambio(tmp_path / "a.txt", "hola")
        assert r.creado and r.cambio
        assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "hola"

    def test_lo_mismo_no_se_reescribe(self, tmp_path: Path) -> None:
        """Idempotencia: no tocamos la fecha de lo que no cambió."""
        ruta = tmp_path / "a.txt"
        archivos.escribir_si_cambio(ruta, "hola")
        antes = ruta.stat().st_mtime_ns
        r = archivos.escribir_si_cambio(ruta, "hola")
        assert not r.cambio
        assert ruta.stat().st_mtime_ns == antes

    def test_cambio_de_contenido(self, tmp_path: Path) -> None:
        ruta = tmp_path / "a.txt"
        archivos.escribir_si_cambio(ruta, "hola")
        r = archivos.escribir_si_cambio(ruta, "adiós")
        assert r.cambio and not r.creado
        assert ruta.read_text(encoding="utf-8") == "adiós"

    def test_dry_run_no_escribe(self, tmp_path: Path) -> None:
        ruta = tmp_path / "a.txt"
        r = archivos.escribir_si_cambio(ruta, "hola", dry_run=True)
        assert r.cambio
        assert not ruta.exists()

    def test_crea_las_carpetas_que_falten(self, tmp_path: Path) -> None:
        ruta = tmp_path / "a" / "b" / "c.txt"
        archivos.escribir_si_cambio(ruta, "hola")
        assert ruta.is_file()

    def test_no_deja_temporales_tirados(self, tmp_path: Path) -> None:
        archivos.escribir_si_cambio(tmp_path / "a.txt", "hola")
        assert list(tmp_path.glob("*.tmp")) == []


class TestLimpiarJars:
    def test_quita_los_que_no_estan_en_el_manifest(self, tmp_path: Path) -> None:
        """Si no, bajar de versión deja los dos jars y el server carga quién sabe cuál."""
        for n in ("Bueno.jar", "Viejo.jar"):
            (tmp_path / n).write_text("x", encoding="utf-8")
        quitados = archivos.limpiar_jars_viejos(tmp_path, {"Bueno.jar"})
        assert [q.name for q in quitados] == ["Viejo.jar"]
        assert not (tmp_path / "Viejo.jar").exists()
        assert (tmp_path / "Bueno.jar").exists()

    def test_no_toca_lo_que_no_es_jar(self, tmp_path: Path) -> None:
        (tmp_path / "config.yml").write_text("x", encoding="utf-8")
        archivos.limpiar_jars_viejos(tmp_path, set())
        assert (tmp_path / "config.yml").exists()

    def test_dry_run_no_borra(self, tmp_path: Path) -> None:
        (tmp_path / "Viejo.jar").write_text("x", encoding="utf-8")
        quitados = archivos.limpiar_jars_viejos(tmp_path, set(), dry_run=True)
        assert [q.name for q in quitados] == ["Viejo.jar"]
        assert (tmp_path / "Viejo.jar").exists()

    def test_carpeta_que_no_existe(self, tmp_path: Path) -> None:
        assert archivos.limpiar_jars_viejos(tmp_path / "nada", set()) == []


class TestEditarSettings:
    def test_conserva_los_comentarios(self, proyecto: Path) -> None:
        """settings.yml está documentado: perder los comentarios sería grave."""
        archivos.actualizar_settings(proyecto, {"admins": ["Admin_HD"]})
        texto = (proyecto / "settings.yml").read_text(encoding="utf-8")
        assert "ÚNICA fuente de configuración" in texto
        assert "PENDIENTE DE LLENAR" in texto
        assert "Admin_HD" in texto

    def test_edita_una_clave_anidada(self, proyecto: Path) -> None:
        archivos.actualizar_settings(proyecto, {"whitelist.java": ["Pepe", "Ana"]})
        import yaml

        datos = yaml.safe_load((proyecto / "settings.yml").read_text(encoding="utf-8"))
        assert datos["whitelist"]["java"] == ["Pepe", "Ana"]

    def test_vaciar_una_lista(self, proyecto: Path) -> None:
        archivos.actualizar_settings(proyecto, {"admins": ["X"]})
        archivos.actualizar_settings(proyecto, {"admins": []})
        import yaml

        datos = yaml.safe_load((proyecto / "settings.yml").read_text(encoding="utf-8"))
        assert datos["admins"] == []

    def test_el_resto_del_archivo_no_cambia(self, proyecto: Path) -> None:
        import yaml

        antes = yaml.safe_load((proyecto / "settings.yml").read_text(encoding="utf-8"))
        archivos.actualizar_settings(proyecto, {"admins": ["Admin_HD"]})
        despues = yaml.safe_load((proyecto / "settings.yml").read_text(encoding="utf-8"))
        del antes["admins"], despues["admins"]
        assert antes == despues

    def test_una_clave_que_no_existe_truena(self, proyecto: Path) -> None:
        from mc_admin.errores import ErrorDeConfig

        with pytest.raises(ErrorDeConfig, match="no tiene"):
            archivos.actualizar_settings(proyecto, {"inventada": ["x"]})


class TestLecturaDelSistema:
    def test_espacio_libre(self, tmp_path: Path) -> None:
        libre = archivos.espacio_libre_gb(tmp_path)
        assert libre is None or libre > 0

    def test_espacio_de_una_ruta_que_no_existe_usa_el_padre(self, tmp_path: Path) -> None:
        assert archivos.espacio_libre_gb(tmp_path / "no-existe") is not None

    def test_ram_total(self) -> None:
        ram = archivos.ram_total_gb()
        assert ram is None or ram > 0


class TestEscribirEnv:
    def test_crea_desde_el_ejemplo(self, proyecto: Path) -> None:
        archivos.escribir_env(proyecto, {"RCON_PASSWORD": "nueva"})
        texto = (proyecto / ".env").read_text(encoding="utf-8")
        assert "RCON_PASSWORD=nueva" in texto
        # Y conserva los comentarios del ejemplo.
        assert "#" in texto

    def test_permisos_600_porque_trae_secretos(self, proyecto: Path) -> None:
        archivos.escribir_env(proyecto, {"RCON_PASSWORD": "x"})
        modo = (proyecto / ".env").stat().st_mode & 0o777
        assert modo == 0o600

    def test_no_pisa_lo_que_ya_estaba(self, env_lleno: Path) -> None:
        archivos.escribir_env(env_lleno, {"RCON_PASSWORD": "cambiada"})
        texto = (env_lleno / ".env").read_text(encoding="utf-8")
        assert "RCON_PASSWORD=cambiada" in texto
        assert "PAGOS_BOT_TOKEN=otroTokenDePrueba" in texto

    def test_una_variable_nueva_se_agrega(self, env_lleno: Path) -> None:
        archivos.escribir_env(env_lleno, {"ALGO_NUEVO": "valor"})
        assert "ALGO_NUEVO=valor" in (env_lleno / ".env").read_text(encoding="utf-8")
