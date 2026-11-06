#!/usr/bin/env python3
"""Copia el respaldo más reciente del VPS a esta PC y verifica su sha256.

Pensado para correr desde un timer de systemd del usuario. No necesita
credenciales nuevas: usa la misma llave SSH con la que administras el VPS.
El respaldo se guarda en `~/Respaldos_Minecraft_HD/AAAA-MM-DD/`, con su
`.sha256`, su `.json` y un `SHA256SUMS` de la carpeta.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

REMOTO = os.environ.get("MC_SSH", "")
LLAVE = Path(os.environ.get("MC_SSH_KEY", "~/.ssh/id_ed25519")).expanduser()
CARPETA_REMOTA = os.environ.get("MC_RESPALDOS_REMOTOS", "~/minecraft-hd/backups")
LOCAL = Path(os.environ.get("MC_RESPALDOS_PC", "~/Respaldos_Minecraft_HD")).expanduser()
CONSERVAR_DIAS = int(os.environ.get("MC_RESPALDOS_PC_DIAS", "14"))

RE_RESPALDO = re.compile(r"^world-\d{8}-\d{6}\.tgz$")
SSH = [
    "ssh",
    "-i",
    str(LLAVE),
    "-o",
    "IdentitiesOnly=yes",
    "-o",
    "BatchMode=yes",
    "-o",
    "StrictHostKeyChecking=accept-new",
    "-o",
    "ConnectTimeout=20",
]


def log(texto: str) -> None:
    LOCAL.mkdir(parents=True, exist_ok=True)
    linea = f"{datetime.now().astimezone().isoformat(timespec='seconds')}  {texto}"
    sys.stdout.write(linea + "\n")
    sys.stdout.flush()
    with (LOCAL / "copiar.log").open("a", encoding="utf-8") as archivo:
        archivo.write(linea + "\n")


def correr(comando: list[str]) -> str:
    resultado = subprocess.run(
        comando,
        check=True,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    return resultado.stdout


def sha256(ruta: Path) -> str:
    digest = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            digest.update(bloque)
    return digest.hexdigest()


def listar_remotos() -> list[str]:
    salida = correr(
        [
            *SSH,
            REMOTO,
            f"find {CARPETA_REMOTA} -maxdepth 1 -type f -name 'world-*.tgz' -printf '%f\\n'",
        ]
    )
    return sorted(n for n in salida.splitlines() if RE_RESPALDO.match(n))


def traer(archivo: str, destino: Path) -> None:
    for sufijo in ("", ".sha256", ".json"):
        nombre = archivo + sufijo
        parcial = destino / (nombre + ".parcial")
        try:
            correr(
                [
                    "rsync",
                    "-a",
                    "--partial",
                    "-e",
                    " ".join(SSH),
                    f"{REMOTO}:{CARPETA_REMOTA}/{nombre}",
                    str(parcial),
                ]
            )
        except subprocess.CalledProcessError:
            parcial.unlink(missing_ok=True)
            if sufijo == "":
                raise
            continue
        parcial.replace(destino / nombre)


def verificar(archivo: Path) -> None:
    sidecar = archivo.with_name(archivo.name + ".sha256")
    esperado = sidecar.read_text(encoding="utf-8").split()[0] if sidecar.is_file() else ""
    real = sha256(archivo)
    if esperado and real != esperado:
        raise RuntimeError(f"el sha256 de {archivo.name} no coincide")
    if not esperado:
        sidecar.write_text(f"{real}  {archivo.name}\n", encoding="utf-8")


def limpiar_viejos() -> None:
    limite = datetime.now().astimezone().date() - timedelta(days=CONSERVAR_DIAS)
    for carpeta in LOCAL.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]"):
        try:
            fecha = date.fromisoformat(carpeta.name)
        except ValueError:
            continue
        if fecha < limite:
            shutil.rmtree(carpeta)
            log(f"borré la copia vieja {carpeta.name}")


def main() -> int:
    if not REMOTO:
        sys.stderr.write("ERROR: define MC_SSH, por ejemplo usuario@tu-vps\n")
        return 1
    LOCAL.mkdir(parents=True, exist_ok=True)
    with (LOCAL / ".lock").open("w", encoding="utf-8") as bloqueo:
        try:
            fcntl.flock(bloqueo, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("ya hay otra copia en curso; salgo")
            return 0

        try:
            remotos = listar_remotos()
            if not remotos:
                raise RuntimeError("el VPS no tiene ningún respaldo")
            archivo = remotos[-1]
            fecha = archivo.removeprefix("world-")[:8]
            carpeta = LOCAL / f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:]}"
            destino = carpeta / archivo
            if destino.is_file():
                log(f"{archivo} ya estaba en la PC")
                return 0

            carpeta.mkdir(parents=True, exist_ok=True)
            log(f"trayendo {archivo}...")
            traer(archivo, carpeta)
            verificar(destino)
            archivos = sorted(p for p in carpeta.iterdir() if p.is_file())
            (carpeta / "SHA256SUMS").write_text(
                "".join(f"{sha256(p)}  {p.name}\n" for p in archivos if p.name != "SHA256SUMS"),
                encoding="utf-8",
            )
            log(f"listo: {destino} ({destino.stat().st_size / 1024**2:.1f} MB)")
            limpiar_viejos()
            return 0
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            log(f"ERROR: {exc}")
            if shutil.which("notify-send"):
                subprocess.run(
                    ["notify-send", "Respaldo de Minecraft HD", f"Falló la copia: {exc}"],
                    check=False,
                )
            return 1


if __name__ == "__main__":
    sys.exit(main())
