# Decisiones de diseño

Esta página explica las decisiones que no son obvias al leer el código o el
`docker-compose.yml`. Las versiones concretas y las alternativas que se
descartaron están en **[versiones.md](versiones.md)**.

## Paper 26.1.2, no la versión más nueva

Cuando se armó el proyecto, la versión más nueva de Minecraft era la 26.3
(septiembre de 2026), pero se usa **26.1.2** porque es la más reciente que
soportan con releases estables todas las piezas:

| Pieza | Hasta dónde llega | Por qué importa |
|---|---|---|
| EssentialsX 2.22.0 | 26.1.2 | Es el cuello de botella: da `/home`, `/sethome`, `/spawn`, `/tpa`, `/back` y el formato del chat |
| AuthMe 6.0.1 | 26.1 (probado) | Sin AuthMe no hay servidor no premium seguro |
| Geyser 2.12.1 | 26.3 | Sin Geyser no entra nadie de Bedrock |
| ViaVersion 5.12.2 | 26.3 | Traduce a los clientes de Java más nuevos que el servidor |
| CoreProtect 24.1 | 26.2 | Es la red de seguridad contra grifeo |
| Towns and Towers | 26.2 | El datapack se quedó en 26.2, y se necesita el datapack para que Bedrock lo vea |

Subir a 26.2 obligaría a usar un build de desarrollo de EssentialsX y AuthMe
sin probar. Subir a 26.3 además dejaría fuera CoreProtect y Towns and Towers.
Minecraft 26.x también exige **Java 25**: la imagen es
`itzg/minecraft-server:2026.9.2-java25`, no una `-java21`.

## Versiones fijadas con SHA256

Los **28 artefactos** descargables tienen versión y hash fijados en
`minecraft/manifest.yml`:

- 18 entradas de plugins: 17 plugins y la base SQLite de Floodgate.
- 5 datapacks.
- 5 packs de Vanilla Tweaks.

`mc build` descarga, calcula el SHA256 y solo entonces copia el archivo. Si un
hash no coincide, el build falla. Con `latest`, un reinicio cualquiera podría
traer una versión nueva de Paper o de un plugin y romper el servidor sin que
nadie lo haya decidido. `mc update` es la vía para revisar y aplicar versiones
nuevas de forma consciente.

## GravesX en vez de AngelChest

AngelChest no tiene release estable para 26.x. Su último release estable es de
enero de 2025 y lo único probado para 26.x era un release candidate servido
desde un endpoint de “lo más nuevo”, así que tampoco se podía fijar con SHA256.

Se probó AxGraves, pero dibujaba la tumba solo con paquetes y un jugador de
Bedrock no la veía. **GravesX 2026.4.9.2** sí declara soporte para 26.1.2 y
coloca un bloque real (una cabeza), que Geyser muestra a Bedrock como cualquier
otro bloque. Además conserva la XP, dura una hora y cualquiera puede abrirla,
tal como se pidió.

## Vanilla Tweaks: dos packs que ya no existen

Se pidieron seis packs y solo cuatro siguen publicados para 26.x:

| Pack | Estado |
|---|---|
| armor statues | Instalado, v2.8.22 |
| more mob heads | Instalado, v2.19.1 |
| wandering trades | Instalado, v1.7.15 |
| anti enderman grief | Instalado, v1.1.16 |
| invisible item frames | Ya no existe para 26.x |
| right-click harvest | Ya no existe para 26.x |

No se sustituyeron por plugins de autores sin reputación: cada dependencia
extra es otra cosa que se puede romper en la siguiente actualización.

## Datapacks en vez de mods para el mundo

Terralith, Incendium, Nullscape, Dungeons and Taverns y Towns and Towers son
**datapacks de bloques vanilla**. Es intencional: así los jugadores de Bedrock
ven los mismos biomas y estructuras que los de Java sin instalar nada. Lo mismo
aplica a Timber: la tala de árbol completo es un datapack de Vanilla Tweaks, no
un plugin más.

## Configuración generada, no editada

`settings.yml` es la única fuente de verdad para nombre, MOTD, versión, puertos,
memoria, idioma, respaldos y datos del bot. `mc build` valida ese archivo y
`.env` con pydantic, renderiza las plantillas Jinja2 y escribe las
configuraciones en `data/`.

Por eso **no se editan los archivos de `data/`**: se sobrescriben. Las copias
comentadas para leer están en `minecraft/generated/`, y el bloque `MC_*` que
`mc build` escribe al final de `.env` tampoco se toca a mano.

## Dos contenedores y timers de systemd

La arquitectura no usa un tercer contenedor para respaldos:

| Pieza | Qué hace |
|---|---|
| `mc-hd-servidor` | Paper 26.1.2, plugins, datapacks y mundo |
| `mc-hd-pagos` | Bot de Discord y su SQLite; solo arranca con `pagos.activo` |
| `mc-backup.timer` | Respaldo local cada 6 horas |
| `mc-backup-verify.timer` | Verificación semanal de los respaldos |
| `mc-monitor.timer` | Revisión horaria de respaldo, disco y servidor |
| `mc-copiar-respaldos.timer` | Copia diaria del VPS a la PC (timer de usuario) |

Los respaldos corren con systemd y `mc backup now` para que no dependan del
ciclo de vida de un contenedor y sigan funcionando aunque Minecraft esté
apagado. Es una decisión deliberada, no una pieza faltante.

## `mc doctor` como health check

`mc doctor` revisa puertos, RAM, disco, TPS, versiones y traducciones. No
sustituye a un sistema de observabilidad completo, pero cubre lo que puede
romper el servidor en este despliegue y lo hace sin servicios externos.
`mc-monitor.timer` complementa la revisión cada hora y avisa por Discord.
