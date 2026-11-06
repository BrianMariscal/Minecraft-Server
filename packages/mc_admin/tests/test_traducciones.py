"""El detector de mensajes en inglés que usa `mc doctor`."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from mc_admin.core.traducciones import palabras_inglesas_en, revisar_archivos, revisar_texto


class TestDetectarIngles:
    def test_una_frase_en_ingles_se_marca(self) -> None:
        palabras = palabras_inglesas_en("You do not have permission to do that")
        assert len(palabras) >= 2

    def test_una_frase_en_español_no(self) -> None:
        assert palabras_inglesas_en("No tienes permiso para eso.") == []

    def test_una_clave_de_yaml_sola_no_cuenta(self) -> None:
        assert palabras_inglesas_en("  no-permission:") == []

    def test_los_codigos_de_color_no_cuentan(self) -> None:
        assert palabras_inglesas_en("<primary><secondary>§a&c") == []

    def test_los_placeholders_no_cuentan(self) -> None:
        assert palabras_inglesas_en("{0} %player% {NOMBRE}") == []

    def test_una_url_no_cuenta(self) -> None:
        assert palabras_inglesas_en("https://docs.papermc.io/paper/reference") == []

    def test_una_sola_palabra_no_alcanza(self) -> None:
        """Con una sola nos llenaríamos de falsos positivos."""
        assert revisar_texto("spawn: 10", "x.yml") == []


class TestRevisarTexto:
    def test_encuentra_la_linea_y_el_numero(self) -> None:
        texto = "primera: hola\nsegunda: You must be logged in\ntercera: adiós\n"
        hallazgos = revisar_texto(texto, "prueba.yml")
        assert len(hallazgos) == 1
        assert hallazgos[0].numero == 2
        assert hallazgos[0].archivo == "prueba.yml"
        assert "logged" in hallazgos[0].palabras

    def test_los_comentarios_se_ignoran(self) -> None:
        """Nuestros comentarios están en español pero citan opciones en inglés."""
        texto = "# This setting must not be changed by you\nclave: valor\n"
        assert revisar_texto(texto, "x.yml") == []

    def test_las_lineas_vacias_se_ignoran(self) -> None:
        assert revisar_texto("\n\n   \n", "x.yml") == []

    def test_la_ubicacion_se_lee_bien(self) -> None:
        hallazgos = revisar_texto("a: You must not do that\n", "cosa.yml")
        assert hallazgos[0].ubicacion == "cosa.yml:1"


class TestRevisarArchivos:
    def test_lee_varios_y_ordena(self, tmp_path: Path) -> None:
        (tmp_path / "a.yml").write_text("x: You must not\n", encoding="utf-8")
        (tmp_path / "b.yml").write_text("y: No tienes permiso\n", encoding="utf-8")
        hallazgos = revisar_archivos([tmp_path / "a.yml", tmp_path / "b.yml"], tmp_path)
        assert [h.archivo for h in hallazgos] == ["a.yml"]

    def test_un_binario_no_tumba_la_revision(self, tmp_path: Path) -> None:
        binario = tmp_path / "cosa.bin"
        binario.write_bytes(b"\x00\x01\x02\xff\xfe")
        assert revisar_archivos([binario], tmp_path) == []

    def test_un_archivo_que_no_existe_se_salta(self, tmp_path: Path) -> None:
        assert revisar_archivos([tmp_path / "no-existe.yml"], tmp_path) == []


class TestNuestrasTraduccionesEstanEnEspanol:
    """Contra los archivos de traducción versionados."""

    def test_las_traducciones_propias_pasan_el_detector(self, proyecto: Path) -> None:
        carpeta = proyecto / "minecraft" / "translations" / "es_mx"
        archivos = [
            p for p in carpeta.iterdir() if p.is_file() and p.suffix in {".yml", ".properties"}
        ]
        assert archivos, "no encontré las traducciones"

        por_archivo: dict[str, int] = {}
        for h in revisar_archivos(archivos, proyecto):
            por_archivo[h.archivo] = por_archivo.get(h.archivo, 0) + 1

        # Margen: en EssentialsX hay subcomandos literales que NO se traducen
        # (clear, send, set...) porque son lo que el jugador teclea.
        problematicos = {a: n for a, n in por_archivo.items() if n > 60}
        assert problematicos == {}, f"demasiado inglés en: {problematicos}"


class TestEspaciosSignificativos:
    """En un .properties de Java, un espacio al final SÍ significa algo.

    Un linter de "limpiar espacios al final" los borra y rompe los mensajes
    sin que nadie se dé cuenta. Ya pasó una vez:
    `.pre-commit-config.yaml` excluye los .properties justo por esto.
    """

    # clave -> por qué necesita el espacio final
    CLAVES_CON_ESPACIO_FINAL: ClassVar[dict[str, str]] = {
        "chatTypeLocal": "separa la etiqueta [L] del mensaje",
        "listGroupTag": "separa 'Admins:' de la lista de nombres",
    }

    def test_las_claves_que_necesitan_espacio_final_lo_tienen(self, proyecto: Path) -> None:
        ruta = (
            proyecto / "minecraft" / "translations" / "es_mx" / "essentials-messages_es.properties"
        )
        lineas = {
            ln.split("=", 1)[0]: ln
            for ln in ruta.read_text(encoding="utf-8").splitlines()
            if "=" in ln and not ln.startswith("#")
        }
        for clave, porque in self.CLAVES_CON_ESPACIO_FINAL.items():
            assert clave in lineas, f"falta la clave {clave}"
            assert lineas[clave].endswith(" "), (
                f"{clave} perdió su espacio final, y lo necesita porque {porque}. "
                "¿Algún linter limpió los espacios del .properties?"
            )
