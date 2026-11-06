"""Pagos que cruzan de mes: adelantados, atrasados y confirmaciones por mes."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from ayudas import momento
from test_servicio import ServicioCongelado

from pagos_bot.config import PagosConfig, ParticipanteConfig
from pagos_bot.discord_ui import textos
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import Estado, Reparto
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.services.cobros import AVISO_PREVIO, AVISO_TARDIO, ErrorDeCobro
from pagos_bot.vigia import Cambio, EstadoDelVigia

OCTUBRE = Periodo(2026, 10)
NOVIEMBRE = Periodo(2026, 11)


@pytest.fixture
def config_dia_2(config: PagosConfig) -> PagosConfig:
    """Como el settings.yml real: se paga el día 2."""
    return config.model_copy(update={"dia_de_pago": 2})


@pytest.fixture
def svc(config_dia_2: PagosConfig, repo: RepositorioPagos) -> ServicioCongelado:
    s = ServicioCongelado(config_dia_2, repo, momento(1))
    s.mes_actual()
    return s


def _pagar_todo(svc: ServicioCongelado, periodo: Periodo) -> None:
    for p in svc.config.participantes:
        svc.confirmar(p.discord_id, periodo)


class TestPagoAdelantado:
    """El aviso previo de noviembre sale el 30 de octubre, con su botón."""

    def test_ya_pague_el_30_cuenta_para_noviembre(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        svc.viajar_a(momento(30, mes=10))
        assert svc.aviso_que_toca() is not None  # abre noviembre

        mes = svc.dijo_que_pago(2)

        assert mes.periodo == NOVIEMBRE
        assert mes.cuota_de(2).estado is Estado.POR_CONFIRMAR

    def test_sin_aviso_previo_todavia_esta_al_corriente(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        svc.viajar_a(momento(20, mes=10))
        with pytest.raises(ErrorDeCobro, match="ya tienes el mes pagado"):
            svc.dijo_que_pago(2)

    def test_el_tesorero_confirma_el_mes_correcto(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        svc.viajar_a(momento(30, mes=10))
        svc.aviso_que_toca()
        svc.dijo_que_pago(2)

        mes = svc.confirmar(2)

        assert mes.periodo == NOVIEMBRE
        assert mes.cuota_de(2).estado is Estado.PAGADO


class TestPrimeroLoAtrasado:
    def test_paga_el_mes_mas_viejo_primero(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(10, mes=11))  # octubre quedó sin pagar
        mes = svc.dijo_que_pago(3)
        assert mes.periodo == OCTUBRE

    def test_luego_el_actual(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(10, mes=11))
        svc.dijo_que_pago(3)
        svc.confirmar(3)
        mes = svc.dijo_que_pago(3)
        assert mes.periodo == NOVIEMBRE

    def test_confirmar_sin_mes_va_a_lo_que_dijo_que_pago(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(10, mes=11))
        svc.confirmar(4, NOVIEMBRE)  # noviembre en efectivo
        svc.dijo_que_pago(4)  # y dice que pagó octubre
        mes = svc.confirmar(4)
        assert mes.periodo == OCTUBRE


class TestSinSpamAlTesorero:
    def test_picarle_dos_veces_no_vuelve_a_avisar(self, svc: ServicioCongelado) -> None:
        svc.dijo_que_pago(2)
        with pytest.raises(ErrorDeCobro, match="falta que lo confirme"):
            svc.dijo_que_pago(2)
        assert svc.mes_actual().cuota_de(2).estado is Estado.POR_CONFIRMAR


class TestConfirmarYMoverPorMes:
    def test_confirmar_lo_ya_confirmado_lo_dice(self, svc: ServicioCongelado) -> None:
        svc.confirmar(2)
        with pytest.raises(ErrorDeCobro, match="ya estaba confirmado"):
            svc.confirmar(2, OCTUBRE)

    def test_sin_deuda_no_hay_que_confirmar(self, svc: ServicioCongelado) -> None:
        svc.confirmar(2)
        with pytest.raises(ErrorDeCobro, match="no debe nada"):
            svc.confirmar(2)

    def test_un_mes_que_no_existe(self, svc: ServicioCongelado) -> None:
        with pytest.raises(ErrorDeCobro, match="no hay cobro de marzo de 2025"):
            svc.confirmar(2, Periodo(2025, 3))

    def test_eximir_un_mes_viejo(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(10, mes=11))
        mes = svc.eximir(3, OCTUBRE)
        assert mes.periodo == OCTUBRE
        assert mes.cuota_de(3).estado is Estado.EXENTO

    def test_desmarcar_reabre_un_mes_cerrado(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        assert svc.repo.esta_cerrado(OCTUBRE)
        svc.desmarcar(2, OCTUBRE)
        assert not svc.repo.esta_cerrado(OCTUBRE)


class TestDeudasAnteriores:
    def test_cambiar_de_mes_no_borra_la_deuda(self, svc: ServicioCongelado) -> None:
        for quien in (1, 2):
            svc.confirmar(quien)
        svc.viajar_a(momento(10, mes=11))

        deudas = svc.deudas_anteriores()

        assert [m.periodo for m in deudas] == [OCTUBRE]
        assert {c.participante.discord_id for c in deudas[0].faltantes} == {3, 4}

    def test_un_mes_saldado_ya_no_sale(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        svc.viajar_a(momento(10, mes=11))
        assert svc.deudas_anteriores() == []

    def test_el_tardio_de_octubre_sigue_saliendo_en_noviembre(self, svc: ServicioCongelado) -> None:
        # Octubre se paga el 2 y avisa cada 2 días: el 2 de noviembre van 31
        # días (non), el 3 van 32 (par), así que toca el 3.
        svc.viajar_a(momento(3, mes=11))
        avisos = svc.avisos_que_tocan()
        de_octubre = [a for a in avisos if a.mes.periodo == OCTUBRE]
        assert len(de_octubre) == 1
        assert de_octubre[0].tipo == AVISO_TARDIO
        assert de_octubre[0].dias_de_atraso == 32

    def test_no_se_repite_el_mismo_dia(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(3, mes=11))
        for aviso in svc.avisos_que_tocan():
            svc.anotar_que_se_mando(aviso)
        assert svc.avisos_que_tocan() == []

    def test_el_mes_en_curso_va_primero(self, svc: ServicioCongelado) -> None:
        # Con un recordatorio diario, el 4 de noviembre tocan los dos: el
        # tardío de noviembre (2 días) y el de octubre (33 días).
        config = svc.config.model_copy(
            update={"avisos": svc.config.avisos.model_copy(update={"cada_dias_despues": 1})}
        )
        s = ServicioCongelado(config, svc.repo, momento(4, mes=11))
        avisos = s.avisos_que_tocan()
        assert [a.mes.periodo for a in avisos] == [NOVIEMBRE, OCTUBRE]


class TestTextos:
    def test_deudas_anteriores_se_leen_bien(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(10, mes=11))
        texto = textos.deudas_anteriores(svc.deudas_anteriores())
        assert texto.startswith("**Octubre de 2026**: ")
        assert "Pepe" in texto

    def test_el_aviso_dice_de_que_mes_es(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(3, mes=11))
        aviso = next(a for a in svc.avisos_que_tocan() if a.mes.periodo == OCTUBRE)
        texto = textos.aviso_tardio(aviso.mes, svc.agenda, aviso.dias_de_atraso)
        assert "octubre de 2026" in texto


class TestElPrevioSigueFuncionando:
    def test_previo_de_noviembre(self, svc: ServicioCongelado) -> None:
        _pagar_todo(svc, OCTUBRE)
        svc.viajar_a(momento(30, mes=10))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_PREVIO
        assert aviso.mes.periodo == NOVIEMBRE


class TestFotoDeLaBase:
    def test_la_foto_abre_y_trae_los_datos(self, svc: ServicioCongelado, tmp_path: Path) -> None:
        svc.confirmar(2)
        foto = tmp_path / "pagos.copia.sqlite"
        svc.repo.copiar_a(foto)

        otra = RepositorioPagos(foto)
        try:
            mes = otra.leer_mes(OCTUBRE)
        finally:
            otra.cerrar()
        assert mes is not None
        assert mes.cuota_de(2).estado is Estado.PAGADO


class TestDescuadre:
    def _config(self, total: str, montos: list[str]) -> PagosConfig:
        return PagosConfig(
            dia_de_pago=2,
            monto_total_mxn=Decimal(total),
            reparto=Reparto.PERSONALIZADO,
            participantes=[
                ParticipanteConfig(nombre=f"p{i}", discord_id=i + 1, monto_mxn=Decimal(m))
                for i, m in enumerate(montos)
            ],
            tesorero={"nombre": "p0", "discord_id": 1},  # type: ignore[arg-type]
            avisos={"dias_antes": 3, "cada_dias_despues": 2},  # type: ignore[arg-type]
        )

    def test_cuadra(self) -> None:
        assert self._config("80.00", ["40", "40"]).descuadre is None

    def test_sobra(self) -> None:
        """Como el settings.yml de hoy: 7 x 40 = 280 contra 240."""
        assert self._config("240.00", ["40"] * 7).descuadre == Dinero.de_pesos("40.00")

    def test_falta(self) -> None:
        assert self._config("100.00", ["40", "40"]).descuadre == Dinero.de_pesos("-20.00")

    def test_iguales_siempre_cuadra(self, config: PagosConfig) -> None:
        assert config.descuadre is None


class TestVigia:
    def test_no_avisa_mientras_arranca(self) -> None:
        """Antes de verlo arriba, que no conteste es normal (está arrancando)."""
        v = EstadoDelVigia(fallas_para_avisar=3)
        assert [v.registrar(False) for _ in range(10)] == [None] * 10

    def test_avisa_una_sola_vez_cuando_se_cae(self) -> None:
        v = EstadoDelVigia(fallas_para_avisar=3)
        v.registrar(True)
        cambios = [v.registrar(False) for _ in range(6)]
        assert cambios == [None, None, Cambio.SE_CAYO, None, None, None]

    def test_avisa_cuando_vuelve(self) -> None:
        v = EstadoDelVigia(fallas_para_avisar=2)
        v.registrar(True)
        v.registrar(False)
        v.registrar(False)
        assert v.registrar(True) is Cambio.VOLVIO
        assert v.registrar(True) is None

    def test_un_parpadeo_no_es_caida(self) -> None:
        v = EstadoDelVigia(fallas_para_avisar=3)
        v.registrar(True)
        v.registrar(False)
        v.registrar(True)
        v.registrar(False)
        v.registrar(False)
        assert v.avisado is False
