"""Configuración del bot: lee la sección `pagos` de settings.yml y el .env.

Comparte settings.yml con el resto del proyecto a propósito: un solo archivo
que editar. El bot lo monta de solo lectura en su contenedor.
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pagos_bot.domain.cobro import Participante, Reparto
from pagos_bot.domain.dinero import Dinero

MARCADOR_PENDIENTE = "CAMBIAME"


class ErrorDeConfig(Exception):
    """settings.yml o el entorno están mal. El mensaje se le muestra al usuario."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, str_strip_whitespace=True)


class ParticipanteConfig(_Base):
    nombre: str = Field(min_length=1, max_length=32)
    discord_id: int = Field(ge=0)
    monto_mxn: Decimal | None = None

    def a_dominio(self) -> Participante:
        return Participante(
            nombre=self.nombre,
            discord_id=self.discord_id,
            monto_fijo=Dinero.de_pesos(self.monto_mxn) if self.monto_mxn is not None else None,
        )


class TesoreroConfig(_Base):
    nombre: str = Field(min_length=1, max_length=32)
    discord_id: int = Field(ge=0)


class AvisosConfig(_Base):
    dias_antes: int = Field(ge=0, le=28)
    cada_dias_despues: int = Field(ge=1, le=30)


class PagosConfig(_Base):
    """La sección `pagos` de settings.yml, ya validada."""

    activo: bool = True
    zona_horaria: str = "America/Mexico_City"
    dia_de_pago: int = Field(ge=1, le=31)
    monto_total_mxn: Decimal
    reparto: Reparto
    participantes: list[ParticipanteConfig]
    tesorero: TesoreroConfig
    rol_admin_id: int = Field(default=0, ge=0)
    avisos: AvisosConfig

    @field_validator("zona_horaria")
    @classmethod
    def _zona_existe(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            msg = f"la zona horaria '{v}' no existe; usa algo como America/Mexico_City"
            raise ValueError(msg) from exc
        return v

    @field_validator("monto_total_mxn")
    @classmethod
    def _total_positivo(cls, v: Decimal) -> Decimal:
        if v <= 0:
            msg = "el monto total del VPS tiene que ser mayor que cero"
            raise ValueError(msg)
        return v

    # -- lo que usa el resto del bot --------------------------------------- #

    @property
    def zona(self) -> ZoneInfo:
        return ZoneInfo(self.zona_horaria)

    @property
    def total(self) -> Dinero:
        return Dinero.de_pesos(self.monto_total_mxn)

    @property
    def gente(self) -> list[Participante]:
        return [p.a_dominio() for p in self.participantes]

    @property
    def esta_sin_llenar(self) -> bool:
        """¿Todavía trae los CAMBIAME del archivo de ejemplo?"""
        if self.tesorero.nombre == MARCADOR_PENDIENTE or self.tesorero.discord_id == 0:
            return True
        return any(p.nombre == MARCADOR_PENDIENTE or p.discord_id == 0 for p in self.participantes)

    def puede_administrar(self, discord_id: int, roles: list[int]) -> bool:
        """¿Esta persona puede confirmar pagos y mover el mes?"""
        if discord_id == self.tesorero.discord_id:
            return True
        return bool(self.rol_admin_id) and self.rol_admin_id in roles


class Entorno(_Base):
    """Lo que viene del .env, por variables de entorno."""

    token: str
    guild_id: int
    canal_id: int
    ruta_db: Path

    @classmethod
    def desde_entorno(cls) -> Self:
        """Lee las variables. Truena con un mensaje claro si falta alguna."""
        faltan = [
            v
            for v in ("PAGOS_BOT_TOKEN", "PAGOS_GUILD_ID", "PAGOS_CANAL_ID")
            if not os.environ.get(v)
        ]
        if faltan:
            msg = (
                "faltan variables de entorno: " + ", ".join(faltan) + ".\n"
                "Están en .env; corre `mc setup` para llenarlas."
            )
            raise ErrorDeConfig(msg)

        try:
            return cls(
                token=os.environ["PAGOS_BOT_TOKEN"],
                guild_id=int(os.environ["PAGOS_GUILD_ID"]),
                canal_id=int(os.environ["PAGOS_CANAL_ID"]),
                ruta_db=Path(os.environ.get("PAGOS_DB", "/datos/pagos.sqlite")),
            )
        except ValueError as exc:
            msg = (
                "PAGOS_GUILD_ID y PAGOS_CANAL_ID tienen que ser números.\n"
                "Son los IDs de Discord: clic derecho > Copiar ID, con el modo\n"
                "desarrollador prendido. Ver docs/bot-pagos.md."
            )
            raise ErrorDeConfig(msg) from exc

    def __repr__(self) -> str:
        """Nunca imprimimos el token."""
        return f"Entorno(guild_id={self.guild_id}, canal_id={self.canal_id})"

    __str__ = __repr__


def cargar_pagos(ruta_settings: Path) -> PagosConfig:
    """Lee la sección `pagos` de settings.yml.

    Raises:
        ErrorDeConfig: si el archivo falta, no es YAML o no pasa validación.
    """
    if not ruta_settings.is_file():
        msg = (
            f"no encontré {ruta_settings}.\n"
            "El contenedor lo monta desde la raíz del proyecto; revisa el "
            "docker-compose.yml."
        )
        raise ErrorDeConfig(msg)

    try:
        crudo = yaml.safe_load(ruta_settings.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"settings.yml no es YAML válido: {exc}"
        raise ErrorDeConfig(msg) from exc

    if not isinstance(crudo, dict) or "pagos" not in crudo:
        msg = "settings.yml no tiene la sección `pagos`"
        raise ErrorDeConfig(msg)

    try:
        return PagosConfig.model_validate(crudo["pagos"])
    except (ValidationError, InvalidOperation) as exc:
        detalle = (
            "\n".join(
                "  • pagos."
                + ".".join(str(p) for p in e["loc"])
                + ": "
                + e["msg"].removeprefix("Value error, ")
                for e in exc.errors()
            )
            if isinstance(exc, ValidationError)
            else str(exc)
        )
        msg = f"la sección `pagos` de settings.yml tiene errores:\n{detalle}"
        raise ErrorDeConfig(msg) from exc
