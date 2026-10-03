"""Quién está usando qué puerto, para `mc doctor`."""

from __future__ import annotations

import socket
from contextlib import closing

from mc_admin.core.diagnostico import DUENO_DESCONOCIDO
from mc_admin.infra.registro import obtener

log = obtener("puertos")


def _intentar_escuchar(puerto: int, tipo: socket.SocketKind) -> bool:
    """Intenta apropiarse del puerto. True si estaba libre."""
    familia = socket.AF_INET
    try:
        with closing(socket.socket(familia, tipo)) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", puerto))  # noqa: S104 — es justo lo que queremos probar
    except OSError:
        return False
    return True


def ocupados(puertos_tcp: list[int], puertos_udp: list[int]) -> dict[int, str]:
    """Devuelve puerto -> quién lo tiene, para los que estén ocupados.

    Para saber el nombre del proceso leemos /proc/net; si no se puede (otro
    sistema operativo, o el proceso es de otro usuario), decimos "otro proceso".
    """
    duenos = _duenos_desde_proc()
    resultado: dict[int, str] = {}

    for puerto in puertos_tcp:
        if not _intentar_escuchar(puerto, socket.SOCK_STREAM):
            resultado[puerto] = duenos.get(puerto, DUENO_DESCONOCIDO)
    for puerto in puertos_udp:
        if not _intentar_escuchar(puerto, socket.SOCK_DGRAM):
            resultado[puerto] = duenos.get(puerto, DUENO_DESCONOCIDO)

    return resultado


def _duenos_desde_proc() -> dict[int, str]:
    """Mapea puerto -> nombre del proceso leyendo /proc (solo Linux).

    Si algo no se puede leer, simplemente no aparece en el mapa: `mc doctor`
    seguirá diciendo que el puerto está ocupado, nada más sin el nombre.
    """
    from pathlib import Path

    inodos: dict[str, int] = {}
    for archivo in ("tcp", "tcp6", "udp", "udp6"):
        ruta = Path("/proc/net") / archivo
        if not ruta.is_file():
            continue
        try:
            lineas = ruta.read_text(encoding="utf-8").splitlines()[1:]
        except OSError:
            continue
        for linea in lineas:
            campos = linea.split()
            if len(campos) < 10:
                continue
            try:
                puerto = int(campos[1].split(":")[1], 16)
            except (IndexError, ValueError):
                continue
            inodos[campos[9]] = puerto

    if not inodos:
        return {}

    resultado: dict[int, str] = {}
    proc = Path("/proc")
    for pid_dir in proc.iterdir():
        if not pid_dir.name.isdigit():
            continue
        fd_dir = pid_dir / "fd"
        try:
            descriptores = list(fd_dir.iterdir())
        except OSError:
            # Proceso de otro usuario o que ya murió: no es asunto nuestro.
            continue
        for fd in descriptores:
            try:
                destino = fd.readlink().name
            except OSError:
                continue
            if not destino.startswith("socket:["):
                continue
            inodo = destino[8:-1]
            puerto_del_socket = inodos.get(inodo)
            if puerto_del_socket is None:
                continue
            try:
                nombre = (pid_dir / "comm").read_text(encoding="utf-8").strip()
            except OSError:
                nombre = f"pid {pid_dir.name}"
            resultado[puerto_del_socket] = nombre

    return resultado
