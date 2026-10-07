# Minecraft HD

Servidor de Minecraft para jugar con la banda: **Java y Bedrock juntos**,
cuentas no premium, hasta 15 jugadores, todo en español de México.

Corre en Docker sobre un VPS Linux y se administra con una CLI, `mc`.

```bash
mc setup     # revisa el entorno y pide los datos que faltan
mc build     # baja los plugins (verifica el sha256) y genera las configs
mc start     # levanta todo
```

---

## Qué trae

**Para jugar**

- Entran desde **PC (Java)**, **celular, tablet, Windows 10/11 (Bedrock)** y
  **consolas** (Xbox, PlayStation, Switch).
- Un jugador de Java y uno de Bedrock pueden ser **el mismo personaje**.
- `/home`, `/sethome`, `/spawn`, `/tpa`, `/back` (incluido volver a donde te
  moriste), `/msg`.
- **Tumbas**: al morir tus cosas y tu XP se quedan una hora en una tumba que
  cualquiera puede abrir.
- **Dormir solo**: con que una persona se duerma, amanece.
- **Talar de un golpe**, sentarse en escalones, cabezas de mobs, poses de
  armor stands.
- **Skins** aunque la cuenta no sea premium.

**El mundo**

Terralith, Incendium y Nullscape cambian los biomas, el Nether y el End.
Dungeons and Taverns y Towns and Towers agregan estructuras y aldeas. Todos
son **datapacks de bloques vanilla**, a propósito: así los de Bedrock los ven
igual que los de Java, sin instalar nada.

**Juego técnico**

Las granjas funcionan: hierro, oro, XP, mobs, cultivos, aldeanos (criaderos,
salones de comercio, curar zombis) y raids. La duplicación con pistones y con
portal del End está prendida.

El control de lag va **solo por configuración** de Paper y Spigot. No hay un
solo plugin que borre mobs, porque eso es justo lo que rompe las granjas.

**Discord**

- Un bot aparte que le recuerda a la banda que toca pagar el VPS, lleva la
  cuenta de quién pagó (también lo atrasado de meses anteriores) y avisa
  cuando ya está cubierto.
- Opcional: el mismo bot avisa si el servidor de Minecraft se cae.

**Seguridad**

- Al ser no premium, cada quien tiene su contraseña (`/register`, `/login`).
  Antes de entrar no puedes moverte ni abrir tu inventario.
- Whitelist encendida.
- CoreProtect registra quién movió qué y deja revertirlo.
- **No hay protección de terrenos**: compartimos todo.

---

## Empezar de cero

Si vas a montarlo en un VPS, la guía completa es
**[docs/vps.md](docs/vps.md)**: qué contratar, dónde, cómo instalar Docker,
cómo subir la carpeta y cómo cerrar el firewall.

El resumen:

```bash
# En el VPS, con Docker y uv ya instalados.
cd ~/minecraft-hd

mc setup     # te pide la contraseña de RCON y el token del bot de pagos
mc build     # baja 24 plugins y datapacks, verificando cada sha256
mc start     # arranca
mc logs -f   # el primer arranque tarda: genera el mundo
```

Y luego:

```bash
mc admin add TuNombre        # hazte admin
mc whitelist add Pepe        # mete a la banda
mc whitelist add "Gamer Tag" --bedrock
mc doctor                    # revisa que todo esté bien
```

---

## Las guías

| Guía | De qué |
|---|---|
| **[vps.md](docs/vps.md)** | Montar el VPS de cero: Docker, subir la carpeta, firewall, dominio. Y cómo mudarte de proveedor |
| **[conectarse.md](docs/conectarse.md)** | Cómo entra la banda, desde Java, Bedrock y consolas |
| **[vincular-cuentas.md](docs/vincular-cuentas.md)** | Tener el mismo personaje en Java y en Bedrock |
| **[administrar.md](docs/administrar.md)** | Whitelist, admins, pregen, regenerar el mundo, CoreProtect |
| **[respaldos.md](docs/respaldos.md)** | Los automáticos, restaurar, y una copia fuera del VPS |
| **[bot-pagos.md](docs/bot-pagos.md)** | Crear el bot de pagos y configurar a la banda |
| **[versiones.md](docs/versiones.md)** | Qué versión está fijada y **por qué**, y cómo subirlas |

---

## Lo único que editas

**`settings.yml`**, en la raíz. Ahí está el nombre del servidor, el MOTD, la
versión, los puertos, la memoria, el idioma, los respaldos y los
datos del bot de pagos. Está comentado línea por línea.

Después de cambiar algo:

```bash
mc build && mc restart
```

Los secretos (tokens, contraseñas) van en **`.env`**, que no entra a git.
`mc setup` te lo llena. Al final de `.env`, `mc build` escribe un bloque
marcado con la versión, la memoria, los puertos y los respaldos sacados de
`settings.yml`: de ahí los lee `docker-compose.yml`. Ese bloque no se edita
a mano.

> **No edites los archivos de `data/`**: `mc build` los sobrescribe. Las
> configs comentadas, para leerlas, están en `minecraft/generated/`.

---

## Los comandos de `mc`

### Preparar

| Comando | Qué hace |
|---|---|
| `mc setup` | Revisa el entorno, crea `.env` y pide los datos que faltan |
| `mc build` | Baja los plugins verificando su sha256 y genera las configs |
| `mc build --dry-run` | Te enseña qué haría, sin tocar nada |

### Día a día

| Comando | Qué hace |
|---|---|
| `mc start` | Enciende, y aplica gamerules, permisos y whitelist |
| `mc stop` | Apaga guardando el mundo |
| `mc restart` | Guarda, apaga y vuelve a levantar todo, aplicando lo que cambiaste en `settings.yml` o `.env` |
| `mc status` | Qué está arriba, quién anda conectado, a cuántos TPS |
| `mc logs` / `mc logs -f` | Los logs |
| `mc console` | Consola interactiva por RCON |

### Jugadores

| Comando | Qué hace |
|---|---|
| `mc whitelist add Pepe` | Mete a alguien de Java |
| `mc whitelist add "Gamer Tag" --bedrock` | Mete a alguien de Bedrock |
| `mc whitelist remove Pepe` | Lo saca |
| `mc whitelist list` | Ve la lista |
| `mc admin add Admin_HD` | Lo hace admin (grupo de LuckPerms y op) |
| `mc admin remove Admin_HD` / `mc admin list` | |

### Respaldos

| Comando | Qué hace |
|---|---|
| `mc backup now` | Uno ya, sin apagar el servidor |
| `mc backup list` | Ve los que hay |
| `mc backup restore ultimo` | Restaura, con doble confirmación |

### El mundo

| Comando | Qué hace |
|---|---|
| `mc pregen` | Pregenera el mapa con Chunky |
| `mc pregen --radio 1500` | Con otro radio |
| `mc world reset` | Regenera el mundo desde cero |

### Mantenimiento

| Comando | Qué hace |
|---|---|
| `mc doctor` | Puertos, RAM, disco, TPS, versiones, traducciones |
| `mc doctor --traducciones` | Qué mensajes siguen en inglés |
| `mc update` | Si hay versiones nuevas y qué soporta nuestra versión |

Todos aceptan `--help`. Las operaciones peligrosas (`restore`, `world reset`)
piden doble confirmación, hacen un respaldo antes y tienen `--dry-run`.

---

## La estructura

```
minecraft-hd/
├── settings.yml              ← LO ÚNICO que editas normalmente
├── .env                      ← los secretos (no entra a git)
├── .env.example              ← la plantilla, comentada
├── docker-compose.yml        ← los contenedores (lee sus números de .env)
│
├── minecraft/
│   ├── manifest.yml          ← plugins y datapacks, con URL y sha256
│   ├── templates/            ← plantillas Jinja2 de las configs
│   ├── translations/es_mx/   ← las traducciones propias
│   └── generated/            ← las configs generadas, CON comentarios
│
├── packages/
│   ├── mc_admin/             ← la CLI `mc`
│   │   ├── src/mc_admin/
│   │   │   ├── cli/          ← los comandos (Typer + Rich), sin lógica
│   │   │   ├── core/         ← lógica pura y testeable
│   │   │   ├── infra/        ← Docker, RCON, archivos, descargas
│   │   │   └── config.py     ← valida settings.yml y .env con pydantic
│   │   └── tests/
│   └── pagos_bot/            ← el bot de pagos
│       ├── src/pagos_bot/
│       │   ├── domain/       ← dinero, calendario y reglas puras
│       │   ├── services/     ← casos de uso
│       │   ├── repository/   ← SQLite
│       │   └── discord_ui/   ← comandos slash, botones y embeds
│       ├── tests/
│       └── Dockerfile
│
├── data/                     ← lo que usa el servidor (lo hace mc build)
├── backups/                  ← los respaldos
├── pagos-datos/              ← la base de datos del bot
├── logo/                     ← aquí va logo.png
└── docs/                     ← las guías
```

### Los tres contenedores

| Servicio | Qué hace |
|---|---|
| `minecraft` | El servidor (Paper 26.1.2 + 19 plugins + 10 datapacks) |
| `respaldos` | Un respaldo cada 6 horas, sin apagar el servidor |
| `pagos-bot` | El bot de Discord que cobra el VPS |

---

## Decisiones que conviene conocer

**Minecraft 26.1.2, no la más nueva.** La 26.3 ya existe, pero EssentialsX
—que da `/home`, `/back` y el formato del chat— solo tiene release estable
hasta 26.1.2. El detalle de qué topa cada pieza está en
[docs/versiones.md](docs/versiones.md).

**Las versiones están fijadas, con sha256.** `mc build` no instala nada cuyo
hash no coincida. Con `latest`, un reinicio cualquiera puede romperte tres
plugins y te enteras cuando nadie puede entrar.

**AxGraves en vez de AngelChest.** AngelChest no tiene release estable para
26.x: el último es de enero de 2025. [Por qué](docs/versiones.md#angelchest--axgraves).

**Hay dos packs de Vanilla Tweaks que ya no existen** para 26.x (marcos
invisibles y cosechar con clic derecho). No se sustituyeron por plugins de
autores sin reputación. [Detalle](docs/versiones.md#vanilla-tweaks-dos-packs-que-ya-no-existen).

**Todo lo que se programó es Python**, con tipos en todo, mypy estricto y
ruff. El único shell que hay son los comandos de las guías.

---

## Para desarrollar

```bash
uv sync                      # instala todo
uv run pre-commit install    # los ganchos de git

uv run ruff check packages   # lint
uv run ruff format packages  # formato
uv run mypy packages         # tipos, en estricto
uv run pytest                # los tests
uv run pytest --cov=mc_admin.core --cov=pagos_bot.domain
```

355 tests. Ninguno levanta un contenedor ni abre un socket: Docker y RCON se
sustituyen por dobles. Los tests leen el `settings.yml`, el `manifest.yml` y
las plantillas **reales**, así que si un cambio rompe el chat por grupo, la
duplicación de pistones o la ruta de los datapacks, el test correspondiente
falla.
