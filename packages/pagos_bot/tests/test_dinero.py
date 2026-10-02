"""El dinero nunca pierde centavos."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pagos_bot.domain.dinero import Dinero, repartir, sumar


class TestConstruccion:
    def test_de_pesos_guarda_centavos(self) -> None:
        assert Dinero.de_pesos("450.00").centavos == 45000
        assert Dinero.de_pesos(Decimal("12.34")).centavos == 1234
        assert Dinero.de_pesos(100).centavos == 10000

    def test_redondea_al_centavo_mas_cercano(self) -> None:
        # Medio centavo para arriba, como en la caja de cualquier tienda.
        assert Dinero.de_pesos("1.005").centavos == 101
        assert Dinero.de_pesos("1.004").centavos == 100

    def test_cero(self) -> None:
        assert not Dinero.cero()
        assert Dinero.cero().centavos == 0


class TestFormato:
    @pytest.mark.parametrize(
        ("centavos", "esperado"),
        [
            (0, "$0.00"),
            (5, "$0.05"),
            (15000, "$150.00"),
            (123456, "$1,234.56"),
            (100000000, "$1,000,000.00"),
        ],
    )
    def test_se_escribe_como_en_mexico(self, centavos: int, esperado: str) -> None:
        assert str(Dinero(centavos)) == esperado


class TestAritmetica:
    def test_suma_y_resta(self) -> None:
        a, b = Dinero.de_pesos("10.50"), Dinero.de_pesos("4.25")
        assert (a + b).centavos == 1475
        assert (a - b).centavos == 625

    def test_multiplicacion(self) -> None:
        assert (Dinero.de_pesos("112.50") * 4).centavos == 45000

    def test_se_puede_ordenar(self) -> None:
        montos = [Dinero(300), Dinero(100), Dinero(200)]
        assert [m.centavos for m in sorted(montos)] == [100, 200, 300]


class TestRepartir:
    @pytest.mark.parametrize("entre", [1, 2, 3, 4, 5, 7, 11, 15])
    def test_la_suma_siempre_da_el_total(self, entre: int) -> None:
        """Lo que importa: el total no cambia por dividirlo."""
        total = Dinero.de_pesos("450.00")
        partes = repartir(total, entre)
        assert len(partes) == entre
        assert sumar(partes) == total

    def test_los_centavos_que_sobran_se_reparten(self) -> None:
        # $100 entre 3 no puede ser 33.33 cada uno: faltaría un centavo.
        partes = repartir(Dinero.de_pesos("100.00"), 3)
        assert [p.centavos for p in partes] == [3334, 3333, 3333]
        assert sumar(partes) == Dinero.de_pesos("100.00")

    def test_reparto_exacto_no_inventa_centavos(self) -> None:
        partes = repartir(Dinero.de_pesos("450.00"), 3)
        assert [p.centavos for p in partes] == [15000, 15000, 15000]

    @pytest.mark.parametrize("entre", [0, -1])
    def test_no_se_reparte_entre_cero_o_menos(self, entre: int) -> None:
        with pytest.raises(ValueError, match="al menos una persona"):
            repartir(Dinero.de_pesos("100.00"), entre)

    def test_un_peso_entre_siete(self) -> None:
        """El caso más feo: más gente que centavos por repartir parejo."""
        partes = repartir(Dinero(100), 7)
        assert sumar(partes).centavos == 100
        assert [p.centavos for p in partes] == [15, 15, 14, 14, 14, 14, 14]


class TestSumar:
    def test_lista_vacia_da_cero(self) -> None:
        assert sumar([]) == Dinero.cero()

    def test_suma_normal(self) -> None:
        assert sumar([Dinero(100), Dinero(250), Dinero(1)]).centavos == 351
