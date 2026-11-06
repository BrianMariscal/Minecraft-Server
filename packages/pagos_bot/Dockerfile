# ===========================================================================
#  Bot de pagos del VPS — imagen multi-etapa
# ===========================================================================
#  Se construye desde la RAÍZ del proyecto, porque necesita uv.lock:
#      docker compose build pagos-bot
# ===========================================================================

# --- Etapa 1: instalar las dependencias ------------------------------------
# La hacemos aparte para que la capa de dependencias se cachee: cambiar el
# código del bot no vuelve a bajar discord.py.
FROM python:3.12-slim AS dependencias

# uv resuelve e instala desde uv.lock, o sea las MISMAS versiones que en
# desarrollo. Sin esto, una build de la semana que entra podría traer otra
# versión de discord.py sin que nadie lo pida.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Primero solo los archivos que definen dependencias.
COPY pyproject.toml uv.lock ./
COPY packages/mc_admin/pyproject.toml packages/mc_admin/
COPY packages/pagos_bot/pyproject.toml packages/pagos_bot/

# --no-install-project: todavía no copiamos el código.
# --package pagos-bot: del workspace solo queremos el bot, no la CLI `mc`
# (que arrastra httpx, jinja2, typer y rich sin necesidad).
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --package pagos-bot

# Ahora sí el código, y lo instalamos.
COPY packages/pagos_bot/src packages/pagos_bot/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package pagos-bot


# --- Etapa 2: la imagen que se ejecuta --------------------------------
FROM python:3.12-slim AS runtime

# Usuario sin privilegios: si alguien se mete por el bot, no es root.
# El uid 1000 es el mismo que el del servidor de Minecraft, para que los
# archivos del volumen compartido se puedan leer entre los dos.
RUN groupadd --gid 1000 pagos \
 && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin pagos

WORKDIR /app

# Solo el entorno virtual ya armado. Nada de uv ni de compiladores en la
# imagen final: menos cosas que puedan tener un agujero.
COPY --from=dependencias --chown=pagos:pagos /app/.venv /app/.venv
COPY --chown=pagos:pagos packages/pagos_bot/src/pagos_bot /app/pagos_bot

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PAGOS_DB=/datos/pagos.sqlite \
    PAGOS_SETTINGS=/app/settings.yml

# El volumen de la base de datos.
RUN mkdir -p /datos && chown pagos:pagos /datos
VOLUME ["/datos"]

USER pagos

# El bot escribe una marca cada minuto mientras está conectado a Discord;
# esto la revisa. Si se atoró, Docker lo reinicia.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD ["python", "-m", "pagos_bot.salud"]

ENTRYPOINT ["python", "-m", "pagos_bot.main"]
