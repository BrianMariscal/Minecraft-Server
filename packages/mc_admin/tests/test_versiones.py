"""Comparación de versiones, con las formas raras que se usan."""

from __future__ import annotations

import pytest

from mc_admin.core.versiones import Cambio, Comparacion, comparar, filtrar_compatibles, resumir


class TestComparar:
    @pytest.mark.parametrize(
        ("actual", "nueva", "esperado"),
        [
            ("1.0.0", "1.0.1", Cambio.SUBE),
            ("1.0.1", "1.0.0", Cambio.BAJA),
            ("1.0.0", "1.0.0", Cambio.IGUAL),
            # Builds de Geyser y Floodgate.
            ("2.11.3-b1247", "2.11.3-b1248", Cambio.SUBE),
            ("2.2.5-b141", "2.2.5-b140", Cambio.BAJA),
            # LuckPerms trae prefijo v y sufijo de plataforma.
            ("v5.5.71-bukkit", "v5.5.85-bukkit", Cambio.SUBE),
            # Sufijos de plataforma, como el de Towns and Towers.
            ("5.28-paper", "5.29-paper", Cambio.SUBE),
            ("26.1-datapack", "26.2-datapack", Cambio.SUBE),
            # PacketEvents.
            ("2.14.0+spigot", "2.15.0+spigot", Cambio.SUBE),
            # Más trozos gana.
            ("2.11.3", "2.11.3.1", Cambio.SUBE),
        ],
    )
    def test_casos_reales(self, actual: str, nueva: str, esperado: Cambio) -> None:
        assert comparar(actual, nueva) is esperado

    def test_sin_version_disponible(self) -> None:
        assert comparar("1.0.0", None) is Cambio.DESCONOCIDO

    def test_un_numero_gana_a_un_texto(self) -> None:
        """2.11.3 es más nueva que 2.11.beta."""
        assert comparar("2.11.beta", "2.11.3") is Cambio.SUBE


class TestFiltrarCompatibles:
    def c(self, nombre: str, soporta: tuple[str, ...], canal: str = "release") -> Comparacion:
        return Comparacion(
            nombre=nombre,
            actual="1.0",
            disponible="2.0",
            cambio=Cambio.SUBE,
            soporta_minecraft=soporta,
            canal=canal,
        )

    def test_lo_que_soporta_nuestra_version_se_propone(self) -> None:
        aplicables, descartadas = filtrar_compatibles(
            [self.c("Buena", ("26.1.2", "26.2"))], "26.1.2"
        )
        assert [c.nombre for c in aplicables] == ["Buena"]
        assert descartadas == []

    def test_lo_que_ya_no_la_soporta_se_descarta(self) -> None:
        """Subirlo rompería el servidor de un día para otro."""
        aplicables, descartadas = filtrar_compatibles([self.c("Mala", ("26.3",))], "26.1.2")
        assert aplicables == []
        assert [c.nombre for c in descartadas] == ["Mala"]

    def test_si_no_sabemos_que_soporta_no_arriesgamos_descartarlo(self) -> None:
        """Sin información, lo proponemos pero el usuario decide."""
        aplicables, _ = filtrar_compatibles([self.c("Incierta", ())], "26.1.2")
        assert [c.nombre for c in aplicables] == ["Incierta"]

    def test_lo_que_ya_esta_igual_no_aparece(self) -> None:
        igual = Comparacion("Igual", "1.0", "1.0", Cambio.IGUAL)
        aplicables, descartadas = filtrar_compatibles([igual], "26.1.2")
        assert aplicables == []
        assert descartadas == []


class TestCanales:
    def test_release_es_seguro(self) -> None:
        c = Comparacion("X", "1.0", "2.0", Cambio.SUBE, canal="release")
        assert c.es_seguro

    @pytest.mark.parametrize("canal", ["beta", "alpha"])
    def test_beta_y_alpha_no(self, canal: str) -> None:
        c = Comparacion("X", "1.0", "2.0", Cambio.SUBE, canal=canal)
        assert not c.es_seguro


class TestResumir:
    def test_todo_al_dia(self) -> None:
        iguales = [Comparacion("X", "1.0", "1.0", Cambio.IGUAL)]
        assert "más nueva" in resumir(iguales, "26.1.2")

    def test_cuenta_estables_y_riesgosas(self) -> None:
        cs = [
            Comparacion("A", "1.0", "2.0", Cambio.SUBE, canal="release"),
            Comparacion("B", "1.0", "2.0", Cambio.SUBE, canal="beta"),
        ]
        texto = resumir(cs, "26.1.2")
        assert "1 actualización(es) en canal estable" in texto
        assert "1 solo en beta o alpha" in texto
