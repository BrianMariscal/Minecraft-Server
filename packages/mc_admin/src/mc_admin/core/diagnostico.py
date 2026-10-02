"""Las reglas de `mc doctor`.

Cada chequeo es una función pura que recibe datos ya leídos y devuelve un
`Hallazgo`. Quien va por los datos (puertos, RAM, TPS, disco) es `infra`; aquí
nada más decidimos si está bien, regular o mal, y qué decirle al usuario.

Partirlo así nos deja probar el diagnóstico completo sin Docker ni servidor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Nivel(StrEnum):
    """Qué tan grave es un hallazgo."""

    BIEN = "bien"
    AVISO = "aviso"
    MAL = "mal"


@dataclass(frozen=True, slots=True)
class Hallazgo:
    """El resultado de un chequeo, listo para imprimir."""

    titulo: str
    nivel: Nivel
    detalle: str
    pista: str = ""


@dataclass(slots=True)
class Reporte:
    """Todo lo que encontró `mc doctor`."""

    hallazgos: list[Hallazgo] = field(default_factory=list)

    def agregar(self, hallazgo: Hallazgo) -> None:
        self.hallazgos.append(hallazgo)

    @property
    def hay_problemas(self) -> bool:
        return any(h.nivel is Nivel.MAL for h in self.hallazgos)

    @property
    def hay_avisos(self) -> bool:
        return any(h.nivel is Nivel.AVISO for h in self.hallazgos)

    def resumen(self) -> str:
        """Una línea con el veredicto."""
        malos = sum(1 for h in self.hallazgos if h.nivel is Nivel.MAL)
        avisos = sum(1 for h in self.hallazgos if h.nivel is Nivel.AVISO)
        if malos:
            return f"{malos} cosa(s) mal y {avisos} aviso(s). Arregla lo de arriba."
        if avisos:
            return f"Todo jala, con {avisos} aviso(s) que puedes revisar sin prisa."
        return "Todo en orden."


# --------------------------------------------------------------------------- #
#  Chequeos
# --------------------------------------------------------------------------- #

# Cuánta RAM hay que dejarle a lo demás, APARTE de lo que pide el servidor.
#
# El heap que pides (MEMORY=6G) no es todo lo que gasta Java: encima van los
# metaspace, los buffers de red y el stack de cada hilo, fácil 1 GB más. Y
# luego el sistema, el bot de pagos y el contenedor de respaldos.
#
# Con 2 GB de colchón va bien. Con menos, funciona pero el VPS va a andar
# justo, así que lo avisamos: en el VPS de referencia (8 GB con MEMORY=6G)
# quedan como 1 GB libres, y eso es bueno saberlo antes de que empiece a
# irse a swap.
COLCHON_COMODO_GB = 2.0
# Debajo de este colchón ya no arranca bien: lo marcamos como error.
COLCHON_MINIMO_GB = 1.0
# Un mundo pregenerado de radio 3000 más 7 días de respaldos pesa fácil 20 GB.
DISCO_MINIMO_GB = 15.0
# Debajo de 18 TPS ya se siente el lag al minar y al pelear.
TPS_ACEPTABLE = 18.0
TPS_MALO = 15.0


def revisar_docker(disponible: bool, version: str | None) -> Hallazgo:
    """¿Está Docker instalado y responde?"""
    if not disponible:
        return Hallazgo(
            "Docker",
            Nivel.MAL,
            "no encontré Docker o no me deja hablar con él",
            "Instálalo con los pasos de docs/vps.md. Si ya está, revisa que tu "
            "usuario esté en el grupo `docker` (y vuelve a entrar a la sesión).",
        )
    return Hallazgo("Docker", Nivel.BIEN, f"funcionando ({version or 'versión desconocida'})")


def revisar_memoria(ram_total_gb: float | None, memoria_pedida: str) -> Hallazgo:
    """¿Alcanza la RAM del host para lo que pide settings.yml?"""
    if ram_total_gb is None:
        return Hallazgo("Memoria", Nivel.AVISO, "no pude leer la RAM de esta máquina")
    pedida_gb = float(memoria_pedida[:-1]) / (1024 if memoria_pedida.endswith("M") else 1)
    libre = ram_total_gb - pedida_gb

    if libre < COLCHON_MINIMO_GB:
        return Hallazgo(
            "Memoria",
            Nivel.MAL,
            f"el servidor pide {memoria_pedida} y la máquina solo tiene "
            f"{ram_total_gb:.1f} GB en total",
            f"Bájale a recursos.memoria en settings.yml (prueba "
            f"{max(1, int(ram_total_gb - COLCHON_COMODO_GB))}G) o súbele RAM al VPS.",
        )
    if libre < COLCHON_COMODO_GB:
        return Hallazgo(
            "Memoria",
            Nivel.AVISO,
            f"{ram_total_gb:.1f} GB de RAM y el servidor pide {memoria_pedida}: "
            f"quedan {libre:.1f} GB para todo lo demás",
            "Va a funcionar, pero queda justo. Encima del heap, Java gasta "
            "como 1 GB más, y luego van el sistema, el bot de pagos y los "
            "respaldos. Si ves al VPS irse a swap, bájale a recursos.memoria.",
        )
    return Hallazgo(
        "Memoria",
        Nivel.BIEN,
        f"{ram_total_gb:.1f} GB disponibles, el servidor pide {memoria_pedida}",
    )


def revisar_disco(libre_gb: float | None, radio_pregen: int) -> Hallazgo:
    """¿Hay disco para el mundo pregenerado y los respaldos?"""
    if libre_gb is None:
        return Hallazgo("Disco", Nivel.AVISO, "no pude leer el espacio libre")
    # Regla de dedo: un mundo de radio N pesa ~N²/450000 GB con estos datapacks.
    estimado = (radio_pregen**2) / 450_000
    necesario = estimado * 2 + 5  # el mundo, los respaldos y algo de colchón
    if libre_gb < DISCO_MINIMO_GB:
        return Hallazgo(
            "Disco",
            Nivel.MAL,
            f"solo quedan {libre_gb:.1f} GB libres",
            "Libera espacio o súbele disco al VPS antes de pregenerar.",
        )
    if libre_gb < necesario:
        return Hallazgo(
            "Disco",
            Nivel.AVISO,
            f"{libre_gb:.1f} GB libres; un mundo de radio {radio_pregen} más "
            f"los respaldos puede pedir unos {necesario:.0f} GB",
            f"O le bajas a mundo.radio_pregen (prueba "
            f"{int((((libre_gb - 5) / 2) * 450_000) ** 0.5 // 100 * 100)}) o súbele disco.",
        )
    return Hallazgo("Disco", Nivel.BIEN, f"{libre_gb:.1f} GB libres")


def revisar_puertos(ocupados: dict[int, str], esperados: dict[str, int]) -> list[Hallazgo]:
    """¿Están libres los puertos que necesitamos?

    `ocupados` mapea puerto -> quién lo tiene. Si el que lo tiene es nuestro
    propio contenedor, está bien: significa que el servidor ya anda.
    """
    hallazgos: list[Hallazgo] = []
    for servicio, puerto in esperados.items():
        quien = ocupados.get(puerto)
        if quien is None:
            hallazgos.append(Hallazgo(f"Puerto {puerto} ({servicio})", Nivel.BIEN, "libre"))
        elif "minecraft" in quien.lower() or "mc-" in quien.lower():
            hallazgos.append(
                Hallazgo(
                    f"Puerto {puerto} ({servicio})",
                    Nivel.BIEN,
                    f"lo usa {quien}, o sea nosotros",
                )
            )
        else:
            hallazgos.append(
                Hallazgo(
                    f"Puerto {puerto} ({servicio})",
                    Nivel.MAL,
                    f"ocupado por {quien}",
                    f"Apaga ese proceso o cámbiale el puerto a {servicio} en settings.yml.",
                )
            )
    return hallazgos


def revisar_tps(tps: float | None) -> Hallazgo:
    """¿Cómo va el rendimiento del servidor?"""
    if tps is None:
        return Hallazgo("TPS", Nivel.AVISO, "no pude preguntarle al servidor (seguro está apagado)")
    if tps < TPS_MALO:
        return Hallazgo(
            "TPS",
            Nivel.MAL,
            f"{tps:.1f} de 20: el servidor va lento y se siente",
            "Revisa `mc logs`. Suele ser una granja muy grande o un pregen corriendo.",
        )
    if tps < TPS_ACEPTABLE:
        return Hallazgo("TPS", Nivel.AVISO, f"{tps:.1f} de 20: algo cargado pero jugable")
    return Hallazgo("TPS", Nivel.BIEN, f"{tps:.1f} de 20")


def revisar_version_manifest(version_settings: str, version_manifest: str) -> Hallazgo:
    """¿El manifest se verificó contra la versión que pide settings.yml?"""
    if version_settings != version_manifest:
        return Hallazgo(
            "Versiones",
            Nivel.MAL,
            f"settings.yml pide Minecraft {version_settings} pero manifest.yml se "
            f"verificó contra {version_manifest}",
            "Corre `mc update` para revisar qué plugin soporta qué.",
        )
    return Hallazgo("Versiones", Nivel.BIEN, f"Minecraft {version_settings}, todo cuadra")


def revisar_secretos(faltantes: list[str]) -> Hallazgo:
    """¿Está lleno el .env?"""
    if faltantes:
        return Hallazgo(
            "Secretos (.env)",
            Nivel.MAL,
            f"faltan por llenar: {', '.join(faltantes)}",
            "Corre `mc setup` y te los va pidiendo uno por uno.",
        )
    return Hallazgo("Secretos (.env)", Nivel.BIEN, "todo lo necesario está lleno")


def revisar_logo(existe: bool, ruta: str) -> Hallazgo:
    """El logo es opcional: si falta, el servidor arranca igual."""
    if existe:
        return Hallazgo("Logo", Nivel.BIEN, f"{ruta} listo, se convierte a 64x64 al arrancar")
    return Hallazgo(
        "Logo",
        Nivel.AVISO,
        f"no hay {ruta}; el servidor arranca sin icono",
        "Pon una imagen cuadrada ahí. Lee logo/README.md.",
    )


def revisar_traducciones(sospechosas: int) -> Hallazgo:
    """¿Quedó texto en inglés en las configs generadas?"""
    if sospechosas == 0:
        return Hallazgo("Traducciones", Nivel.BIEN, "no encontré mensajes en inglés")
    return Hallazgo(
        "Traducciones",
        Nivel.AVISO,
        f"{sospechosas} línea(s) parecen seguir en inglés",
        "Corre `mc doctor --traducciones` para ver cuáles y en qué archivo.",
    )


def revisar_pendientes_de_llenar(
    pagos_pendiente: bool, admins: int, whitelist: int
) -> list[Hallazgo]:
    """Avisa de lo que todavía trae datos de ejemplo."""
    hallazgos: list[Hallazgo] = []
    if pagos_pendiente:
        hallazgos.append(
            Hallazgo(
                "Bot de pagos",
                Nivel.AVISO,
                "la sección `pagos` de settings.yml todavía trae CAMBIAME",
                "Pon a la banda y al tesorero. Guía en docs/bot-pagos.md.",
            )
        )
    if admins == 0:
        hallazgos.append(
            Hallazgo(
                "Admins",
                Nivel.AVISO,
                "no hay ningún admin configurado",
                "Agrégate con `mc admin add TuNombre`.",
            )
        )
    if whitelist == 0:
        hallazgos.append(
            Hallazgo(
                "Whitelist",
                Nivel.AVISO,
                "la whitelist está vacía: nadie puede entrar",
                "Agrega gente con `mc whitelist add Pepe` (o --bedrock).",
            )
        )
    return hallazgos
