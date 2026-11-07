# Respaldos

Los respaldos tienen cinco partes:

1. Respaldo local automático cada 6 horas, sin apagar el servidor.
2. Verificación semanal de todos los respaldos.
3. Simulacro mensual de restauración: se extrae el último respaldo en un
   temporal y se comprueba que el mundo y las bases SQLite abren.
4. Copia diaria a la PC por SSH, fuera del VPS.
5. Alertas por Discord si un respaldo falla o el servidor se queda sin
   respaldo reciente.

Los respaldos locales están en `backups/`. La copia externa vive en
`~/Respaldos_Minecraft_HD/` en la PC.

---

## Qué hace `mc backup now`

El comando ejecuta este procedimiento:

1. Pide al servidor `save-off` y `save-all flush` por RCON, para que el mundo
   quede quieto en disco.
2. Detecta las bases SQLite dentro de `data/` y las del bot de pagos.
3. Pide a SQLite una copia consistente de cada base con su API de respaldo,
   así no importa que el servidor o el bot sigan escribiendo.
4. Escribe el archivo `.tgz` en un nombre temporal y lo renombra al final.
   Nunca queda un respaldo a medias con nombre definitivo.
5. Agrega `BACKUP_INFO.json` dentro del archivo, con fecha, versión de
   Minecraft, lista de bases y número de archivos.
6. Calcula el SHA256 y escribe dos archivos al lado: `.sha256` y `.json`.
7. Actualiza `estado.json` con el resultado y vuelve a activar `save-on`.

Un bloqueo con `flock` impide que dos respaldos se ejecuten a la vez. Si el
servidor está apagado, el respaldo se hace igual, sin RCON.

### Qué entra

- El mundo completo, con sus dimensiones, datapacks y datos de jugadores.
- Las configs de los plugins.
- Las bases SQLite: CoreProtect, AuthMe, GSit, Floodgate y las dos del bot de
  pagos.
- El `settings.yml` con el que se hizo el respaldo.

### Qué no entra

Los jars de los plugins, `cache/`, `logs/`, `libraries/`, `versions/` y el
punto de montaje vacío `pagos-datos/` dentro de `data/`.

Todo eso se regenera con `mc build` o lo vuelve a crear el servidor. Incluirlo
solo aumenta el tamaño del respaldo.

### Formato de los archivos

```
backups/
├── world-20261031-011258.tgz
├── world-20261031-011258.tgz.sha256
├── world-20261031-011258.tgz.json
├── estado.json
└── .bloqueo
```

Los respaldos anteriores a esta versión del comando pueden llamarse `.tar.gz`
y no tener sidecars. `mc backup verify` los revisa igual; solo los respaldos
nuevos exigen `BACKUP_INFO.json`.

---

## Configuración

En `settings.yml`:

```yaml
respaldos:
  intervalo: "6h"
  conservar_dias: 7
```

- `intervalo` describe la frecuencia esperada. El timer de systemd es quien
  dispara el respaldo.
- `conservar_dias` es la ventana de retención. `mc backup prune` borra los
  respaldos más viejos junto con sus sidecars.

La copia externa y las alertas se configuran en `.env` y en los timers, no en
`settings.yml`.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `mc backup now` | Crea un respaldo en caliente |
| `mc backup list` | Lista los respaldos y su tamaño |
| `mc backup verify` | Revisa SHA256, contenido y bases SQLite de todos |
| `mc backup verify 20261031-011258` | Revisa uno concreto |
| `mc backup drill` | Simulacro: extrae el último respaldo en un temporal y lo valida |
| `mc backup drill 20261031-011258 --guardar` | Simulacro de uno concreto, dejando lo extraído para revisarlo |
| `mc backup prune` | Borra los que salen de la ventana de retención |
| `mc backup prune --dry-run` | Muestra qué borraría, sin borrar |
| `mc backup status` | Último respaldo, edad, disco y último error |
| `mc backup restore ultimo` | Restaura el más reciente |
| `mc backup restore <id> --dry-run` | Muestra qué trae, sin tocar nada |

Haz un respaldo manual antes de actualizar un plugin, cambiar algo grande en
`settings.yml`, regenerar el mundo o hacer un rollback de CoreProtect.
`mc world reset` y `mc backup restore` ya crean uno antes de tocar nada.

---

## Respaldos automáticos con systemd

Los respaldos no viven en un contenedor. Los ejecuta un timer de systemd con
el usuario `minecraft`, que llama a `mc backup now` y después a
`mc backup prune`.

Los archivos están en `deploy/systemd/`:

| Unit | Cuándo |
|---|---|
| `mc-backup.service` | Ejecuta el respaldo y la poda |
| `mc-backup.timer` | Cada 6 horas |
| `mc-backup-verify.service` | Verifica todos los respaldos |
| `mc-backup-verify.timer` | Domingos a las 09:00 |
| `mc-backup-drill.service` | Simulacro de restauración del último respaldo |
| `mc-backup-drill.timer` | Primer domingo de cada mes, a las 10:00 |
| `mc-monitor.service` | Revisa respaldo, disco y servidor |
| `mc-monitor.timer` | Cada hora |
| `mc-backup-alerta.service` | Envía una alerta si falla un respaldo |

Instalación:

```bash
cd ~/minecraft-hd
sudo install -m 644 deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mc-backup.timer mc-monitor.timer mc-backup-verify.timer mc-backup-drill.timer
```

Comprobación:

```bash
systemctl list-timers --all | grep mc-
sudo systemctl start mc-backup.service
journalctl -u mc-backup.service -n 50 --no-pager
```

El servicio tiene `TimeoutStartSec=1h` porque un mundo pregenerado puede tardar
varios minutos en comprimirse.

---

## Simulacro de restauración

Verificar el `.tgz` no prueba que se pueda restaurar. El simulacro hace la
parte peligrosa de una restauración (extraer el mundo y abrir las bases) en una
carpeta temporal, sin apagar el servidor ni tocar `data/`:

```bash
mc backup drill                 # el más reciente
mc backup drill 20261031-011258 # uno concreto
mc backup drill --guardar       # deja lo extraído para revisarlo a mano
```

Qué revisa:

1. SHA256, contenido y `BACKUP_INFO.json`, igual que `mc backup verify`.
2. Que el tar se pueda extraer completo.
3. Que exista `world/level.dat` y no esté vacío.
4. Que cada base SQLite extraída pase `integrity_check`.

El resultado queda en `backups/estado.json` y se ve en `mc backup status`.
El timer lo corre el **primer domingo de cada mes** y, si falla, dispara la
alerta de Discord. Necesita espacio libre suficiente para descomprimir el
mundo: el doble del tamaño del respaldo, aproximadamente.

---

## Copia diaria a la PC

Tener los respaldos solo en el VPS no sirve si se pierde el VPS. La copia
externa se hace por SSH desde la PC, sin credenciales nuevas: usa la misma
llave con la que administras el servidor.

El script está en `deploy/pc/copiar_respaldos.py`. Hace esto:

1. Pregunta al VPS cuál es el respaldo más reciente.
2. Lo baja con `rsync` a `~/Respaldos_Minecraft_HD/AAAA-MM-DD/`.
3. Verifica el SHA256 contra el sidecar.
4. Escribe un `SHA256SUMS` de la carpeta.
5. Borra las carpetas de más de 14 días.

Instalación en la PC:

```bash
mkdir -p ~/.local/bin ~/.config/systemd/user ~/.config/minecraft-hd
install -m 755 deploy/pc/copiar_respaldos.py ~/.local/bin/
install -m 644 deploy/pc/mc-copiar-respaldos.service \
                deploy/pc/mc-copiar-respaldos.timer \
                ~/.config/systemd/user/

cat > ~/.config/minecraft-hd/copiar.env <<'EOF'
MC_SSH=usuario@tu-vps
MC_SSH_KEY=~/.ssh/id_ed25519
EOF
chmod 600 ~/.config/minecraft-hd/copiar.env

systemctl --user daemon-reload
systemctl --user enable --now mc-copiar-respaldos.timer

# Para que el timer funcione aunque no tengas sesión abierta:
sudo loginctl enable-linger "$USER"
```

Comprobación:

```bash
systemctl --user list-timers mc-copiar-respaldos.timer
systemctl --user start mc-copiar-respaldos.service
tail -20 ~/Respaldos_Minecraft_HD/copiar.log
sha256sum -c ~/Respaldos_Minecraft_HD/AAAA-MM-DD/SHA256SUMS
```

Variables del script:

| Variable | Valor por defecto |
|---|---|
| `MC_SSH` | Obligatorio; por ejemplo `usuario@tu-vps` |
| `MC_SSH_KEY` | `~/.ssh/id_ed25519` |
| `MC_RESPALDOS_REMOTOS` | `~/minecraft-hd/backups` |
| `MC_RESPALDOS_PC` | `~/Respaldos_Minecraft_HD` |
| `MC_RESPALDOS_PC_DIAS` | `14` |

`MC_SSH` y `MC_SSH_KEY` se leen del archivo
`~/.config/minecraft-hd/copiar.env`; no se guardan en el repositorio.

El timer corre a las 03:15, con hasta 15 minutos de retraso aleatorio. Si la
PC está apagada a esa hora, systemd lo ejecuta al siguiente encendido gracias
a `Persistent=true`.

---

## Alertas por Discord

`mc alert` manda un mensaje al canal configurado. `mc monitor` revisa tres
cosas y avisa si alguna falla:

- El respaldo más reciente tiene más de 8 horas.
- Quedan menos de 15 GB libres.
- El contenedor de Minecraft no está corriendo o no está sano.

```bash
mc alert --titulo "Prueba" "Mensaje de prueba"
mc alert --seco --titulo "Prueba" "Solo imprime el texto"
mc monitor
mc monitor --horas-max 12 --disco-minimo-gb 20
```

El canal se toma de `ALERTAS_CANAL_ID`. Si está vacío, se usa
`PAGOS_CANAL_ID`. El token es el mismo del bot de pagos. No hace falta un
webhook aparte.

Para evitar spam, `mc monitor` guarda una huella del problema en
`backups/.monitor.json` y no repite la misma alerta hasta que pasan 6 horas.
Cuando todo está bien, borra ese archivo.

`mc-backup.service` y `mc-backup-verify.service` tienen
`OnFailure=mc-backup-alerta.service`, así que un fallo del timer también llega
a Discord.

---

## Restaurar

```bash
mc backup restore ultimo --dry-run
mc backup restore ultimo
```

El comando:

1. Muestra qué respaldo es, de cuándo y cuánto pesa.
2. Pide doble confirmación: primero sí/no, después la palabra `RESTAURAR`.
3. Crea un respaldo de lo que hay ahora, con etiqueta
   `antes-de-restaurar`.
4. Apaga el servidor.
5. Borra los mundos actuales y extrae los del respaldo.
6. Consolida las bases SQLite que vengan con un `-wal` viejo.
7. Restaura la base del bot de pagos.
8. Deja el respaldo previo en `backups/` por si hay que volver.

Después:

```bash
mc start
```

### Qué no se restaura solo

El `settings.yml` va dentro del respaldo, pero no se escribe encima del
actual. Si quieres recuperarlo:

```bash
tar xzf backups/world-20261031-011258.tgz settings.yml -O > settings-del-respaldo.yml
diff settings.yml settings-del-respaldo.yml
```

La base del bot de pagos sí se restaura, porque forma parte del mismo punto en
el tiempo que el mundo.

### Respaldos viejos con WAL

Los respaldos anteriores copiaban la base viva con su `-wal` y su `-shm`. Al
restaurar, el comando actual extrae esos archivos a un temporal y los consolida
con la API de SQLite. Al destino llega un solo archivo sano, sin acompañantes
viejos que se apliquen encima.

---

## Verificación y simulacro de restauración

La verificación semanal revisa:

- Que el SHA256 coincida con el sidecar, cuando existe.
- Que el archivo se pueda abrir como tar.
- Que exista `world/level.dat`.
- Que las bases SQLite pasen `PRAGMA integrity_check`.

Para un simulacro completo sin tocar producción:

```bash
mkdir -p /tmp/restore-drill
tar -xzf backups/world-20261031-011258.tgz -C /tmp/restore-drill
```

Después valida el contenido:

```bash
# level.dat debe ser gzip y un compound NBT
python3 - <<'PY'
import gzip, struct
from pathlib import Path
datos = gzip.decompress(Path("/tmp/restore-drill/world/level.dat").read_bytes())
tipo, = struct.unpack(">B", datos[:1])
print("NBT tipo:", tipo)
PY

# Todas las bases deben pasar integrity_check
find /tmp/restore-drill -name '*.db' -o -name '*.sqlite' | while read -r base; do
  sqlite3 "$base" 'PRAGMA integrity_check;'
done
```

En Paper 26.1 las regiones de chunks viven en
`world/dimensions/minecraft/<dimension>/region/`. No uses el tamaño del archivo
como prueba de integridad: el formato de esta versión no alinea los archivos a
4096 bytes. Para una prueba fuerte, compara los hashes de las regiones contra
el mundo en producción o valida la cabecera y los chunks de cada `.mca`.

Al terminar:

```bash
rm -rf /tmp/restore-drill
```

---

## Problemas comunes

### `no hay carpeta data/ que respaldar`

Ejecuta `mc build` primero.

### `ya hay otro respaldo en curso`

El bloqueo `backups/.bloqueo` está tomado. Espera a que termine el timer o
revisa `mc backup status`. No borres el archivo de bloqueo mientras haya un
proceso corriendo.

### El respaldo pesa demasiado

Lo normal es 1–3 GB con el mundo pregenerado. Revisa qué ocupa espacio:

```bash
du -sh data/* | sort -h | tail -5
```

Si aparece algo que se regenera solo, agrégalo a las exclusiones de los respaldos.

### `mc backup verify` marca un respaldo

No lo borres. Revisa el mensaje, compara el SHA256 y, si hace falta, restaura
en un directorio temporal para inspeccionarlo. Un respaldo con error puede ser
la única copia de un período.

### El timer no corre

```bash
systemctl status mc-backup.timer
systemctl list-timers --all | grep mc-
journalctl -u mc-backup.service -n 100 --no-pager
```

### La copia a la PC no corre sin sesión

Falta el lingering:

```bash
sudo loginctl enable-linger "$USER"
loginctl show-user "$USER" | grep Linger
```

### No llega la alerta a Discord

```bash
mc alert --seco --titulo "Prueba" "Texto"
mc alert --titulo "Prueba" "Texto"
```

Si el segundo falla, revisa `PAGOS_BOT_TOKEN`, `ALERTAS_CANAL_ID` (o
`PAGOS_CANAL_ID`) y la conexión del VPS. El bot debe tener permiso para
escribir en ese canal.
