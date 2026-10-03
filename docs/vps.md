# Subir el servidor a un VPS

Esta guía va de cero: desde contratar el VPS hasta tener el servidor
corriendo.

---

## 1. Qué VPS contratar

Lo que necesitas para 15 jugadores con estos datapacks:

| | Mínimo | Recomendado |
|---|---|---|
| RAM | 8 GB | 8 GB |
| vCores | 4 | 4 |
| Disco | 40 GB SSD | 80 GB SSD |
| Sistema | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |

Con 8 GB, `settings.yml` le da 6 GB al servidor y quedan ~2 GB para el
sistema, el bot de pagos y los respaldos. `mc doctor` te avisa si queda
justo.

El disco pesa más de lo que parece: un mundo pregenerado de radio 3000 son
unos 20 GB, más 7 días de respaldos.

### Dónde, si juegas desde México

Lo que importa es el **ping**, y el ping lo manda la distancia. De más cerca
a más lejos:

| Centro de datos | Ping típico desde el centro de México |
|---|---|
| **Querétaro / Ciudad de México** | 10–25 ms |
| **Dallas, Texas** | 30–50 ms |
| **Miami, Florida** | 50–70 ms |
| Los Ángeles | 60–80 ms |
| Virginia / Nueva York | 70–90 ms |
| Europa | 140 ms+ |

**Querétaro o Ciudad de México** es lo mejor si lo encuentras. Si no,
**Dallas** es la opción más común y barata con buen ping a todo México.
Miami sirve si la banda está repartida entre México y Sudamérica.

Nada de Europa: a 140 ms el PvP se siente raro y romper bloques va con
retraso.

---

## 2. Entrar al VPS

```bash
ssh usuario@la-ip-de-tu-vps
```

Si es la primera vez y solo tienes `root`, crea un usuario normal. Correr el
servidor como root es un riesgo que no hace falta tomar:

```bash
adduser minecraft
usermod -aG sudo minecraft
# Y vuelve a entrar como ese usuario.
```

---

## 3. Instalar Docker

Los pasos oficiales de Docker para Ubuntu:

```bash
# 1. Quitar versiones viejas que pueda traer Ubuntu.
for p in docker.io docker-doc docker-compose podman-docker containerd runc; do
  sudo apt-get remove -y $p
done

# 2. El repositorio oficial de Docker.
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) \
signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 3. Instalar.
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

### Para no andar con `sudo` en cada comando

```bash
sudo usermod -aG docker $USER
```

**Y luego sal y vuelve a entrar por SSH.** Si no cierras la sesión, el grupo
no aplica y `mc` te va a decir que no encuentra Docker.

Comprueba que jaló:

```bash
docker compose version
```

---

## 4. Instalar uv

`uv` es lo que corre la CLI `mc`:

```bash
curl -fsSL https://astral.sh/uv/install.sh | sh
```

Y recarga tu shell:

```bash
source ~/.bashrc
uv --version
```

---

## 5. Subir la carpeta del proyecto

Desde **tu computadora**, no desde el VPS.

### Con rsync (lo mejor)

Solo manda lo que cambió, así que la segunda vez es rapidísimo:

```bash
# Desde la carpeta que CONTIENE a minecraft-hd/
rsync -avz --progress \
  --exclude 'data/' \
  --exclude 'backups/' \
  --exclude 'pagos-datos/' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '.cache/' \
  --exclude 'minecraft/generated/' \
  minecraft-hd/ \
  usuario@tu-vps:~/minecraft-hd/
```

Fíjate en los `--exclude`: `data/`, `backups/` y `pagos-datos/` son del VPS
y pueden pesar gigas (o, en el caso del bot, pisarte quién ya pagó). No
tiene sentido mandarlos de ida ni de vuelta. Y `.env` lleva tus tokens.

> Si ya habías corrido el bot de pagos en tu computadora y quieres conservar
> lo que anotó, súbelo **una sola vez**, antes del primer `mc start`:
> `scp -r minecraft-hd/pagos-datos usuario@tu-vps:~/minecraft-hd/`.

### Con scp (si no tienes rsync)

```bash
# Desde la carpeta que CONTIENE a minecraft-hd/
tar czf mc-hd.tar.gz \
  --exclude='data' --exclude='backups' --exclude='pagos-datos' \
  --exclude='.env' --exclude='.venv' \
  --exclude='__pycache__' --exclude='.cache' \
  --exclude='minecraft/generated' \
  minecraft-hd

# Revisa que no salió vacío (debe pesar cientos de KB, no unos bytes):
ls -lh mc-hd.tar.gz

scp mc-hd.tar.gz usuario@tu-vps:~/
ssh usuario@tu-vps 'tar xzf mc-hd.tar.gz && rm mc-hd.tar.gz'
```

### ¿Y el `.env`?

**No lo subas con rsync.** Tiene tus tokens. Mejor corre `mc setup` en el VPS
y lo llenas ahí: así el archivo con los secretos existe en un solo lugar.

---

## 6. Arrancar

Ya en el VPS, dentro de la carpeta:

```bash
cd ~/minecraft-hd

# 1. Revisa el entorno y llena los secretos.
uv run mc setup

# 2. Baja los plugins (verifica el sha256 de cada uno) y genera las configs.
uv run mc build

# 3. Levanta todo.
uv run mc start
```

El primer arranque **tarda**: genera el mundo con los 10 datapacks. Míralo
con:

```bash
uv run mc logs -f
```

Cuando veas `Done (...)! For help, type "help"`, ya está.

### Para escribir `mc` y no `uv run mc`

```bash
echo 'alias mc="cd ~/minecraft-hd && uv run mc"' >> ~/.bashrc
source ~/.bashrc
```

De aquí en adelante la guía usa `mc` sin más.

---

## 7. El firewall

Esto es lo más importante de seguridad del VPS. Solo tres puertos abiertos.

```bash
# El orden importa: primero SSH, o te quedas fuera de tu propio servidor.
sudo ufw allow OpenSSH

sudo ufw allow 25565/tcp comment 'Minecraft Java'
sudo ufw allow 19132/udp comment 'Minecraft Bedrock'
sudo ufw allow 8100/tcp  comment 'Mapa web BlueMap'

sudo ufw enable
sudo ufw status numbered
```

Debe verse así:

```
22/tcp    ALLOW IN    Anywhere    # OpenSSH
25565/tcp ALLOW IN    Anywhere    # Minecraft Java
19132/udp ALLOW IN    Anywhere    # Minecraft Bedrock
8100/tcp  ALLOW IN    Anywhere    # Mapa web BlueMap
```

### Dos cosas que hay que tener claras

**El `/udp` de Bedrock no es opcional.** Bedrock va por UDP. Si abres
`19132/tcp` por error, no va a entrar nadie de Bedrock y el error no dice
nada útil.

**RCON (25575) NO se abre. Nunca.** Quien tenga esa contraseña es dueño
del servidor: puede dar op, banear y apagarlo. En el `docker-compose.yml`
está publicado **solo en `127.0.0.1`**, para que `mc` lo alcance desde el
propio VPS; desde internet ese puerto no existe, haga lo que haga el
firewall.

**Ojo: Docker se salta `ufw`.** Los puertos que publica Docker se abren por
su cuenta en iptables, aunque `ufw` diga que están cerrados. Por eso lo que
debe ser privado se amarra a `127.0.0.1` en el compose, y no basta con "no
abrirlo" en `ufw`.

### Si quieres el mapa privado

Por lo de arriba, quitar la regla del 8100 en `ufw` **no** lo esconde. Hazlo
desde `settings.yml`:

```yaml
mapa:
  publico: false
```

```bash
mc build && mc restart
sudo ufw delete allow 8100/tcp   # ya no hace falta
```

Y entra por un túnel SSH desde tu compu:

```bash
ssh -L 8100:localhost:8100 usuario@tu-vps
```

Luego abre `http://localhost:8100` en tu navegador.

### Swap: un colchón para la RAM

Con `recursos.memoria: "6G"`, el contenedor del servidor puede llegar a
7.5 GB (Java usa memoria fuera del heap). En un VPS de 8 GB conviene tener
swap para que un pico no tumbe nada:

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
# Que solo lo use de emergencia:
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swap.conf
sudo sysctl --system
```

---

## 8. Una dirección fácil de recordar

Nadie se acuerda de `203.0.113.11`.

### Gratis: DuckDNS

1. Entra a [duckdns.org](https://www.duckdns.org) y métete con Google o
   GitHub.
2. Escoge un nombre, por ejemplo `minecrafthd`. Te queda
   `minecrafthd.duckdns.org`.
3. Pon la IP de tu VPS y dale a "update ip".

Para que se actualice solo si tu VPS cambia de IP:

```bash
mkdir -p ~/duckdns
cat > ~/duckdns/actualizar.sh <<'EOS'
#!/bin/sh
curl -s "https://www.duckdns.org/update?domains=minecrafthd&token=TU-TOKEN&ip=" \
  > ~/duckdns/duck.log
EOS
chmod +x ~/duckdns/actualizar.sh

# Cada 5 minutos.
(crontab -l 2>/dev/null; echo "*/5 * * * * ~/duckdns/actualizar.sh >/dev/null 2>&1") | crontab -
```

La banda entra con `minecrafthd.duckdns.org`.

### Con tu propio dominio

Si compraste un dominio, crea un registro **A**:

| Tipo | Nombre | Valor |
|---|---|---|
| A | `mc` | la IP de tu VPS |

Y ya entran con `mc.tudominio.com`.

### Para que no tengan que escribir el puerto (solo Java)

Con un registro **SRV**, los de Java entran escribiendo nada más
`mc.tudominio.com`, sin `:25565`:

| Campo | Valor |
|---|---|
| Tipo | SRV |
| Nombre | `_minecraft._tcp.mc` |
| Prioridad | 0 |
| Peso | 5 |
| Puerto | 25565 |
| Destino | `mc.tudominio.com` |

En algunos paneles se escribe todo junto en un campo:

```
_minecraft._tcp.mc  SRV  0 5 25565 mc.tudominio.com.
```

Ojo con el punto final: muchos paneles lo necesitan.

**El SRV solo funciona para Java.** Los de Bedrock siempre tienen que poner
la dirección y el puerto `19132` a mano. Es una limitación de Bedrock, no de
tu configuración.

---

## 9. Que arranque solo si el VPS se reinicia

Ya está: los contenedores llevan `restart: unless-stopped`.

Si quieres asegurarte de que Docker arranca con el sistema:

```bash
sudo systemctl enable docker
```

---

## 10. Revisar que todo esté bien

```bash
mc doctor
```

Te revisa Docker, la RAM, el disco, los puertos, las versiones, los
secretos, el logo, las traducciones y los TPS.

```bash
mc status
```

Te dice qué contenedores están arriba, quién anda conectado y a cuántos TPS
va el servidor.

---

## Si algo no jala

### `mc` dice que no encuentra Docker

Te falta salir y volver a entrar por SSH después del `usermod -aG docker`.

```bash
groups           # ¿sale "docker"?
docker compose version
```

### Un puerto está ocupado

```bash
mc doctor        # te dice qué proceso lo tiene
sudo ss -tulpn | grep -E '25565|19132|8100'
```

### Los de Bedrock no pueden entrar

1. ¿Abriste el puerto como **UDP**? `sudo ufw status | grep 19132`
2. ¿Están poniendo el puerto 19132 en el juego?
3. ¿Están en la whitelist con `mc whitelist add Nombre --bedrock`?

### Los archivos de `data/` quedaron de otro usuario

Pasa si corriste Docker con `sudo` alguna vez:

```bash
sudo chown -R $USER:$USER data
id -u    # que este número...
id -g    # ...y este, sean los de UID y GID en .env
```

### El servidor se queda sin memoria

```bash
mc doctor        # te dice cuánto colchón queda
free -h
```

Si va justo, bájale a `recursos.memoria` en `settings.yml` y corre
`mc build && mc restart`.

---

## Cambiar de proveedor de VPS

La pregunta normal es "¿me llevo mi Docker y ya?". Casi: los contenedores
son desechables, lo que importa son los **datos**.

Y aquí hay algo que juega a tu favor: el `docker-compose.yml` usa *bind
mounts* a la carpeta del proyecto, no volúmenes de Docker. O sea que **todo
lo irremplazable vive dentro de `minecraft-hd/`**. No hay nada escondido
en `/var/lib/docker` que haya que exportar.

### Lo que SÍ te llevas

| Qué | Por qué |
|---|---|
| `data/` | El mundo, y las bases de datos de CoreProtect, AuthMe, LuckPerms y la vinculación de cuentas. **Esto es lo único que no se puede volver a generar.** |
| `pagos-datos/` | Quién ha pagado qué mes. |
| `settings.yml` | Tu configuración. |
| `.env` | Los tokens y la contraseña de RCON. |
| `minecraft/`, `packages/`, `docker-compose.yml` | El proyecto. |
| `backups/` | Opcional, pero llévate al menos el último. |

### Lo que NO te llevas

| Qué | Por qué |
|---|---|
| Las imágenes de Docker | Se bajan solas de Docker Hub por su tag. La del bot de pagos se construye en el VPS nuevo. |
| `.cache/` | Son los jars ya bajados. Pesa bastante y `mc build` los vuelve a bajar verificando el sha256. |
| `data/plugins/*.jar`, `data/libraries/`, `data/versions/` | Igual: `mc build` los repone. |
| `data/cache/`, `data/logs/` | Basura regenerable. |
| `minecraft/generated/` | Lo regenera `mc build`. |
| `.venv/` | Lo rehace `uv sync`. |

### Cómo hacerlo

**Primero, apaga el servidor.** Copiar un mundo que se está escribiendo te
da un mundo inconsistente, y eso no se nota hasta que un chunk sale
corrupto.

```bash
# --- en el VPS VIEJO ---
mc stop
mc backup now        # por si acaso
```

Luego, desde **tu computadora**, pasas la carpeta de un VPS al otro:

```bash
rsync -avz --progress \
  --exclude '.cache/' \
  --exclude '.venv/' \
  --exclude 'minecraft/generated/' \
  --exclude '__pycache__/' \
  --exclude 'data/cache/' \
  --exclude 'data/logs/' \
  --exclude 'data/libraries/' \
  --exclude 'data/versions/' \
  --exclude 'data/plugins/*.jar' \
  --exclude 'data/plugins/BlueMap/bluemap/web/' \
  usuario@vps-viejo:~/minecraft-hd/ \
  usuario@vps-nuevo:~/minecraft-hd/
```

Si no puedes ir de servidor a servidor directo, bájalo a tu compu y súbelo:
es el mismo comando en dos pasos.

```bash
# --- en el VPS NUEVO ---
# 1. Docker y uv, igual que la primera vez (secciones 3 y 4 de esta guía).

# 2. Los archivos tienen que ser tuyos. Si el usuario del VPS nuevo tiene
#    otro número de id, los permisos quedan mal y el servidor no arranca.
sudo chown -R $USER:$USER ~/minecraft-hd
id -u; id -g        # que estos dos coincidan con UID y GID de .env

# 3. Repone los jars y regenera las configs.
cd ~/minecraft-hd
mc build

# 4. Revisa antes de arrancar.
mc doctor

# 5. Arranca.
mc start
mc logs -f
```

### Las cuatro cosas que Docker NO se lleva

Esto es lo que de verdad se olvida:

1. **El firewall.** El VPS nuevo viene abierto o cerrado de fábrica, no como
   lo dejaste. Vuelve a hacer la sección 7 de esta guía: `25565/tcp`,
   `19132/udp` y el de BlueMap. Y acuérdate de `OpenSSH` antes de
   `ufw enable`.
2. **El DNS.** Tu dominio o tu DuckDNS siguen apuntando a la IP vieja. Si no
   lo cambias, la banda se conecta a un servidor que ya no existe.
   - DuckDNS: actualiza la IP y el cron de `~/duckdns/actualizar.sh`.
   - Dominio propio: cambia el registro **A**. El **SRV** no se toca (apunta
     al nombre, no a la IP).
   - Los DNS tardan en propagarse. Si quieres que sea instantáneo, baja el
     TTL a 300 segundos **unos días antes** de mudarte.
3. **Que Docker arranque con el sistema**: `sudo systemctl enable docker`.
4. **Los respaldos fuera del VPS**, si los tenías: hay que volver a
   configurar `rclone` en el VPS nuevo (`docs/respaldos.md`).

### Lo que NO hay que tocar

- **Los tokens de Discord.** Están amarrados a la aplicación, no a la
  máquina. Los dos bots siguen funcionando igual.
- **La contraseña de RCON.** Vive solo en la red interna de Docker.
- **Las cuentas de los jugadores.** Sus contraseñas de AuthMe, sus casas de
  `/sethome`, sus permisos y sus cuentas vinculadas van dentro de `data/`.
  Nadie tiene que volver a registrarse.
- **El mes del bot de pagos.** Va en `pagos-datos/`, así que no se pierde
  quién ya pagó.

### La ruta alterna: por respaldo

Si prefieres no andar con `rsync` y sus exclusiones, un respaldo ya trae
exactamente lo que hay que llevarse (deja fuera los jars, el caché y los
logs solito):

```bash
# en el viejo
mc stop && mc backup now
mc backup list        # apunta el id

# copias la carpeta del proyecto SIN data/, más el .tgz del respaldo

# en el nuevo
mc build
mc backup restore <el-id>
mc start
```

### Comprobar que quedó bien

```bash
mc doctor       # puertos, memoria, disco, versiones, secretos
mc status       # contenedores y TPS
```

Y dentro del juego: que tu `/home` te lleve a tu casa de verdad, y que el
mapa web abra en `http://la-ip-nueva:8100`. Si las dos cosas jalan, la
mudanza salió bien.

Cuando ya estés seguro, apaga el VPS viejo. No antes: tener los dos unos
días cuesta poco y te deja volver si algo salió mal.

## Mantenimiento

| Cada cuándo | Qué |
|---|---|
| Nunca (es automático) | Los respaldos, cada 6 horas |
| Cada semana | `mc doctor` |
| Cada mes | `mc update` y `sudo apt update && sudo apt upgrade` |
| Antes de cualquier cambio | `mc backup now` |
