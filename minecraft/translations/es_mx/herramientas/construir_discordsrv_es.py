"""Arma messages.yml de DiscordSRV en español de México.

Parte del messages/es.yml que trae el jar (que está completo y decente) y le
aplica nuestros cambios: el formato de chat igual al del juego y los textos
en español de México en vez de España.
"""

import sys

import yaml

RUTA_ES = "dsrv_msg_es.yml"
SALIDA = "discordsrv-messages.yml"

with open(RUTA_ES, encoding="utf-8") as f:
    datos = yaml.safe_load(f)

# --------------------------------------------------------------------------
#  Formato del chat: que se lea igual en el juego y en Discord.
#  En el juego usamos `Nombre » mensaje`, así que en Discord igual.
# --------------------------------------------------------------------------
datos["MinecraftChatToDiscordMessageFormat"] = "**%primarygroup%** %displayname% » %message%"
datos["MinecraftChatToDiscordMessageFormatNoPrimaryGroup"] = "%displayname% » %message%"
# Del lado del juego, que se note que viene de Discord pero sin gritar.
datos["DiscordToMinecraftChatMessageFormat"] = (
    "<#5865F2>[Discord]</#5865F2> %toprolecolor%%toprolealias%<reset> "
    "<#C9D1D3>%name%</#C9D1D3>%reply% <#6E797C>»</#6E797C> <white>%message%</white>"
)
datos["DiscordToMinecraftChatMessageFormatNoRole"] = (
    "<#5865F2>[Discord]</#5865F2> <#C9D1D3>%name%</#C9D1D3>%reply% "
    "<#6E797C>»</#6E797C> <white>%message%</white>"
)
datos["DiscordToMinecraftMessageReplyFormat"] = " (le contesta a %name%)"


# --------------------------------------------------------------------------
#  Entradas, salidas, muertes y logros.
#  El jar dice "Entró al servidor" con mayúscula a media frase.
# --------------------------------------------------------------------------
def texto_autor(clave, texto):
    """Cambia el nombre del autor del embed sin tocar el resto."""
    datos[clave]["Embed"]["Author"]["Name"] = texto


texto_autor("MinecraftPlayerJoinMessage", "%username% se conectó")
texto_autor("MinecraftPlayerLeaveMessage", "%username% se desconectó")
texto_autor("MinecraftPlayerFirstJoinMessage", "%username% llegó por primera vez")
# La muerte usa el mensaje vanilla tal cual: así cada quien lo lee en su
# idioma dentro del juego y en Discord sale el del servidor.
texto_autor("MinecraftPlayerDeathMessage", "%deathmessage%")
texto_autor("MinecraftPlayerAchievementMessage", "%username% consiguió el progreso %achievement%")

# --------------------------------------------------------------------------
#  Avisos de encendido y apagado.
# --------------------------------------------------------------------------
datos["DiscordChatChannelServerStartupMessage"] = (
    ":white_check_mark: **Ya está prendido el servidor**"
)
datos["DiscordChatChannelServerShutdownMessage"] = ":octagonal_sign: **Se apagó el servidor**"

CABECERA = """\
# ===========================================================================
#  DiscordSRV - mensajes en espanol de Mexico
# ===========================================================================
#  NO LO EDITES A MANO. Lo arma
#  minecraft/translations/es_mx/herramientas/construir_discordsrv_es.py
#  a partir del messages/es.yml del jar 1.30.5.
#
#  `mc build` lo copia a plugins/DiscordSRV/messages.yml.
#
#  El es.yml del jar esta completo y bien, asi que partimos de el y solo
#  cambiamos:
#   - El formato del chat, para que se lea igual que dentro del juego
#     (`Nombre >> mensaje`) en los dos lados.
#   - "Entro al servidor" -> "se conecto". El jar pone mayuscula a media
#     frase y suena a reporte.
#   - "ha conseguido el progreso X!" -> "consiguio el progreso X".
#   - Los avisos de encendido y apagado.
#
#  Los %placeholders% los rellena DiscordSRV: no los cambies de nombre.
#  Los mensajes de muerte se dejan en %deathmessage%, que es el texto
#  vanilla: asi cada cliente lo traduce a su idioma.
# ===========================================================================

"""

with open(SALIDA, "w", encoding="utf-8") as f:
    f.write(CABECERA)
    yaml.safe_dump(
        datos, f, allow_unicode=True, sort_keys=False, width=200, default_flow_style=False
    )

print(f"escrito {SALIDA}: {len(datos)} claves de primer nivel", file=sys.stderr)
