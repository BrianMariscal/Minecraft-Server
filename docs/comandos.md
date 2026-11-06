# Comandos de `mc`

`mc` es la CLI del proyecto. Todos los comandos aceptan `--help`, y los que
modifican el servidor o los datos tienen `--dry-run` cuando aplica.

## Preparar

| Comando | Qué hace |
|---|---|
| `mc setup` | Revisa el entorno, crea `.env` y pide los datos que faltan |
| `mc build` | Baja los plugins verificando su SHA256 y genera las configuraciones |
| `mc build --dry-run` | Enseña qué haría, sin tocar nada |

## Día a día

| Comando | Qué hace |
|---|---|
| `mc start` | Enciende los contenedores y aplica gamerules, permisos y whitelist |
| `mc stop` | Apaga guardando el mundo |
| `mc restart` | Guarda, apaga y vuelve a levantar todo, aplicando los cambios de `settings.yml` o `.env` |
| `mc status` | Muestra qué está arriba, quién anda conectado y a cuántos TPS |
| `mc logs` / `mc logs -f` | Muestra los logs; con `-f` los sigue en vivo |
| `mc console` | Abre la consola interactiva por RCON |

## Jugadores

| Comando | Qué hace |
|---|---|
| `mc whitelist add Pepe` | Mete a alguien de Java |
| `mc whitelist add "Gamer Tag" --bedrock` | Mete a alguien de Bedrock |
| `mc whitelist remove Pepe` | Saca a alguien de la whitelist |
| `mc whitelist list` | Muestra la lista |
| `mc admin add Admin_HD` | Lo hace admin: grupo de LuckPerms y op |
| `mc admin remove Admin_HD` | Le quita los permisos de admin |
| `mc admin list` | Muestra quiénes son admins |

## Respaldos

| Comando | Qué hace |
|---|---|
| `mc backup now` | Crea un respaldo sin apagar el servidor |
| `mc backup list` | Muestra los respaldos disponibles |
| `mc backup verify` | Revisa checksum, contenido y bases SQLite |
| `mc backup drill` | Simulacro: extrae el último respaldo a un temporal y valida el mundo y las bases |
| `mc backup drill 20261031-011258 --guardar` | Simulacro de uno concreto, dejando lo extraído para revisarlo |
| `mc backup prune` | Borra los respaldos que salen de la retención |
| `mc backup status` | Muestra el último respaldo, su edad, el disco, el último error y el último simulacro |
| `mc backup restore ultimo` | Restaura el último respaldo, con doble confirmación |

## El mundo

| Comando | Qué hace |
|---|---|
| `mc pregen` | Pregenera el mapa con Chunky |
| `mc pregen --radio 1500` | Pregenera usando otro radio |
| `mc world reset` | Regenera el mundo desde cero |

## Mantenimiento

| Comando | Qué hace |
|---|---|
| `mc doctor` | Revisa puertos, RAM, disco, TPS, versiones y traducciones |
| `mc doctor --traducciones` | Muestra qué mensajes siguen en inglés |
| `mc update` | Revisa si hay versiones nuevas y qué soporta la versión actual |
| `mc monitor` | Revisa respaldo, disco y servidor; avisa por Discord |
| `mc alert` | Manda una alerta al canal de Discord |

## Operaciones peligrosas

`mc backup restore` y `mc world reset` piden doble confirmación, hacen un
respaldo antes de tocar nada y aceptan `--dry-run`. Para el resto de comandos,
`mc --help` y `mc <comando> --help` muestran las opciones disponibles.

Antes de restaurar o regenerar el mundo, revisa
**[respaldos.md](respaldos.md)** y **[administrar.md](administrar.md)**.
