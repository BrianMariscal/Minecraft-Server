"""Respaldos: nombres, orden, búsqueda y retención."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mc_admin.core.respaldos import (
    Respaldo,
    buscar,
    cuales_sobran,
    interpretar_nombre,
    ordenar_recientes_primero,
)
from mc_admin.errores import ErrorDeRespaldo

ZONA = ZoneInfo("America/Mexico_City")


def r(marca: str, tamano: int = 1024) -> Respaldo:
    resultado = interpretar_nombre(f"world-{marca}.tgz", tamano, ZONA)
    assert resultado is not None
    return resultado


class TestInterpretarNombre:
    def test_formato_de_itzg(self) -> None:
        res = interpretar_nombre("world-20260930-143000.tgz", 2048, ZONA)
        assert res is not None
        assert res.momento.year == 2026
        assert res.momento.hour == 14
        assert res.id == "20260930-143000"

    @pytest.mark.parametrize(
        "nombre",
        ["cualquier-cosa.txt", "world.tgz", "world-malafecha-143000.tgz", "latest.tar"],
    )
    def test_lo_que_no_es_un_respaldo_se_ignora(self, nombre: str) -> None:
        assert interpretar_nombre(nombre, 10, ZONA) is None

    @pytest.mark.parametrize("ext", ["tgz", "tar.gz", "zip", "tar.zst"])
    def test_extensiones_aceptadas(self, ext: str) -> None:
        assert interpretar_nombre(f"world-20260930-143000.{ext}", 10, ZONA) is not None

    def test_prefijos_propios(self) -> None:
        """Los que hace `mc backup` antes de un reset o un restore."""
        assert interpretar_nombre("antes-de-reset-20260930-143000.tgz", 10, ZONA) is not None


class TestTamanoLegible:
    @pytest.mark.parametrize(
        ("bytes_", "esperado"),
        [(512, "512 B"), (2048, "2.0 KB"), (5 * 1024**2, "5.0 MB"), (3 * 1024**3, "3.0 GB")],
    )
    def test_formato(self, bytes_: int, esperado: str) -> None:
        assert Respaldo("x", datetime.now(ZONA), bytes_).tamano_legible == esperado


class TestBuscar:
    @pytest.fixture
    def tres(self) -> list[Respaldo]:
        return [r("20260928-100000"), r("20260930-143000"), r("20260929-120000")]

    def test_el_mas_nuevo_primero(self, tres: list[Respaldo]) -> None:
        ids = [x.id for x in ordenar_recientes_primero(tres)]
        assert ids == ["20260930-143000", "20260929-120000", "20260928-100000"]

    def test_por_id_exacto(self, tres: list[Respaldo]) -> None:
        assert buscar(tres, "20260929-120000").id == "20260929-120000"

    def test_por_nombre_de_archivo(self, tres: list[Respaldo]) -> None:
        assert buscar(tres, "world-20260929-120000.tgz").id == "20260929-120000"

    @pytest.mark.parametrize("palabra", ["ultimo", "último", "last", "-1", "ULTIMO"])
    def test_ultimo(self, tres: list[Respaldo], palabra: str) -> None:
        assert buscar(tres, palabra).id == "20260930-143000"

    def test_por_prefijo(self, tres: list[Respaldo]) -> None:
        assert buscar(tres, "20260930").id == "20260930-143000"

    def test_prefijo_ambiguo_avisa(self) -> None:
        dos = [r("20260930-100000"), r("20260930-200000")]
        with pytest.raises(ErrorDeRespaldo, match="coincide con 2"):
            buscar(dos, "20260930")

    def test_no_existe(self, tres: list[Respaldo]) -> None:
        with pytest.raises(ErrorDeRespaldo) as info:
            buscar(tres, "19990101-000000")
        assert "no encontré" in info.value.mensaje
        assert "mc backup list" in (info.value.pista or "")

    def test_sin_respaldos_sugiere_hacer_uno(self) -> None:
        with pytest.raises(ErrorDeRespaldo) as info:
            buscar([], "ultimo")
        assert "no hay ningún respaldo" in info.value.mensaje
        assert "mc backup now" in (info.value.pista or "")


class TestRetencion:
    def test_los_viejos_sobran(self) -> None:
        ahora = datetime(2026, 10, 10, 12, 0, tzinfo=ZONA)
        respaldos = [r("20261010-120000"), r("20261009-120000"), r("20260901-120000")]
        sobran = cuales_sobran(respaldos, conservar_dias=7, ahora=ahora)
        assert [x.id for x in sobran] == ["20260901-120000"]

    def test_el_mas_reciente_nunca_se_borra(self) -> None:
        """Aunque esté viejísimo: borrar el único respaldo sería un desastre."""
        ahora = datetime(2027, 1, 1, 12, 0, tzinfo=ZONA)
        respaldos = [r("20260901-120000")]
        assert cuales_sobran(respaldos, conservar_dias=7, ahora=ahora) == []

    def test_sin_respaldos(self) -> None:
        assert cuales_sobran([], 7, datetime.now(ZONA)) == []

    def test_todos_recientes(self) -> None:
        ahora = datetime(2026, 10, 10, 12, 0, tzinfo=ZONA)
        respaldos = [r("20261010-120000"), r("20261009-120000")]
        assert cuales_sobran(respaldos, conservar_dias=7, ahora=ahora) == []


class TestFechaBonita:
    def test_en_español(self) -> None:
        res = r("20260930-143000")
        assert res.fecha_bonita(ZONA) == "30 de septiembre 2026, 14:30"
