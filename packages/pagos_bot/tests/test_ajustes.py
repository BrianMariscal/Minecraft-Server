"""Administrar el cobro desde Discord: miembros, montos y ajustes.

Y que las tarjetas que se mandan a Discord respeten sus límites: un mensaje
con el diseño nuevo admite hasta 40 componentes y 4000 caracteres de texto.
Pasarse no da error al armarlo, sino cuando Discord lo rechaza.
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from ayudas import momento
from test_servicio import ServicioCongelado

from pagos_bot.config import PagosConfig, ParticipanteConfig
from pagos_bot.discord_ui import botones, tarjetas
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import Estado, Reparto
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.esquema import VERSION_ACTUAL, version_de
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.services.ajustes import ServicioDeAjustes, cargar_config, leer_monto
from pagos_bot.services.cobros import ErrorDeCobro

OCTUBRE = Periodo(2026, 10)


@pytest.fixture
def config_personal(config: PagosConfig) -> PagosConfig:
    """Como el settings.yml real: cada quien su monto."""
    return config.model_copy(
        update={
            "reparto": Reparto.PERSONALIZADO,
            "participantes": [
                p.model_copy(update={"monto_mxn": Decimal("40.00")}) for p in config.participantes
            ],
        }
    )


@pytest.fixture
def svc(config_personal: PagosConfig, repo: RepositorioPagos) -> ServicioCongelado:
    s = ServicioCongelado(config_personal, repo, momento(1))
    s.mes_actual()
    return s


@pytest.fixture
def ajustes(svc: ServicioCongelado) -> ServicioDeAjustes:
    return ServicioDeAjustes(svc)


class TestLaConfigViveEnLaBase:
    def test_la_primera_vez_sale_de_settings_y_se_guarda(
        self, repo: RepositorioPagos, config: PagosConfig
    ) -> None:
        cfg, de_la_base = cargar_config(repo, config)
        assert not de_la_base
        assert cfg == config
        assert repo.leer_ajuste("config") is not None

    def test_despues_manda_la_de_la_base(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes, config_personal: PagosConfig
    ) -> None:
        cargar_config(svc.repo, config_personal)
        ajustes.cambiar_dia(15)
        cfg, de_la_base = cargar_config(svc.repo, config_personal)
        assert de_la_base
        assert cfg.dia_de_pago == 15

    def test_activo_y_zona_siempre_salen_de_settings(
        self, repo: RepositorioPagos, config: PagosConfig
    ) -> None:
        cargar_config(repo, config)
        apagado = config.model_copy(update={"activo": False, "zona_horaria": "America/Tijuana"})
        cfg, _ = cargar_config(repo, apagado)
        assert cfg.activo is False
        assert cfg.zona_horaria == "America/Tijuana"

    def test_una_base_vieja_se_migra(self, tmp_path: Path) -> None:
        """La base que ya existe en tu compu está en la versión 1."""
        ruta = tmp_path / "pagos.sqlite"
        cx = sqlite3.connect(ruta)
        from pagos_bot.repository.esquema import _v1

        _v1(cx)
        cx.execute("PRAGMA user_version = 1")
        cx.commit()
        cx.close()

        repo = RepositorioPagos(ruta)
        try:
            assert version_de(repo._cx) == VERSION_ACTUAL
            repo.guardar_ajuste("x", "1")
            assert repo.leer_ajuste("x") == "1"
        finally:
            repo.cerrar()


class TestMiembros:
    def test_agregar_entra_al_mes_en_curso(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        cuota = ajustes.agregar_miembro(50, "Nuevo", "35.50")
        assert cuota == Dinero.de_pesos("35.50")
        mes = svc.mes_actual()
        assert mes.cuota_de(50).estado is Estado.PENDIENTE
        assert any(p.discord_id == 50 for p in svc.config.participantes)

    def test_agregar_dos_veces(self, ajustes: ServicioDeAjustes) -> None:
        with pytest.raises(ErrorDeCobro, match="ya está en la lista"):
            ajustes.agregar_miembro(2, "Pepe", "40")

    def test_personalizado_pide_monto(self, ajustes: ServicioDeAjustes) -> None:
        with pytest.raises(ErrorDeCobro, match="cuánto paga"):
            ajustes.agregar_miembro(50, "Nuevo", None)

    def test_quitar_a_quien_debe_lo_exime_este_mes(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        que_paso = ajustes.quitar_miembro(3)
        assert "este mes ya no se le cobra" in que_paso
        assert svc.mes_actual().cuota_de(3).estado is Estado.EXENTO
        assert all(p.discord_id != 3 for p in svc.config.participantes)

    def test_quitar_a_quien_ya_pago_conserva_su_pago(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        svc.confirmar(3)
        ajustes.quitar_miembro(3)
        assert svc.mes_actual().cuota_de(3).estado is Estado.PAGADO

    def test_quien_se_quita_no_entra_al_mes_siguiente(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        ajustes.quitar_miembro(3)
        svc.viajar_a(momento(10, mes=11))
        assert svc.mes_actual().cuota_de(3) is None

    def test_cambiar_monto_desde_el_que_viene(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        ajustes.cambiar_monto(2, "50", este_mes=False)
        assert svc.mes_actual().cuota_de(2).monto == Dinero.de_pesos("40.00")
        svc.viajar_a(momento(10, mes=11))
        assert svc.mes_actual().cuota_de(2).monto == Dinero.de_pesos("50.00")

    def test_cambiar_monto_tambien_este_mes(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        ajustes.cambiar_monto(2, "$50,00", este_mes=True)
        assert svc.mes_actual().cuota_de(2).monto == Dinero.de_pesos("50.00")

    def test_no_se_cambia_lo_ya_pagado(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        svc.confirmar(2)
        with pytest.raises(ErrorDeCobro, match="ya pagó"):
            ajustes.cambiar_monto(2, "50", este_mes=True)

    def test_renombrar(self, svc: ServicioCongelado, ajustes: ServicioDeAjustes) -> None:
        ajustes.renombrar(2, "  Pepito  ")
        assert next(p for p in svc.config.participantes if p.discord_id == 2).nombre == "Pepito"


class TestAjustes:
    def test_dia_cambia_los_avisos(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        ajustes.cambiar_dia(20)
        assert svc.agenda.fecha_limite(OCTUBRE).day == 20

    def test_dia_invalido_no_se_guarda(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        with pytest.raises(ErrorDeCobro, match="no se puede"):
            ajustes.cambiar_dia(40)
        assert svc.config.dia_de_pago == 5

    def test_total(self, svc: ServicioCongelado, ajustes: ServicioDeAjustes) -> None:
        assert ajustes.cambiar_total("300") == Dinero.de_pesos("300")
        assert svc.config.total == Dinero.de_pesos("300")

    def test_el_precio_nuevo_sale_en_el_mes_en_curso(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        """Lo que reportó el tesorero: cambiaba el precio y la tarjeta seguía igual."""
        ajustes.cambiar_total("500")
        mes = svc.mes_actual()
        assert mes.meta == Dinero.de_pesos("500")
        assert "de $500.00 juntados" in tarjetas_texto(svc)

    def test_los_meses_pasados_conservan_su_precio(
        self, svc: ServicioCongelado, ajustes: ServicioDeAjustes
    ) -> None:
        svc.viajar_a(momento(10, mes=11))
        svc.mes_actual()
        ajustes.cambiar_total("500")
        assert svc.repo.leer_mes(OCTUBRE).meta == svc.repo.leer_mes(OCTUBRE).total
        assert svc.repo.leer_mes(OCTUBRE).meta != Dinero.de_pesos("500")
        assert svc.mes_actual().meta == Dinero.de_pesos("500")

    def test_avisos_y_hora(self, svc: ServicioCongelado, ajustes: ServicioDeAjustes) -> None:
        ajustes.cambiar_avisos(5, 3)
        ajustes.cambiar_hora(19)
        assert svc.agenda.dias_antes == 5
        assert svc.agenda.cada_dias_despues == 3
        assert svc.config.hora_aviso == 19

    def test_tesorero_y_rol(self, svc: ServicioCongelado, ajustes: ServicioDeAjustes) -> None:
        ajustes.cambiar_tesorero(2, "Pepe")
        ajustes.cambiar_rol_admin(777)
        assert svc.config.puede_administrar(2, [])
        assert not svc.config.puede_administrar(1, [])
        assert svc.config.puede_administrar(9, [777])

    def test_personalizado_exige_montos(self, config: PagosConfig, repo: RepositorioPagos) -> None:
        iguales = ServicioDeAjustes(ServicioCongelado(config, repo, momento(1)))
        with pytest.raises(ErrorDeCobro, match="ponle monto"):
            iguales.cambiar_reparto(Reparto.PERSONALIZADO)

    def test_con_iguales_no_hay_monto_por_persona(
        self, config: PagosConfig, repo: RepositorioPagos
    ) -> None:
        iguales = ServicioDeAjustes(ServicioCongelado(config, repo, momento(1)))
        with pytest.raises(ErrorDeCobro, match="iguales"):
            iguales.cambiar_monto(2, "50", este_mes=False)


class TestLeerMonto:
    @pytest.mark.parametrize(
        ("texto", "valor"),
        [("40", "40"), ("$40.50", "40.50"), ("40,5", "40.5"), (" 1 200 ", "1200")],
    )
    def test_formas_de_escribirlo(self, texto: str, valor: str) -> None:
        assert leer_monto(texto) == Decimal(valor)

    @pytest.mark.parametrize("malo", ["", "cuarenta", "0", "-5", "40.123"])
    def test_malos(self, malo: str) -> None:
        with pytest.raises(ErrorDeCobro):
            leer_monto(malo)


def tarjetas_texto(svc: ServicioCongelado) -> str:
    """Todo el texto de la tarjeta de /pagos, para buscar cosas en él."""
    vista = tarjetas.estado_del_mes(
        svc.mes_actual(),
        svc.agenda,
        svc.agenda.hoy(svc.ahora()),
        tesorero="Ana",
        atrasados=[],
        botones=[],
    )
    return repr(vista.to_components())


# --------------------------------------------------------------------------- #
#  Las tarjetas que van a Discord
# --------------------------------------------------------------------------- #

MAX_COMPONENTES = 40
MAX_TEXTO = 4000


def _medir(componentes: list[dict[str, Any]]) -> tuple[int, int]:
    """(cuántos componentes, cuántos caracteres de texto) en todo el mensaje."""
    total, texto = 0, 0
    pendientes = list(componentes)
    while pendientes:
        c = pendientes.pop()
        total += 1
        texto += len(c.get("content", ""))
        pendientes.extend(c.get("components", []))
        if "accessory" in c:
            pendientes.append(c["accessory"])
    return total, texto


@pytest.fixture
def mucha_gente(config: PagosConfig, repo: RepositorioPagos) -> ServicioCongelado:
    """El peor caso: 15 jugadores con nombre largo y un año de deudas."""
    gente = [
        ParticipanteConfig(nombre=f"Jugador con nombre largo {i:02d}", discord_id=100 + i)
        for i in range(15)
    ]
    cfg = config.model_copy(update={"participantes": gente, "dia_de_pago": 2})
    s = ServicioCongelado(cfg, repo, momento(1, mes=10, anio=2025))
    for mes in range(10, 13):
        s.viajar_a(momento(5, mes=mes, anio=2025))
        s.mes_actual()
    for mes in range(1, 11):
        s.viajar_a(momento(5, mes=mes, anio=2026))
        s.mes_actual()
    for p in gente[:5]:
        s.confirmar(p.discord_id, Periodo(2026, 10))
    s.dijo_que_pago(gente[6].discord_id)
    return s


class TestTarjetas:
    def test_estado_del_mes_cabe_aunque_sean_muchos(self, mucha_gente: ServicioCongelado) -> None:
        s = mucha_gente
        vista = tarjetas.estado_del_mes(
            s.mes_actual(),
            s.agenda,
            s.agenda.hoy(s.ahora()),
            tesorero="Ana",
            atrasados=s.deudas_anteriores(),
            botones=[botones.BotonYaPague()],
        )
        componentes, texto = _medir(vista.to_components())
        assert componentes <= MAX_COMPONENTES
        assert texto <= MAX_TEXTO

    def test_ajustes_cabe(self, mucha_gente: ServicioCongelado) -> None:
        componentes, texto = _medir(tarjetas.ajustes(mucha_gente.config).to_components())
        assert componentes <= MAX_COMPONENTES
        assert texto <= MAX_TEXTO

    def test_historial_cabe(self, mucha_gente: ServicioCongelado) -> None:
        componentes, texto = _medir(tarjetas.historial(mucha_gente.historial()).to_components())
        assert componentes <= MAX_COMPONENTES
        assert texto <= MAX_TEXTO

    def test_el_estado_no_menciona_a_nadie(self) -> None:
        """/pagos nombra a toda la banda: no debe sonarle a nadie."""
        assert tarjetas.SIN_MENCIONES.users is False
        assert tarjetas.SIN_MENCIONES.roles is False

    def test_el_boton_va_dentro_de_la_tarjeta(self, svc: ServicioCongelado) -> None:
        vista = tarjetas.estado_del_mes(
            svc.mes_actual(),
            svc.agenda,
            svc.agenda.hoy(svc.ahora()),
            tesorero="Ana",
            atrasados=[],
            botones=[botones.BotonYaPague()],
        )
        [contenedor] = vista.to_components()
        ids = re.findall(r"'custom_id': '([^']+)'", repr(contenedor))
        assert ids == [botones.ID_YA_PAGUE]


class TestBotones:
    def test_confirmar_lleva_quien_y_mes(self) -> None:
        b = botones.BotonConfirmar(42, Periodo(2026, 11))
        match = re.fullmatch(botones.PLANTILLA_CONFIRMAR, b.item.custom_id or "")
        assert match is not None
        r = asyncio.run(botones.BotonConfirmar.from_custom_id(None, None, match))  # type: ignore[arg-type]
        assert (r.de_quien, r.periodo) == (42, Periodo(2026, 11))

    def test_los_botones_viejos_se_reconocen(self) -> None:
        """Los "Ya pagué" de antes de 1.1 tenían el mismo custom_id: siguen jalando."""
        assert re.fullmatch(botones.ID_YA_PAGUE, "pagos:ya_pague")
        assert re.fullmatch(r"pagos:confirmar", "pagos:confirmar")
