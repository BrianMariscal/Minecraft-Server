"""`mc whitelist` y `mc admin`: quién puede entrar y quién manda.

settings.yml es la única fuente de configuración. Cada comando lo edita y luego
`sincronizar` deja al servidor igual: escribe `whitelist.json` completo, con
el UUID correcto de cada quien, y si el servidor está encendido le dice que
lo vuelva a leer y aplica los admins.
"""

from __future__ import annotations

import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core import jugadores as core
from mc_admin.core.jugadores import Plataforma
from mc_admin.errores import ErrorDeConfig, ErrorDeRcon, ErrorMc
from mc_admin.infra import archivos, rcon, xbox

whitelist_app = typer.Typer(help="Quién puede entrar al servidor.")
admin_app = typer.Typer(help="Quién tiene permisos de administración.")


# --------------------------------------------------------------------------- #
#  Dejar al servidor igual que settings.yml
# --------------------------------------------------------------------------- #


def sincronizar(ctx: Contexto, *, en_vivo: bool = True) -> bool:
    """Escribe whitelist.json y, si el servidor contesta, aplica todo en vivo.

    Devuelve True si se aplicó en el servidor encendido.
    """
    w = ctx.settings.whitelist
    entradas, sin_xuid = core.entradas_whitelist(
        list(w.java),
        list(ctx.settings.admins),
        list(w.bedrock),
        dict(w.xuid),
        ctx.settings.seguridad.prefijo_bedrock,
    )
    archivos.escribir_whitelist(ctx.carpeta_datos, [e.a_json() for e in entradas])
    for gamertag in sin_xuid:
        consola.aviso(
            f"{gamertag} (Bedrock) no tiene XUID y NO puede entrar todavía. "
            f'Corre: mc whitelist add "{gamertag}" --bedrock --xuid <número>'
        )

    if not en_vivo:
        return False

    comandos = ["whitelist reload"]
    # LuckPerms por UUID: con el nombre no encuentra a quien no ha entrado.
    comandos += [
        f"lp user {a['uuid']} parent add admin" for a in core.admins_con_uuid(ctx.settings)
    ]
    # `op` solo con nombre de Java: a un UUID lo toma como si fuera un nombre
    # (probado). Los admins de Bedrock tienen los permisos del grupo admin.
    comandos += [f"op {admin}" for admin in ctx.settings.admins]
    try:
        rcon.mandar_varios(ctx.conexion_rcon, comandos)
    except ErrorDeRcon:
        return False
    return True


def _resultado(ctx: Contexto, *, cambio_en_vivo: list[str] | None = None) -> None:
    """Recarga settings.yml, sincroniza y le dice al usuario qué pasó."""
    nuevo = Contexto.cargar(ctx.raiz)
    vivo = sincronizar(nuevo)
    if vivo and cambio_en_vivo:
        try:
            rcon.mandar_varios(nuevo.conexion_rcon, cambio_en_vivo)
        except ErrorDeRcon:  # pragma: no cover — acaba de contestar
            vivo = False
    if vivo:
        consola.ok("ya quedó también en el servidor encendido")
    else:
        consola.tenue("  (el servidor está apagado; se aplica al arrancar)")


def _avisar_de_registrarse(nombre: str) -> None:
    """El hueco de un servidor no premium, dicho a tiempo.

    Sin cuentas de Mojang, el nombre no prueba nada: la contraseña de AuthMe
    la pone el PRIMERO que entra con ese nombre y hace /register. Si alguien
    de fuera se entera del nombre antes que su dueño entre, se queda con la
    cuenta, y si es un admin, con el op. Los de Bedrock no tienen este
    problema: Xbox ya los autenticó y el punto de Floodgate no se puede
    teclear en un nombre de Java.
    """
    consola.aviso(
        f"{nombre} tiene que entrar y hacer /register YA. Mientras no lo haga, "
        "cualquiera que se meta con ese nombre le pone la contraseña y se queda "
        "con su cuenta."
    )


def _xuid_de(gamertag: str, xuid: str | None) -> int:
    """El XUID que nos dieron o, si no, el que encuentre infra.xbox."""
    if xuid:
        return core.validar_xuid(xuid)
    consola.paso(f"Buscando el XUID de {gamertag}...")
    encontrado = xbox.buscar_xuid(gamertag)
    if encontrado is None:
        raise ErrorDeConfig(
            f"no encontré el XUID de '{gamertag}'",
            pista=(
                "Revisa que el gamertag esté bien escrito (el de Xbox, tal cual).\n"
                "Si está bien, consíguelo a mano:\n"
                f"  1. Entra a https://www.cxkes.me/xbox/xuid y busca '{gamertag}'.\n"
                "  2. Copia el número de 'XUID (DEC)'.\n"
                f'  3. mc whitelist add "{gamertag}" --bedrock --xuid <ese número>'
            ),
        )
    consola.ok(f"XUID {encontrado}")
    return encontrado


# --------------------------------------------------------------------------- #
#  Whitelist
# --------------------------------------------------------------------------- #


@whitelist_app.command("add")
def whitelist_add(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
    xuid: str | None = typer.Option(
        None, "--xuid", help="El XUID de Xbox (solo Bedrock, si no se encuentra solo)."
    ),
) -> None:
    """Agrega a alguien a la whitelist."""
    try:
        ctx = Contexto.cargar()
        w = ctx.settings.whitelist

        if not bedrock:
            if xuid:
                raise ErrorDeConfig("--xuid solo sirve con --bedrock")
            cambio = core.agregar(list(w.java), jugador, Plataforma.JAVA)
            if not cambio.cambio:
                consola.aviso(cambio.mensaje)
                return
            archivos.actualizar_settings(ctx.raiz, {"whitelist.java": list(cambio.lista)})
            consola.ok(cambio.mensaje)
            _resultado(ctx)
            _avisar_de_registrarse(core.validar(jugador, Plataforma.JAVA))
            return

        gamertag = core.validar(jugador, Plataforma.BEDROCK)
        ya_tiene = {k.lower() for k in w.xuid}
        cambio = core.agregar(list(w.bedrock), jugador, Plataforma.BEDROCK)
        if not cambio.cambio and gamertag.lower() in ya_tiene and not xuid:
            consola.aviso(cambio.mensaje)
            return

        numero = _xuid_de(jugador.strip(), xuid)
        xuids = {k: v for k, v in w.xuid.items() if k.lower() != gamertag.lower()}
        xuids[gamertag] = numero
        archivos.actualizar_settings(
            ctx.raiz,
            {
                "whitelist.bedrock": list(cambio.lista),
                "whitelist.xuid": dict(sorted(xuids.items())),
            },
        )
        nombre = core.nombre_con_prefijo(gamertag, ctx.settings.seguridad.prefijo_bedrock)
        consola.ok(f"Agregué a {gamertag}. En el servidor se llama: {nombre}")
        _resultado(ctx)
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@whitelist_app.command("remove")
def whitelist_remove(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
) -> None:
    """Saca a alguien de la whitelist."""
    try:
        ctx = Contexto.cargar()
        w = ctx.settings.whitelist
        plataforma = Plataforma.BEDROCK if bedrock else Plataforma.JAVA
        nombre = core.validar(jugador, plataforma)

        admins = ctx.settings.admins_bedrock if bedrock else ctx.settings.admins
        if nombre.lower() in {core.normalizar_gamertag(a).lower() for a in admins}:
            raise ErrorDeConfig(
                f"{nombre} es admin, y los admins siempre están en la whitelist",
                pista=f"Primero quítale el admin: mc admin remove {jugador!r}"
                + (" --bedrock" if bedrock else ""),
            )

        lista = list(w.bedrock if bedrock else w.java)
        cambio = core.quitar(lista, jugador, plataforma)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        cambios: dict[str, list[str] | dict[str, int]] = {
            f"whitelist.{plataforma.value}": list(cambio.lista)
        }
        if bedrock:
            cambios["whitelist.xuid"] = {
                k: v for k, v in w.xuid.items() if k.lower() != nombre.lower()
            }
        archivos.actualizar_settings(ctx.raiz, cambios)
        consola.ok(cambio.mensaje)

        en_el_servidor = (
            core.nombre_con_prefijo(nombre, ctx.settings.seguridad.prefijo_bedrock)
            if bedrock
            else nombre
        )
        # Si está conectado, que se vaya ya: la whitelist solo se revisa al entrar.
        _resultado(ctx, cambio_en_vivo=[f"kick {en_el_servidor} Ya no estás en la whitelist."])
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@whitelist_app.command("list")
def whitelist_list() -> None:
    """Enseña quién está en la whitelist."""
    try:
        ctx = Contexto.cargar()
        w = ctx.settings.whitelist
        admins = list(ctx.settings.admins)
        if not w.java and not w.bedrock and not admins:
            consola.aviso("la whitelist está vacía: nadie puede entrar.")
            consola.tenue("  Agrega gente con: mc whitelist add Pepe")
            return

        t = consola.tabla("Whitelist", ["Jugador", "Plataforma", "Nombre en el servidor", ""])
        for n in admins:
            t.add_row(n, "Java", n, "[dato]admin[/dato]")
        for n in w.java:
            if n.lower() not in {a.lower() for a in admins}:
                t.add_row(n, "Java", n, "")
        prefijo = ctx.settings.seguridad.prefijo_bedrock
        xuids = {k.lower() for k in w.xuid}
        for n in w.bedrock:
            normal = core.normalizar_gamertag(n)
            es_admin = normal.lower() in {
                core.normalizar_gamertag(a).lower() for a in ctx.settings.admins_bedrock
            }
            estado = (
                "[mal]sin XUID: no puede entrar[/mal]"
                if normal.lower() not in xuids
                else ("[dato]admin[/dato]" if es_admin else "")
            )
            t.add_row(n, "Bedrock", core.nombre_con_prefijo(normal, prefijo), estado)
        consola.consola.print(t)
        total = len({n.lower() for n in [*admins, *w.java]}) + len(w.bedrock)
        consola.tenue(f"\n  Total: {total} de {ctx.settings.servidor.max_jugadores} lugares")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


# --------------------------------------------------------------------------- #
#  Admins
# --------------------------------------------------------------------------- #


@admin_app.command("add")
def admin_add(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
    xuid: str | None = typer.Option(
        None, "--xuid", help="El XUID de Xbox (solo Bedrock, si no se encuentra solo)."
    ),
) -> None:
    """Hace admin a alguien: grupo `admin` de LuckPerms y whitelist (y op si es de Java)."""
    try:
        ctx = Contexto.cargar()
        if bedrock:
            _admin_bedrock(ctx, jugador, xuid)
            return
        if xuid:
            raise ErrorDeConfig("--xuid solo sirve con --bedrock")
        cambio = core.agregar(list(ctx.settings.admins), jugador, Plataforma.JAVA)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        archivos.actualizar_settings(ctx.raiz, {"admins": list(cambio.lista)})
        nombre = core.validar(jugador, Plataforma.JAVA)
        consola.ok(f"{cambio.mensaje} Ya está también en la whitelist.")
        _resultado(ctx)
        _regenerar_guion_de_grupos(ctx)
        _avisar_de_registrarse(nombre)
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def _admin_bedrock(ctx: Contexto, jugador: str, xuid: str | None) -> None:
    """Admin de Bedrock: a la whitelist con su XUID, y al grupo admin por UUID."""
    w = ctx.settings.whitelist
    gamertag = core.validar(jugador, Plataforma.BEDROCK)
    admins = core.agregar(list(ctx.settings.admins_bedrock), jugador, Plataforma.BEDROCK)
    ya_tiene_xuid = gamertag.lower() in {k.lower() for k in w.xuid}
    if not admins.cambio and ya_tiene_xuid and not xuid:
        consola.aviso(admins.mensaje)
        return

    cambios: dict[str, list[str] | dict[str, int]] = {"admins_bedrock": list(admins.lista)}
    if xuid or not ya_tiene_xuid:
        numero = _xuid_de(jugador.strip(), xuid)
        xuids = {k: v for k, v in w.xuid.items() if k.lower() != gamertag.lower()}
        xuids[gamertag] = numero
        cambios["whitelist.xuid"] = dict(sorted(xuids.items()))
    lista = core.agregar(list(w.bedrock), jugador, Plataforma.BEDROCK)
    cambios["whitelist.bedrock"] = list(lista.lista)
    archivos.actualizar_settings(ctx.raiz, cambios)

    nombre = core.nombre_con_prefijo(gamertag, ctx.settings.seguridad.prefijo_bedrock)
    consola.ok(f"{gamertag} ya es admin (en el servidor: {nombre}) y está en la whitelist.")
    _resultado(ctx)
    _regenerar_guion_de_grupos(ctx)


@admin_app.command("remove")
def admin_remove(
    jugador: str = typer.Argument(..., help="Nombre de Java, o gamertag si es --bedrock."),
    bedrock: bool = typer.Option(False, "--bedrock", "-b", help="Es alguien de Bedrock."),
) -> None:
    """Le quita el admin a alguien. Sigue en la whitelist como jugador normal."""
    try:
        ctx = Contexto.cargar()
        if bedrock:
            cambio = core.quitar(list(ctx.settings.admins_bedrock), jugador, Plataforma.BEDROCK)
            if not cambio.cambio:
                consola.aviso(cambio.mensaje)
                return
            gamertag = core.validar(jugador, Plataforma.BEDROCK)
            xuid = {k.lower(): v for k, v in ctx.settings.whitelist.xuid.items()}.get(
                gamertag.lower()
            )
            archivos.actualizar_settings(ctx.raiz, {"admins_bedrock": list(cambio.lista)})
            consola.ok(f"{cambio.mensaje} Sigue en la whitelist como jugador normal.")
            en_vivo = [f"lp user {core.uuid_floodgate(xuid)} parent remove admin"] if xuid else []
            _resultado(ctx, cambio_en_vivo=en_vivo)
            _regenerar_guion_de_grupos(ctx)
            return

        cambio = core.quitar(list(ctx.settings.admins), jugador, Plataforma.JAVA)
        if not cambio.cambio:
            consola.aviso(cambio.mensaje)
            return

        nombre = core.validar(jugador, Plataforma.JAVA)
        # Que siga pudiendo entrar: pasa a la whitelist normal.
        java = core.agregar(list(ctx.settings.whitelist.java), nombre, Plataforma.JAVA)
        archivos.actualizar_settings(
            ctx.raiz, {"admins": list(cambio.lista), "whitelist.java": list(java.lista)}
        )
        consola.ok(f"{cambio.mensaje} Sigue en la whitelist como jugador normal.")
        uuid = core.uuid_offline(nombre)
        _resultado(ctx, cambio_en_vivo=[f"lp user {uuid} parent remove admin", f"deop {nombre}"])
        _regenerar_guion_de_grupos(ctx)
    except ErrorMc as exc:
        consola.salir_con_error(exc)


@admin_app.command("list")
def admin_list() -> None:
    """Enseña quiénes son admins."""
    try:
        ctx = Contexto.cargar()
        if not ctx.settings.admins and not ctx.settings.admins_bedrock:
            consola.aviso("no hay ningún admin configurado.")
            consola.tenue("  Agrégate con: mc admin add TuNombre")
            return
        consola.titulo("Admins")
        for n in ctx.settings.admins:
            consola.info(f"[dato]{n}[/dato] [tenue](Java)[/tenue]")
        for n in ctx.settings.admins_bedrock:
            consola.info(f"[dato]{n}[/dato] [tenue](Bedrock)[/tenue]")
    except ErrorMc as exc:
        consola.salir_con_error(exc)


def _regenerar_guion_de_grupos(ctx: Contexto) -> None:
    """El guion de LuckPerms trae la lista de admins: que no quede viejo."""
    from mc_admin.core.plantillas import renderizar_todo

    nuevo = Contexto.cargar(ctx.raiz)
    for g in renderizar_todo(
        nuevo.settings, nuevo.secretos, nuevo.carpeta_templates, solo="luckperms-grupos.txt.j2"
    ):
        archivos.escribir_si_cambio(nuevo.carpeta_generados / g.ruta_relativa, g.contenido)
