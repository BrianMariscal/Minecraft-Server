"""Excepciones propias de `mc`.

Todas llevan un mensaje en español listo para mostrarle al usuario y, cuando
aplica, una `pista` con el siguiente paso concreto. La capa CLI las atrapa y
las imprime bonito, sin traceback.
"""

from __future__ import annotations


class ErrorMc(Exception):
    """Base de todos los errores esperables de `mc`.

    Un `ErrorMc` significa "algo salió mal y sabemos qué": se le muestra al
    usuario tal cual. Cualquier otra excepción es un bug nuestro y sí debe
    salir con traceback.
    """

    def __init__(self, mensaje: str, pista: str | None = None) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.pista = pista


class ErrorDeConfig(ErrorMc):
    """settings.yml o .env están mal escritos, incompletos o inconsistentes."""


class ErrorDeEntorno(ErrorMc):
    """Falta algo en la máquina: Docker, permisos, puertos, espacio en disco."""


class ErrorDeDescarga(ErrorMc):
    """No se pudo bajar un plugin o datapack, o el sha256 no coincide."""


class ErrorDeRcon(ErrorMc):
    """No se pudo hablar con la consola del servidor."""


class ErrorDeDocker(ErrorMc):
    """Un comando de `docker compose` falló."""


class ErrorDeRespaldo(ErrorMc):
    """Un respaldo no se pudo crear, listar o restaurar."""


class OperacionCancelada(ErrorMc):
    """El usuario dijo que no en una confirmación. No es una falla."""

    def __init__(self, mensaje: str = "Operación cancelada. No se tocó nada.") -> None:
        super().__init__(mensaje)
