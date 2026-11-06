"""Arma messages_es.properties en español de México para EssentialsX.

Parte del es_ES que trae el jar, le completa las claves que faltan, traduce
las que quedaron idénticas al inglés y corrige lo que suena a España o a
traducción automática.
"""

import re
import sys


def cargar(p):
    orden, datos = [], {}
    for ln in open(p, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, _, v = ln.partition("=")
        k = k.strip()
        if k not in datos:
            orden.append(k)
        datos[k] = v
    return orden, datos


en_orden, EN = cargar("ess_en.properties")
_, ES = cargar("ess_es.properties")

# --- Etiquetas que NUNCA se traducen -------------------------------------
# <primary>, <secondary> y los colores son MiniMessage; <command> lo
# sustituye EssentialsX con el nombre real del comando.
NO_TOCAR = {
    "command",
    "primary",
    "secondary",
    "reset",
    "st",
    "i",
    "b",
    "u",
    "gray",
    "white",
    "black",
    "red",
    "dark_red",
    "green",
    "dark_green",
    "blue",
    "dark_blue",
    "aqua",
    "dark_aqua",
    "yellow",
    "gold",
    "light_purple",
    "dark_purple",
    "italic",
    "bold",
    "underlined",
    "strikethrough",
    "obfuscated",
    "newline",
    "click",
    "hover",
}

# Nombres de argumento que SÍ se traducen dentro de los textos de uso.
ARGUMENTOS = {
    "player": "jugador",
    "playername": "jugador",
    "otherplayer": "otro jugador",
    "other player": "otro jugador",
    "target": "objetivo",
    "world": "mundo",
    "message": "mensaje",
    "msg": "mensaje",
    "name": "nombre",
    "new name": "nombre nuevo",
    "nickname": "apodo",
    "reason": "motivo",
    "amount": "cantidad",
    "number": "cantidad",
    "item": "item",
    "itemname": "item",
    "itemid": "id del item",
    "kitname": "kit",
    "kit": "kit",
    "warp": "warp",
    "jailname": "jaula",
    "seconds": "segundos",
    "radius": "radio",
    "speed": "velocidad",
    "type": "tipo",
    "mob": "mob",
    "mob type": "tipo de mob",
    "args": "argumentos",
    "price": "precio",
    "delay": "espera",
    "expire time": "tiempo",
    "datediff": "tiempo",
    "line number": "fila",
    "text": "texto",
    "meta": "meta",
    "value": "valor",
    "owner": "propietario",
    "texture": "textura",
    "channel": "canal",
    "duration": "tiempo",
    "description": "texto",
    "page": "hoja",
    "to": "para",
    "address": "ip",
    "x": "x",
    "y": "y",
    "z": "z",
    "yaw": "yaw",
    "pitch": "pitch",
}

# El mismo regex de EssentialsX, para comprobar que cada nombre que ponemos
# sigue siendo un argumento que el plugin va a resaltar.
RE_ARG_VALIDO = re.compile(r"^[A-Za-z |]+$")

RE_TAG = re.compile(r"<([^<>]+)>")


def traducir_argumentos(texto):
    """Traduce <player> -> <jugador> sin tocar las etiquetas de color."""

    def reemplazo(m):
        dentro = m.group(1)
        if dentro.lower() in NO_TOCAR or dentro.startswith("/"):
            return m.group(0)
        # Opciones separadas por | : <tree|birch|redwood>
        if "|" in dentro:
            partes = [ARGUMENTOS.get(p.strip().lower(), p) for p in dentro.split("|")]
            return "<" + "|".join(partes) + ">"
        return "<" + ARGUMENTOS.get(dentro.lower(), dentro) + ">"

    salida = RE_TAG.sub(reemplazo, texto)

    # [player] y [reason] entre corchetes también son argumentos opcionales.
    def corchetes(m):
        dentro = m.group(1)
        if "|" in dentro:
            partes = [ARGUMENTOS.get(p.strip().lower(), p) for p in dentro.split("|")]
            return "[" + "|".join(partes) + "]"
        return "[" + ARGUMENTOS.get(dentro.lower(), dentro) + "]"

    salida = re.sub(r"\[([^\[\]]+)\]", corchetes, salida)
    # Ultima pasada para los argumentos compuestos que los dos reemplazos de
    # arriba no parten, como [player\:], [player/message...] o <[player\:]name>.
    # Es seguro hacerlo por palabra completa: ningun subcomando de EssentialsX
    # se llama "player", "name" ni "message".
    for ingles, espanol in (
        ("players", "jugadores"),
        ("player", "jugador"),
        ("message", "mensaje"),
        ("name", "nombre"),
    ):
        salida = re.sub(rf"\b{ingles}\b", espanol, salida)
    return salida


print("script listo", file=sys.stderr)

# --------------------------------------------------------------------------
#  Textos que escribimos a mano: los que lee un jugador.
#  Tono mexicano, corto, natural. Nada de "Por favor, proceda a...".
# --------------------------------------------------------------------------
A_MANO = {
    # --- Silenciados: avisos de plugin que no le sirven al jugador -------
    # Vacío = EssentialsX no manda nada. "Comprobación de actualización
    # desactivada" les salía a los admins en cada entrada, y el de /back
    # en cada muerte (el comando sigue funcionando).
    "versionCheckDisabled": "",
    "backAfterDeath": "",
    # --- Casas (el jar decía "hogar", que nadie dice) --------------------
    "homeSet": "<gray>Guardé tu casa.",
    "homes": "<primary>Tus casas:<reset> {0}",
    "noHomeSetPlayer": "<primary>Ese jugador no tiene casas guardadas.",
    "maxHomes": "<dark_red>Ya tienes tus<secondary> {0} <dark_red>casas. Borra una con <secondary>/delhome<dark_red>.",
    "deleteHome": "<gray>Borré la casa<secondary> {0}<gray>.",
    "invalidHome": "<dark_red>No tienes ninguna casa que se llame<secondary> {0}<dark_red>.",
    "teleportHome": "<primary>Yendo a tu casa<secondary> {0}<primary>.",
    "invalidHomeName": "<dark_red>Ese nombre de casa no sirve.",
    "homeConfirmation": "<primary>Ya tienes una casa que se llama<secondary> {0}<primary>.\n<primary>Vuelve a escribir el comando para reemplazarla.",
    "homeRenamed": "<gray>La casa<secondary> {0} <gray>ahora se llama<secondary> {1}<gray>.",
    # --- Teletransporte --------------------------------------------------
    "teleporting": "<primary>Teletransportando...",
    "teleportationCommencing": "<primary>Ahí voy...",
    "teleportHereRequest": "<secondary>{0}<primary> quiere que te teletransportes con él.",
    "teleportRequest": "<secondary>{0}<primary> quiere teletransportarse contigo.",
    "requestSent": "<primary>Le mandé la petición a<secondary> {0}<primary>.",
    "requestAccepted": "<primary>Aceptaron tu petición.",
    "requestAcceptedFrom": "<secondary>{0}<primary> aceptó tu petición.",
    "requestDenied": "<primary>Rechazaste la petición.",
    "requestDeniedFrom": "<secondary>{0}<primary> rechazó tu petición.",
    "requestTimedOut": "<dark_red>Se acabó el tiempo de la petición.",
    "requestTimedOutFrom": "<dark_red>Se acabó el tiempo de la petición de<secondary> {0}<dark_red>.",
    "typeTpaccept": "<primary>Escribe <secondary>/tpaccept <primary>para aceptar.",
    "typeTpdeny": "<primary>Escribe <secondary>/tpdeny <primary>para rechazar.",
    "typeTpacancel": "<primary>Escribe <secondary>/tpacancel <primary>para cancelar.",
    "pendingTeleportCancelled": "<dark_red>Cancelé la petición de teletransporte.",
    "teleportRequestAllCancelled": "<primary>Cancelé todas tus peticiones.",
    "teleportRequestTimeoutInfo": "<primary>La petición se cancela sola en<secondary> {0} segundos<primary>.",
    "teleportDisabled": "<secondary>{0} <dark_red>trae el teletransporte apagado.",
    "teleportAAll": "<gray>Le mandé la petición a todos...",
    "unsafeTeleportDestination": "<dark_red>Ahí no se puede caer, está peligroso.",
    "teleportTop": "<primary>Teletransportando hasta arriba.",
    "backUsageMsg": "<primary>Volviendo a donde estabas.",
    "noLocationFound": "<dark_red>No hay ningún lugar al que volver.",
    # --- Spawn -----------------------------------------------------------
    "spawnSet": "<primary>Dejé el spawn del grupo<secondary> {0}<primary> aquí.",
    # --- Teletransporte aleatorio (/tpr) ---------------------------------
    "tprSuccess": "<primary>Te mandé a un lugar al azar.",
    "tprSuccessDone": "<primary>Listo, caíste en un lugar al azar.",
    "tprOtherUser": "<primary>Mandando a<secondary> {0}<primary> a un lugar al azar.",
    "tprNoPermission": "<dark_red>No tienes permiso para ir a ese lugar.",
    "tprNotExist": "<dark_red>Ese destino al azar no existe.",
    # --- Mensajes privados: `Pepe → tú: mensaje` -------------------------
    # EssentialsX usa {0} para quien manda, {1} para quien recibe y {2} para
    # el mensaje. Nosotros ponemos la flecha y los colores del chat.
    "msgFormat": "<gray>{0} <secondary>→ <gray>{1}<reset>: <white>{2}",
    "msgDisabled": "<primary>Ya no vas a recibir mensajes privados.",
    "msgEnabled": "<primary>Otra vez vas a recibir mensajes privados.",
    "msgDisabledFor": "<secondary>{0}<primary> no recibe mensajes privados.",
    "replyLastRecipientDisabled": "<primary>Ya no voy a recordar a quién le contestas.",
    "replyLastRecipientEnabled": "<primary>Voy a recordar a quién le contestas para el /r.",
    "socialSpy": "<primary>Espía de chat de <secondary>{0}<primary>: <secondary>{1}",
    "socialSpyPrefix": "<white>[<primary>SS<white>] <reset>",
    "socialSpyMutedPrefix": "<white>[<primary>SS<white>] <gray>(callado) <reset>",
    "socialSpyMsgFormat": "<gray>{0} <secondary>→ <gray>{1}<reset>: <white>{2}",
    "socialSpyCmdFormat": "<gray>{0}: {1}",
    # --- Errores comunes -------------------------------------------------
    "noPerm": "<dark_red>No tienes el permiso <secondary>{0}<dark_red>.",
    "noAccessCommand": "<dark_red>No tienes permiso para ese comando.",
    "noPermToSpawnMob": "<dark_red>No tienes permiso para sacar ese mob.",
    "playerNotFound": "<dark_red>No encuentro a ese jugador.",
    "errorWithMessage": "<secondary>Error:<dark_red> {0}",
    "unknownItemName": "<dark_red>No conozco ese ítem: {0}.",
    "pageLimitExceeded": "<dark_red>Esa página no existe, el máximo es 100.",
    "playerNotMuted": "<secondary>{0} <primary>no está callado.",
    "unmuteNotify": "<secondary>{0} <primary>le quitó el silencio a<secondary> {1}<primary>.",
    "warpNotExist": "<dark_red>Ese warp no existe.",
    "warps": "<primary>Warps:<reset> {0}",
    # --- Baneos (los ve quien intenta entrar) ----------------------------
    "banIpJoin": "Tu IP está baneada de este servidor. Razón: {0}",
    "tempbanJoin": "Estás baneado de este servidor por {0}. Razón: {1}",
    # --- Cárcel ----------------------------------------------------------
    "jailedPlayersEmpty": "<primary>No hay nadie en la cárcel.",
    "jailedPlayersList": "<primary>En la cárcel:<reset> {0}",
    # --- Kits ------------------------------------------------------------
    "kitCost": " <gray><i>({0})<reset>",
    "kitDelay": "<st>{0}<reset>",
    "kitItem": "<primary>- <white>{0}",
    "createKitSeparator": "<st>-----------------------",
    # --- Chat local y varios ---------------------------------------------
    "localFormat": "<dark_aqua>[L] <reset><{0}> {1}",
    "localNoOne": "",
    "chatTypeLocal": "<dark_aqua>[L] ",
    "action": "<dark_purple>* {0} <dark_purple>{1}",
    "listGroupTag": "<primary>{0}<reset>: ",
    "mobsAvailable": "<primary>Mobs:<reset> {0}",
    "matchingAccounts": "{0}",
    "itemId": "<primary>ID:<secondary> {0}",
    "coordsKeyword": "{0}, {1}, {2}",
    "nearbyPlayersList": "{0}<white>(<secondary>{1}m<white>)",
    "balanceTopLine": "{0}. {1}, {2}",
    "recipeGrid": "<secondary>{0}X <primary>| {1}X <primary>| {2}X",
    "signFormatFail": "<dark_red>[{0}]",
    "signFormatSuccess": "<dark_blue>[{0}]",
    "sudoRun": "<primary>Obligando a<secondary> {0} <primary>a correr:<reset> /{1}",
    "timeSetWorldPermission": "<dark_red>No tienes permiso para cambiar la hora del mundo ''{0}''.",
    # --- /whois ----------------------------------------------------------
    "whoisPlaytime": "<primary> - Tiempo jugado:<reset> {0}",
    "whoisUuid": "<primary> - UUID:<reset> {0}",
    "whoisWhitelist": "<primary> - En la whitelist:<reset> {0}",
    "whoisCommandDescription": "Muestra información básica de un jugador.",
    # --- Correo interno --------------------------------------------------
    "mailFormat": "<primary>[<reset>{0}<primary>] <reset>{1}",
    "mailFormatNew": "<primary>[<reset>{0}<primary>] <primary>[<reset>{1}<primary>] <reset>{2}",
    "mailFormatNewRead": "<primary>[<reset>{0}<primary>] <primary>[<reset>{1}<primary>] <gray><i>{2}",
    "mailFormatNewTimed": "<primary>[<yellow>⚠<primary>] <primary>[<reset>{0}<primary>] <primary>[<reset>{1}<primary>] <reset>{2}",
    "mailFormatNewReadTimed": "<primary>[<yellow>⚠<primary>] <primary>[<reset>{0}<primary>] <primary>[<reset>{1}<primary>] <gray><i>{2}",
    # --- Ayuda -----------------------------------------------------------
    "helpLine": "<primary>/{0}<reset>: {1}",
    "commandHelpLineUsage": "{0} <primary>- {1}",
    # --- Avisos del servidor (consola) -----------------------------------
    "versionOutputFine": "<primary>{0} versión: <green>{1}",
    "versionOutputWarn": "<primary>{0} versión: <secondary>{1}",
    "versionOutputUnsupported": "<light_purple>{0} <primary>versión: <light_purple>{1}",
    "serverUnsupportedClass": "<red>Clase que determina el estado: {0}",
    "serverUnsupportedDumbPlugins": "<dark_red>Traes plugins que se sabe que dan guerra con EssentialsX y con otros plugins.",
    "serverUnsupportedLimitedApi": "<red>Este servidor tiene la API recortada. EssentialsX va a funcionar, pero algunas cosas se van a desactivar.",
    "serverUnsupportedMods": "<dark_red>Este servidor no soporta bien los plugins de Bukkit. No mezcles plugins de Bukkit con mods de Forge o Fabric.",
    # --- Otras descripciones de comandos ---------------------------------
    "jailedplayersCommandDescription": "Lista a todos los que están en la cárcel.",
    "tprCommandUsage2Description": "Te manda a un lugar al azar del mundo que digas",
    "tprCommandUsage3Description": "Manda al jugador que digas a un lugar al azar del mundo que digas",
    "skullCommandUsage4Description": "Le da a un jugador la cabeza del dueño que digas",
    "skullCommandUsage5Description": "Le da a un jugador una cabeza con la textura que digas (el hash de una URL o un valor Base64)",
}

# --------------------------------------------------------------------------
#  Claves donde la traduccion del jar tiene errores reales: perdio los
#  {0}/{1} que EssentialsX rellena, o trae pegado el texto de otra clave.
#  Verificado comparando contra messages.properties del mismo jar.
# --------------------------------------------------------------------------
A_MANO.update(
    {
        # El jar se comio el {1} (el mensaje que intento mandar).
        "mutedUserSpeaks": "{0} quiso hablar, pero est\u00e1 silenciado: {1}",
        # El jar tiene aqui pegado "/<command> <nombre>.", que es texto de un
        # CommandUsage. Es un error de copiado en su archivo es.
        "muteNotifyFor": "<secondary>{0} <primary>silenci\u00f3 a<secondary> {1}<primary> por<secondary> {2}<primary>.",
        # El jar se comio el {0} (a quien no puedes sudar).
        "sudoExempt": "<dark_red>No puedes usar sudo con <secondary>{0}<dark_red>.",
        # El jar se comio el {0} (el mundo) en los dos.
        "weatherStorm": "<primary>Pusiste tormenta en<secondary> {0}<primary>.",
        "weatherSun": "<primary>Pusiste sol en<secondary> {0}<primary>.",
    }
)

# --------------------------------------------------------------------------
#  Correcciones generales sobre el español de España que trae el jar.
#  Solo palabras completas, para no romper nada a media frase.
# --------------------------------------------------------------------------
ARREGLOS = [
    # EssentialsX sustituye la cadena literal "<command>" por el nombre real
    # del comando (Essentials.java:842, .replace("<command>", commandLabel)).
    # La traduccion es_ES del jar la cambio a "<comando>", asi que en espanol
    # TODA la ayuda sale como "/<comando> <jugador>" en vez de "/tpa <jugador>".
    # Esto lo deshace.
    (r"<comando>", "<command>"),
    (r"\bhogares\b", "casas"),
    (r"\bHogares\b", "Casas"),
    (r"\bhogar\b", "casa"),
    (r"\bHogar\b", "Casa"),
    (r"\bordenador\b", "computadora"),
    (r"\bPetici(o)n\b", r"Petición"),
    (r"\bpetici(o)n\b", r"petición"),
    (r"\bha sido eliminado\b", "se borró"),
    (r"\bha sido enviada\b", "se envió"),
    (r"\bha sido colocado\b", "quedó"),
    (r"\bha sido establecido\b", "quedó"),
    (r"\bse ha agotado\b", "se acabó"),
    (r"\bdenegada\b", "rechazada"),
    (r"\bdenegado\b", "rechazado"),
    # El espanol del jar escribe "item" sin acento. En los TEXTOS si lleva
    # (es "itema" en ingles, "item" en espanol se acentua). Ojo: esto NO
    # toca los textos de uso, que se generan del ingles aparte y necesitan
    # nombres de argumento sin acentos.
    (r"\bitem\b", "\u00edtem"),
    (r"\bitems\b", "\u00edtems"),
    (r"\bItem\b", "\u00cdtem"),
    (r"\bItems\b", "\u00cdtems"),
]

# --------------------------------------------------------------------------
#  Nombres de argumento que el jar dejo con acentos o guiones.
#
#  EssentialsX resalta los argumentos con
#      ARGUMENT_PATTERN = ([ :>])(([\[<])[A-Za-z |]+[>\]])
#  (EssentialsCommand.java:44), que SOLO acepta letras sin acento, espacios
#  y |. Un acento o un guion y el argumento deja de resaltarse.
#
#  En vez de escribir mal la palabra, usamos un sinonimo que no lleve acento.
# --------------------------------------------------------------------------
ARGUMENTOS_DEL_JAR = {
    "raz\u00f3n": "motivo",
    "p\u00e1gina": "hoja",
    "duraci\u00f3n": "tiempo",
    "descripci\u00f3n": "texto",
    "n\u00famero": "cantidad",
    "n\u00famero de l\u00ednea": "fila",
    "cap\u00edtulo": "parte",
    "direcci\u00f3n IP": "ip",
    "direcci\u00f3n-ip": "ip",
    "inclinaci\u00f3n": "pitch",
    "\u00edtem": "item",
    "t\u00e9rmido de b\u00fasqueda": "texto",
    "Nombre del Encantamiento (en ingles)": "encantamiento",
    "jugador|direcci\u00f3n-ip": "jugador|ip",
    "p\u00e1gina|warp": "hoja|warp",
}


def normalizar_argumentos_del_jar(texto):
    """Cambia los nombres acentuados por su equivalente sin acento."""

    def reemplazo(m):
        abre, dentro, cierra = m.group(1), m.group(2), m.group(3)
        return abre + ARGUMENTOS_DEL_JAR.get(dentro, dentro) + cierra

    return re.sub(r"([<\[])([^<>\[\]]+)([>\]])", reemplazo, texto)


def aplicar_arreglos(texto):
    for patron, reemplazo in ARREGLOS:
        texto = re.sub(patron, reemplazo, texto)
    return texto


def construir():
    salida = {}
    estadisticas = {
        "a_mano": 0,
        "completadas": 0,
        "arregladas": 0,
        "del_jar": 0,
        "uso_del_ingles": 0,
    }
    for clave in en_orden:
        if clave in A_MANO:
            salida[clave] = A_MANO[clave]
            estadisticas["a_mano"] += 1
        elif "CommandUsage" in clave and not clave.endswith("Description"):
            # Los textos de uso los generamos SIEMPRE del ingles, nunca del
            # es_ES del jar. Razon: su traduccion tradujo cosas que no se
            # traducen y quedan comandos que no existen. Por ejemplo
            #   mailCommandUsage3  EN: /<command> clear <player> [number]
            #                      ES: /<comando> borrar <numero de linea>
            # "clear" es lo que el jugador TECLEA; "borrar" no es un
            # subcomando de /mail, asi que esa ayuda manda a un comando que
            # no existe. Ademas el jar perdio variantes enteras del comando.
            #
            # Del ingles solo cambiamos los nombres de argumento, que si son
            # texto descriptivo, y dejamos intactos <command> y los
            # subcomandos literales.
            salida[clave] = traducir_argumentos(EN[clave])
            estadisticas["uso_del_ingles"] += 1
        elif clave in ES and ES[clave].strip() and ES[clave] != EN[clave]:
            # ES[clave].strip(): el jar trae tres claves de uso VACIAS
            # (bigtreeCommandUsage1, jumpCommandUsage, mailCommandUsage5).
            # Una cadena vacia no es una traduccion: caemos al ingles.
            arreglado = aplicar_arreglos(ES[clave])
            if "CommandUsage" in clave:
                arreglado = normalizar_argumentos_del_jar(arreglado)
            if arreglado != ES[clave]:
                estadisticas["arregladas"] += 1
            else:
                estadisticas["del_jar"] += 1
            salida[clave] = arreglado
        else:
            # Falta, o es idéntica al inglés: traducimos los argumentos.
            salida[clave] = traducir_argumentos(EN[clave])
            estadisticas["completadas"] += 1
    return salida, estadisticas


CABECERA = """\
# ===========================================================================
#  EssentialsX - mensajes en espanol de Mexico
# ===========================================================================
#  NO LO EDITES A MANO. Lo arma
#  minecraft/translations/es_mx/herramientas/construir_essentials_es.py
#  a partir del messages_es.properties y el messages.properties del jar
#  2.22.0. Si cambias de version de EssentialsX, vuelve a correrlo.
#
#  `mc build` lo copia a plugins/Essentials/messages_es.properties.
#  EssentialsX le da prioridad al archivo de su carpeta sobre el del jar.
#
#  ---------------------------------------------------------------------
#  Por que no usamos tal cual el espanol que trae EssentialsX
#  ---------------------------------------------------------------------
#  1. BUG REAL: su traduccion cambio "<command>" por "<comando>".
#     EssentialsX sustituye la cadena literal "<command>" por el nombre real
#     del comando (Essentials.java:842, .replace("<command>", commandLabel)).
#     Con "<comando>" no sustituye nada, asi que en espanol TODA la ayuda
#     sale como "/<comando> <jugador>" en vez de "/tpa <jugador>".
#
#  2. OTRO BUG: tradujo subcomandos, que son lo que el jugador TECLEA.
#     mailCommandUsage3  ingles:  /<command> clear <player> [number]
#                        espanol: /<comando> borrar <numero de linea>
#     "/mail borrar" no existe. Por eso TODOS los textos de uso los
#     generamos del ingles y solo traducimos los nombres de argumento.
#
#  3. Claves con los {0}/{1} perdidos (weatherSun, weatherStorm,
#     mutedUserSpeaks, sudoExempt) y una, muteNotifyFor, con el texto de
#     otra clave pegado por error.
#
#  4. Tres textos de uso vacios: bigtreeCommandUsage1, jumpCommandUsage y
#     mailCommandUsage5.
#
#  5. Espanol de Espana y frases en pasiva: "hogar" por casa, "la peticion
#     ha sido enviada", "denegada".
#
#  ---------------------------------------------------------------------
#  Lo que NO se toca
#  ---------------------------------------------------------------------
#   - <primary>, <secondary>, <gray>, <reset> y los colores son etiquetas
#     de MiniMessage. Traducirlas saca el mensaje con la etiqueta adentro.
#   - <command> lo sustituye EssentialsX. Tiene que quedarse asi.
#   - Los subcomandos literales (clear, send, set, reload...) son lo que se
#     teclea; van en ingles aunque suene raro.
#   - {0}, {1}, {2} los rellena EssentialsX.
#   - Los nombres de argumento van SIN acentos ni guiones a proposito:
#     EssentialsX solo los resalta si cumplen [A-Za-z |]+
#     (EssentialsCommand.java:44). Donde la palabra correcta lleva acento
#     usamos un sinonimo que no lo lleve ("motivo" en vez de "razon",
#     "hoja" en vez de "pagina"), nunca la palabra mal escrita.
#
#  El archivo va en UTF-8 plano, con los acentos tal cual: es como
#  EssentialsX guarda el suyo. Nada de escapes \\uXXXX.
# ===========================================================================

"""


def validar_argumentos():
    """Comprueba que cada nombre de argumento siga cumpliendo el regex de
    EssentialsX ([A-Za-z |]+). Un acento o un guion rompe el resaltado."""
    malos = [v for v in ARGUMENTOS.values() if not RE_ARG_VALIDO.match(v)]
    if malos:
        raise SystemExit(
            "Estos nombres de argumento rompen el resaltado de EssentialsX "
            "(solo acepta letras sin acento, espacios y |): " + ", ".join(malos)
        )


if __name__ == "__main__":
    validar_argumentos()
    datos, est = construir()
    # Se escribe en UTF-8 PLANO, con los acentos tal cual. Es exactamente
    # como EssentialsX guarda su propio messages_es.properties (verificado
    # con `cat -v` sobre el archivo del jar 2.22.0).
    #
    # NO uses unicode_escape de Python aqui: produce \xf1 para la "n", y
    # Java solo entiende \u00f1. El resultado se ve como "axf1adido" dentro
    # del juego. Tampoco hace falta escapar nada: los valores ya traen sus
    # propios escapes (\:) copiados del archivo original.
    with open("messages_es_mx.properties", "w", encoding="utf-8") as f:
        f.write(CABECERA)
        for clave in en_orden:
            f.write(f"{clave}={datos[clave]}\n")
    print("claves totales:", len(datos))
    print("  escritas a mano:   ", est["a_mano"])
    print("  completadas:       ", est["completadas"])
    print("  corregidas del jar:", est["arregladas"])
    print("  textos de uso del ingles:", est["uso_del_ingles"])
    print("  tal cual del jar:  ", est["del_jar"])
