"""Renderizado de las configs del servidor a partir de plantillas + settings.yml.

Esta capa decide QUÉ se genera y con qué datos. Escribir a disco es trabajo de
`infra.archivos`, así que aquí todo devuelve texto.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound
from jinja2 import TemplateSyntaxError as JinjaSyntaxError

from mc_admin.config import Settings
from mc_admin.errores import ErrorDeConfig

# Plantilla -> ruta de salida relativa a minecraft/generated/.
# La ruta de salida es también la ruta DENTRO de la carpeta de datos del
# servidor, así `mc build` solo copia respetando el árbol.
SALIDAS: dict[str, str] = {
    "server.properties.j2": "server.properties",
    "paper-global.yml.j2": "config/paper-global.yml",
    "paper-world-defaults.yml.j2": "config/paper-world-defaults.yml",
    "spigot.yml.j2": "spigot.yml",
    "bukkit.yml.j2": "bukkit.yml",
    "geyser-config.yml.j2": "plugins/Geyser-Spigot/config.yml",
    "floodgate-config.yml.j2": "plugins/floodgate/config.yml",
    "essentials-config.yml.j2": "plugins/Essentials/config.yml",
    "authme-config.yml.j2": "plugins/AuthMe/config.yml",
    "discordsrv-config.yml.j2": "plugins/DiscordSRV/config.yml",
    "axgraves-config.yml.j2": "plugins/AxGraves/config.yml",
    "luckperms-config.yml.j2": "plugins/LuckPerms/config.yml",
    "bluemap-core.conf.j2": "plugins/BlueMap/core.conf",
    "bluemap-webserver.conf.j2": "plugins/BlueMap/webserver.conf",
    "chatsentinel-config.yml.j2": "plugins/ChatSentinel/config.yml",
    "coreprotect-config.yml.j2": "plugins/CoreProtect/config.yml",
    "skinsrestorer-config.yml.j2": "plugins/SkinsRestorer/config.yml",
    "gsit-config.yml.j2": "plugins/GSit/config.yml",
    "bienvenida.txt.j2": "mensajes/bienvenida.txt",
    "luckperms-grupos.txt.j2": "mensajes/luckperms-grupos.txt",
}


@dataclass(frozen=True, slots=True)
class ArchivoGenerado:
    """Una config lista para escribirse."""

    ruta_relativa: str
    contenido: str

    @property
    def nombre(self) -> str:
        return Path(self.ruta_relativa).name


def _minimessage_a_legacy(texto: str) -> str:
    """Pasa un subconjunto de MiniMessage a códigos § (legacy).

    server.properties y algunos plugins viejos solo entienden códigos §, y es
    justo lo que Geyser traduce mejor a Bedrock. Solo soportamos lo que de
    verdad usamos en settings.yml: colores hex, <bold> y <white>.

    No metemos degradados a propósito: Bedrock los aplana a un solo color y se
    ve peor que un color sólido bien elegido.
    """
    import re

    resultado = texto

    # <#RRGGBB> -> §x§R§R§G§G§B§B, que es como Spigot codifica hex.
    def hex_a_legacy(match: re.Match[str]) -> str:
        hexa = match.group(1)
        return "§x" + "".join(f"§{c}" for c in hexa.lower())

    resultado = re.sub(r"<#([0-9A-Fa-f]{6})>", hex_a_legacy, resultado)
    resultado = re.sub(r"</#[0-9A-Fa-f]{6}>", "§r", resultado)
    simples = {
        "<bold>": "§l",
        "</bold>": "§r",
        "<white>": "§f",
        "</white>": "§r",
        "<reset>": "§r",
    }
    for k, v in simples.items():
        resultado = resultado.replace(k, v)
    return resultado


def _yaml_str(valor: Any) -> str:
    """Escapa un valor para meterlo entre comillas dobles en YAML."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, int | float | Decimal):
        return str(valor)
    texto = str(valor).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{texto}"'


def crear_entorno(carpeta_templates: Path) -> Environment:
    """Arma el entorno de Jinja2.

    `StrictUndefined` hace que una variable que falte truene al renderizar en
    vez de salir vacía: preferimos un error claro a una config a medias.
    """
    entorno = Environment(
        loader=FileSystemLoader(carpeta_templates),
        undefined=StrictUndefined,
        autoescape=False,  # noqa: S701 — generamos YAML/properties, no HTML
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    entorno.filters["legacy"] = _minimessage_a_legacy
    entorno.filters["yaml_str"] = _yaml_str
    return entorno


def construir_contexto(settings: Settings) -> dict[str, Any]:
    """Arma el diccionario que ven todas las plantillas.

    Las plantillas NO reciben el objeto Settings crudo: les damos un contexto
    plano y explícito, para que se lea de un golpe qué dato usa cada config.
    """
    s = settings
    motd_legacy_1 = _minimessage_a_legacy(s.servidor.motd.linea_1)
    motd_legacy_2 = _minimessage_a_legacy(s.servidor.motd.linea_2)

    return {
        # Identidad
        "nombre": s.servidor.nombre,
        "motd_1": s.servidor.motd.linea_1,
        "motd_2": s.servidor.motd.linea_2,
        "motd_legacy": f"{motd_legacy_1}\\n{motd_legacy_2}",
        "semilla": s.servidor.semilla,
        # Jugadores y mundo
        "max_jugadores": s.servidor.max_jugadores,
        "dificultad": s.servidor.dificultad,
        "modo_juego": s.servidor.modo_juego,
        "pvp": s.servidor.pvp,
        "view_distance": s.rendimiento.view_distance,
        "simulation_distance": s.rendimiento.simulation_distance,
        "dormir_con_un_jugador": s.mundo.dormir_con_un_jugador,
        # Puertos
        "puerto_java": s.puertos.java,
        "puerto_bedrock": s.puertos.bedrock,
        "puerto_bluemap": s.puertos.bluemap,
        "puerto_rcon": s.puertos.rcon,
        # Idioma
        "idioma": s.idioma.codigo,
        "geyser_locale": s.idioma.geyser_locale,
        # Seguridad
        "online_mode": s.seguridad.online_mode,
        "whitelist": s.seguridad.whitelist,
        "kick_whitelist": s.seguridad.mensaje_kick_whitelist,
        "prefijo_bedrock": s.seguridad.prefijo_bedrock,
        "authme": s.seguridad.authme.model_dump(),
        # Técnico
        "duplicacion_pistones": s.tecnico.duplicacion_pistones,
        "duplicacion_portal_end": s.tecnico.duplicacion_portal_end,
        # Chat
        "chat": s.chat.model_dump(),
        # Tumbas
        "tumbas": s.tumbas.model_dump(),
        # Discord
        "discord": s.discord.model_dump(),
        # Versiones
        "version_minecraft": s.versiones.minecraft,
    }


def renderizar_todo(
    settings: Settings, carpeta_templates: Path, solo: str | None = None
) -> list[ArchivoGenerado]:
    """Renderiza todas las plantillas (o una sola, si pasas `solo`).

    Raises:
        ErrorDeConfig: si falta una plantilla, tiene un error de sintaxis o usa
            una variable que no existe en el contexto.
    """
    entorno = crear_entorno(carpeta_templates)
    contexto = construir_contexto(settings)
    salidas = {solo: SALIDAS[solo]} if solo else SALIDAS

    generados: list[ArchivoGenerado] = []
    for plantilla, destino in salidas.items():
        try:
            contenido = entorno.get_template(plantilla).render(**contexto)
        except TemplateNotFound as exc:
            raise ErrorDeConfig(
                f"falta la plantilla minecraft/templates/{plantilla}",
                pista="Si la borraste, recupérala con git checkout.",
            ) from exc
        except JinjaSyntaxError as exc:
            raise ErrorDeConfig(
                f"la plantilla {plantilla} tiene un error de sintaxis "
                f"en la línea {exc.lineno}: {exc.message}"
            ) from exc
        except Exception as exc:
            raise ErrorDeConfig(
                f"no pude renderizar {plantilla}: {exc}",
                pista="Suele ser una variable que la plantilla pide y settings.yml no tiene.",
            ) from exc
        generados.append(ArchivoGenerado(destino, contenido))

    return generados
