"""Detección de mensajes que siguen en inglés.

Lo usa `mc doctor` para avisar que quedó texto sin traducir en las configs
generadas y en los archivos de mensajes de los plugins.

Es heurístico a propósito: no intentamos "detectar idioma" de verdad, nada más
buscamos palabras que solo aparecen en inglés y que son típicas de los mensajes
de plugins de Minecraft.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Palabras que delatan un mensaje en inglés sin traducir. Están escogidas para
# no chocar con el español ni con claves de YAML:
#   - "no" y "error" son iguales en los dos idiomas, así que no van.
#   - "server", "plugin" y "chat" los usamos en español, tampoco van.
PALABRAS_INGLESAS: frozenset[str] = frozenset(
    {
        "you",
        "your",
        "yourself",
        "please",
        "successfully",
        "success",
        "failed",
        "unknown",
        "permission",
        "denied",
        "allowed",
        "disabled",
        "enabled",
        "player",
        "players",
        "already",
        "cannot",
        "could",
        "doesn",
        "don",
        "isn",
        "must",
        "need",
        "needs",
        "available",
        "unavailable",
        "invalid",
        "missing",
        "wrong",
        "correct",
        "incorrect",
        "password",
        "register",
        "registered",
        "login",
        "logged",
        "logout",
        "welcome",
        "goodbye",
        "joined",
        "left",
        "online",
        "offline",
        "whitelist",
        "whitelisted",
        "banned",
        "kicked",
        "muted",
        "command",
        "commands",
        "usage",
        "help",
        "reload",
        "reloaded",
        "world",
        "worlds",
        "home",
        "homes",
        "spawn",
        "teleport",
        "teleporting",
        "request",
        "requests",
        "accepted",
        "cancelled",
        "canceled",
        "expired",
        "sent",
        "received",
        "found",
        "not",
        "the",
        "this",
        "that",
        "with",
        "without",
        "from",
        "into",
        "and",
        "but",
        "for",
        "are",
        "was",
        "were",
        "has",
        "have",
        "been",
        "will",
        "would",
        "should",
        "can",
        "too",
        "now",
        "again",
        "back",
        "here",
        "there",
        "when",
        "while",
        "before",
        "after",
        "because",
        "only",
        "other",
        "others",
        "someone",
        "something",
        "nothing",
        "everyone",
        "nobody",
        "seconds",
        "minutes",
        "hours",
        "days",
        "item",
        "items",
        "inventory",
        "experience",
        "level",
        "levels",
        "death",
        "died",
        "grave",
        "sitting",
        "skin",
        "skins",
        "money",
        "balance",
    }
)

# Hint de que el valor NO es texto para el jugador, sino configuración.
_RE_CLAVE_YAML = re.compile(r"^\s*[A-Za-z0-9_.\-]+\s*:\s*$")
_RE_SOLO_SIMBOLOS = re.compile(r"^[\W\d_]*$", re.UNICODE)
# Códigos de color y marcadores que no cuentan como palabras.
_RE_RUIDO = re.compile(
    r"(§.|&[0-9a-fk-or]|<[^>]{1,40}>|\{[^}]{1,40}\}|%[a-z_]{1,40}%|https?://\S+)",
    re.IGNORECASE,
)

# Identificadores, que NO son mensajes y hay que quitar antes de contar.
#
# Sin esto el detector marcaba 94 líneas, y TODAS eran falsos positivos:
# nombres de permisos (`essentials.back.ondeath`), claves de configuración
# (`aliases: now-in-commands.yml`) y comandos de consola. Un detector que
# grita 94 veces sin razón es un detector que nadie va a volver a correr.
_RE_IDENTIFICADORES = re.compile(
    r"""(
        \b[\w-]+\.(?:yml|yaml|json|txt|properties|jar|zip|png|conf|dat)\b  # un archivo
      | \b[a-z][\w]*(?:\.[\w*]+)+\b                                      # algo.con.puntos
      | \b\w+[-_]\w[\w-]*\b                                              # kebab_o-snake
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Líneas que son comandos de consola, no mensajes para nadie.
_RE_COMANDO = re.compile(
    r"^\s*(?:lp|co|coreprotect|luckperms|execute|gamerule|whitelist|op|deop"
    r"|chunky|geyser|floodgate|essentials|mc)\s",
    re.IGNORECASE,
)
# Al menos dos palabras inglesas en la misma línea para marcarla: con una sola
# nos llenaríamos de falsos positivos por claves de configuración.
MINIMO_PALABRAS = 2


@dataclass(frozen=True, slots=True)
class LineaSospechosa:
    """Una línea que parece seguir en inglés."""

    archivo: str
    numero: int
    texto: str
    palabras: tuple[str, ...]

    @property
    def ubicacion(self) -> str:
        return f"{self.archivo}:{self.numero}"


def palabras_inglesas_en(linea: str) -> list[str]:
    """Devuelve las palabras inglesas que encuentra en una línea.

    Antes de contar, saca todo lo que no es un mensaje: códigos de color,
    marcadores, nombres de archivo, identificadores con puntos o guiones y
    las líneas que son comandos de consola.
    """
    if _RE_CLAVE_YAML.match(linea) or _RE_COMANDO.match(linea):
        return []
    limpia = _RE_RUIDO.sub(" ", linea)
    limpia = _RE_IDENTIFICADORES.sub(" ", limpia)
    if _RE_SOLO_SIMBOLOS.match(limpia):
        return []
    tokens = re.findall(r"[A-Za-z']{2,}", limpia)
    vistas: list[str] = []
    for t in tokens:
        bajo = t.lower().strip("'")
        if bajo in PALABRAS_INGLESAS and bajo not in vistas:
            vistas.append(bajo)
    return vistas


def revisar_texto(texto: str, nombre_archivo: str) -> list[LineaSospechosa]:
    """Busca líneas en inglés dentro de un texto ya leído."""
    hallazgos: list[LineaSospechosa] = []
    for numero, linea in enumerate(texto.splitlines(), start=1):
        desnuda = linea.strip()
        # Los comentarios de las plantillas están en español a propósito y
        # pueden citar nombres de opciones en inglés.
        if not desnuda or desnuda.startswith("#"):
            continue
        encontradas = palabras_inglesas_en(linea)
        if len(encontradas) >= MINIMO_PALABRAS:
            hallazgos.append(
                LineaSospechosa(nombre_archivo, numero, desnuda[:120], tuple(encontradas))
            )
    return hallazgos


def revisar_archivos(rutas: list[Path], raiz: Path) -> list[LineaSospechosa]:
    """Revisa varios archivos y devuelve todo lo sospechoso, en orden."""
    hallazgos: list[LineaSospechosa] = []
    for ruta in sorted(rutas):
        try:
            texto = ruta.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # Un archivo binario o ilegible no es asunto del traductor.
            continue
        relativa = str(ruta.relative_to(raiz)) if ruta.is_relative_to(raiz) else str(ruta)
        hallazgos.extend(revisar_texto(texto, relativa))
    return hallazgos
