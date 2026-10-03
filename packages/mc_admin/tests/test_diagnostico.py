"""Las reglas de `mc doctor`.

Son funciones puras: reciben datos ya leídos y deciden si está bien, regular
o mal. Así se puede probar el diagnóstico completo sin Docker ni servidor.
"""

from __future__ import annotations

import pytest

from mc_admin.core import diagnostico as diag
from mc_admin.core.diagnostico import (
    DUENO_DESCONOCIDO,
    Nivel,
    Reporte,
    revisar_disco,
    revisar_docker,
    revisar_logo,
    revisar_memoria,
    revisar_pendientes_de_llenar,
    revisar_puertos,
    revisar_secretos,
    revisar_tps,
    revisar_traducciones,
    revisar_version_manifest,
)


class TestDocker:
    def test_disponible(self) -> None:
        h = revisar_docker(True, "2.30.0")
        assert h.nivel is Nivel.BIEN
        assert "2.30.0" in h.detalle

    def test_no_disponible_dice_como_arreglarlo(self) -> None:
        h = revisar_docker(False, None)
        assert h.nivel is Nivel.MAL
        assert "grupo `docker`" in h.pista


class TestMemoria:
    def test_de_sobra(self) -> None:
        assert revisar_memoria(16.0, "6G").nivel is Nivel.BIEN

    def test_el_vps_de_8gb_del_proyecto(self) -> None:
        """8 GB con 6G para el server: va, pero sin mucho margen."""
        h = revisar_memoria(7.8, "6G")
        assert h.nivel is Nivel.AVISO

    def test_no_alcanza(self) -> None:
        h = revisar_memoria(4.0, "6G")
        assert h.nivel is Nivel.MAL
        # La pista tiene que decir un valor concreto que sí quepa.
        assert "settings.yml" in h.pista
        assert "2G" in h.pista

    def test_memoria_en_megas(self) -> None:
        assert revisar_memoria(8.0, "2048M").nivel is Nivel.BIEN

    def test_si_no_se_puede_leer_solo_avisa(self) -> None:
        assert revisar_memoria(None, "6G").nivel is Nivel.AVISO


class TestDisco:
    def test_de_sobra(self) -> None:
        assert revisar_disco(200.0, 3000).nivel is Nivel.BIEN

    def test_casi_lleno(self) -> None:
        h = revisar_disco(5.0, 3000)
        assert h.nivel is Nivel.MAL
        assert "Libera espacio" in h.pista

    def test_alcanza_pero_apenas_para_el_pregen(self) -> None:
        h = revisar_disco(20.0, 3000)
        assert h.nivel is Nivel.AVISO
        assert "radio_pregen" in h.pista

    def test_si_no_se_puede_leer_solo_avisa(self) -> None:
        assert revisar_disco(None, 3000).nivel is Nivel.AVISO


class TestPuertos:
    def test_todos_libres(self) -> None:
        hallazgos = revisar_puertos({}, {"Java": 25565, "Bedrock": 19132})
        assert all(h.nivel is Nivel.BIEN for h in hallazgos)
        assert len(hallazgos) == 2

    def test_ocupado_por_otro_proceso(self) -> None:
        hallazgos = revisar_puertos({25565: "nginx"}, {"Java": 25565})
        assert hallazgos[0].nivel is Nivel.MAL
        assert "nginx" in hallazgos[0].detalle

    def test_ocupado_por_nosotros_esta_bien(self) -> None:
        """Si el puerto lo tiene nuestro contenedor, el server ya anda."""
        hallazgos = revisar_puertos({25565: "mc-hd-servidor"}, {"Java": 25565})
        assert hallazgos[0].nivel is Nivel.BIEN
        assert "nosotros" in hallazgos[0].detalle

    def test_docker_proxy_sin_nombre_con_servidor_encendido(self) -> None:
        """Sin sudo no se ve el dueño; con el servidor prendido es nuestro."""
        hallazgos = revisar_puertos(
            {25565: DUENO_DESCONOCIDO}, {"Java": 25565}, servidor_encendido=True
        )
        assert hallazgos[0].nivel is Nivel.BIEN

    def test_dueno_desconocido_con_servidor_apagado_es_malo(self) -> None:
        hallazgos = revisar_puertos({25565: DUENO_DESCONOCIDO}, {"Java": 25565})
        assert hallazgos[0].nivel is Nivel.MAL

    def test_otro_proceso_con_nombre_sigue_mal_aunque_este_encendido(self) -> None:
        hallazgos = revisar_puertos({25565: "nginx"}, {"Java": 25565}, servidor_encendido=True)
        assert hallazgos[0].nivel is Nivel.MAL

    def test_reconoce_el_nombre_de_la_imagen(self) -> None:
        hallazgos = revisar_puertos({25565: "java (minecraft)"}, {"Java": 25565})
        assert hallazgos[0].nivel is Nivel.BIEN


class TestTps:
    @pytest.mark.parametrize("tps", [20.0, 19.5, 18.0])
    def test_bien(self, tps: float) -> None:
        assert revisar_tps(tps).nivel is Nivel.BIEN

    @pytest.mark.parametrize("tps", [17.9, 15.0])
    def test_cargado(self, tps: float) -> None:
        assert revisar_tps(tps).nivel is Nivel.AVISO

    def test_mal(self) -> None:
        h = revisar_tps(10.0)
        assert h.nivel is Nivel.MAL
        assert "mc logs" in h.pista

    def test_servidor_apagado(self) -> None:
        h = revisar_tps(None)
        assert h.nivel is Nivel.AVISO
        assert "apagado" in h.detalle


class TestVersiones:
    def test_cuadran(self) -> None:
        assert revisar_version_manifest("26.1.2", "26.1.2").nivel is Nivel.BIEN

    def test_no_cuadran(self) -> None:
        h = revisar_version_manifest("26.2", "26.1.2")
        assert h.nivel is Nivel.MAL
        assert "mc update" in h.pista


class TestSecretos:
    def test_todo_lleno(self) -> None:
        assert revisar_secretos([]).nivel is Nivel.BIEN

    def test_faltan(self) -> None:
        h = revisar_secretos(["RCON_PASSWORD", "PAGOS_BOT_TOKEN"])
        assert h.nivel is Nivel.MAL
        assert "RCON_PASSWORD" in h.detalle
        assert "mc setup" in h.pista


class TestLogo:
    def test_existe(self) -> None:
        assert revisar_logo(True, "logo/logo.png").nivel is Nivel.BIEN

    def test_no_existe_es_solo_aviso(self) -> None:
        """El logo es opcional: el servidor arranca igual."""
        h = revisar_logo(False, "logo/logo.png")
        assert h.nivel is Nivel.AVISO
        assert "logo/README.md" in h.pista


class TestTraducciones:
    def test_todo_en_español(self) -> None:
        assert revisar_traducciones(0).nivel is Nivel.BIEN

    def test_queda_ingles(self) -> None:
        h = revisar_traducciones(12)
        assert h.nivel is Nivel.AVISO
        assert "--traducciones" in h.pista


class TestPendientes:
    def test_todo_listo(self) -> None:
        assert revisar_pendientes_de_llenar(False, 2, 5) == []

    def test_pagos_sin_llenar(self) -> None:
        hallazgos = revisar_pendientes_de_llenar(True, 1, 1)
        assert any("CAMBIAME" in h.detalle for h in hallazgos)

    def test_sin_admins(self) -> None:
        hallazgos = revisar_pendientes_de_llenar(False, 0, 1)
        assert any("mc admin add" in h.pista for h in hallazgos)

    def test_whitelist_vacia_avisa_que_nadie_entra(self) -> None:
        hallazgos = revisar_pendientes_de_llenar(False, 1, 0)
        assert any("nadie puede entrar" in h.detalle for h in hallazgos)

    def test_los_tres_a_la_vez(self) -> None:
        assert len(revisar_pendientes_de_llenar(True, 0, 0)) == 3


class TestReporte:
    def test_vacio(self) -> None:
        r = Reporte()
        assert not r.hay_problemas
        assert r.resumen() == "Todo en orden."

    def test_solo_avisos(self) -> None:
        r = Reporte()
        r.agregar(revisar_logo(False, "logo/logo.png"))
        assert not r.hay_problemas
        assert r.hay_avisos
        assert "Todo jala" in r.resumen()

    def test_con_problemas(self) -> None:
        r = Reporte()
        r.agregar(revisar_docker(False, None))
        r.agregar(revisar_logo(False, "logo/logo.png"))
        assert r.hay_problemas
        assert "1 cosa(s) mal" in r.resumen()
        assert "1 aviso" in r.resumen()


class TestCompose:
    def test_al_dia(self) -> None:
        assert diag.revisar_compose(True).nivel is diag.Nivel.BIEN

    def test_desfasado_pide_build(self) -> None:
        h = diag.revisar_compose(False)
        assert h.nivel is diag.Nivel.AVISO
        assert "mc build" in h.pista


class TestRclone:
    def test_apagado_no_dice_nada(self) -> None:
        assert diag.revisar_rclone(False, False, "x") is None

    def test_prendido_sin_configurar_es_problema(self) -> None:
        h = diag.revisar_rclone(True, False, "/home/yo/.config/rclone/rclone.conf")
        assert h is not None
        assert h.nivel is diag.Nivel.MAL

    def test_prendido_y_configurado(self) -> None:
        h = diag.revisar_rclone(True, True, "x")
        assert h is not None
        assert h.nivel is diag.Nivel.BIEN
