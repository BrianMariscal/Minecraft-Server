"""Las variables que conectan settings.yml con docker-compose.yml.

El compose no tiene números escritos a mano: lee la versión, la memoria, los
puertos y los respaldos de variables `MC_*`. `mc build` las calcula aquí a
partir de settings.yml y las escribe en un bloque marcado dentro de `.env`,
que es el archivo que Docker Compose lee solo. Así funciona igual con `mc
start` que con un `docker compose up -d` a mano.

Pura: recibe la configuración y devuelve texto. No toca el disco.
"""

from __future__ import annotations

from mc_admin.config import Settings

# Lo que la JVM usa FUERA del heap (metaspace, hilos, buffers de red de
# Geyser, los hilos de los plugins). Si el límite del contenedor es igual al
# heap, el kernel mata a Java en cuanto el servidor se pone a trabajar.
MEMORIA_EXTRA_MB = 1536

# Los perfiles de Compose: servicios que solo arrancan si están prendidos
# en settings.yml.
PERFIL_PAGOS = "pagos"
PERFIL_REMOTO = "remoto"
TODOS_LOS_PERFILES = (PERFIL_PAGOS, PERFIL_REMOTO)

# Las marcas del bloque que `mc build` administra dentro de .env.
INICIO_BLOQUE = "# >>> generado por `mc build` desde settings.yml: no lo edites a mano"
FIN_BLOQUE = "# <<< fin de lo generado por `mc build`"


def memoria_en_mb(memoria: str) -> int:
    """'6G' -> 6144, '5632M' -> 5632."""
    numero = int(memoria[:-1])
    return numero * 1024 if memoria.upper().endswith("G") else numero


def limite_del_contenedor(memoria: str) -> str:
    """El tope de RAM del contenedor: el heap más lo que Java usa fuera de él."""
    return f"{memoria_en_mb(memoria) + MEMORIA_EXTRA_MB}m"


def separar_remoto(destino: str) -> tuple[str, str]:
    """'gdrive:minecraft-hd' -> ('gdrive', 'minecraft-hd').

    itzg/mc-backup pide el nombre del remoto de rclone y la carpeta por
    separado; en settings.yml se escriben juntos, como en la línea de
    comandos de rclone.
    """
    remoto, _, carpeta = destino.partition(":")
    return remoto.strip(), carpeta.strip().strip("/")


def variables(settings: Settings, *, uid: int, gid: int, conf_rclone: str) -> dict[str, str]:
    """Todas las variables que lee docker-compose.yml, ya calculadas."""
    v = settings.versiones
    p = settings.puertos
    r = settings.respaldos

    valores = {
        "MC_VERSION": v.minecraft,
        "MC_IMAGEN": v.imagen_servidor,
        "MC_IMAGEN_RESPALDOS": v.imagen_respaldos,
        "MC_MEMORIA": settings.recursos.memoria,
        "MC_MEMORIA_LIMITE": limite_del_contenedor(settings.recursos.memoria),
        "MC_AIKAR": "true" if settings.recursos.flags_aikar else "false",
        "MC_PUERTO_JAVA": str(p.java),
        "MC_PUERTO_BEDROCK": str(p.bedrock),
        "MC_PUERTO_RCON": str(p.rcon),
        "MC_RESPALDOS_INTERVALO": r.intervalo,
        "MC_RESPALDOS_DIAS": str(r.conservar_dias),
        "MC_UID": str(uid),
        "MC_GID": str(gid),
    }

    perfiles: list[str] = []
    if settings.pagos.activo:
        perfiles.append(PERFIL_PAGOS)
    if r.remoto.activo:
        perfiles.append(PERFIL_REMOTO)
        remoto, carpeta = separar_remoto(r.remoto.destino)
        valores |= {
            "MC_REMOTO_INTERVALO": r.remoto.intervalo,
            "RCLONE_REMOTE": remoto,
            "RCLONE_DEST_DIR": carpeta,
            "MC_RCLONE_CONF": conf_rclone,
        }
    # Se escribe aunque quede vacío: si no, un valor viejo de cuando algo
    # estuvo prendido seguiría vivo en el .env.
    valores["COMPOSE_PROFILES"] = ",".join(perfiles)

    return valores


def bloque(valores: dict[str, str]) -> str:
    """El texto que va dentro de .env, con sus marcas."""
    lineas = [INICIO_BLOQUE]
    lineas.extend(f"{k}={val}" for k, val in valores.items())
    lineas.append(FIN_BLOQUE)
    return "\n".join(lineas)


def reemplazar_bloque(texto_env: str, nuevo_bloque: str) -> str:
    """Pone el bloque en el .env, sustituyendo el anterior si ya había uno.

    Lo de fuera del bloque (los secretos, tus comentarios) no se toca.
    """
    lineas = texto_env.splitlines()
    try:
        inicio = lineas.index(INICIO_BLOQUE)
        fin = lineas.index(FIN_BLOQUE, inicio)
    except ValueError:
        base = texto_env.rstrip("\n")
        separador = "\n\n" if base else ""
        return f"{base}{separador}{nuevo_bloque}\n"

    resultado = [*lineas[:inicio], *nuevo_bloque.splitlines(), *lineas[fin + 1 :]]
    return "\n".join(resultado) + "\n"
