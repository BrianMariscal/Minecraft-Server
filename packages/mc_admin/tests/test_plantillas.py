"""Las configs generadas: que rendericen, sean YAML válido y lleven lo nuestro."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mc_admin.config import cargar_secretos, cargar_settings
from mc_admin.core.plantillas import (
    SALIDAS,
    TRADUCCIONES,
    _minimessage_a_legacy,
    renderizar_todo,
)
from mc_admin.errores import ErrorDeConfig


@pytest.fixture
def generados(env_lleno: Path) -> dict[str, str]:
    """Todas las configs ya renderizadas, por ruta de salida."""
    s = cargar_settings(env_lleno)
    sec = cargar_secretos(env_lleno, usar_entorno=False)
    return {
        g.ruta_relativa: g.contenido
        for g in renderizar_todo(s, sec, env_lleno / "minecraft" / "templates")
    }


class TestRenderizado:
    def test_se_generan_todas(self, generados: dict[str, str]) -> None:
        assert len(generados) == len(SALIDAS)

    def test_ninguna_sale_vacia(self, generados: dict[str, str]) -> None:
        vacias = [r for r, c in generados.items() if not c.strip()]
        assert vacias == []

    def test_todo_el_yaml_es_valido(self, generados: dict[str, str]) -> None:
        """Una config con YAML roto tumba el plugin al arrancar."""
        for ruta, contenido in generados.items():
            if ruta.endswith((".yml", ".yaml")):
                yaml.safe_load(contenido)  # truena si está mal

    def test_cada_plantilla_del_disco_esta_en_salidas(self, env_lleno: Path) -> None:
        """Una plantilla que nadie usa es una plantilla que se va a podrir."""
        en_disco = {p.name for p in (env_lleno / "minecraft" / "templates").glob("*.j2")}
        assert en_disco == set(SALIDAS)

    def test_las_traducciones_existen(self, env_lleno: Path) -> None:
        carpeta = env_lleno / "minecraft" / "translations" / "es_mx"
        faltan = [n for n in TRADUCCIONES if not (carpeta / n).is_file()]
        assert faltan == []

    def test_una_variable_que_falta_truena_claro(self, env_lleno: Path) -> None:
        """StrictUndefined: mejor un error que una config a medias."""
        mala = env_lleno / "minecraft" / "templates" / "server.properties.j2"
        mala.write_text("algo={{ variable_que_no_existe }}\n", encoding="utf-8")
        s = cargar_settings(env_lleno)
        sec = cargar_secretos(env_lleno, usar_entorno=False)
        with pytest.raises(ErrorDeConfig, match=r"server\.properties\.j2"):
            renderizar_todo(s, sec, env_lleno / "minecraft" / "templates")


class TestServerProperties:
    def test_lo_imprescindible(self, generados: dict[str, str]) -> None:
        sp = generados["server.properties"]
        assert "online-mode=false" in sp
        assert "white-list=true" in sp
        assert "enforce-whitelist=true" in sp
        assert "max-players=15" in sp

    def test_rcon_lleva_contraseña(self, generados: dict[str, str]) -> None:
        """Sin rcon.password el servidor deja RCON apagado sin avisar fuerte."""
        sp = generados["server.properties"]
        assert "enable-rcon=true" in sp
        assert "rcon.password=contrasenaDePrueba" in sp

    def test_el_motd_va_en_codigos_legacy(self, generados: dict[str, str]) -> None:
        linea = next(
            ln for ln in generados["server.properties"].splitlines() if ln.startswith("motd=")
        )
        assert "§" in linea
        assert "Minecraft HD" in linea
        # Las dos líneas, separadas por el \n literal que entiende Minecraft.
        assert "\\n" in linea
        # Nada de MiniMessage crudo, que saldría literal.
        assert "<#" not in linea


class TestRedstoneTecnica:
    def test_duplicacion_de_pistones_prendida(self, generados: dict[str, str]) -> None:
        paper = yaml.safe_load(generados["config/paper-global.yml"])
        assert paper["unsupported-settings"]["allow-piston-duplication"] is True
        assert paper["unsupported-settings"]["allow-headless-pistons"] is True

    def test_duplicacion_con_portal_del_end(self, generados: dict[str, str]) -> None:
        """OJO con el nombre: es ...teleportation, no ...teleports."""
        paper = yaml.safe_load(generados["config/paper-global.yml"])
        assert paper["unsupported-settings"]["allow-unsafe-end-portal-teleportation"] is True

    def test_los_exploits_de_verdad_siguen_apagados(self, generados: dict[str, str]) -> None:
        paper = yaml.safe_load(generados["config/paper-global.yml"])
        assert paper["unsupported-settings"]["allow-permanent-block-break-exploits"] is False


class TestGranjasNoSeRompen:
    def test_los_aldeanos_siguen_activos_de_lejos(self, generados: dict[str, str]) -> None:
        spigot = yaml.safe_load(generados["spigot.yml"])
        activacion = spigot["world-settings"]["default"]["entity-activation-range"]
        # Los subimos, NO los bajamos: es donde se rompen los criaderos.
        assert activacion["villagers"] >= 32
        assert activacion["tick-inactive-villagers"] is True
        assert activacion["villagers-active-for-panic"] is True

    def test_las_raids_siguen_funcionando(self, generados: dict[str, str]) -> None:
        spigot = yaml.safe_load(generados["spigot.yml"])
        assert spigot["world-settings"]["default"]["entity-activation-range"]["raiders"] >= 64

    def test_los_mobs_de_spawner_siguen_soltando_botin(self, generados: dict[str, str]) -> None:
        spigot = yaml.safe_load(generados["spigot.yml"])
        assert spigot["world-settings"]["default"]["nerf-spawner-mobs"] is False

    def test_los_limites_de_spawn_son_los_vanilla(self, generados: dict[str, str]) -> None:
        """Bajarlos es la forma más común de matar las granjas de mobs."""
        bukkit = yaml.safe_load(generados["bukkit.yml"])
        assert bukkit["spawn-limits"]["monsters"] == 70
        assert bukkit["ticks-per"]["monster-spawns"] == 1

    def test_las_explosiones_no_se_optimizan(self, generados: dict[str, str]) -> None:
        """optimize-explosions cambia el daño de la TNT y rompe los cañones."""
        mundos = yaml.safe_load(generados["config/paper-world-defaults.yml"])
        assert mundos["environment"]["optimize-explosions"] is False

    def test_no_hay_ningun_plugin_que_borre_mobs(self, env_lleno: Path) -> None:
        """El control de lag va SOLO por configuración."""
        manifest = yaml.safe_load(
            (env_lleno / "minecraft" / "manifest.yml").read_text(encoding="utf-8")
        )
        nombres = " ".join(p["nombre"].lower() for p in manifest["plugins"].values())
        for prohibido in ("clearlag", "limbo", "mobstacker", "farmlimiter"):
            assert prohibido not in nombres


class TestCrossplay:
    def test_geyser_en_español_de_mexico(self, generados: dict[str, str]) -> None:
        geyser = yaml.safe_load(generados["plugins/Geyser-Spigot/config.yml"])
        assert geyser["default-locale"] == "es_mx"

    def test_geyser_copia_el_motd_del_servidor(self, generados: dict[str, str]) -> None:
        """Para no tener dos MOTD que mantener."""
        geyser = yaml.safe_load(generados["plugins/Geyser-Spigot/config.yml"])
        assert geyser["motd"]["passthrough-motd"] is True
        assert geyser["java"]["auth-type"] == "floodgate"

    def test_cooldown_type_es_un_valor_valido(self, generados: dict[str, str]) -> None:
        """Geyser solo acepta crosshair, hotbar o disabled."""
        geyser = yaml.safe_load(generados["plugins/Geyser-Spigot/config.yml"])
        assert geyser["gameplay"]["cooldown-type"] in {"crosshair", "hotbar", "disabled"}

    def test_floodgate_con_vinculacion_local(self, generados: dict[str, str]) -> None:
        fg = yaml.safe_load(generados["plugins/floodgate/config.yml"])
        assert fg["player-link"]["enable-own-linking"] is True
        assert fg["player-link"]["allowed"] is True
        assert fg["player-link"]["type"] == "sqlite"
        # El global apagado: los datos se quedan en el VPS.
        assert fg["player-link"]["enable-global-linking"] is False

    def test_el_prefijo_de_bedrock_cuadra_entre_plugins(self, generados: dict[str, str]) -> None:
        """Si AuthMe no acepta el punto, los de Bedrock no pueden registrarse."""
        fg = yaml.safe_load(generados["plugins/floodgate/config.yml"])
        authme = yaml.safe_load(generados["plugins/AuthMe/config.yml"])
        prefijo = fg["username-prefix"]
        permitidos = authme["settings"]["restrictions"]["allowedNicknameCharacters"]
        assert prefijo == "."
        assert "\\." in permitidos


class TestSeguridad:
    def test_authme_protege_el_inventario(self, generados: dict[str, str]) -> None:
        authme = yaml.safe_load(generados["plugins/AuthMe/config.yml"])
        r = authme["settings"]["restrictions"]
        assert r["ProtectInventoryBeforeLogIn"] is True
        assert r["allowMovement"] is False
        assert r["allowChat"] is False

    def test_authme_usa_bcrypt(self, generados: dict[str, str]) -> None:
        authme = yaml.safe_load(generados["plugins/AuthMe/config.yml"])
        assert authme["settings"]["security"]["passwordHash"] == "BCRYPT"

    def test_el_nombre_de_bedrock_cabe_con_el_punto(self, generados: dict[str, str]) -> None:
        """Un gamertag de 16 más el punto son 17."""
        authme = yaml.safe_load(generados["plugins/AuthMe/config.yml"])
        assert authme["settings"]["restrictions"]["maxNicknameLength"] >= 17

    def test_no_hay_proxy_configurado(self, generados: dict[str, str]) -> None:
        """Con online-mode false, un proxy mal puesto es un hoyo de seguridad."""
        spigot = yaml.safe_load(generados["spigot.yml"])
        assert spigot["settings"]["bungeecord"] is False


class TestChat:
    def test_formato_por_grupo_con_etiqueta_de_admin(self, generados: dict[str, str]) -> None:
        ess = yaml.safe_load(generados["plugins/Essentials/config.yml"])
        formatos = ess["chat"]["group-formats"]
        assert "[Admin]" in formatos["admin"]
        assert "[Admin]" not in formatos["default"]

    def test_el_chat_usa_codigos_que_geyser_traduce(self, generados: dict[str, str]) -> None:
        """Nada de degradados: Bedrock los aplana a un solo color."""
        ess = yaml.safe_load(generados["plugins/Essentials/config.yml"])
        for formato in ess["chat"]["group-formats"].values():
            assert "&" in formato
            assert "gradient" not in formato

    def test_back_funciona_al_morir(self, generados: dict[str, str]) -> None:
        ess = yaml.safe_load(generados["plugins/Essentials/config.yml"])
        assert ess["register-back-in-listener"] is True

    def test_entradas_y_salidas_cortas(self, generados: dict[str, str]) -> None:
        ess = yaml.safe_load(generados["plugins/Essentials/config.yml"])
        assert "+" in ess["custom-join-message"]
        assert "-" in ess["custom-quit-message"]

    def test_sin_filtro_de_groserias(self, generados: dict[str, str]) -> None:
        cs = yaml.safe_load(generados["plugins/ChatSentinel/config.yml"])
        assert cs["blacklist"]["enabled"] is False

    def test_el_antispam_corrige_en_vez_de_bloquear(self, generados: dict[str, str]) -> None:
        cs = yaml.safe_load(generados["plugins/ChatSentinel/config.yml"])
        assert cs["flood"]["replace"] is True
        assert cs["capitalization"]["correct"] is True


class TestTumbas:
    def test_duran_una_hora_guardan_xp_y_las_abre_cualquiera(
        self, generados: dict[str, str]
    ) -> None:
        ax = yaml.safe_load(generados["plugins/AxGraves/config.yml"])
        assert ax["despawn-time-seconds"] == 3600
        assert ax["store-xp"] is True
        assert ax["xp-keep-percentage"] == 1.0
        assert ax["interact-only-own"] is False


class TestSecretos:
    def test_la_contrasena_de_rcon_llega_a_server_properties(
        self, generados: dict[str, str]
    ) -> None:
        assert "rcon.password=contrasenaDePrueba" in generados["server.properties"]

    def test_bluemap_acepta_la_descarga_o_no_arranca(self, generados: dict[str, str]) -> None:
        assert "accept-download: true" in generados["plugins/BlueMap/core.conf"]


class TestMiniMessageALegacy:
    def test_color_hex(self) -> None:
        assert _minimessage_a_legacy("<#4FB0C6>hola") == "§x§4§f§b§0§c§6hola"

    def test_negritas(self) -> None:
        assert "§l" in _minimessage_a_legacy("<bold>hola</bold>")

    def test_no_deja_resets_pegados(self) -> None:
        """Cerrar <bold> dentro de un color dejaba §r§r."""
        salida = _minimessage_a_legacy("<#4FB0C6><bold>Minecraft HD</bold></#4FB0C6>")
        assert "§r§r" not in salida
        assert not salida.endswith("§r")

    def test_texto_sin_etiquetas_no_cambia(self) -> None:
        assert _minimessage_a_legacy("hola mundo") == "hola mundo"
