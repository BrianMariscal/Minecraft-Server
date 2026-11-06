"""Guardar y leer los pagos en SQLite.

Esta capa NO tiene reglas de negocio: traduce entre el dominio y las tablas.
Quien decide qué significa cada cosa es `domain` y `services`.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path

from pagos_bot.domain.auditoria import Actor, RegistroDeAuditoria
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import Cuota, Estado, MesDeCobro, Participante, Reparto
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.esquema import migrar


class RepositorioPagos:
    """Acceso a la base de datos del bot."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(self.ruta, isolation_level=None)
        self._cx.row_factory = sqlite3.Row
        # WAL: el bot escribe mientras el contenedor de respaldos lee.
        self._cx.execute("PRAGMA journal_mode = WAL")
        self._cx.execute("PRAGMA foreign_keys = ON")
        migrar(self._cx)

    def cerrar(self) -> None:
        self._cx.close()

    def copiar_a(self, destino: Path) -> None:
        """Saca una foto consistente de la base con la API de respaldo de SQLite.

        Los respaldos copian los archivos tal cual, y una base en WAL copiada
        a medio escribir puede no abrir. Esta foto siempre abre: si la base
        principal de un respaldo sale dañada, `mc backup restore` usa esta.
        Se escribe a un temporal y se renombra, para que un respaldo nunca
        se lleve una foto a medias.
        """
        temporal = destino.with_name(destino.name + ".tmp")
        temporal.unlink(missing_ok=True)
        copia = sqlite3.connect(temporal)
        try:
            self._cx.backup(copia)
            # La foto es un solo archivo, sin -wal que se pueda quedar atrás.
            copia.execute("PRAGMA journal_mode = DELETE")
        finally:
            copia.close()
        temporal.replace(destino)

    @contextmanager
    def _transaccion(self) -> Iterator[sqlite3.Connection]:
        """Todo o nada: si truena a medias, no queda a medias."""
        self._cx.execute("BEGIN")
        try:
            yield self._cx
        except Exception:
            self._cx.execute("ROLLBACK")
            raise
        self._cx.execute("COMMIT")

    # -- periodos ---------------------------------------------------------- #

    def guardar_mes(self, mes: MesDeCobro, reparto: Reparto) -> None:
        """Escribe un mes completo. Si ya existía, lo reemplaza."""
        with self._transaccion() as cx:
            cx.execute(
                "INSERT INTO periodos (clave, total_centavos, reparto, abierto_en) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET total_centavos=excluded.total_centavos, "
                "reparto=excluded.reparto",
                (
                    mes.periodo.clave,
                    mes.total.centavos,
                    reparto.value,
                    datetime.now().astimezone().isoformat(),
                ),
            )
            for c in mes.cuotas:
                cx.execute(
                    "INSERT INTO cuotas "
                    "(periodo, discord_id, nombre, monto_centavos, estado, "
                    " dijo_que_pago, confirmado) VALUES (?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(periodo, discord_id) DO UPDATE SET "
                    "nombre=excluded.nombre, monto_centavos=excluded.monto_centavos, "
                    "estado=excluded.estado, dijo_que_pago=excluded.dijo_que_pago, "
                    "confirmado=excluded.confirmado",
                    (
                        mes.periodo.clave,
                        c.participante.discord_id,
                        c.participante.nombre,
                        c.monto.centavos,
                        c.estado.value,
                        c.dijo_que_pago.isoformat() if c.dijo_que_pago else None,
                        c.confirmado.isoformat() if c.confirmado else None,
                    ),
                )

    def leer_mes(self, periodo: Periodo) -> MesDeCobro | None:
        """Lee un mes. None si no existe."""
        fila = self._cx.execute(
            "SELECT total_centavos FROM periodos WHERE clave = ?", (periodo.clave,)
        ).fetchone()
        if fila is None:
            return None

        cuotas = tuple(
            Cuota(
                participante=Participante(nombre=r["nombre"], discord_id=r["discord_id"]),
                monto=Dinero(r["monto_centavos"]),
                estado=Estado(r["estado"]),
                dijo_que_pago=_a_fecha(r["dijo_que_pago"]),
                confirmado=_a_fecha(r["confirmado"]),
            )
            for r in self._cx.execute(
                "SELECT * FROM cuotas WHERE periodo = ? ORDER BY nombre COLLATE NOCASE",
                (periodo.clave,),
            )
        )
        return MesDeCobro(periodo=periodo, total=Dinero(fila["total_centavos"]), cuotas=cuotas)

    def periodos_guardados(self, limite: int = 12) -> list[Periodo]:
        """Los meses que existen, del más nuevo al más viejo."""
        return [
            Periodo.de_clave(r["clave"])
            for r in self._cx.execute(
                "SELECT clave FROM periodos ORDER BY clave DESC LIMIT ?", (limite,)
            )
        ]

    def marcar_cerrado(self, periodo: Periodo, cuando: datetime) -> None:
        with self._transaccion() as cx:
            cx.execute(
                "UPDATE periodos SET cerrado_en = ? WHERE clave = ? AND cerrado_en IS NULL",
                (cuando.isoformat(), periodo.clave),
            )

    def reabrir(self, periodo: Periodo) -> None:
        """Quita la marca de cerrado: alguien volvió a deber ese mes."""
        with self._transaccion() as cx:
            cx.execute("UPDATE periodos SET cerrado_en = NULL WHERE clave = ?", (periodo.clave,))

    def esta_cerrado(self, periodo: Periodo) -> bool:
        fila = self._cx.execute(
            "SELECT cerrado_en FROM periodos WHERE clave = ?", (periodo.clave,)
        ).fetchone()
        return bool(fila and fila["cerrado_en"])

    # -- ajustes ----------------------------------------------------------- #

    def leer_ajuste(self, clave: str) -> str | None:
        """El JSON guardado bajo esa clave, o None si no hay."""
        fila = self._cx.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
        return str(fila["valor"]) if fila else None

    def guardar_ajuste(self, clave: str, valor_json: str) -> None:
        with self._transaccion() as cx:
            cx.execute(
                "INSERT INTO ajustes (clave, valor, actualizado_en) VALUES (?, ?, ?) "
                "ON CONFLICT(clave) DO UPDATE SET valor=excluded.valor, "
                "actualizado_en=excluded.actualizado_en",
                (clave, valor_json, datetime.now().astimezone().isoformat()),
            )

    # -- avisos ------------------------------------------------------------ #

    def ya_se_mando(self, periodo: Periodo, tipo: str, dia: date) -> bool:
        """¿Ya mandamos este aviso hoy?

        Es lo que hace los recordatorios idempotentes: si el bot se reinicia
        tres veces el día de pago, el aviso sale una sola vez.
        """
        return (
            self._cx.execute(
                "SELECT 1 FROM avisos WHERE periodo = ? AND tipo = ? AND dia = ?",
                (periodo.clave, tipo, dia.isoformat()),
            ).fetchone()
            is not None
        )

    def anotar_aviso(self, periodo: Periodo, tipo: str, dia: date, cuando: datetime) -> None:
        with self._transaccion() as cx:
            cx.execute(
                "INSERT OR IGNORE INTO avisos (periodo, tipo, dia, mandado_en) VALUES (?, ?, ?, ?)",
                (periodo.clave, tipo, dia.isoformat(), cuando.isoformat()),
            )

    # -- auditoría --------------------------------------------------------- #

    def anotar_auditoria(self, registro: RegistroDeAuditoria) -> None:
        """Agrega un movimiento al libro. Nunca se actualiza ni se borra."""
        with self._transaccion() as cx:
            cx.execute(
                "INSERT INTO auditoria "
                "(cuando, actor_id, actor_nombre, accion, periodo, objetivo_id, detalle) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    registro.cuando.isoformat(),
                    registro.actor.discord_id,
                    registro.actor.nombre,
                    registro.accion,
                    registro.periodo.clave if registro.periodo else None,
                    registro.objetivo_id,
                    json.dumps(registro.detalle, ensure_ascii=False, sort_keys=True),
                ),
            )

    def leer_auditoria(self, limite: int = 20) -> list[RegistroDeAuditoria]:
        """Los últimos movimientos, del más nuevo al más viejo."""
        registros: list[RegistroDeAuditoria] = []
        for fila in self._cx.execute("SELECT * FROM auditoria ORDER BY id DESC LIMIT ?", (limite,)):
            registros.append(
                RegistroDeAuditoria(
                    cuando=_a_fecha(fila["cuando"]) or datetime.min.replace(tzinfo=UTC),
                    actor=Actor(
                        discord_id=int(fila["actor_id"]),
                        nombre=str(fila["actor_nombre"]),
                    ),
                    accion=str(fila["accion"]),
                    periodo=Periodo.de_clave(fila["periodo"]) if fila["periodo"] else None,
                    objetivo_id=int(fila["objetivo_id"])
                    if fila["objetivo_id"] is not None
                    else None,
                    detalle=_a_detalle(fila["detalle"]),
                )
            )
        return registros


def _a_fecha(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:  # pragma: no cover — datos corruptos
        return None


def _a_detalle(valor: object) -> dict[str, str]:
    """El JSON guardado, convertido a un dict de strings."""
    try:
        datos = json.loads(str(valor))
    except (TypeError, ValueError):  # pragma: no cover — datos corruptos
        return {}
    if not isinstance(datos, dict):
        return {}
    return {str(k): str(v) for k, v in datos.items()}
