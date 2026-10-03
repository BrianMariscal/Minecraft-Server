"""La búsqueda del XUID, sin salir a internet."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from mc_admin.infra import xbox


def _respuestas(por_url: dict[str, tuple[int, Any]]) -> Any:
    def falso_get(url: str, **_kwargs: Any) -> httpx.Response:
        for pedazo, (codigo, cuerpo) in por_url.items():
            if pedazo in url:
                return httpx.Response(codigo, json=cuerpo)
        return httpx.Response(404, json={})

    return falso_get


def _playerdb(nombre: str, xuid: str) -> dict[str, Any]:
    return {"code": "player.found", "data": {"player": {"username": nombre, "id": xuid}}}


class TestBuscarXuid:
    def test_usa_geyser_si_lo_conoce(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx, "get", _respuestas({"geysermc": (200, {"xuid": 1234567890123456})})
        )
        assert xbox.buscar_xuid("AdminBedrock") == 1234567890123456

    def test_si_geyser_no_lo_conoce_va_a_playerdb(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "get",
            _respuestas(
                {
                    "geysermc": (400, {"message": "Unable to find user in our cache"}),
                    "playerdb.co/api/player/xbox/JugadorBedrock2": (
                        200,
                        _playerdb("Jugador Bedrock 2", "1234567890123457"),
                    ),
                }
            ),
        )
        assert xbox.buscar_xuid("Jugador Bedrock 2") == 1234567890123457

    def test_no_acepta_otra_cuenta(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            httpx,
            "get",
            _respuestas({"playerdb": (200, _playerdb("OtroDistinto", "1234567899999999"))}),
        )
        assert xbox.buscar_xuid("JugadorBedrock4") is None

    def test_nadie_lo_conoce(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(httpx, "get", _respuestas({}))
        assert xbox.buscar_xuid("NoExiste") is None

    def test_sin_internet(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def sin_red(*_a: Any, **_k: Any) -> httpx.Response:
            raise httpx.ConnectError("sin red")

        monkeypatch.setattr(httpx, "get", sin_red)
        assert xbox.buscar_xuid("JugadorBedrock4") is None
