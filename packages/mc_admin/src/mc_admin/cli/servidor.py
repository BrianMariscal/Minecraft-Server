"""Comandos del día a día: start, stop, restart, status, logs y console."""

from __future__ import annotations

import time

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import gamerules
from mc_admin.errores import ErrorDeRcon, ErrorMc
from mc_admin.infra import rcon
from mc_admin.infra.docker import SERVICIO_MINECRAFT

# Cuánto esperamos a que el servidor conteste antes de rendirnos y decirle al
# usuario que lo revise luego. El primer arranque con los datapacks genera
# mundo y puede tardar mucho más que esto.
ESPERA_MAXIMA = 90
ESPERA_ENTRE_INTENTOS = 5


def _ctx() -> Contexto:
    return Contexto.cargar()


def _esperar_a_que_conteste(ctx: Contexto) -> bool:
    """Espera a que RCON conteste. True si contestó dentro del plazo."""
    esperado = 0
    while esperado < ESPERA_MAXIMA:
        if rcon.esta_vivo(ctx.conexion_rcon):
            return True
        time.sleep(ESPERA_ENTRE_INTENTOS)
        esperado += ESPERA_ENTRE_INTENTOS
    return False


def aplicar_configuracion_en_vivo(ctx: Contexto) -> None:
    """Pone las gamerules, los grupos de LuckPerms y la whitelist.

    Esto no se puede dejar en un archivo de config: las gamerules viven en el
    mundo y los grupos en la base de datos de LuckPerms, así que hay que
    decírselo al servidor ya encendido. Correrlo dos veces no hace daño.
    """
    from mc_admin.core import jugadores as core_jugadores

    # --- Gamerules ------------------------------------------------------ #
    reglas = gamerules.reglas_para(dormir_con_un_jugador=ctx.settings.mundo.dormir_con_un_jugador)
    try:
        rcon.mandar_varios(ctx.conexion_rcon, gamerules.comandos_de(reglas))
        consola.ok(f"{len(reglas)} gamerules puestas")
    except ErrorDeRcon as exc:
        consola.aviso(f"no pude poner las gamerules: {exc.mensaje}")

    # --- Grupos de LuckPerms -------------------------------------------- #
    guion = ctx.carpeta_generados / "mensajes" / "luckperms-grupos.txt"
    if guion.is_file():
        comandos = [
            linea.strip()
            for linea in guion.read_text(encoding="utf-8").splitlines()
            if linea.strip() and not linea.lstrip().startswith("#")
        ]
        try:
            rcon.mandar_varios(ctx.conexion_rcon, comandos, timeout=rcon.TIMEOUT_LARGO)
            consola.ok(f"grupos y permisos aplicados ({len(comandos)} comandos)")
        except ErrorDeRcon as exc:
            consola.aviso(f"no pude aplicar los grupos: {exc.mensaje}")

    # --- Whitelist ------------------------------------------------------- #
    nombres = core_jugadores.nombres_para_el_servidor(
        list(ctx.settings.whitelist.java),
        list(ctx.settings.whitelist.bedrock),
        ctx.settings.seguridad.prefijo_bedrock,
    )
    if nombres:
        try:
            rcon.mandar_varios(ctx.conexion_rcon, [f"whitelist add {n}" for n in nombres])
            consola.ok(f"{len(nombres)} jugador(es) en la whitelist")
        except ErrorDeRcon as exc:
            consola.aviso(f"no pude aplicar la whitelist: {exc.mensaje}")


def _revisar_que_se_pueda_arrancar(ctx: Contexto) -> None:
    """Truena si falta algo imprescindible para encender el servidor."""
    faltan = ctx.secretos.faltantes_para(
        discord=ctx.settings.discord.activo, pagos=ctx.settings.pagos.activo
    )
    if faltan:
        raise ErrorMc(
            "faltan cosas por llenar en .env: " + ", ".join(faltan),
            "Corre `mc setup` y te las va pidiendo una por una.",
        )
    if not (ctx.carpeta_datos / "server.properties").is_file():
        raise ErrorMc(
            "todavía no hay configs generadas",
            "Corre `mc build` antes de arrancar.",
        )


def start() -> None:
    """Enciende el servidor (y el bot de pagos y los respaldos)."""
    try:
        ctx = _ctx()
        _revisar_que_se_pueda_arrancar(ctx)

        consola.paso(f"Encendiendo {ctx.settings.servidor.nombre}...")
        ctx.compose.arrancar()
        consola.ok("contenedores arriba")

        consola.paso("Esperando a que el servidor conteste...")
        if _esperar_a_que_conteste(ctx):
            aplicar_configuracion_en_vivo(ctx)
        else:
            consola.tenue(
                "  Todavía no contesta. Es normal en el primer arranque: está\n"
                "  generando el mundo con los 10 datapacks.\n"
                "  Cuando termine, corre `mc start` otra vez para que aplique\n"
                "  las gamerules y los grupos de permisos."
            )

        consola.tenue("\n  Míralo con: mc logs -f\n  Revisa que todo esté bien con: mc doctor")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def stop() -> None:
    """Apaga el servidor guardando el mundo."""
    try:
        ctx = _ctx()
        # Guardamos antes de apagar: `compose stop` manda SIGTERM y la imagen
        # de itzg hace un `stop` limpio, pero un save-all extra no sobra y
        # cubre el caso de que el servidor esté lento.
        try:
            rcon.mandar(ctx.conexion_rcon, "save-all", timeout=rcon.TIMEOUT_LARGO)
            consola.ok("mundo guardado")
        except ErrorDeRcon:
            consola.tenue("  (no contestó por RCON; seguro ya estaba apagado)")

        consola.paso("Apagando...")
        ctx.compose.apagar()
        consola.ok("apagado")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def restart() -> None:
    """Reinicia el servidor."""
    try:
        ctx = _ctx()
        try:
            rcon.mandar(ctx.conexion_rcon, "save-all", timeout=rcon.TIMEOUT_LARGO)
            consola.ok("mundo guardado")
        except ErrorDeRcon:
            pass
        consola.paso("Reiniciando...")
        ctx.compose.reiniciar()
        consola.ok("reiniciado")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def status() -> None:
    """Dice cómo está el servidor y quién anda conectado."""
    try:
        ctx = _ctx()
        consola.titulo(ctx.settings.servidor.nombre)

        estados = ctx.compose.estado()
        if not estados:
            consola.aviso("no hay ningún contenedor. Arranca con `mc start`.")
            return

        t = consola.tabla("", ["Servicio", "Estado"])
        for e in estados:
            color = "ok" if e.sano else ("aviso" if e.corriendo else "mal")
            t.add_row(e.nombre, f"[{color}]{e.descripcion}[/{color}]")
        consola.consola.print(t)

        servidor = next((e for e in estados if e.nombre == SERVICIO_MINECRAFT), None)
        if servidor and servidor.corriendo:
            try:
                conectados, maximo, nombres = rcon.jugadores_conectados(ctx.conexion_rcon)
                consola.info(f"\nJugadores: [dato]{conectados}[/dato] de {maximo}")
                if nombres:
                    consola.info("  " + ", ".join(nombres))
                tps = rcon.leer_tps(ctx.conexion_rcon)
                if tps is not None:
                    color = "ok" if tps >= 18 else ("aviso" if tps >= 15 else "mal")
                    consola.info(f"TPS: [{color}]{tps:.1f}[/{color}] de 20")
            except ErrorDeRcon:
                consola.tenue("\n  (todavía no contesta por RCON; puede seguir arrancando)")

        consola.tenue(
            f"\n  Java:    tu-ip:{ctx.settings.puertos.java}\n"
            f"  Bedrock: tu-ip:{ctx.settings.puertos.bedrock}\n"
            f"  Mapa:    http://tu-ip:{ctx.settings.puertos.bluemap}"
        )
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def logs(
    seguir: bool = typer.Option(False, "--seguir", "-f", help="Quédate viendo los logs."),
    lineas: int = typer.Option(80, "--lineas", "-n", help="Cuántas líneas mostrar."),
    servicio: str | None = typer.Option(
        None, "--servicio", "-s", help="Solo un servicio: minecraft, respaldos o pagos-bot."
    ),
) -> None:
    """Muestra los logs del servidor."""
    try:
        ctx = _ctx()
        ctx.compose.logs(servicio, lineas=lineas, seguir=seguir)
    except KeyboardInterrupt:
        consola.tenue("\n  Listo.")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def console() -> None:
    """Consola interactiva del servidor por RCON."""
    try:
        ctx = _ctx()
        if not rcon.esta_vivo(ctx.conexion_rcon):
            raise ErrorDeRcon(
                "el servidor no contesta",
                "Revisa con `mc status` y arranca con `mc start`.",
            )

        consola.titulo(f"Consola de {ctx.settings.servidor.nombre}")
        consola.tenue("  Escribe comandos sin la diagonal. `salir` para terminar.\n")

        with rcon.abrir(ctx.conexion_rcon) as cliente:
            while True:
                try:
                    linea = typer.prompt("mc", prompt_suffix="> ").strip()
                except (EOFError, KeyboardInterrupt):
                    consola.consola.print()
                    break
                if not linea:
                    continue
                if linea.lower() in {"salir", "exit", "quit"}:
                    break
                # `stop` desde aquí dejaría la consola colgada hablando con un
                # servidor que ya se murió.
                if linea.lower().split()[0] == "stop":
                    consola.aviso("para apagar usa `mc stop`, que además guarda el mundo.")
                    continue
                try:
                    respuesta = rcon.limpiar(cliente.command(linea.lstrip("/")) or "")
                except Exception as exc:
                    consola.mal(f"falló: {exc}")
                    continue
                consola.consola.print(respuesta or "[tenue](sin respuesta)[/tenue]")

        consola.tenue("  Listo.")
    except ErrorMc as exc:
        consola.salir_con_error(exc)
