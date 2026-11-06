"""Lógica de respaldos: nombrar, ordenar y elegir cuál restaurar.

Pura: trabaja con nombres de archivo y fechas. Crear, listar en disco y
restaurar es trabajo de `infra`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from mc_admin.errores import ErrorDeRespaldo

# Formato que usa itzg/mc-backup: world-20260930-143000.tgz
RE_RESPALDO = re.compile(
    r"^(?P<prefijo>[A-Za-z0-9_\-]+)-"
    r"(?P<fecha>\d{8})-(?P<hora>\d{6})"
    r"\.(?P<extension>tgz|tar\.gz|zip|tar\.zst)$"
)
FORMATO_MARCA = "%Y%m%d-%H%M%S"


@dataclass(frozen=True, slots=True)
class Respaldo:
    """Un respaldo que existe en disco."""

    archivo: str
    momento: datetime
    bytes: int

    @property
    def id(self) -> str:
        """Identificador corto y estable que el usuario puede teclear.

        Es la marca de tiempo: `mc backup restore 20260930-143000`.
        """
        return self.momento.strftime(FORMATO_MARCA)

    @property
    def tamano_legible(self) -> str:
        """El tamaño en unidades que un humano lee de un golpe."""
        tamano = float(self.bytes)
        if tamano < 1024:
            return f"{tamano:.0f} B"
        for unidad in ("KB", "MB", "GB"):
            tamano /= 1024
            if tamano < 1024 or unidad == "GB":
                return f"{tamano:.1f} {unidad}"
        raise AssertionError  # pragma: no cover — el bucle siempre sale antes

    def fecha_bonita(self, zona: ZoneInfo) -> str:
        """La fecha en español de México, para la tabla de `mc backup list`."""
        local = self.momento.astimezone(zona)
        meses = (
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        )
        return f"{local.day} de {meses[local.month - 1]} {local.year}, {local:%H:%M}"


def interpretar_nombre(archivo: str, tamano: int, zona: ZoneInfo) -> Respaldo | None:
    """Saca la fecha del nombre de un respaldo. Devuelve None si no es uno."""
    coincide = RE_RESPALDO.match(archivo)
    if not coincide:
        return None
    marca = f"{coincide['fecha']}-{coincide['hora']}"
    try:
        # itzg/mc-backup nombra con la hora local del contenedor, que es la
        # misma zona que le pasamos por TZ en el docker-compose.
        momento = datetime.strptime(marca, FORMATO_MARCA).replace(tzinfo=zona)
    except ValueError:
        return None
    return Respaldo(archivo, momento, tamano)


def ordenar_recientes_primero(respaldos: list[Respaldo]) -> list[Respaldo]:
    """Del más nuevo al más viejo: es el orden en que uno los busca."""
    return sorted(respaldos, key=lambda r: r.momento, reverse=True)


def buscar(respaldos: list[Respaldo], identificador: str) -> Respaldo:
    """Encuentra un respaldo por id, por nombre de archivo o por prefijo.

    Acepta también "ultimo" / "último" para el más reciente, que es lo que uno
    quiere el 90% de las veces.

    Raises:
        ErrorDeRespaldo: si no existe o si el prefijo es ambiguo.
    """
    if not respaldos:
        raise ErrorDeRespaldo(
            "no hay ningún respaldo todavía",
            pista="Haz uno con `mc backup now`.",
        )

    ordenados = ordenar_recientes_primero(respaldos)
    clave = identificador.strip().lower()

    if clave in {"ultimo", "último", "last", "-1"}:
        return ordenados[0]

    exactos = [r for r in ordenados if clave in (r.id.lower(), r.archivo.lower())]
    if len(exactos) == 1:
        return exactos[0]

    parciales = [r for r in ordenados if r.id.lower().startswith(clave)]
    if len(parciales) == 1:
        return parciales[0]
    if len(parciales) > 1:
        raise ErrorDeRespaldo(
            f"'{identificador}' coincide con {len(parciales)} respaldos",
            pista="Dame más dígitos. Mira la lista con `mc backup list`.",
        )

    raise ErrorDeRespaldo(
        f"no encontré ningún respaldo que se llame '{identificador}'",
        pista="Mira los que hay con `mc backup list`.",
    )


def cuales_sobran(
    respaldos: list[Respaldo], conservar_dias: int, ahora: datetime
) -> list[Respaldo]:
    """Respaldos más viejos que la ventana de retención.

    Siempre conservamos el más reciente, pase lo que pase: si el server estuvo
    apagado una semana, borrar el único respaldo que queda sería un desastre.
    """
    if not respaldos:
        return []
    ordenados = ordenar_recientes_primero(respaldos)
    limite = ahora.timestamp() - conservar_dias * 86400
    return [r for r in ordenados[1:] if r.momento.timestamp() < limite]
