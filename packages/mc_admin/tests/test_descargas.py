"""Descargas de Vanilla Tweaks: caché estable y verificación de los packs.

El ZIP contenedor cambia de bytes entre generaciones, así que lo que se
verifica es cada datapack de adentro. Estas pruebas usan un transporte falso
de httpx: no abren sockets ni tocan vanillatweaks.net.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from mc_admin.core.manifest import PackVanillaTweaks, VanillaTweaks
from mc_admin.errores import ErrorDeDescarga
from mc_admin.infra import descargas


def _zip_de(packs: dict[str, bytes]) -> bytes:
    """Un ZIP en memoria con los datapacks que le pidamos."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for nombre, contenido in packs.items():
            z.writestr(nombre, contenido)
    return buffer.getvalue()


def _vt(packs: dict[str, bytes], *, version: str = "26.1") -> VanillaTweaks:
    return VanillaTweaks(
        version_mc=version,
        url="https://vanillatweaks.net/assets/server/zipdatapacks.php",
        seleccion={"Convenience": list(packs)},
        packs=[
            PackVanillaTweaks(
                archivo=nombre,
                sha256=hashlib.sha256(contenido).hexdigest(),
            )
            for nombre, contenido in packs.items()
        ],
    )


def _cliente(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestObtenerVanillaTweaks:
    def test_baja_el_zip_y_verifica_cada_pack(self, tmp_path: Path) -> None:
        packs = {"timber v1.zip": b"timber", "armor statues v1.zip": b"armor"}
        pedidos: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            pedidos.append(request.method)
            if request.method == "POST":
                return httpx.Response(200, json={"status": "success", "link": "/download/x.zip"})
            return httpx.Response(200, content=_zip_de(packs))

        with _cliente(handler) as cliente:
            salida = descargas.obtener_vanilla_tweaks(_vt(packs), tmp_path, cliente)

        assert pedidos == ["POST", "GET"]
        assert [nombre for nombre, _ in salida] == list(packs)
        for (_, ruta), contenido in zip(salida, packs.values(), strict=True):
            assert ruta.read_bytes() == contenido

    def test_la_segunda_vez_sale_del_cache(self, tmp_path: Path) -> None:
        packs = {"timber v1.zip": b"timber"}
        llamadas: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            llamadas.append(request.method)
            if request.method == "POST":
                return httpx.Response(200, json={"status": "success", "link": "/download/x.zip"})
            return httpx.Response(200, content=_zip_de(packs))

        with _cliente(handler) as cliente:
            descargas.obtener_vanilla_tweaks(_vt(packs), tmp_path, cliente)

        # Si intentara pedir algo, este handler lo delata.
        def no_debe_llamar(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"no debía pedir {request.url}")

        with _cliente(no_debe_llamar) as cliente:
            salida = descargas.obtener_vanilla_tweaks(_vt(packs), tmp_path, cliente)

        assert len(salida) == 1
        assert llamadas == ["POST", "GET"]

    def test_si_falta_un_pack_avisa_cual(self, tmp_path: Path) -> None:
        packs = {"timber v1.zip": b"timber", "otro v1.zip": b"otro"}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"status": "success", "link": "/download/x.zip"})
            return httpx.Response(200, content=_zip_de({"timber v1.zip": b"timber"}))

        with _cliente(handler) as cliente, pytest.raises(ErrorDeDescarga, match=r"otro v1\.zip"):
            descargas.obtener_vanilla_tweaks(_vt(packs), tmp_path, cliente)

    def test_un_pack_con_otro_contenido_aborta(self, tmp_path: Path) -> None:
        vt = _vt({"timber v1.zip": b"timber"})
        distinto = vt.packs[0].model_copy(update={"sha256": "b" * 64})
        vt = vt.model_copy(update={"packs": [distinto]})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(200, json={"status": "success", "link": "/download/x.zip"})
            return httpx.Response(200, content=_zip_de({"timber v1.zip": b"timber"}))

        with _cliente(handler) as cliente, pytest.raises(ErrorDeDescarga, match="no coincide"):
            descargas.obtener_vanilla_tweaks(vt, tmp_path, cliente)
