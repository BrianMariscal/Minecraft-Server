"""`mc setup`: revisa el entorno y te pide lo que falte en .env."""

from __future__ import annotations

import secrets as pysecrets

import typer

from mc_admin.cli import consola
from mc_admin.config import ARCHIVO_ENV, cargar_secretos
from mc_admin.contexto import Contexto
from mc_admin.errores import ErrorMc
from mc_admin.infra import archivos

# Qué le pedimos al usuario, en orden, y cómo se lo explicamos.
PREGUNTAS: list[tuple[str, str, str, bool]] = [
    (
        "RCON_PASSWORD",
        "Contraseña de la consola remota",
        "La usan `mc console`, la whitelist y los respaldos. Vive solo dentro\n"
        "  de Docker, nunca se expone a internet. Si la dejas vacía te genero una.",
        False,
    ),
    (
        "PAGOS_BOT_TOKEN",
        "Token del bot de pagos",
        "El bot de Discord que cobra el VPS. Cómo crearlo: docs/bot-pagos.md",
        True,
    ),
    (
        "PAGOS_GUILD_ID",
        "ID de tu servidor de Discord",
        "Clic derecho en el nombre del servidor > Copiar ID.",
        True,
    ),
    (
        "PAGOS_CANAL_ID",
        "ID del canal #pagos",
        "Donde el bot va a mandar los recordatorios.",
        True,
    ),
    (
        "ALERTAS_CANAL_ID",
        "ID del canal de alertas (opcional)",
        "El bot de pagos avisa ahí si el servidor de Minecraft se cae y cuando\n"
        "  vuelve. Déjalo vacío si no lo quieres. Puede ser el mismo #pagos.",
        False,
    ),
]


def setup() -> None:
    """Revisa el entorno, crea .env si falta y te pide los datos necesarios."""
    try:
        ctx = Contexto.cargar()
        consola.titulo(f"Preparando {ctx.settings.servidor.nombre}")

        # --- 1. ¿Está Docker? ------------------------------------------- #
        disponible, version = ctx.compose.disponible()
        if disponible:
            consola.ok(f"Docker listo ({version or 'versión desconocida'})")
        else:
            consola.mal("no encontré Docker, o no me deja hablar con él")
            consola.tenue(
                "  Instálalo con los pasos de docs/vps.md.\n"
                "  Si ya está, revisa que tu usuario esté en el grupo `docker`."
            )

        # --- 2. ¿Existe .env? -------------------------------------------- #
        ruta_env = ctx.raiz / ARCHIVO_ENV
        if not ruta_env.is_file():
            consola.aviso(f"no hay {ARCHIVO_ENV}; lo voy a crear desde .env.example")

        # --- 3. Pedir lo que falte --------------------------------------- #
        actuales = cargar_secretos(ctx.raiz, usar_entorno=False)
        nuevos: dict[str, str] = {}

        consola.titulo("Datos que hacen falta")
        consola.tenue(
            "  Déjalo vacío para no cambiarlo. Nada de esto entra a git:\n"
            "  .env está en .gitignore.\n"
        )

        for clave, etiqueta, ayuda, es_secreto in PREGUNTAS:
            # Si el bot de pagos está apagado, no molestamos con eso.
            if clave.startswith(("PAGOS", "ALERTAS")) and not ctx.settings.pagos.activo:
                continue

            ya = getattr(actuales, clave.lower(), "")
            estado = "[ok]ya está[/ok]" if ya else "[aviso]falta[/aviso]"
            consola.consola.print(f"\n[dato]{etiqueta}[/dato] ({clave}) — {estado}")
            consola.tenue(f"  {ayuda}")

            respuesta = typer.prompt(
                "  valor", default="", show_default=False, hide_input=es_secreto
            ).strip()

            if not respuesta and clave == "RCON_PASSWORD" and not ya:
                respuesta = pysecrets.token_urlsafe(32)
                consola.ok("te generé una contraseña larga y aleatoria")
            if respuesta:
                nuevos[clave] = respuesta

        if nuevos:
            archivos.escribir_env(ctx.raiz, nuevos)
            consola.ok(f"guardé {len(nuevos)} dato(s) en {ARCHIVO_ENV} (permisos 600)")
        else:
            consola.tenue("\n  No cambiaste nada.")

        # --- 4. ¿Qué falta todavía? --------------------------------------- #
        finales = cargar_secretos(ctx.raiz, usar_entorno=False)
        faltan = finales.faltantes_para(pagos=ctx.settings.pagos.activo)

        consola.titulo("Cómo vamos")
        if faltan:
            consola.aviso("todavía faltan: " + ", ".join(faltan))
            consola.tenue("  Vuelve a correr `mc setup` cuando los tengas.")
        else:
            consola.ok("ya está todo lo de .env")

        pendientes: list[str] = []
        if ctx.settings.pagos.pendiente_de_llenar:
            pendientes.append("la sección `pagos` de settings.yml trae CAMBIAME")
        if not ctx.settings.admins:
            pendientes.append("no hay admins (`mc admin add TuNombre`)")
        if not (ctx.settings.whitelist.java or ctx.settings.whitelist.bedrock):
            pendientes.append("la whitelist está vacía (`mc whitelist add Pepe`)")
        if not ctx.ruta_logo.is_file():
            pendientes.append(f"no hay {ctx.settings.servidor.logo} (lee logo/README.md)")

        if pendientes:
            consola.consola.print()
            for p in pendientes:
                consola.aviso(p)

        consola.tenue("\n  Siguiente paso: mc build")

    except ErrorMc as exc:
        consola.salir_con_error(exc)
