"""Fechas: meses cortos, bisiestos y cuándo toca cada aviso."""

from __future__ import annotations

from datetime import date

import pytest
from ayudas import ZONA, momento

from pagos_bot.domain.calendario import Agenda, Periodo, fecha_de_pago


class TestDiaDePagoEnMesesCortos:
    """El bug clásico de estos bots: pagar el 31 en un mes de 30 días."""

    @pytest.mark.parametrize(
        ("mes", "dia_esperado"),
        [
            (1, 31),  # enero sí tiene 31
            (2, 28),  # febrero 2026 no es bisiesto
            (4, 30),  # abril tiene 30
            (6, 30),
            (9, 30),
            (11, 30),
            (12, 31),
        ],
    )
    def test_dia_31(self, mes: int, dia_esperado: int) -> None:
        assert fecha_de_pago(2026, mes, 31).day == dia_esperado

    def test_febrero_bisiesto(self) -> None:
        assert fecha_de_pago(2028, 2, 31) == date(2028, 2, 29)
        assert fecha_de_pago(2028, 2, 30) == date(2028, 2, 29)

    def test_febrero_no_bisiesto(self) -> None:
        assert fecha_de_pago(2026, 2, 29) == date(2026, 2, 28)

    def test_un_dia_que_si_existe_no_se_toca(self) -> None:
        assert fecha_de_pago(2026, 10, 5) == date(2026, 10, 5)


class TestPeriodo:
    def test_clave_y_nombre(self) -> None:
        p = Periodo(2026, 10)
        assert p.clave == "2026-10"
        assert p.nombre == "octubre de 2026"

    def test_ida_y_vuelta_por_la_clave(self) -> None:
        p = Periodo(2026, 3)
        assert Periodo.de_clave(p.clave) == p

    def test_cambio_de_anio(self) -> None:
        assert Periodo(2026, 12).siguiente() == Periodo(2027, 1)
        assert Periodo(2026, 1).anterior() == Periodo(2025, 12)

    def test_mes_invalido(self) -> None:
        with pytest.raises(ValueError, match="no existe"):
            Periodo(2026, 13)

    def test_clave_mal_escrita(self) -> None:
        with pytest.raises(ValueError, match="no es un periodo válido"):
            Periodo.de_clave("octubre")

    def test_se_pueden_ordenar(self) -> None:
        ps = [Periodo(2026, 3), Periodo(2025, 12), Periodo(2026, 1)]
        assert [p.clave for p in sorted(ps)] == ["2025-12", "2026-01", "2026-03"]


class TestAgenda:
    @pytest.fixture
    def agenda(self) -> Agenda:
        return Agenda(dia_de_pago=5, dias_antes=3, cada_dias_despues=2, zona=ZONA)

    def test_dias_para_pagar(self, agenda: Agenda) -> None:
        p = Periodo(2026, 10)
        assert agenda.dias_para_pagar(p, momento(1)) == 4
        assert agenda.dias_para_pagar(p, momento(5)) == 0
        assert agenda.dias_para_pagar(p, momento(9)) == -4

    def test_aviso_previo_solo_el_dia_exacto(self, agenda: Agenda) -> None:
        p = Periodo(2026, 10)
        assert agenda.toca_aviso_previo(p, momento(2))  # 3 días antes
        assert not agenda.toca_aviso_previo(p, momento(1))
        assert not agenda.toca_aviso_previo(p, momento(3))

    def test_aviso_del_dia(self, agenda: Agenda) -> None:
        p = Periodo(2026, 10)
        assert agenda.toca_aviso_del_dia(p, momento(5))
        assert not agenda.toca_aviso_del_dia(p, momento(4))
        assert not agenda.toca_aviso_del_dia(p, momento(6))

    def test_recordatorio_tardio_cada_dos_dias(self, agenda: Agenda) -> None:
        p = Periodo(2026, 10)
        # El mismo día no cuenta: eso ya lo cubre toca_aviso_del_dia.
        assert not agenda.toca_recordatorio_tardio(p, momento(5))
        assert not agenda.toca_recordatorio_tardio(p, momento(6))
        assert agenda.toca_recordatorio_tardio(p, momento(7))
        assert not agenda.toca_recordatorio_tardio(p, momento(8))
        assert agenda.toca_recordatorio_tardio(p, momento(9))

    def test_nunca_toca_antes_de_la_fecha(self, agenda: Agenda) -> None:
        p = Periodo(2026, 10)
        for dia in range(1, 5):
            assert not agenda.toca_recordatorio_tardio(p, momento(dia))

    def test_con_dia_31_el_limite_se_ajusta(self) -> None:
        agenda = Agenda(dia_de_pago=31, dias_antes=3, cada_dias_despues=2, zona=ZONA)
        # Noviembre tiene 30, así que el límite es el 30.
        assert agenda.fecha_limite(Periodo(2026, 11)) == date(2026, 11, 30)
        assert agenda.toca_aviso_del_dia(Periodo(2026, 11), momento(30, mes=11))

    def test_fecha_bonita(self, agenda: Agenda) -> None:
        assert agenda.fecha_bonita(date(2026, 10, 5)) == "5 de octubre"
        assert agenda.fecha_bonita(date(2026, 1, 31)) == "31 de enero"
