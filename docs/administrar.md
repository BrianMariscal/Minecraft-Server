# Administrar el servidor

Todo desde la carpeta del proyecto, con la CLI `mc`.

---

## Whitelist: quién puede entrar

El servidor tiene whitelist porque es **no premium**: sin ella, cualquiera
podría entrar con el nombre que quisiera, incluido el tuyo.

### Agregar gente

```bash
# Alguien de Java (PC): su nombre de Minecraft
mc whitelist add Pepe

# Alguien de Bedrock (celular, consola): su GAMERTAG de Xbox
mc whitelist add "Gamer Tag 7" --bedrock
```

Con `--bedrock`, `mc` hace dos cosas solas:

1. Cambia los espacios por guion bajo (`Gamer Tag 7` → `Gamer_Tag_7`), que es
   lo que hace Floodgate.
2. Le pone el punto del prefijo (`.Gamer_Tag_7`), que es como el servidor lo
   va a ver.

**Tú dale el gamertag tal cual**, sin punto y con espacios si los tiene.

### Quitar y ver

```bash
mc whitelist remove Pepe
mc whitelist remove "Gamer Tag 7" --bedrock
mc whitelist list
```

`mc whitelist list` te muestra las dos listas y, para los de Bedrock, con qué
nombre los ve el servidor.

### Cómo funciona por dentro

Los cambios se guardan en `settings.yml` **y** se le dicen al servidor por
RCON en el momento. Si el servidor está apagado, se aplican al arrancar.

Correrlo dos veces no duplica nada y no distingue mayúsculas (Minecraft
tampoco).

---

## Admins

```bash
mc admin add Admin_HD
mc admin remove Admin_HD
mc admin list
```

Esto hace tres cosas:

1. Lo mete a `admins:` en `settings.yml`.
2. Lo pone en el grupo `admin` de LuckPerms (prefijo `[Admin]` en el chat).
3. Le da `op`.

Después de agregar un admin, corre `mc build` para que quede también en el
guion de grupos que se aplica en cada arranque.

### Qué puede hacer un admin

- Todos los comandos de EssentialsX.
- CoreProtect: ver y revertir quién movió qué.
- Chunky: pregenerar.
- Saltarse el anti-spam del chat.
- Abrir y borrar tumbas de cualquiera.
- Comandos de Geyser y Floodgate.
- `whitelist`, `gamemode`, `gamerule`, `kick`, `ban`.

### Solo para admins: investigar y revertir

No hay protección de terrenos (compartimos todo), así que **CoreProtect es la
única red de seguridad**.

```bash
mc console
```

Y ahí:

```
co i                          # modo inspección: pega un bloque y te dice quién fue
co lookup u:Pepe t:3d          # qué hizo Pepe en los últimos 3 días
co lookup u:Pepe t:1d a:block  # solo bloques
co rollback u:Pepe t:1d r:50   # revierte lo de Pepe en 50 bloques a la redonda
co rollback u:Pepe t:1d r:50 preview   # ver antes de aplicar
```

El `preview` muestra cómo quedaría sin aplicar nada. Úsalo siempre antes de
un rollback grande.

---

## El día a día

```bash
mc start      # enciende
mc stop       # apaga guardando el mundo
mc restart    # reinicia
mc status     # qué está arriba, quién anda conectado, a cuántos TPS
mc logs       # últimas 80 líneas
mc logs -f    # te quedas viendo
mc logs -s pagos-bot   # solo un servicio
```

### `mc start` hace más que prender

Cuando el servidor contesta, `mc start` le aplica:

- Las **gamerules** (dormir con un jugador, que las raids pasen, etc.).
- Los **grupos y permisos** de LuckPerms.
- La **whitelist** de `settings.yml`.

Si el servidor todavía está generando el mundo cuando `mc start` termina, te
avisa: corre `mc start` otra vez cuando acabe y lo aplica.

### La consola

```bash
mc console
```

Escribes comandos sin la diagonal, y `salir` para terminar.

```
mc> list
mc> tps
mc> say ya merito reinicio
mc> salir
```

`stop` desde ahí no se permite: usa `mc stop`, que además guarda el mundo.

---

## Revisar que todo esté bien

```bash
mc doctor
```

Te revisa, en este orden:

| Qué | Qué te dice |
|---|---|
| Docker | si responde y qué versión |
| Memoria | si alcanza para lo que pide `settings.yml`, con su colchón |
| Disco | si hay espacio para el mundo pregenerado y los respaldos |
| Puertos | si están libres, y si no, qué proceso los tiene |
| Versiones | si `settings.yml` y el manifest cuadran |
| Secretos | si falta algo en `.env` |
| Logo | si está `logo/logo.png` |
| Traducciones | si quedó algún mensaje en inglés |
| TPS | cómo va el rendimiento |
| Pendientes | si falta llenar los pagos, los admins o la whitelist |

### Ver qué quedó en inglés

```bash
mc doctor --traducciones
```

Te dice archivo, línea y qué palabras le parecieron inglesas.

---

## El mundo

### Pregenerar el mapa

Genera los chunks de antemano para que no haya tirones al explorar.

```bash
mc pregen                # radio de settings.yml (3000)
mc pregen --radio 1500   # un radio más chico
```

**Tarda horas** y trae el servidor cargado todo ese rato. Hazlo de noche o
antes de invitar a la banda. Te dice cuántos chunks y cuántos GB son antes de
empezar, y te pide confirmación.

Para pararlo:

```bash
mc console
mc> chunky pause
```

Y para seguirle después, `chunky continue`.

### Regenerar el mundo

Si el spawn no les gustó o quieren empezar de nuevo:

```bash
mc world reset --dry-run   # primero mira qué se va a borrar
mc world reset
```

Esto:

1. Te dice **exactamente** qué carpetas se borran y cuánto pesan.
2. Te pide **doble confirmación**: un sí/no y luego teclear
   `BORRAR EL MUNDO`.
3. Hace un **respaldo antes** de tocar nada.
4. Apaga el servidor.
5. Borra `world`, `world_nether` y `world_the_end`.

En el siguiente `mc start` se genera un mundo nuevo con semilla aleatoria.

> **Se pierden todas las construcciones, cofres y granjas.** Las casas de
> `/sethome` van a apuntar a coordenadas que ya no existen, así que conviene
> avisarle a la banda que las vuelva a poner.

Si quieres una semilla específica, ponla en `settings.yml` antes de arrancar:

```yaml
servidor:
  semilla: "12345678"
```

---

## Respaldos

Los automáticos corren **cada 6 horas** sin apagar el servidor, y se
conservan **7 días**. No hay que hacer nada.

```bash
mc backup now              # uno ya, ahora
mc backup list             # ver los que hay
mc backup restore ultimo   # restaurar el más reciente
mc backup restore 20260930-143000
mc backup restore ultimo --dry-run   # ver qué trae sin aplicar
```

Más detalle en [docs/respaldos.md](respaldos.md).

---

## Cuando algo se pone lento

```bash
mc status     # ¿cómo van los TPS?
mc doctor     # ¿memoria? ¿disco?
mc logs | grep -i "lag\|took\|overload"
```

Causas más comunes, en orden:

1. **Un pregen corriendo.** Es normal que baje los TPS. `chunky pause`.
2. **Una granja muy grande.** Busca en el log qué chunk se queja.
3. **Falta RAM.** `mc doctor` te lo dice.
4. **Disco lento.** Si el VPS tiene disco mecánico, se nota al guardar.

Lo que **no** hay que hacer es instalar un plugin que borre mobs: rompe las
granjas, que es justo lo que no queremos. El control de lag de este servidor
va todo por configuración de Paper y Spigot, y está documentado en los
comentarios de `minecraft/generated/spigot.yml` y
`minecraft/generated/config/paper-world-defaults.yml`.

---

## Cambiar la configuración

**Todo** se cambia en `settings.yml`, nunca en los archivos de `data/`.

```bash
nano settings.yml
mc build       # regenera las configs
mc restart
```

### Por qué no editar `data/` a mano

`mc build` **sobrescribe** lo que hay en `data/`. Si editas ahí, el siguiente
build se lleva tu cambio.

Las configs comentadas, para leerlas y entender qué hace cada cosa, están en
`minecraft/generated/`.

### Un detalle de Paper

Paper **reescribe** `paper-global.yml`, `spigot.yml` y `bukkit.yml` en cada
arranque y les borra los comentarios. Por eso la copia comentada vive en
`minecraft/generated/`, y la de `data/` se ve pelona y ordenada
alfabéticamente. Es normal, no es que se haya roto.

---

## Actualizar los plugins

```bash
mc backup now   # siempre
mc update       # qué hay nuevo
```

`mc update` no edita nada solo. Los pasos completos están en
[docs/versiones.md](versiones.md#cómo-subir-una-versión).

---

## Dónde está cada cosa

```
Minecraft server/
├── settings.yml              ← LO ÚNICO que editas normalmente
├── .env                      ← los secretos (no entra a git)
├── docker-compose.yml
│
├── minecraft/
│   ├── manifest.yml          ← plugins y datapacks, con su sha256
│   ├── templates/            ← las plantillas de las configs
│   ├── translations/es_mx/   ← las traducciones propias
│   └── generated/            ← las configs generadas, CON comentarios
│
├── data/                     ← lo que usa el servidor (lo hace mc build)
├── backups/                  ← los respaldos
├── pagos-datos/              ← la base de datos del bot de pagos
├── logo/                     ← aquí va logo.png
├── docs/                     ← estas guías
└── packages/                 ← el código de `mc` y del bot
```
