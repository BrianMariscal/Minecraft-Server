"""Carga y validación de `settings.yml` y `.env`.

Todo lo configurable del proyecto pasa por aquí. Si algo está mal, lanzamos
`ErrorDeConfig` diciendo QUÉ está mal y DÓNDE, en español, sin traceback.
"""

from __future__ import annotations

import os
import re
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from mc_admin.errores import ErrorDeConfig

# Nombres de archivo que esperamos en la raíz del proyecto.
ARCHIVO_SETTINGS = "settings.yml"
ARCHIVO_ENV = ".env"
ARCHIVO_ENV_EJEMPLO = ".env.example"

# Marcador que dejamos en settings.yml donde falta llenar datos.
MARCADOR_PENDIENTE = "CAMBIAME"

_RE_NOMBRE_JAVA = re.compile(r"^[A-Za-z0-9_]{3,16}$")
_RE_PUERTO_LIBRE = re.compile(r"^\d+$")

Puerto = Annotated[int, Field(ge=1, le=65535)]


class _Base(BaseModel):
    """Base común: prohibimos campos desconocidos para atrapar typos."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# --------------------------------------------------------------------------- #
#  settings.yml
# --------------------------------------------------------------------------- #


class Motd(_Base):
    """Las dos líneas del MOTD, en formato MiniMessage."""

    linea_1: str = Field(min_length=1)
    linea_2: str = Field(min_length=1)


class Servidor(_Base):
    nombre: str = Field(min_length=1, max_length=48)
    motd: Motd
    max_jugadores: int = Field(ge=1, le=200)
    dificultad: Literal["peaceful", "easy", "normal", "hard"]
    modo_juego: Literal["survival", "creative", "adventure", "spectator"]
    pvp: bool
    semilla: str = ""
    logo: str = "logo/logo.png"
    # La IP o el dominio con que se conecta la banda; solo lo usa `mc status`.
    direccion: str = ""


class Versiones(_Base):
    minecraft: str = Field(pattern=r"^\d+(\.\d+){0,2}$")
    imagen_servidor: str = Field(min_length=1)
    imagen_respaldos: str = Field(min_length=1)

    @field_validator("imagen_servidor", "imagen_respaldos")
    @classmethod
    def _sin_latest(cls, v: str) -> str:
        """Prohibimos tags móviles: el proyecto se construye reproducible."""
        tag = v.rsplit(":", 1)[-1] if ":" in v else ""
        if tag in {"", "latest", "stable"}:
            msg = (
                f"la imagen de Docker '{v}' usa un tag móvil. Fija una versión "
                "exacta (por ejemplo itzg/minecraft-server:2026.9.2-java25) para "
                "que el servidor no cambie solo de versión al reiniciar"
            )
            raise ValueError(msg)
        return v


class Recursos(_Base):
    memoria: str = Field(pattern=r"^\d+[MG]$")
    flags_aikar: bool = True


class Rendimiento(_Base):
    view_distance: int = Field(ge=3, le=32)
    simulation_distance: int = Field(ge=3, le=32)

    @model_validator(mode="after")
    def _simulacion_no_mayor_que_vista(self) -> Self:
        if self.simulation_distance > self.view_distance:
            msg = (
                "rendimiento.simulation_distance no puede ser mayor que "
                "rendimiento.view_distance: simular chunks que nadie ve es "
                "gastar CPU de a gratis"
            )
            raise ValueError(msg)
        return self


class Puertos(_Base):
    java: Puerto
    bedrock: Puerto
    rcon: Puerto

    @model_validator(mode="after")
    def _sin_repetidos(self) -> Self:
        # bedrock es UDP, así que puede repetir número con un TCP sin choque,
        # pero lo prohibimos igual para no confundir al configurar el firewall.
        usados = [self.java, self.bedrock, self.rcon]
        repetidos = {p for p in usados if usados.count(p) > 1}
        if repetidos:
            msg = (
                f"hay puertos repetidos en la sección `puertos`: "
                f"{', '.join(str(p) for p in sorted(repetidos))}. "
                "Dale un número distinto a cada servicio"
            )
            raise ValueError(msg)
        return self


class Idioma(_Base):
    codigo: str = Field(pattern=r"^[a-z]{2}_[a-z]{2}$")
    geyser_locale: str = Field(pattern=r"^[a-z]{2}_[a-z]{2}$")


class ConfigAuthme(_Base):
    min_password: int = Field(ge=4, le=64)
    max_password: int = Field(ge=8, le=256)
    max_intentos: int = Field(ge=1, le=20)
    timeout_login: int = Field(ge=10, le=600)

    @model_validator(mode="after")
    def _rango_coherente(self) -> Self:
        if self.min_password > self.max_password:
            msg = (
                "seguridad.authme.min_password es mayor que max_password: nadie podría registrarse"
            )
            raise ValueError(msg)
        return self


class Seguridad(_Base):
    online_mode: bool
    whitelist: bool
    mensaje_kick_whitelist: str = Field(min_length=1)
    prefijo_bedrock: str = Field(min_length=0, max_length=2)
    authme: ConfigAuthme

    @model_validator(mode="after")
    def _no_premium_exige_whitelist(self) -> Self:
        """Un servidor abierto y sin whitelist es tomado en días."""
        if not self.online_mode and not self.whitelist:
            msg = (
                "con seguridad.online_mode: false (servidor no premium) necesitas "
                "seguridad.whitelist: true. Sin whitelist cualquiera puede entrar "
                "con el nombre que quiera, incluido el de un admin"
            )
            raise ValueError(msg)
        return self


class Mundo(_Base):
    radio_pregen: int = Field(ge=100, le=20000)
    dormir_con_un_jugador: bool


class Tecnico(_Base):
    duplicacion_pistones: bool
    duplicacion_portal_end: bool


class RespaldoRemoto(_Base):
    activo: bool = False
    destino: str = ""
    # Subir 1-3 GB a la nube cada 6 horas es mucho; una vez al día basta.
    intervalo: str = Field(default="24h", pattern=r"^\d+[mhd]$")

    @model_validator(mode="after")
    def _destino_si_activo(self) -> Self:
        if self.activo and not self.destino:
            msg = (
                "respaldos.remoto.activo es true pero respaldos.remoto.destino está "
                "vacío. Pon el remoto de rclone, por ejemplo 'gdrive:minecraft-hd'"
            )
            raise ValueError(msg)
        if self.activo and ":" not in self.destino:
            msg = (
                f"respaldos.remoto.destino '{self.destino}' no trae el remoto de rclone. "
                "Se escribe remoto:carpeta, por ejemplo 'gdrive:minecraft-hd'"
            )
            raise ValueError(msg)
        return self


class Respaldos(_Base):
    intervalo: str = Field(pattern=r"^\d+[mhd]$")
    conservar_dias: int = Field(ge=1, le=365)
    remoto: RespaldoRemoto


class Recordatorio(_Base):
    activo: bool = False
    cada_minutos: int = Field(default=60, ge=5, le=1440)


class AntiSpam(_Base):
    activo: bool = True
    segundos_entre_mensajes: int = Field(ge=0, le=60)
    max_mayusculas_pct: int = Field(ge=10, le=100)
    filtro_groserias: bool = False


class Chat(_Base):
    formato_default: str = Field(min_length=1)
    formato_admin: str = Field(min_length=1)
    entrada: str = Field(min_length=1)
    salida: str = Field(min_length=1)
    primera_vez: str = Field(min_length=1)
    recordatorio: Recordatorio
    anti_spam: AntiSpam

    @field_validator("formato_default", "formato_admin")
    @classmethod
    def _tiene_placeholders(cls, v: str) -> str:
        faltan = [p for p in ("{nombre}", "{mensaje}") if p not in v]
        if faltan:
            msg = f"al formato de chat le faltan los marcadores {', '.join(faltan)}"
            raise ValueError(msg)
        return v

    @field_validator("entrada", "salida", "primera_vez")
    @classmethod
    def _tiene_nombre(cls, v: str) -> str:
        if "{nombre}" not in v:
            msg = "al mensaje le falta el marcador {nombre}"
            raise ValueError(msg)
        return v


class Tumbas(_Base):
    duracion_minutos: int = Field(ge=1, le=10080)
    guardar_xp: bool
    cualquiera_puede_abrir: bool


class Participante(_Base):
    """Alguien que coopera para el VPS."""

    nombre: str = Field(min_length=1, max_length=32)
    discord_id: int = Field(ge=0)
    monto_mxn: Decimal | None = None

    @field_validator("monto_mxn")
    @classmethod
    def _monto_positivo(cls, v: Decimal | None) -> Decimal | None:
        if v is not None and v <= 0:
            msg = "el monto de un participante tiene que ser mayor que cero"
            raise ValueError(msg)
        return v


class Tesorero(_Base):
    nombre: str = Field(min_length=1, max_length=32)
    discord_id: int = Field(ge=0)


class AvisosPagos(_Base):
    dias_antes: int = Field(ge=0, le=28)
    cada_dias_despues: int = Field(ge=1, le=30)


class Pagos(_Base):
    activo: bool
    zona_horaria: str
    dia_de_pago: int = Field(ge=1, le=31)
    monto_total_mxn: Decimal
    reparto: Literal["iguales", "personalizado"]
    participantes: list[Participante]
    tesorero: Tesorero
    rol_admin_id: int = Field(default=0, ge=0)
    avisos: AvisosPagos

    @field_validator("zona_horaria")
    @classmethod
    def _zona_existe(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = (
                f"pagos.zona_horaria '{v}' no existe. Usa un nombre de la base "
                "de datos IANA, por ejemplo 'America/Mexico_City'"
            )
            raise ValueError(msg) from exc
        return v

    @field_validator("monto_total_mxn")
    @classmethod
    def _total_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            msg = "pagos.monto_total_mxn tiene que ser mayor que cero"
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _reparto_coherente(self) -> Self:
        if not self.activo:
            return self
        if self.reparto == "personalizado":
            sin_monto = [p.nombre for p in self.participantes if p.monto_mxn is None]
            if sin_monto:
                msg = (
                    "pagos.reparto es 'personalizado' pero estos participantes no "
                    f"tienen monto_mxn: {', '.join(sin_monto)}"
                )
                raise ValueError(msg)
        return self

    @property
    def pendiente_de_llenar(self) -> bool:
        """True si todavía trae los `CAMBIAME` del archivo de ejemplo."""
        if self.tesorero.nombre == MARCADOR_PENDIENTE or self.tesorero.discord_id == 0:
            return True
        return any(p.nombre == MARCADOR_PENDIENTE or p.discord_id == 0 for p in self.participantes)


class Settings(_Base):
    """settings.yml completo y validado."""

    servidor: Servidor
    versiones: Versiones
    recursos: Recursos
    rendimiento: Rendimiento
    puertos: Puertos
    idioma: Idioma
    seguridad: Seguridad
    mundo: Mundo
    tecnico: Tecnico
    respaldos: Respaldos
    chat: Chat
    tumbas: Tumbas
    pagos: Pagos
    admins: list[str] = Field(default_factory=list)
    # Admins que juegan en Bedrock: su gamertag (sin el punto). Tienen que
    # estar también en whitelist.bedrock con su XUID; `mc admin add --bedrock`
    # hace las dos cosas.
    admins_bedrock: list[str] = Field(default_factory=list)
    whitelist: Whitelist

    @field_validator("admins")
    @classmethod
    def _nombres_java_validos(cls, v: list[str]) -> list[str]:
        malos = [n for n in v if not _RE_NOMBRE_JAVA.match(n)]
        if malos:
            msg = (
                f"estos nombres de admin no son nombres válidos de Minecraft Java: "
                f"{', '.join(malos)}. Deben tener de 3 a 16 caracteres, solo letras, "
                "números y guion bajo"
            )
            raise ValueError(msg)
        return v


class Whitelist(_Base):
    java: list[str] = Field(default_factory=list)
    bedrock: list[str] = Field(default_factory=list)
    # El XUID de Xbox de cada gamertag de `bedrock`. De ahí sale el UUID con
    # el que Floodgate identifica al jugador. Lo llena `mc whitelist add
    # --bedrock`; a mano casi nunca hace falta.
    xuid: dict[str, int] = Field(default_factory=dict)

    @field_validator("java")
    @classmethod
    def _java_validos(cls, v: list[str]) -> list[str]:
        malos = [n for n in v if not _RE_NOMBRE_JAVA.match(n)]
        if malos:
            msg = (
                f"estos nombres de la whitelist de Java no son válidos: "
                f"{', '.join(malos)}. De 3 a 16 caracteres, letras, números y guion bajo"
            )
            raise ValueError(msg)
        return v

    @field_validator("bedrock")
    @classmethod
    def _bedrock_sin_prefijo(cls, v: list[str]) -> list[str]:
        """El punto de Floodgate lo pone `mc`, no el usuario."""
        con_punto = [n for n in v if n.startswith(".")]
        if con_punto:
            msg = (
                f"quita el punto de estos nombres de la whitelist de Bedrock: "
                f"{', '.join(con_punto)}. El prefijo de Floodgate lo agrega `mc` solo"
            )
            raise ValueError(msg)
        return v


# Resolvemos la referencia adelantada a Whitelist dentro de Settings.
Settings.model_rebuild()


# --------------------------------------------------------------------------- #
#  .env
# --------------------------------------------------------------------------- #


class Secretos(_Base):
    """Lo que vive en .env. Nunca se loguea ni se imprime."""

    rcon_password: str = ""
    pagos_bot_token: str = ""
    pagos_guild_id: str = ""
    pagos_canal_id: str = ""
    # Opcional: canal donde el bot avisa si el servidor de Minecraft se cae.
    alertas_canal_id: str = ""
    tz: str = "America/Mexico_City"

    def __repr__(self) -> str:
        """Nunca mostramos los valores, solo qué está lleno y qué no."""
        llenos = sorted(k for k, v in self.model_dump().items() if v and k != "tz")
        return f"Secretos(llenos={llenos})"

    __str__ = __repr__

    def faltantes_para(self, *, pagos: bool) -> list[str]:
        """Devuelve los nombres de variables que faltan según lo que esté activo."""
        faltan: list[str] = []
        if not self.rcon_password:
            faltan.append("RCON_PASSWORD")
        if pagos:
            if not self.pagos_bot_token:
                faltan.append("PAGOS_BOT_TOKEN")
            if not self.pagos_guild_id:
                faltan.append("PAGOS_GUILD_ID")
            if not self.pagos_canal_id:
                faltan.append("PAGOS_CANAL_ID")
        return faltan


# --------------------------------------------------------------------------- #
#  Carga
# --------------------------------------------------------------------------- #


def _traducir_errores(exc: ValidationError, archivo: str) -> str:
    """Convierte un ValidationError de pydantic en texto legible en español."""
    lineas: list[str] = []
    for err in exc.errors():
        ruta = ".".join(str(p) for p in err["loc"]) or "(raíz)"
        detalle = err["msg"]
        # pydantic prefija los errores de nuestros validadores con "Value error, ".
        detalle = detalle.removeprefix("Value error, ")
        lineas.append(f"  • {ruta}: {detalle}")
    return f"{archivo} tiene errores:\n" + "\n".join(lineas)


def cargar_settings(raiz: Path) -> Settings:
    """Lee y valida settings.yml.

    Args:
        raiz: carpeta del proyecto (la que tiene settings.yml).

    Raises:
        ErrorDeConfig: si el archivo falta, no es YAML válido o no pasa validación.
    """
    ruta = raiz / ARCHIVO_SETTINGS
    if not ruta.is_file():
        raise ErrorDeConfig(
            f"no encontré {ARCHIVO_SETTINGS} en {raiz}",
            pista="Corre `mc` desde la carpeta del proyecto, la que tiene settings.yml.",
        )

    try:
        crudo = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErrorDeConfig(
            f"{ARCHIVO_SETTINGS} no es YAML válido: {exc}",
            pista="Revisa la indentación; en YAML se usan espacios, nunca tabuladores.",
        ) from exc

    if not isinstance(crudo, dict):
        raise ErrorDeConfig(f"{ARCHIVO_SETTINGS} está vacío o no es un mapa de claves")

    try:
        return Settings.model_validate(crudo)
    except ValidationError as exc:
        raise ErrorDeConfig(
            _traducir_errores(exc, ARCHIVO_SETTINGS),
            pista="Compara tu archivo con los comentarios de settings.yml.",
        ) from exc


def _leer_archivo_env(ruta: Path) -> dict[str, str]:
    """Parsea un .env sencillo: CLAVE=valor, # comentarios, líneas vacías."""
    datos: dict[str, str] = {}
    for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), start=1):
        limpia = linea.strip()
        if not limpia or limpia.startswith("#"):
            continue
        if "=" not in limpia:
            raise ErrorDeConfig(
                f"{ARCHIVO_ENV}, línea {numero}: esperaba CLAVE=valor y encontré '{limpia}'"
            )
        clave, _, valor = limpia.partition("=")
        datos[clave.strip()] = valor.strip().strip("\"'")
    return datos


def cargar_secretos(raiz: Path, *, usar_entorno: bool = True) -> Secretos:
    """Lee .env y, si falta algo, lo completa con variables de entorno.

    Las variables de entorno ganan sobre .env: así el docker-compose o el VPS
    pueden sobrescribir sin editar archivos.
    """
    datos: dict[str, str] = {}
    ruta = raiz / ARCHIVO_ENV
    if ruta.is_file():
        datos.update(_leer_archivo_env(ruta))

    campos = set(Secretos.model_fields)
    if usar_entorno:
        for clave in campos:
            valor = os.environ.get(clave.upper())
            if valor:
                datos[clave.upper()] = valor

    # Pasamos de CLAVE_MAYUSCULA a nombre_de_campo e ignoramos lo desconocido,
    # para que un .env con variables extra no tumbe el arranque.
    normalizado = {k.lower(): v for k, v in datos.items() if k.lower() in campos}
    return Secretos.model_validate(normalizado)


def encontrar_raiz(inicio: Path | None = None) -> Path:
    """Busca hacia arriba la carpeta del proyecto (la que tiene settings.yml)."""
    actual = (inicio or Path.cwd()).resolve()
    for candidata in (actual, *actual.parents):
        if (candidata / ARCHIVO_SETTINGS).is_file():
            return candidata
    raise ErrorDeConfig(
        f"no encontré {ARCHIVO_SETTINGS} ni aquí ni en ninguna carpeta de arriba",
        pista="Métete a la carpeta del proyecto (la que tiene settings.yml).",
    )
