"""Envoltura de `docker compose`.

Toda la interacción con Docker pasa por aquí, para que el resto del código
(y los tests) no sepa que Docker existe.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from mc_admin.errores import ErrorDeDocker, ErrorDeEntorno
from mc_admin.infra.registro import obtener

log = obtener("docker")

# Nombres de los servicios del docker-compose.yml.
SERVICIO_MINECRAFT = "minecraft"
SERVICIO_RESPALDOS = "respaldos"
SERVICIO_PAGOS = "pagos-bot"
SERVICIO_RESPALDOS_REMOTO = "respaldos-remoto"
# Los perfiles que existen en el compose. Para APAGAR los nombramos todos:
# si algo estuvo prendido y luego lo apagaste en settings.yml, su contenedor
# seguiría corriendo y `compose down` sin el perfil ni lo vería.
PERFILES = ("pagos", "remoto")
TIMEOUT_NORMAL = 120
# La primera vez baja las imágenes (~1 GB) y construye la del bot. En un VPS
# con internet lento eso pasa de 5 minutos fácil.
TIMEOUT_ARRANQUE = 900
# El apagado tiene stop_grace_period: 2m en el compose; le damos de sobra.
TIMEOUT_APAGADO = 300


@dataclass(frozen=True, slots=True)
class EstadoServicio:
    """Cómo está un contenedor ahora mismo."""

    nombre: str
    estado: str
    salud: str | None

    @property
    def corriendo(self) -> bool:
        return self.estado == "running"

    @property
    def sano(self) -> bool:
        """Sin healthcheck definido, `running` ya cuenta como sano."""
        return self.corriendo and self.salud in (None, "healthy")

    @property
    def descripcion(self) -> str:
        if not self.corriendo:
            return f"apagado ({self.estado})"
        if self.salud == "starting":
            return "arrancando (todavía no responde)"
        if self.salud == "unhealthy":
            return "corriendo pero el healthcheck falla"
        return "corriendo"


class Compose:
    """Corre `docker compose` en la carpeta del proyecto."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = raiz
        self._binario: list[str] | None = None

    # -- disponibilidad ---------------------------------------------------- #

    def _comando_base(self) -> list[str]:
        """Encuentra `docker compose` (v2) o `docker-compose` (v1)."""
        if self._binario is not None:
            return self._binario

        if docker := shutil.which("docker"):
            prueba = subprocess.run(  # noqa: S603 — ruta resuelta por which
                [docker, "compose", "version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if prueba.returncode == 0:
                self._binario = [docker, "compose"]
                return self._binario

        if viejo := shutil.which("docker-compose"):
            self._binario = [viejo]
            return self._binario

        raise ErrorDeEntorno(
            "no encontré `docker compose` en esta máquina",
            pista=(
                "Instala Docker siguiendo docs/vps.md. Si ya está instalado, "
                "revisa que tu usuario pertenezca al grupo `docker` y vuelve a "
                "iniciar sesión."
            ),
        )

    def disponible(self) -> tuple[bool, str | None]:
        """¿Docker responde? Devuelve (sí/no, versión)."""
        try:
            base = self._comando_base()
        except ErrorDeEntorno:
            return False, None
        try:
            salida = subprocess.run(  # noqa: S603
                [*base, "version", "--short"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                cwd=self.raiz,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False, None
        if salida.returncode != 0:
            return False, None
        return True, salida.stdout.strip() or None

    # -- ejecución --------------------------------------------------------- #

    def correr(
        self,
        *argumentos: str,
        timeout: int | None = TIMEOUT_NORMAL,
        capturar: bool = True,
    ) -> str:
        """Corre un subcomando de compose y devuelve su salida.

        Raises:
            ErrorDeDocker: si el comando falla o se pasa del timeout.
        """
        comando = [*self._comando_base(), *argumentos]
        log.debug("corriendo: %s", " ".join(comando))
        try:
            resultado = subprocess.run(  # noqa: S603
                comando,
                cwd=self.raiz,
                capture_output=capturar,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ErrorDeDocker(
                f"`docker compose {argumentos[0]}` se tardó más de {timeout} segundos",
                pista="Revisa `mc logs` para ver si el servidor se atoró arrancando.",
            ) from exc
        except OSError as exc:
            raise ErrorDeDocker(f"no pude correr Docker: {exc}") from exc

        if resultado.returncode != 0:
            detalle = (resultado.stderr or resultado.stdout or "").strip()
            raise ErrorDeDocker(
                f"`docker compose {' '.join(argumentos)}` falló:\n{detalle[:1500]}",
                pista="Si habla de puertos ocupados, corre `mc doctor`.",
            )
        return resultado.stdout or ""

    # -- comandos de alto nivel -------------------------------------------- #

    def validar_compose(self) -> str:
        """`docker compose config`: comprueba que el YAML y el .env cuadren."""
        return self.correr("config", "--quiet")

    def arrancar(self, servicios: list[str] | None = None) -> None:
        """`up -d --build`: crea o RECREA lo que haya cambiado.

        `--build` reconstruye la imagen del bot si cambió su código (con el
        caché de Docker, si no cambió nada tarda un segundo). Y `up`, a
        diferencia de `restart`, vuelve a leer .env y el compose.
        """
        self.correr(
            "up",
            "-d",
            "--build",
            "--remove-orphans",
            *(servicios or []),
            timeout=TIMEOUT_ARRANQUE,
        )

    def apagar(self, servicios: list[str] | None = None) -> None:
        if servicios:
            self.correr("stop", *servicios, timeout=TIMEOUT_APAGADO)
            return
        perfiles = [arg for p in PERFILES for arg in ("--profile", p)]
        self.correr(*perfiles, "down", timeout=TIMEOUT_APAGADO)

    def estado(self) -> list[EstadoServicio]:
        """Lee el estado de todos los servicios con `compose ps --format json`."""
        salida = self.correr("ps", "--all", "--format", "json")
        estados: list[EstadoServicio] = []
        # compose v2 escribe un objeto JSON por línea.
        for linea in salida.splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                datos = json.loads(linea)
            except json.JSONDecodeError:
                log.debug("no pude leer esta línea de `compose ps`: %r", linea[:120])
                continue
            entradas = datos if isinstance(datos, list) else [datos]
            for d in entradas:
                estados.append(
                    EstadoServicio(
                        nombre=d.get("Service") or d.get("Name", "?"),
                        estado=(d.get("State") or "unknown").lower(),
                        salud=(d.get("Health") or None) or None,
                    )
                )
        return estados

    def estado_de(self, servicio: str) -> EstadoServicio | None:
        return next((e for e in self.estado() if e.nombre == servicio), None)

    def logs(self, servicio: str | None = None, lineas: int = 80, seguir: bool = False) -> None:
        """Muestra los logs. Con `seguir` se queda pegado hasta Ctrl+C."""
        argumentos = ["logs", f"--tail={lineas}"]
        if seguir:
            argumentos.append("--follow")
        if servicio:
            argumentos.append(servicio)
        # Sin capturar: queremos que la salida corra directo a la terminal.
        # `--follow` se queda pegado hasta Ctrl+C: ahí no ponemos timeout.
        self.correr(*argumentos, capturar=False, timeout=None if seguir else TIMEOUT_NORMAL)

    def ejecutar_en(self, servicio: str, *comando: str, timeout: int = TIMEOUT_NORMAL) -> str:
        """Corre un comando dentro de un contenedor que ya está arriba."""
        return self.correr("exec", "-T", servicio, *comando, timeout=timeout)
