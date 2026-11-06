"""Los casos de uso: marcar pagos, abrir el mes y los avisos idempotentes."""

from __future__ import annotations

from datetime import datetime

import pytest
from ayudas import momento

from pagos_bot.config import PagosConfig, ParticipanteConfig
from pagos_bot.domain.calendario import Periodo
from pagos_bot.domain.cobro import Estado
from pagos_bot.domain.dinero import Dinero
from pagos_bot.repository.pagos_repo import RepositorioPagos
from pagos_bot.services.cobros import (
    AVISO_DIA,
    AVISO_PREVIO,
    AVISO_TARDIO,
    ErrorDeCobro,
    ServicioDeCobros,
)


class ServicioCongelado(ServicioDeCobros):
    """Un servicio al que le podemos decir qué hora es.

    Así los tests no dependen del día en que se corran.
    """

    def __init__(self, config: PagosConfig, repo: RepositorioPagos, cuando: datetime) -> None:
        super().__init__(config, repo)
        self._cuando = cuando

    def ahora(self) -> datetime:
        return self._cuando

    def viajar_a(self, cuando: datetime) -> None:
        self._cuando = cuando


@pytest.fixture
def svc(config: PagosConfig, repo: RepositorioPagos) -> ServicioCongelado:
    """El día 1 de octubre de 2026, antes de cualquier aviso."""
    return ServicioCongelado(config, repo, momento(1))


class TestAbrirElMes:
    def test_el_mes_se_abre_solo(self, svc: ServicioCongelado) -> None:
        mes = svc.mes_actual()
        assert mes.periodo == Periodo(2026, 10)
        assert len(mes.cuotas) == 4

    def test_se_guarda_en_la_base(self, svc: ServicioCongelado) -> None:
        svc.mes_actual()
        assert svc.repo.leer_mes(Periodo(2026, 10)) is not None

    def test_abrirlo_dos_veces_no_lo_reinicia(self, svc: ServicioCongelado) -> None:
        svc.dijo_que_pago(2)
        svc.confirmar(2)
        # Volver a pedirlo no debe borrar el pago de Pepe.
        assert svc.mes_actual().cuota_de(2).estado is Estado.PAGADO

    def test_cambiar_de_mes_abre_uno_nuevo(self, svc: ServicioCongelado) -> None:
        svc.confirmar(1)
        svc.viajar_a(momento(3, mes=11))
        nuevo = svc.mes_actual()
        assert nuevo.periodo == Periodo(2026, 11)
        assert all(c.estado is Estado.PENDIENTE for c in nuevo.cuotas)
        # Y el mes viejo sigue ahí con su pago.
        assert svc.repo.leer_mes(Periodo(2026, 10)).cuota_de(1).estado is Estado.PAGADO

    def test_config_sin_llenar_truena_con_mensaje_util(
        self, config: PagosConfig, repo: RepositorioPagos
    ) -> None:
        sin_llenar = config.model_copy(
            update={"participantes": [ParticipanteConfig(nombre="CAMBIAME", discord_id=0)]}
        )
        svc = ServicioCongelado(sin_llenar, repo, momento(1))
        with pytest.raises(ErrorDeCobro, match="CAMBIAME"):
            svc.mes_actual()

    def test_quien_se_agrega_despues_entra_al_mes(
        self, config: PagosConfig, repo: RepositorioPagos
    ) -> None:
        svc = ServicioCongelado(config, repo, momento(1))
        svc.mes_actual()
        con_uno_mas = config.model_copy(
            update={
                "participantes": [
                    *config.participantes,
                    ParticipanteConfig(nombre="Nuevo", discord_id=5),
                ]
            }
        )
        svc2 = ServicioCongelado(con_uno_mas, repo, momento(2))
        mes = svc2.mes_actual()
        assert mes.cuota_de(5) is not None
        assert len(mes.cuotas) == 5

    def test_quien_se_quita_no_se_borra_del_mes_en_curso(
        self, config: PagosConfig, repo: RepositorioPagos
    ) -> None:
        """Si ya pagó, borrarlo descuadraría el total."""
        svc = ServicioCongelado(config, repo, momento(1))
        svc.confirmar(4)
        con_uno_menos = config.model_copy(update={"participantes": config.participantes[:3]})
        svc2 = ServicioCongelado(con_uno_menos, repo, momento(2))
        mes = svc2.mes_actual()
        assert mes.cuota_de(4) is not None
        assert mes.cuota_de(4).estado is Estado.PAGADO


class TestMarcarPagos:
    def test_dijo_que_pago(self, svc: ServicioCongelado) -> None:
        mes = svc.dijo_que_pago(2)
        assert mes.cuota_de(2).estado is Estado.POR_CONFIRMAR

    def test_confirmar(self, svc: ServicioCongelado) -> None:
        svc.dijo_que_pago(2)
        mes = svc.confirmar(2)
        assert mes.cuota_de(2).estado is Estado.PAGADO
        assert mes.juntado == Dinero.de_pesos("112.50")

    def test_el_tesorero_puede_confirmar_sin_que_lo_digan(self, svc: ServicioCongelado) -> None:
        """Pagos en efectivo: nadie picó el botón pero el dinero llegó."""
        mes = svc.confirmar(3)
        assert mes.cuota_de(3).estado is Estado.PAGADO

    def test_desmarcar(self, svc: ServicioCongelado) -> None:
        svc.confirmar(2)
        mes = svc.desmarcar(2)
        assert mes.cuota_de(2).estado is Estado.PENDIENTE
        assert mes.juntado == Dinero.cero()

    def test_eximir(self, svc: ServicioCongelado) -> None:
        mes = svc.eximir(4)
        assert mes.cuota_de(4).estado is Estado.EXENTO
        assert len(mes.activos) == 3

    def test_desconocido(self, svc: ServicioCongelado) -> None:
        with pytest.raises(ErrorDeCobro, match="no estás en la lista"):
            svc.dijo_que_pago(999)

    def test_no_se_puede_pagar_dos_veces(self, svc: ServicioCongelado) -> None:
        svc.confirmar(2)
        with pytest.raises(ErrorDeCobro, match="ya tienes el mes pagado"):
            svc.dijo_que_pago(2)

    def test_un_exento_no_tiene_que_pagar(self, svc: ServicioCongelado) -> None:
        svc.eximir(2)
        with pytest.raises(ErrorDeCobro, match="no te toca pagar"):
            svc.dijo_que_pago(2)

    def test_el_mes_se_cierra_al_completarse(self, svc: ServicioCongelado) -> None:
        for i in (1, 2, 3, 4):
            svc.confirmar(i)
        assert svc.repo.esta_cerrado(Periodo(2026, 10))


class TestAvisos:
    def test_el_dia_2_toca_el_previo(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(2))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_PREVIO
        # En el previo no se señala a nadie.
        assert aviso.mencionar == ()

    def test_el_dia_5_toca_el_del_dia_y_menciona_a_los_que_faltan(
        self, svc: ServicioCongelado
    ) -> None:
        svc.confirmar(1)
        svc.viajar_a(momento(5))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_DIA
        nombres = [c.participante.nombre for c in aviso.mencionar]
        assert "Ana" not in nombres
        assert set(nombres) == {"Pepe", "Lupita", "Juan"}

    def test_el_dia_7_toca_el_tardio(self, svc: ServicioCongelado) -> None:
        svc.viajar_a(momento(7))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_TARDIO
        assert aviso.dias_de_atraso == 2

    def test_los_dias_sin_aviso_no_mandan_nada(self, svc: ServicioCongelado) -> None:
        for dia in (1, 3, 4, 6, 8):
            svc.viajar_a(momento(dia))
            assert svc.aviso_que_toca() is None, f"el día {dia} no debería avisar"

    def test_el_mismo_aviso_no_se_repite(self, svc: ServicioCongelado) -> None:
        """Esto es lo que hace que reiniciar el bot no vuelva a mencionar."""
        svc.viajar_a(momento(5))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        svc.anotar_que_se_mando(aviso)
        assert svc.aviso_que_toca() is None

    def test_un_mes_cubierto_no_avisa(self, svc: ServicioCongelado) -> None:
        for i in (1, 2, 3, 4):
            svc.confirmar(i)
        svc.viajar_a(momento(5))
        assert svc.aviso_que_toca() is None

    def test_si_no_falta_nadie_no_hay_a_quien_recordarle(self, svc: ServicioCongelado) -> None:
        """Todos exentos menos uno, que ya pagó."""
        for i in (2, 3, 4):
            svc.eximir(i)
        svc.confirmar(1)
        svc.viajar_a(momento(7))
        assert svc.aviso_que_toca() is None


class TestHistorial:
    def test_vacio_al_principio(self, svc: ServicioCongelado) -> None:
        svc.mes_actual()
        assert svc.historial() == []

    def test_no_incluye_el_mes_actual(self, svc: ServicioCongelado) -> None:
        svc.mes_actual()
        svc.viajar_a(momento(3, mes=11))
        svc.mes_actual()
        historial = svc.historial()
        assert [m.periodo.clave for m in historial] == ["2026-10"]

    def test_del_mas_nuevo_al_mas_viejo(self, svc: ServicioCongelado) -> None:
        for mes in (10, 11, 12):
            svc.viajar_a(momento(3, mes=mes))
            svc.mes_actual()
        svc.viajar_a(momento(3, mes=1, anio=2027))
        svc.mes_actual()
        assert [m.periodo.clave for m in svc.historial()] == [
            "2026-12",
            "2026-11",
            "2026-10",
        ]


class TestPermisos:
    def test_el_tesorero_puede(self, config: PagosConfig) -> None:
        assert config.puede_administrar(1, [])

    def test_cualquiera_no(self, config: PagosConfig) -> None:
        assert not config.puede_administrar(2, [])

    def test_el_rol_de_admin_puede(self, config: PagosConfig) -> None:
        assert config.puede_administrar(2, [99])

    def test_otro_rol_no(self, config: PagosConfig) -> None:
        assert not config.puede_administrar(2, [42])

    def test_sin_rol_configurado_solo_el_tesorero(self, config: PagosConfig) -> None:
        sin_rol = config.model_copy(update={"rol_admin_id": 0})
        assert not sin_rol.puede_administrar(2, [0])


class TestAvisoPrevioCruzandoMes:
    """El aviso previo puede caer en el MES ANTERIOR al que cobra.

    Con `dia_de_pago: 2` y `dias_antes: 3`, el aviso del periodo de noviembre
    toca el 30 de OCTUBRE, cuando el periodo en curso todavía es octubre.
    Mirar solo el periodo de hoy hacía que ese aviso no saliera NUNCA, y el
    bug no se veía con el día 5 por defecto (ahí el aviso cae el día 2 del
    mismo mes).
    """

    @pytest.fixture
    def config_dia_2(self, config: PagosConfig) -> PagosConfig:
        return config.model_copy(update={"dia_de_pago": 2})

    @pytest.fixture
    def svc_dia_2(self, config_dia_2: PagosConfig, repo: RepositorioPagos) -> ServicioCongelado:
        """Octubre ya pagado, que es el caso normal al llegar fin de mes."""
        svc = ServicioCongelado(config_dia_2, repo, momento(1))
        svc.mes_actual()
        for p in config_dia_2.participantes:
            svc.confirmar(p.discord_id)
        return svc

    def test_el_previo_de_noviembre_sale_el_30_de_octubre(
        self, svc_dia_2: ServicioCongelado
    ) -> None:
        svc_dia_2.viajar_a(momento(30, mes=10))
        aviso = svc_dia_2.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_PREVIO
        # Y es el de NOVIEMBRE, no el de octubre.
        assert aviso.mes.periodo == Periodo(2026, 11)

    def test_el_previo_abre_el_mes_que_viene(self, svc_dia_2: ServicioCongelado) -> None:
        svc_dia_2.viajar_a(momento(30, mes=10))
        aviso = svc_dia_2.aviso_que_toca()
        assert aviso is not None
        assert len(aviso.mes.cuotas) == len(svc_dia_2.config.participantes)
        assert all(c.estado is Estado.PENDIENTE for c in aviso.mes.cuotas)

    def test_no_se_repite_si_el_bot_se_reinicia(self, svc_dia_2: ServicioCongelado) -> None:
        svc_dia_2.viajar_a(momento(30, mes=10))
        aviso = svc_dia_2.aviso_que_toca()
        assert aviso is not None
        svc_dia_2.anotar_que_se_mando(aviso)
        assert svc_dia_2.aviso_que_toca() is None

    def test_el_mes_que_se_abrio_antes_no_sale_en_el_historial(
        self, svc_dia_2: ServicioCongelado
    ) -> None:
        """Noviembre no es 'historial' el 30 de octubre."""
        svc_dia_2.viajar_a(momento(30, mes=10))
        svc_dia_2.aviso_que_toca()
        claves = [m.periodo.clave for m in svc_dia_2.historial()]
        assert "2026-11" not in claves

    def test_el_dia_de_pago_y_los_tardios_siguen_bien(self, svc_dia_2: ServicioCongelado) -> None:
        svc_dia_2.viajar_a(momento(2, mes=11))
        aviso = svc_dia_2.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_DIA
        assert aviso.mes.periodo == Periodo(2026, 11)
        svc_dia_2.anotar_que_se_mando(aviso)

        svc_dia_2.viajar_a(momento(4, mes=11))
        tardio = svc_dia_2.aviso_que_toca()
        assert tardio is not None
        assert tardio.tipo == AVISO_TARDIO
        assert tardio.dias_de_atraso == 2

    def test_un_mes_sin_pagar_tiene_prioridad_sobre_el_previo(
        self, config_dia_2: PagosConfig, repo: RepositorioPagos
    ) -> None:
        """Perseguir un mes que nadie pagó urge más que avisar del siguiente."""
        svc = ServicioCongelado(config_dia_2, repo, momento(1))
        svc.mes_actual()  # octubre abierto y sin pagar
        svc.viajar_a(momento(30, mes=10))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_TARDIO
        assert aviso.mes.periodo == Periodo(2026, 10)

    def test_con_dia_de_pago_tardio_el_previo_cae_en_el_mismo_mes(
        self, config: PagosConfig, repo: RepositorioPagos
    ) -> None:
        """El caso normal, que es el que ya funcionaba: día 5, aviso el 2."""
        svc = ServicioCongelado(config, repo, momento(2))
        aviso = svc.aviso_que_toca()
        assert aviso is not None
        assert aviso.tipo == AVISO_PREVIO
        assert aviso.mes.periodo == Periodo(2026, 10)
