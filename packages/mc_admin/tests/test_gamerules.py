"""Gamerules: los nombres de 26.x y las dimensiones donde aplican.

Estos nombres NO salieron de la documentación: salieron de leer el
game_rules.dat que generó un Paper 26.1.2 de verdad. Con los nombres viejos
en camelCase el servidor contesta "Incorrect argument" y la regla no aplica,
sin más aviso.
"""

from __future__ import annotations

from mc_admin.core.gamerules import Dimension, Regla, comandos_de, reglas_para


class TestNombresDeLa26:
    def test_todos_van_en_snake_case(self) -> None:
        """En 26.x las gamerules dejaron de ser camelCase."""
        for r in reglas_para(dormir_con_un_jugador=True):
            assert r.nombre.islower()
            assert " " not in r.nombre
            assert r.nombre == r.nombre.lower()

    def test_la_del_sueño_tiene_el_nombre_nuevo(self) -> None:
        nombres = {r.nombre for r in reglas_para(dormir_con_un_jugador=True)}
        assert "players_sleeping_percentage" in nombres
        # El nombre viejo que usa toda la documentación NO sirve.
        assert "playersSleepingPercentage" not in nombres


class TestDormirConUnJugador:
    def test_prendido_pone_la_regla_en_1(self) -> None:
        regla = next(
            r
            for r in reglas_para(dormir_con_un_jugador=True)
            if r.nombre == "players_sleeping_percentage"
        )
        assert regla.valor == "1"
        # Solo el overworld: es donde se duerme.
        assert regla.dimensiones == (Dimension.OVERWORLD,)

    def test_apagado_no_la_pone(self) -> None:
        nombres = {r.nombre for r in reglas_para(dormir_con_un_jugador=False)}
        assert "players_sleeping_percentage" not in nombres


class TestLasGranjasNoSeRompen:
    def test_mob_griefing_sigue_prendido(self) -> None:
        """Apagarlo mata las granjas de aldeanos y de TNT."""
        regla = next(
            r for r in reglas_para(dormir_con_un_jugador=True) if r.nombre == "mob_griefing"
        )
        assert regla.valor == "true"

    def test_las_raids_siguen_pasando(self) -> None:
        reglas = {r.nombre: r for r in reglas_para(dormir_con_un_jugador=True)}
        assert reglas["raids"].valor == "true"
        assert reglas["spawn_patrols"].valor == "true"

    def test_los_mensajes_de_muerte_se_quedan(self) -> None:
        """Son vanilla: cada cliente los traduce a su idioma."""
        reglas = {r.nombre: r for r in reglas_para(dormir_con_un_jugador=True)}
        assert reglas["show_death_messages"].valor == "true"


class TestComandos:
    def test_usan_execute_in_porque_son_por_dimension(self) -> None:
        """En 26.x cada dimensión tiene su propio game_rules.dat."""
        for c in comandos_de(reglas_para(dormir_con_un_jugador=True)):
            assert c.startswith("execute in minecraft:")
            assert " run gamerule " in c

    def test_una_regla_de_tres_dimensiones_da_tres_comandos(self) -> None:
        regla = Regla(
            nombre="prueba",
            valor="true",
            porque="test",
            dimensiones=(Dimension.OVERWORLD, Dimension.NETHER, Dimension.END),
        )
        assert len(regla.comandos()) == 3

    def test_cada_regla_dice_por_que_esta(self) -> None:
        for r in reglas_para(dormir_con_un_jugador=True):
            assert r.porque.strip()
