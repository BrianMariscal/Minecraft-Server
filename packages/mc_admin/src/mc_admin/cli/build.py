"""`mc build`: deja la carpeta de datos lista para arrancar.

Baja los plugins y datapacks del manifest verificando su sha256, genera las
configs desde las plantillas y copia las traducciones. Correrlo dos veces
seguidas no cambia nada: es idempotente a propósito.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import typer

from mc_admin.cli import consola
from mc_admin.contexto import Contexto
from mc_admin.core.construccion import Accion, PasoDelPlan, PlanDeConstruccion
from mc_admin.core.manifest import Destino
from mc_admin.core.plantillas import TRADUCCIONES, renderizar_todo
from mc_admin.errores import ErrorMc
from mc_admin.infra import archivos, descargas

app = typer.Typer()


def _accion_de(ruta: Path, contenido: str) -> Accion:
    """Decide qué le va a pasar a un archivo de texto."""
    if not ruta.is_file():
        return Accion.CREAR
    if ruta.read_text(encoding="utf-8") == contenido:
        return Accion.SIN_CAMBIO
    return Accion.ACTUALIZAR


def _accion_de_binario(ruta: Path, tamano: int) -> Accion:
    """Para jars y zips comparamos tamaño: el sha256 ya se verificó al bajar."""
    if not ruta.is_file():
        return Accion.CREAR
    if ruta.stat().st_size == tamano:
        return Accion.SIN_CAMBIO
    return Accion.ACTUALIZAR


def armar_plan(ctx: Contexto, *, descargar: bool = True) -> PlanDeConstruccion:
    """Arma el plan completo de `mc build`.

    Con `descargar=False` no toca la red: solo mira lo que ya está en el
    caché. Es lo que usa `--dry-run` para ser rápido y no bajar 100 MB solo
    para decirte qué haría.
    """
    plan = PlanDeConstruccion()
    manifest = ctx.manifest
    datos = ctx.carpeta_datos

    # 1. ¿El manifest cuadra con la versión de Minecraft que pedimos?
    plan.problemas.extend(manifest.validar_contra(ctx.settings.versiones.minecraft))

    # 2. Configs generadas desde las plantillas.
    generados = renderizar_todo(ctx.settings, ctx.secretos, ctx.carpeta_templates)
    for g in generados:
        destino_gen = ctx.carpeta_generados / g.ruta_relativa
        plan.agregar(
            PasoDelPlan(
                "Configs generadas",
                g.ruta_relativa,
                str(destino_gen.relative_to(ctx.raiz)),
                _accion_de(destino_gen, g.contenido),
            )
        )
        # Las de mensajes/ son referencia para humanos, no van al servidor.
        if g.ruta_relativa.startswith("mensajes/"):
            continue
        plan.agregar(
            PasoDelPlan(
                "Configs del servidor",
                g.ruta_relativa,
                str((datos / g.ruta_relativa).relative_to(ctx.raiz)),
                _accion_de(datos / g.ruta_relativa, g.contenido),
            )
        )

    # 3. Traducciones propias.
    for origen, destino in TRADUCCIONES.items():
        ruta_origen = ctx.carpeta_traducciones / origen
        if not ruta_origen.is_file():
            plan.problemas.append(f"falta la traducción minecraft/translations/es_mx/{origen}")
            continue
        contenido = ruta_origen.read_text(encoding="utf-8")
        plan.agregar(
            PasoDelPlan(
                "Traducciones",
                origen,
                str((datos / destino).relative_to(ctx.raiz)),
                _accion_de(datos / destino, contenido),
            )
        )

    # 4. Plugins y datapacks.
    for destino_tipo, artefacto in manifest.artefactos:
        ruta = datos / artefacto.ruta_destino(destino_tipo)
        en_cache = ctx.carpeta_cache / f"{artefacto.sha256[:12]}-{artefacto.archivo}"
        if en_cache.is_file():
            accion = _accion_de_binario(ruta, en_cache.stat().st_size)
        else:
            accion = Accion.SIN_CAMBIO if ruta.is_file() and not descargar else Accion.CREAR
        categoria = "Plugins" if destino_tipo is Destino.PLUGINS else "Datapacks"
        plan.agregar(
            PasoDelPlan(
                categoria,
                f"{artefacto.nombre} {artefacto.version}",
                str(ruta.relative_to(ctx.raiz)),
                accion,
                detalle="ya en el caché" if en_cache.is_file() else "hay que bajarlo",
            )
        )

    # 5. Vanilla Tweaks.
    if manifest.vanilla_tweaks:
        for pack in manifest.vanilla_tweaks.packs:
            ruta = datos / Destino.DATAPACKS.value / pack.archivo
            plan.agregar(
                PasoDelPlan(
                    "Datapacks",
                    f"Vanilla Tweaks: {pack.archivo}",
                    str(ruta.relative_to(ctx.raiz)),
                    Accion.SIN_CAMBIO if ruta.is_file() else Accion.CREAR,
                )
            )

    # 6. Jars de plugins que ya no están en el manifest.
    esperados = {
        a.archivo for d, a in manifest.artefactos if d is Destino.PLUGINS and not a.subcarpeta
    }
    carpeta_plugins = datos / "plugins"
    if carpeta_plugins.is_dir():
        for jar in sorted(carpeta_plugins.glob("*.jar")):
            if jar.name not in esperados:
                plan.agregar(
                    PasoDelPlan(
                        "Plugins",
                        jar.name,
                        str(jar.relative_to(ctx.raiz)),
                        Accion.QUITAR,
                        detalle="ya no está en el manifest",
                    )
                )

    return plan


def _mostrar_plan(plan: PlanDeConstruccion, *, solo_cambios: bool) -> None:
    for categoria, pasos in plan.por_categoria().items():
        mostrar = [p for p in pasos if p.cambia_algo] if solo_cambios else pasos
        if not mostrar:
            continue
        consola.titulo(categoria)
        for p in mostrar:
            simbolo = {
                Accion.CREAR: "[ok]+[/ok]",
                Accion.ACTUALIZAR: "[dato]~[/dato]",
                Accion.QUITAR: "[mal]-[/mal]",
                Accion.SIN_CAMBIO: "[tenue]=[/tenue]",
            }[p.accion]
            extra = f" [tenue]({p.detalle})[/tenue]" if p.detalle else ""
            consola.consola.print(f"  {simbolo} {p.nombre}{extra}")
            consola.consola.print(f"    [tenue]{p.destino}[/tenue]")


def ejecutar(ctx: Contexto) -> None:
    """Aplica el plan: baja, verifica y escribe.

    No recibe el plan: lo vuelve a derivar de las mismas fuentes. Así no
    puede quedar desfasado entre que se arma y que se aplica.
    """
    archivos.asegurar_carpetas(ctx.raiz)
    datos = ctx.carpeta_datos
    manifest = ctx.manifest

    # --- Configs -------------------------------------------------------- #
    consola.paso("Generando configs desde las plantillas...")
    generados = renderizar_todo(ctx.settings, ctx.secretos, ctx.carpeta_templates)
    for g in generados:
        archivos.escribir_si_cambio(ctx.carpeta_generados / g.ruta_relativa, g.contenido)
        if not g.ruta_relativa.startswith("mensajes/"):
            archivos.escribir_si_cambio(datos / g.ruta_relativa, g.contenido)
    consola.ok(f"{len(generados)} configs generadas")

    # --- Traducciones --------------------------------------------------- #
    consola.paso("Copiando las traducciones al español...")
    for origen, destino in TRADUCCIONES.items():
        ruta_origen = ctx.carpeta_traducciones / origen
        archivos.escribir_si_cambio(datos / destino, ruta_origen.read_text(encoding="utf-8"))
    consola.ok(f"{len(TRADUCCIONES)} archivos de mensajes en español")

    # --- Plugins y datapacks -------------------------------------------- #
    total = len(manifest.artefactos)
    consola.paso(f"Bajando y verificando {total} plugins y datapacks...")
    with descargas.crear_cliente() as cliente:
        for i, (destino_tipo, artefacto) in enumerate(manifest.artefactos, start=1):
            bajado = descargas.obtener_artefacto(artefacto, ctx.carpeta_cache, cliente)
            ruta = datos / artefacto.ruta_destino(destino_tipo)
            archivos.copiar_si_cambio(bajado.ruta, ruta)
            marca = "caché" if bajado.desde_cache else "bajado"
            consola.consola.print(
                f"  [tenue]{i:>2}/{total}[/tenue] [ok]✓[/ok] {artefacto.nombre} "
                f"{artefacto.version} [tenue]({marca}, sha256 ok)[/tenue]"
            )

        # --- Vanilla Tweaks --------------------------------------------- #
        if manifest.vanilla_tweaks:
            consola.paso("Pidiéndole los packs a vanillatweaks.net...")
            packs = descargas.obtener_vanilla_tweaks(
                manifest.vanilla_tweaks, ctx.carpeta_cache, cliente
            )
            for nombre, ruta_pack in packs:
                archivos.copiar_si_cambio(ruta_pack, datos / Destino.DATAPACKS.value / nombre)
            consola.ok(f"{len(packs)} datapacks de Vanilla Tweaks (sha256 ok)")

    # --- Limpieza -------------------------------------------------------- #
    esperados = {
        a.archivo for d, a in manifest.artefactos if d is Destino.PLUGINS and not a.subcarpeta
    }
    quitados = archivos.limpiar_jars_viejos(datos / "plugins", esperados)
    if quitados:
        consola.aviso(f"quité {len(quitados)} jar(s) que ya no están en el manifest")

    # --- El logo ---------------------------------------------------------- #
    if ctx.ruta_logo.is_file():
        consola.ok(f"logo encontrado en {ctx.settings.servidor.logo}")
    else:
        consola.aviso(
            f"no hay {ctx.settings.servidor.logo}; el servidor arranca sin icono "
            "(lee logo/README.md)"
        )


@app.callback(invoke_without_command=True)
def build(
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Enseña qué haría, sin tocar nada."
    ),
    todo: bool = typer.Option(False, "--todo", help="Enseña también lo que ya está al día."),
) -> None:
    """Descarga los plugins, verifica su sha256 y genera todas las configs."""
    try:
        ctx = Contexto.cargar()
        consola.titulo(f"Preparando {ctx.settings.servidor.nombre}")
        consola.tenue(f"  Minecraft {ctx.settings.versiones.minecraft}")

        plan = armar_plan(ctx, descargar=not dry_run)

        if plan.problemas:
            for p in plan.problemas:
                consola.aviso(p)

        if dry_run:
            _mostrar_plan(plan, solo_cambios=not todo)
            consola.titulo("Esto es lo que pasaría")
            consola.info(plan.resumen())
            consola.tenue("\n  Nada de esto se hizo: quita --dry-run para aplicarlo.")
            return

        ejecutar(ctx)
        consola.titulo("Listo")
        consola.info(plan.resumen())
        consola.tenue("\n  Arranca con: mc start")

    except ErrorMc as exc:
        consola.salir_con_error(exc)
    except httpx.HTTPError as exc:  # pragma: no cover — red
        consola.salir_con_error(
            ErrorMc(f"falló la conexión al bajar: {exc}", "Revisa tu internet.")
        )
