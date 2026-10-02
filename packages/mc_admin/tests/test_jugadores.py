"""Nombres de jugadores: el prefijo de Floodgate y las altas idempotentes."""

from __future__ import annotations

import pytest

from mc_admin.core.jugadores import (
    Plataforma,
    agregar,
    nombre_con_prefijo,
    nombres_para_el_servidor,
    normalizar_gamertag,
    quitar,
    validar,
)
from mc_admin.errores import ErrorDeConfig


class TestValidarJava:
    @pytest.mark.parametrize("nombre", ["Pepe", "Admin_HD", "abc", "a" * 16, "Jugador123"])
    def test_nombres_buenos(self, nombre: str) -> None:
        assert validar(nombre, Plataforma.JAVA) == nombre

    @pytest.mark.parametrize("nombre", ["ab", "a" * 17, "con espacio", "con-guion", "ñoño"])
    def test_nombres_malos(self, nombre: str) -> None:
        with pytest.raises(ErrorDeConfig):
            validar(nombre, Plataforma.JAVA)

    def test_sugiere_bedrock_si_parece_gamertag(self) -> None:
        """La pista tiene que decirle al usuario qué hacer, no solo que falló."""
        with pytest.raises(ErrorDeConfig) as info:
            validar("Gamer Tag", Plataforma.JAVA)
        assert "--bedrock" in (info.value.pista or "")

    def test_se_recortan_los_espacios(self) -> None:
        assert validar("  Pepe  ", Plataforma.JAVA) == "Pepe"

    def test_vacio(self) -> None:
        with pytest.raises(ErrorDeConfig, match="vacío"):
            validar("   ", Plataforma.JAVA)


class TestValidarBedrock:
    def test_los_espacios_se_vuelven_guion_bajo(self) -> None:
        """Floodgate hace exactamente esto, y lo replicamos."""
        assert validar("Gamer Tag 7", Plataforma.BEDROCK) == "Gamer_Tag_7"

    def test_rechaza_el_punto_porque_lo_pone_mc(self) -> None:
        with pytest.raises(ErrorDeConfig, match="quita el punto"):
            validar(".Pepe", Plataforma.BEDROCK)

    def test_un_gamertag_corto_sí_se_acepta(self) -> None:
        """A diferencia de Java, Xbox permite gamertags de menos de 3."""
        assert validar("Yo", Plataforma.BEDROCK) == "Yo"


class TestPrefijo:
    def test_se_le_pone_el_punto(self) -> None:
        assert nombre_con_prefijo("Pepe", ".") == ".Pepe"

    def test_no_se_duplica(self) -> None:
        assert nombre_con_prefijo(".Pepe", ".") == ".Pepe"

    def test_sin_prefijo_configurado_no_cambia_nada(self) -> None:
        assert nombre_con_prefijo("Pepe", "") == "Pepe"

    def test_normalizar_gamertag(self) -> None:
        assert normalizar_gamertag("  Gamer Tag  ") == "Gamer_Tag"


class TestAgregarYQuitar:
    def test_agregar(self) -> None:
        r = agregar([], "Pepe", Plataforma.JAVA)
        assert r.cambio
        assert r.lista == ("Pepe",)

    def test_agregar_dos_veces_no_duplica(self) -> None:
        """`mc whitelist add` dos veces no debe romper nada."""
        r = agregar(["Pepe"], "Pepe", Plataforma.JAVA)
        assert not r.cambio
        assert r.lista == ("Pepe",)
        assert "ya estaba" in r.mensaje

    def test_no_distingue_mayusculas(self) -> None:
        """Minecraft tampoco las distingue."""
        r = agregar(["Pepe"], "pepe", Plataforma.JAVA)
        assert not r.cambio

    def test_la_lista_queda_ordenada(self) -> None:
        r = agregar(["Zoe", "ana"], "Mario", Plataforma.JAVA)
        assert r.lista == ("ana", "Mario", "Zoe")

    def test_quitar(self) -> None:
        r = quitar(["Pepe", "Ana"], "Pepe", Plataforma.JAVA)
        assert r.cambio
        assert r.lista == ("Ana",)

    def test_quitar_a_quien_no_esta_no_truena(self) -> None:
        r = quitar(["Ana"], "Pepe", Plataforma.JAVA)
        assert not r.cambio
        assert "no estaba" in r.mensaje

    def test_quitar_sin_distinguir_mayusculas(self) -> None:
        r = quitar(["Pepe"], "PEPE", Plataforma.JAVA)
        assert r.cambio
        assert r.lista == ()


class TestNombresParaElServidor:
    def test_java_tal_cual_y_bedrock_con_punto(self) -> None:
        nombres = nombres_para_el_servidor(["Pepe"], ["Gamer Tag"], ".")
        assert nombres == ["Pepe", ".Gamer_Tag"]

    def test_listas_vacias(self) -> None:
        assert nombres_para_el_servidor([], [], ".") == []

    def test_sin_prefijo(self) -> None:
        assert nombres_para_el_servidor([], ["Pepe"], "") == ["Pepe"]
