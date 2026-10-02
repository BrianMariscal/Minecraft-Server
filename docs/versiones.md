# Versiones: qué está fijado y por qué

Todo en este proyecto tiene versión exacta. Nada de `latest`.

La razón es simple: con `latest`, un reinicio cualquiera puede traerte una
versión nueva de Paper que rompe tres plugins, y te enteras cuando nadie
puede entrar. Aquí las versiones solo cambian cuando tú decides.

- Las versiones del servidor y de las imágenes están en **`settings.yml`**.
- Las de los plugins y datapacks, con su sha256, están en
  **`minecraft/manifest.yml`**.
- Para revisar si hay algo nuevo: **`mc update`**.

---

## Por qué Minecraft 26.1.2 y no la más nueva

Investigado y verificado el 30 de septiembre de 2026.

Cuando se armó esto, la versión más nueva de Minecraft era la **26.3**
(salió el 15 de septiembre de 2026). No la usamos. Tampoco la 26.2.

El proyecto corre en **26.1.2** porque es la versión más reciente que
**todas** las piezas soportan con releases estables. Esto es lo que topa:

| Pieza | Hasta dónde llega | Por qué importa |
|---|---|---|
| **EssentialsX 2.22.0** | **26.1.2** | Es el cuello de botella. Da `/home`, `/sethome`, `/spawn`, `/tpa`, `/back` y el formato del chat. Su último release estable (mayo 2026) soporta hasta 26.1.2, y sus builds de desarrollo siguen en la línea 2.22.1, que son solo parches. |
| **AuthMe Reloaded 6.0.1** | **26.1** (probado) | Sin AuthMe no hay servidor no premium seguro. |
| Geyser 2.11.3 (Spigot) | 26.2 | Sin Geyser no entra nadie de Bedrock. |
| CoreProtect 24.1 | 26.2 | Es la única red de seguridad contra grifeo. |
| Towns and Towers (datapack) | 26.2 | El mod llega a 26.3, pero el **datapack** se quedó en 26.2. Y necesitamos el datapack, no el mod: es lo que hace que Bedrock lo vea bien. |

Subir a 26.2 obligaría a usar un build de desarrollo de EssentialsX (con
riesgo en `/back`, `/home` y todo lo que toca ítems) y AuthMe sin probar.
Subir a 26.3 además dejaría fuera a Geyser, CoreProtect y Towns and Towers.

### Minecraft 26.x pide Java 25

No Java 21. Por eso la imagen es `itzg/minecraft-server:2026.9.2-java25`.
Si la cambias a una `-java21`, el servidor no arranca.

---

## Lo que se cambió respecto a lo que se pidió

### AngelChest → AxGraves

Se pidió AngelChest para las tumbas. **No se puede usar:**

- Su último release estable es **13.9.4, de enero de 2025**, anterior a todo
  Minecraft 26.x.
- Lo único probado en 26.x es **14.0.0-RC5**, un *release candidate* de hace
  unos días.
- Su descarga es un endpoint de "lo más nuevo", así que no se puede fijar con
  sha256: en cuanto salga el RC6, el sha256 dejaría de coincidir y `mc build`
  fallaría.

En su lugar va **AxGraves 1.32.1**, que es release estable, declara soporte
26.1.2, está en Modrinth (URL y sha256 fijables) y cubre los tres requisitos
que se pidieron:

| Se pidió | Cómo queda en AxGraves |
|---|---|
| Duran 1 hora | `despawn-time-seconds: 3600` |
| Guardan la XP | `store-xp: true`, `xp-keep-percentage: 1.0` |
| Cualquiera puede abrirlas | `interact-only-own: false` |

De pasada, AxGraves guarda las tumbas si el servidor se reinicia, que con
respaldos cada 6 horas no sobra.

### Vanilla Tweaks: dos packs que ya no existen

Se pidieron seis packs de Vanilla Tweaks. Cuatro están y dos **ya no se
publican para Minecraft 26.x** (revisado en su API, tanto en los datapacks
como en los *crafting tweaks*):

| Pack | Estado |
|---|---|
| armor statues | ✅ instalado (v2.8.22) |
| more mob heads | ✅ instalado (v2.19.1) |
| wandering trades | ✅ instalado (v1.7.15) |
| anti enderman grief | ✅ instalado (v1.1.16) |
| **invisible item frames** | ❌ ya no existe para 26.x |
| **right-click harvest** | ❌ ya no existe para 26.x |

No se sustituyeron por plugins de terceros a propósito: los que hay son de
autores sin reputación y cada uno es una dependencia más que se puede romper
en la siguiente actualización.

### Tala de árbol completo: datapack en vez de plugin

Se pidió "un plugin ligero compatible con Geyser". Se usa el datapack
**Timber de Vanilla Tweaks** (v2.1.19), que es mejor para este caso:

- Es 100% vanilla del lado del servidor, así que Bedrock lo ve perfecto vía
  Geyser, sin nada que instalar.
- No es un plugin más que mantener ni que se pueda romper al actualizar.
- Se actualiza junto con los otros packs de Vanilla Tweaks.

### Sonido al ser mencionado en el chat: no se puso

Se pidió "si existe un plugin ligero compatible con Geyser; si no, omítelo".
No existe uno mantenido para 26.x, así que no se puso.

Lo único que hay es el `MinecraftMentionSound` de DiscordSRV, que **solo
suena cuando te mencionan desde Discord**, no dentro del chat del juego. Ese
sí está encendido.

---

## Piezas que no se pidieron pero hacen falta

Estas dos salieron de arrancar el servidor de verdad y leer lo que avisaba:

### VaultUnlocked 2.20.3

Sin Vault, EssentialsX avisa al arrancar:

> `[Essentials] Detected supported permissions plugin LuckPerms without Vault
> installed. Features such as chat prefixes/suffixes and group-related
> functionality will not work until you install Vault.`

O sea: **sin Vault no funciona el formato de chat por grupo ni la etiqueta
`[Admin]`**, que es justo el diseño de chat que se pidió. Con Vault puesto,
el log dice `[Essentials] Using Vault based permissions (LuckPerms)`.

Es el fork mantenido de Vault (el original está abandonado). Su `plugin.yml`
se llama `Vault`, así que EssentialsX lo detecta igual.

### PacketEvents 2.14.0

Sin él, AuthMe apaga solo dos protecciones y lo avisa:

> `[AuthMe] WARNING! The protectInventory feature requires PacketEvents!
> Disabling it...`
> `[AuthMe] WARNING! The denyTabComplete feature requires PacketEvents!
> Disabling it...`

En un servidor no premium, que el inventario esté protegido antes de que
alguien escriba su contraseña no es un detalle: es lo que evita que alguien
entre con tu nombre y se lleve tus cosas.

---

## Cosas de Minecraft 26.x que rompen las guías de internet

### Las gamerules cambiaron de nombre

En 26.x pasaron de `camelCase` a `snake_case`:

```
❌ gamerule playersSleepingPercentage 1     <- lo que dice toda la documentación
✅ gamerule players_sleeping_percentage 1   <- lo que de verdad funciona
```

Con el nombre viejo el servidor contesta `Incorrect argument for command` y
**la regla no se aplica**, sin más aviso que esa línea. Es facilísimo creer
que quedó puesta.

### Las gamerules ahora son por dimensión

Ya no viven en `level.dat`. Cada dimensión tiene su propio archivo:

```
world/dimensions/minecraft/overworld/data/minecraft/game_rules.dat
world/dimensions/minecraft/the_nether/data/minecraft/game_rules.dat
world/dimensions/minecraft/the_end/data/minecraft/game_rules.dat
```

Por eso `mc start` las aplica con `execute in <dimensión> run gamerule ...`.
Los nombres que usa `mc` no salieron de la documentación: salieron de leer el
`game_rules.dat` que generó un Paper 26.1.2 de verdad.

### Cuatro avisos de "loot table" en cada arranque (son normales)

En cada arranque, el log saca estas cuatro líneas:

```
WARN: Found loot table element validation problem in {minecraft:entities/bat...}
      .pools[2].entries[0]: Missing element bat_membranes:entities/bat
WARN: ... Missing element husks_drop_sand:entities/husk
WARN: ... Missing element villager_death:entities/villager
WARN: ... Missing element double_shulker_shells:entities/shulker
```

**No es un problema y las cabezas de mobs sí funcionan.**

Vanilla Tweaks arma el pack de "more mob heads" con enganches para convivir
con otros packs suyos, los instales o no. Cada loot table queda con tres
pools:

| Pool | Qué es | Estado |
|---|---|---|
| `pools[0]` | el botín vanilla del mob | ✅ |
| `pools[1]` | **la cabeza del mob** | ✅ |
| `pools[2]` | el enganche al otro pack de VT | ❌ no instalado |

El que importa es el `pools[1]`, y está bien. El `pools[2]` apunta a
"bat membranes", "husks drop sand", "villager death messages" y "double
shulker shells", que son packs que **no se pidieron** y que cambian el juego
(que los husks suelten arena, por ejemplo).

Si quieres que los avisos desaparezcan, agrega esos cuatro packs a
`vanilla_tweaks.seleccion` en `minecraft/manifest.yml` y corre `mc update`
para recalcular los sha256. Pero entonces también te llevas sus cambios de
juego.

### Paper borra los comentarios de sus configs

Paper **reescribe** `config/paper-global.yml`, `spigot.yml` y `bukkit.yml` en
cada arranque, y les borra todos los comentarios (verificado poniendo una
marca y reiniciando).

Por eso la copia comentada vive en **`minecraft/generated/`**, que es la que
se lee y la que se versiona. La que está dentro de `data/` va a aparecer sin
comentarios y con las claves en orden alfabético. Es normal.

---

## Cómo subir una versión

`mc update` te dice qué hay nuevo, pero **no edita el manifest solo**. Es a
propósito: cada versión nueva hay que bajarla y recalcularle el sha256, y eso
conviene hacerlo leyendo el changelog del plugin.

```bash
mc backup now            # primero lo primero
mc update                # qué hay nuevo y qué soporta nuestra versión
```

Luego, para cada plugin que quieras subir:

1. Edita `minecraft/manifest.yml` con la versión y la URL nuevas.
2. Corre `mc build`. **Va a fallar**, y en el error te va a decir el sha256
   real del archivo que bajó.
3. Pega ese sha256 en el manifest.
4. `mc build` otra vez, luego `mc restart`, y revisa `mc logs`.

`mc update` nunca te propone subir un plugin a una versión que ya no soporta
tu Minecraft: así es como se rompe un servidor de un día para otro.

### Si quieres cambiar de versión de Minecraft

Primero revisa que TODO la soporte, sobre todo EssentialsX y AuthMe. Luego
cambia `versiones.minecraft` en `settings.yml`, actualiza
`compatible_con` en el manifest, y corre `mc doctor` para que te confirme
que cuadran.

---

## Fuentes de descarga

| De dónde | Qué | Se verifica |
|---|---|---|
| Modrinth | la mayoría de los plugins y datapacks | sha256 que calculamos nosotros |
| GeyserMC | Geyser, Floodgate y el add-on de SQLite | sha256 **confirmado contra su propia API** |
| GitHub releases | EssentialsX, AuthMe | sha256 que calculamos nosotros |
| vanillatweaks.net | los 5 packs de Vanilla Tweaks | sha256 del ZIP **y** de cada pack de adentro |

Vanilla Tweaks no da URLs fijas: hay que mandarle un POST con la lista de
packs y contesta con un link de id aleatorio. Lo bueno es que el ZIP que
entrega **sí es idéntico byte a byte** para la misma selección (verificado
generándolo dos veces), así que su sha256 se puede fijar igual que todo lo
demás.
