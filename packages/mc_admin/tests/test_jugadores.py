"""Nombres de jugadores: el prefijo de Floodgate y las altas idempotentes."""

from __future__ import annotations

import pytest

from mc_admin.core.jugadores import (
    Plataforma,
    agregar,
    entradas_whitelist,
    nombre_con_prefijo,
    normalizar_gamertag,
    quitar,
    uuid_floodgate,
    uuid_offline,
    validar,
    validar_xuid,
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


class TestUUIDs:
    """Verificados contra un Paper 26.1.2 real (whitelist.json y ops.json)."""

    def test_offline_igual_que_el_servidor(self) -> None:
        assert uuid_offline("Pepe") == "6eed0e07-3df7-3e33-9aa2-baa999bb44ee"
        assert uuid_offline("Zorro") == "94c56451-ca97-328d-a577-186e0ba6ebd3"

    def test_floodgate_es_el_xuid_en_hex(self) -> None:
        # 1234567890123456 = 0x000462d53c8abac0
        assert uuid_floodgate(1234567890123456) == "00000000-0000-0000-0004-62d53c8abac0"

    @pytest.mark.parametrize("malo", ["", "abc", "-5", "0", "12.5"])
    def test_xuid_invalido(self, malo: str) -> None:
        with pytest.raises(ErrorDeConfig):
            validar_xuid(malo)

    def test_xuid_valido(self) -> None:
        assert validar_xuid(" 1234567890123456 ") == 1234567890123456


class TestEntradasWhitelist:
    def test_java_con_uuid_offline(self) -> None:
        entradas, _ = entradas_whitelist(["Pepe"], [], [], {}, ".")
        assert [e.a_json() for e in entradas] == [
            {"uuid": "6eed0e07-3df7-3e33-9aa2-baa999bb44ee", "name": "Pepe"}
        ]

    def test_los_admins_entran_solos_y_sin_duplicar(self) -> None:
        entradas, _ = entradas_whitelist(["Pepe"], ["pepe", "Zorro"], [], {}, ".")
        assert [e.nombre for e in entradas] == ["Pepe", "Zorro"]

    def test_bedrock_con_el_uuid_de_floodgate(self) -> None:
        entradas, sin_xuid = entradas_whitelist(
            [], [], ["Gamer Tag"], {"Gamer_Tag": 1234567890123456}, "."
        )
        assert sin_xuid == []
        assert entradas[0].a_json() == {
            "uuid": "00000000-0000-0000-0004-62d53c8abac0",
            "name": ".Gamer_Tag",
        }

    def test_bedrock_sin_xuid_no_entra_y_se_avisa(self) -> None:
        entradas, sin_xuid = entradas_whitelist([], [], ["Gamer Tag"], {}, ".")
        assert entradas == []
        assert sin_xuid == ["Gamer_Tag"]
