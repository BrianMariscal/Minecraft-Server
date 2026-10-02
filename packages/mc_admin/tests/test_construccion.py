"""El plan de `mc build`: qué se va a hacer antes de hacerlo."""

from __future__ import annotations

from mc_admin.core.construccion import Accion, PasoDelPlan, PlanDeConstruccion


def paso(accion: Accion, categoria: str = "Plugins", nombre: str = "X") -> PasoDelPlan:
    return PasoDelPlan(categoria, nombre, "data/x", accion)


class TestPaso:
    def test_sin_cambio_no_cuenta_como_cambio(self) -> None:
        assert not paso(Accion.SIN_CAMBIO).cambia_algo

    def test_los_demas_si(self) -> None:
        for a in (Accion.CREAR, Accion.ACTUALIZAR, Accion.QUITAR):
            assert paso(a).cambia_algo


class TestPlan:
    def test_vacio(self) -> None:
        plan = PlanDeConstruccion()
        assert not plan.hay_cambios
        assert "Todo estaba al día" in plan.resumen()

    def test_solo_sin_cambios_cuenta_como_al_dia(self) -> None:
        """Es lo que hace idempotente a `mc build`."""
        plan = PlanDeConstruccion()
        for _ in range(5):
            plan.agregar(paso(Accion.SIN_CAMBIO))
        assert not plan.hay_cambios
        assert "Todo estaba al día" in plan.resumen()

    def test_cuenta_cada_tipo_de_cambio(self) -> None:
        plan = PlanDeConstruccion()
        plan.agregar(paso(Accion.CREAR))
        plan.agregar(paso(Accion.CREAR))
        plan.agregar(paso(Accion.ACTUALIZAR))
        plan.agregar(paso(Accion.QUITAR))
        plan.agregar(paso(Accion.SIN_CAMBIO))
        resumen = plan.resumen()
        assert "2 creado(s)" in resumen
        assert "1 actualizado(s)" in resumen
        assert "1 quitado(s)" in resumen
        assert len(plan.cambios) == 4

    def test_agrupa_por_categoria(self) -> None:
        plan = PlanDeConstruccion()
        plan.agregar(paso(Accion.CREAR, "Plugins"))
        plan.agregar(paso(Accion.CREAR, "Datapacks"))
        plan.agregar(paso(Accion.CREAR, "Plugins"))
        grupos = plan.por_categoria()
        assert set(grupos) == {"Plugins", "Datapacks"}
        assert len(grupos["Plugins"]) == 2

    def test_los_problemas_se_guardan_aparte(self) -> None:
        plan = PlanDeConstruccion()
        plan.problemas.append("falta una traducción")
        assert not plan.hay_cambios
        assert plan.problemas == ["falta una traducción"]
