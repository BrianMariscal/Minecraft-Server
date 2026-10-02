"""El modelo del mes: quién debe, cuánto falta y cuándo ya quedó."""

from __future__ import annotations

import pytest
from ayudas import momento

from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import (
    Estado,
    MesDeCobro,
    Participante,
    Reparto,
    abrir_mes,
)
from pagos_bot.domain.dinero import Dinero

CUATRO = [Participante(n, i) for i, n in enumerate(["Ana", "Pepe", "Lupita", "Juan"], 1)]


def mes_nuevo(total: str = "450.00", gente: list[Participante] | None = None) -> MesDeCobro:
    return abrir_mes(Periodo(2026, 10), Dinero.de_pesos(total), gente or CUATRO, Reparto.IGUALES)


class TestAbrirMes:
    def test_todos_empiezan_pendientes(self) -> None:
        mes = mes_nuevo()
        assert len(mes.cuotas) == 4
        assert all(c.estado is Estado.PENDIENTE for c in mes.cuotas)

    def test_reparto_igual_sin_perder_centavos(self) -> None:
        mes = mes_nuevo("100.00", CUATRO[:3])
        assert [c.monto.centavos for c in mes.cuotas] == [3334, 3333, 3333]
        assert mes.por_juntar == Dinero.de_pesos("100.00")

    def test_sin_participantes_truena(self) -> None:
        with pytest.raises(ValueError, match="no hay participantes"):
            abrir_mes(Periodo(2026, 10), Dinero.de_pesos("100"), [], Reparto.IGUALES)

    def test_personalizado_usa_el_monto_de_cada_quien(self) -> None:
        gente = [
            Participante("Ana", 1, Dinero.de_pesos("200.00")),
            Participante("Pepe", 2, Dinero.de_pesos("250.00")),
        ]
        mes = abrir_mes(Periodo(2026, 10), Dinero.de_pesos("450.00"), gente, Reparto.PERSONALIZADO)
        assert [str(c.monto) for c in mes.cuotas] == ["$200.00", "$250.00"]

    def test_personalizado_sin_monto_truena_diciendo_a_quien_le_falta(self) -> None:
        gente = [
            Participante("Ana", 1, Dinero.de_pesos("200.00")),
            Participante("Pepe", 2),
        ]
        with pytest.raises(ValueError, match="Pepe"):
            abrir_mes(Periodo(2026, 10), Dinero.de_pesos("450"), gente, Reparto.PERSONALIZADO)


class TestEstados:
    def test_marcar_no_muta_el_original(self) -> None:
        """El modelo es inmutable: marcar devuelve uno nuevo."""
        mes = mes_nuevo()
        nuevo = mes.con_estado(1, Estado.PAGADO, momento(5))
        assert mes.cuota_de(1).estado is Estado.PENDIENTE
        assert nuevo.cuota_de(1).estado is Estado.PAGADO

    def test_por_confirmar_guarda_cuando_lo_dijo(self) -> None:
        cuando = momento(5)
        mes = mes_nuevo().con_estado(1, Estado.POR_CONFIRMAR, cuando)
        cuota = mes.cuota_de(1)
        assert cuota.dijo_que_pago == cuando
        assert cuota.confirmado is None

    def test_pagado_guarda_las_dos_fechas(self) -> None:
        mes = mes_nuevo().con_estado(1, Estado.POR_CONFIRMAR, momento(5))
        mes = mes.con_estado(1, Estado.PAGADO, momento(6))
        cuota = mes.cuota_de(1)
        assert cuota.dijo_que_pago == momento(5)
        assert cuota.confirmado == momento(6)

    def test_volver_a_pendiente_borra_las_fechas(self) -> None:
        mes = mes_nuevo().con_estado(1, Estado.PAGADO, momento(5))
        mes = mes.con_estado(1, Estado.PENDIENTE, momento(6))
        cuota = mes.cuota_de(1)
        assert cuota.dijo_que_pago is None
        assert cuota.confirmado is None


class TestCuantoFalta:
    def test_solo_cuenta_lo_confirmado(self) -> None:
        """Si el tesorero no lo vio, el dinero no está."""
        mes = mes_nuevo().con_estado(1, Estado.POR_CONFIRMAR, momento(5))
        assert mes.juntado == Dinero.cero()
        assert mes.por_juntar == Dinero.de_pesos("450.00")

    def test_juntado_suma_los_pagados(self) -> None:
        mes = mes_nuevo()
        mes = mes.con_estado(1, Estado.PAGADO, momento(5))
        mes = mes.con_estado(2, Estado.PAGADO, momento(5))
        assert mes.juntado == Dinero.de_pesos("225.00")
        assert mes.por_juntar == Dinero.de_pesos("225.00")

    def test_faltantes_incluye_a_los_por_confirmar(self) -> None:
        mes = mes_nuevo().con_estado(1, Estado.POR_CONFIRMAR, momento(5))
        nombres = [c.participante.nombre for c in mes.faltantes]
        assert nombres == ["Ana", "Pepe", "Lupita", "Juan"]

    def test_los_exentos_no_cuentan_para_el_total(self) -> None:
        mes = mes_nuevo().con_estado(4, Estado.EXENTO, momento(5))
        assert len(mes.activos) == 3
        assert mes.por_juntar == Dinero.de_pesos("337.50")
        assert "Juan" not in [c.participante.nombre for c in mes.faltantes]


class TestCubierto:
    def test_no_esta_cubierto_al_empezar(self) -> None:
        assert not mes_nuevo().esta_cubierto

    def test_se_cubre_cuando_todos_pagan(self) -> None:
        mes = mes_nuevo()
        for i in (1, 2, 3, 4):
            mes = mes.con_estado(i, Estado.PAGADO, momento(5))
        assert mes.esta_cubierto
        assert mes.avance == 1.0

    def test_se_cubre_aunque_haya_exentos(self) -> None:
        mes = mes_nuevo().con_estado(4, Estado.EXENTO, momento(5))
        for i in (1, 2, 3):
            mes = mes.con_estado(i, Estado.PAGADO, momento(5))
        assert mes.esta_cubierto

    def test_un_por_confirmar_no_lo_cubre(self) -> None:
        mes = mes_nuevo()
        for i in (1, 2, 3):
            mes = mes.con_estado(i, Estado.PAGADO, momento(5))
        mes = mes.con_estado(4, Estado.POR_CONFIRMAR, momento(5))
        assert not mes.esta_cubierto

    def test_todos_exentos_cuenta_como_cubierto(self) -> None:
        """Nadie debe nada, así que no hay nada que cobrar."""
        mes = mes_nuevo()
        for i in (1, 2, 3, 4):
            mes = mes.con_estado(i, Estado.EXENTO, momento(5))
        assert not mes.activos
        assert not mes.esta_cubierto  # sin activos no hay mes que cerrar
        assert mes.avance == 1.0


class TestAvance:
    @pytest.mark.parametrize(
        ("cuantos_pagaron", "esperado"),
        [(0, 0.0), (1, 0.25), (2, 0.5), (4, 1.0)],
    )
    def test_avance(self, cuantos_pagaron: int, esperado: float) -> None:
        mes = mes_nuevo()
        for i in range(1, cuantos_pagaron + 1):
            mes = mes.con_estado(i, Estado.PAGADO, momento(5))
        assert mes.avance == pytest.approx(esperado)


class TestEstadoVisual:
    def test_cada_estado_tiene_emoji_y_texto(self) -> None:
        for e in Estado:
            assert e.emoji
            assert e.texto


class TestParticipante:
    def test_mencion_de_discord(self) -> None:
        assert Participante("Pepe", 123).mencion == "<@123>"
