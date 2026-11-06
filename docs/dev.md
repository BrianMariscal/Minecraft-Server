# Desarrollo

## Requisitos

- Python 3.12 o más nuevo.
- [uv](https://docs.astral.sh/uv/) para instalar dependencias y correr las herramientas.
- Docker con Compose, solo si vas a levantar el servidor o validar `docker-compose.yml`.
- Git.

Los tests **no** necesitan Docker: no levantan contenedores ni abren sockets.

## Instalación

```bash
git clone https://github.com/BrianMariscal/Minecraft-Server.git
cd Minecraft-Server

uv sync
uv run pre-commit install
```

`uv sync` instala el workspace de `packages/mc_admin` y `packages/pagos_bot`, más las herramientas de desarrollo: ruff, mypy, pytest, pytest-cov y pre-commit.

El repositorio no versiona `settings.yml`: ese archivo lleva los nombres, Discord IDs y XUIDs reales. Para desarrollo, crea tu copia desde la plantilla:

```bash
cp settings.example.yml settings.yml
```

`mc setup` también la crea sola la primera vez.

## lint, tipos y tests

```bash
uv run ruff check packages      # lint
uv run ruff format packages     # formato
uv run mypy packages            # tipos, en modo estricto
uv run pytest                   # tests
uv run pytest --cov=mc_admin --cov=pagos_bot
```

El `pre-commit` ejecuta, antes de cada commit:

- Limpieza de espacios y fin de archivo.
- Validación de YAML y TOML.
- `gitleaks` para detectar secretos.
- `ruff check --fix` y `ruff format`.
- `mypy packages` en estricto.

## Los tests

Son **575 tests**. Ninguno levanta un contenedor ni abre un socket: Docker y RCON se sustituyen por dobles. Los tests parten de `settings.example.yml`, el `manifest.yml` y las plantillas **reales**, así que detectan cambios que rompan el formato del chat, la duplicación de pistones, las rutas de los datapacks o las reglas del bot de pagos.

La configuración compartida está en `pyproject.toml`:

- `pytest` recoge `packages/mc_admin/tests` y `packages/pagos_bot/tests`.
- `mypy` revisa también los tests, con reglas relajadas solo donde un test necesita una aserción directa.
- `ruff` prohíbe `print()` fuera de la capa CLI.

## Estructura del repositorio

```text
minecraft-hd/
├── settings.example.yml      ← plantilla con datos ficticios
├── settings.yml              ← tu configuración (no entra a git)
├── .env                      ← secretos (no entra a git)
├── .env.example              ← plantilla comentada
├── docker-compose.yml        ← los dos contenedores
│
├── minecraft/
│   ├── manifest.yml          ← plugins y datapacks, con URL y SHA256
│   ├── templates/            ← plantillas Jinja2 de las configs
│   ├── translations/es_mx/   ← traducciones propias
│   └── generated/            ← configs generadas, con comentarios
│
├── packages/
│   ├── mc_admin/             ← la CLI `mc`
│   │   ├── src/mc_admin/
│   │   │   ├── cli/          ← comandos Typer + Rich, sin lógica
│   │   │   ├── core/         ← lógica pura y testeable
│   │   │   ├── infra/        ← Docker, RCON, archivos y descargas
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
├── deploy/
│   ├── systemd/              ← respaldo, verificación y monitor
│   └── pc/                   ← copia diaria del VPS a la PC
│
├── data/                     ← datos del servidor (lo genera mc build)
├── backups/                  ← respaldos locales
├── pagos-datos/              ← base de datos del bot
├── logo/                     ← logo.png opcional
└── docs/                     ← las guías
```

## Contenedores y timers

| Servicio | Qué hace |
|---|---|
| `mc-hd-servidor` | Paper 26.1.2 + plugins + datapacks |
| `mc-hd-pagos` | Bot de Discord y su SQLite; solo arranca con `pagos.activo` |
| `mc-backup.timer` | Respaldo local cada 6 horas |
| `mc-backup-verify.timer` | Verificación semanal de los respaldos |
| `mc-monitor.timer` | Revisión horaria de respaldo, disco y servidor |
| `mc-copiar-respaldos.timer` | Copia diaria del VPS a la PC (timer de usuario) |

Los respaldos son timers de systemd, **no** un contenedor. `mc backup now` se puede correr a mano y los timers siguen funcionando aunque Minecraft esté apagado.

## CI

El workflow `.github/workflows/ci.yml` corre en `main`, en `produccion` y en cada pull request:

1. `ruff` (lint y formato).
2. `mypy` estricto.
3. `pytest` con cobertura.
4. `docker compose --profile pagos config`.
5. Build de la imagen del bot de pagos.
6. `gitleaks` sobre el historial.

El badge del README apunta a la rama `main`.
