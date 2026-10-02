"""Piezas compartidas por los tests del bot de pagos."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from pagos_bot.config import AvisosConfig, PagosConfig, ParticipanteConfig, TesoreroConfig
from pagos_bot.domain.cobro import Reparto
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.services.cobros import ServicioDeCobros


@pytest.fixture
def config() -> PagosConfig:
    """Cuatro amigos, $450 al mes, se paga el día 5."""
    return PagosConfig(
        activo=True,
        zona_horaria="America/Mexico_City",
        dia_de_pago=5,
        monto_total_mxn=Decimal("450.00"),
        reparto=Reparto.IGUALES,
        participantes=[
            ParticipanteConfig(nombre="Ana", discord_id=1),
            ParticipanteConfig(nombre="Pepe", discord_id=2),
            ParticipanteConfig(nombre="Lupita", discord_id=3),
            ParticipanteConfig(nombre="Juan", discord_id=4),
        ],
        tesorero=TesoreroConfig(nombre="Ana", discord_id=1),
        rol_admin_id=99,
        avisos=AvisosConfig(dias_antes=3, cada_dias_despues=2),
    )


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[RepositorioPagos]:
    """Una base de datos nueva por test, y se cierra al terminar."""
    r = RepositorioPagos(tmp_path / "pagos.sqlite")
    yield r
    r.cerrar()


@pytest.fixture
def servicio(config: PagosConfig, repo: RepositorioPagos) -> ServicioDeCobros:
    return ServicioDeCobros(config, repo)
