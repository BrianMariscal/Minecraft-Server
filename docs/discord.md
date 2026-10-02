# Conectar el chat con Discord (DiscordSRV)

Esto hace que lo que se escribe en el juego se vea en un canal de Discord, y
al revés.

**Ojo:** este es el **bot #1**. El bot de pagos es **otro bot distinto**, con
su propia aplicación y su propio token. Si usas el mismo token para los dos,
ninguno va a funcionar bien. El bot de pagos está en
[docs/bot-pagos.md](bot-pagos.md).

---

## 1. Crear la aplicación

1. Entra a **[discord.com/developers/applications](https://discord.com/developers/applications)**
   con tu cuenta de Discord.
2. Arriba a la derecha: **New Application**.
3. Nombre: `Minecraft HD Chat` (o lo que quieras; es el nombre que verá la
   banda).
4. Acepta los términos y **Create**.

## 2. Convertirla en bot y sacar el token

1. En el menú de la izquierda: **Bot**.
2. En **Username** ponle cómo quieres que se vea en el chat, por ejemplo
   `Minecraft HD`.
3. Si quieres, súbele un avatar (el logo del servidor queda bien).
4. Busca **Reset Token** y pícale. Confirma.
5. **Copia el token.** Es una cadena larga tipo
   `TU_TOKEN_DE_DISCORD_AQUI`

> **El token es como la contraseña del bot.** No lo pegues en Discord, ni en
> una captura, ni lo subas a git. Si se te sale, vuelve a darle a
> **Reset Token** y el viejo deja de servir.
>
> Discord detecta tokens filtrados en repositorios públicos y los invalida
> solo, pero no te confíes.

### Lo que NO hay que prender

Más abajo en la misma página hay **Privileged Gateway Intents**. DiscordSRV
**no los necesita**:

- ❌ Presence Intent
- ❌ Server Members Intent
- ❌ Message Content Intent

Déjalos apagados. Menos permisos es mejor.

## 3. Invitar el bot a tu servidor

1. Menú izquierdo: **OAuth2** → **URL Generator**.
2. En **Scopes** marca solo:
   - ✅ `bot`
3. En **Bot Permissions** marca:
   - ✅ View Channels
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Read Message History
   - ✅ Manage Webhooks *(para que los mensajes salgan con el nombre y el
     avatar de cada jugador en lugar de todos con el del bot)*
4. Hasta abajo te sale una URL **GENERATED URL**. Cópiala, ábrela en el
   navegador y escoge tu servidor de Discord.

## 4. Sacar los IDs

Discord no muestra los IDs hasta que prendes el modo desarrollador.

1. En Discord: **Ajustes de usuario** (el engranito abajo a la izquierda).
2. **Avanzado** → prende **Modo desarrollador**.

Ahora:

- **ID del canal de chat:** clic derecho en el canal donde quieres el chat
  (por ejemplo `#minecraft`) → **Copiar ID del canal**.
- **ID del canal de consola** (opcional, ve más abajo): igual, en un canal
  **privado** solo para admins.

Son números largos tipo `1234567890123456789`.

## 5. Ponerlo en el proyecto

```bash
mc setup
```

Te va a pedir el token y el ID del canal. También puedes editar `.env` a
mano:

```bash
DISCORD_TOKEN=el-token-que-copiaste
DISCORD_CHANNEL_CHAT=1234567890123456789
```

Y aplícalo:

```bash
mc build
mc restart
```

Si todo jaló, en `mc logs` vas a ver que DiscordSRV se conectó, y en el canal
va a salir:

> ✅ **Ya está prendido el servidor**

---

## Qué se ve en Discord

| En el juego pasa | En Discord sale |
|---|---|
| Alguien escribe en el chat | `Nombre » mensaje` |
| Alguien entra | `Pepe se conectó` |
| Alguien sale | `Pepe se desconectó` |
| Alguien entra por primera vez | `Pepe llegó por primera vez` |
| Alguien se muere | El mensaje de muerte de Minecraft |
| Alguien saca un logro | `Pepe consiguió el progreso X` |
| El servidor prende o apaga | ✅ / 🛑 |

Y de Discord al juego:

```
[Discord] Nombre » mensaje
```

### Escribir `quienhay` en el canal

Contesta quién está conectado ahora mismo. Es el equivalente de `/list`.

---

## El canal de consola (opcional)

Puedes tener un canal donde se vea **toda** la consola del servidor y desde
donde correr comandos.

> **Ponlo en un canal privado.** Ahí se ve todo: errores con rutas de
> archivos, quién entra con qué IP, y los comandos que corre cada quien.

1. Crea un canal privado, por ejemplo `#consola-admins`, y dale acceso solo a
   los admins y al bot.
2. Copia su ID.
3. En `settings.yml`:
   ```yaml
   discord:
     canal_consola: true
   ```
4. En `.env`:
   ```bash
   DISCORD_CHANNEL_CONSOLA=9876543210987654321
   ```
5. `mc build && mc restart`

### Correr comandos desde Discord

Con el canal de consola prendido, en el canal de chat puedes escribir:

```
!c say hola a todos
!c tps
```

Hay **dos candados** a propósito:

- Solo quien tenga el rol **`Admin`** en Discord.
- Solo estos comandos: `say`, `tps`, `list`, `whitelist`. Los demás no, aunque
  seas admin.

Y hay comandos que **nunca** se pueden correr desde Discord, pase lo que
pase: `op`, `deop`, `execute`, `ban`, `pardon` y `stop`.

Es a propósito: si un día alguien se mete a tu Discord, que no pueda volverse
dueño del servidor de Minecraft.

Para que funcione, crea un rol llamado exactamente **`Admin`** en tu Discord
y dáselo a quien corresponda.

---

## Cambiar cómo se ve

Todo está en `minecraft/templates/discordsrv-config.yml.j2` y los textos en
`minecraft/translations/es_mx/discordsrv-messages.yml`.

Después de editar:

```bash
mc build
mc restart
```

**No edites `data/plugins/DiscordSRV/config.yml` a mano:** `mc build` lo
sobrescribe. Edita la plantilla.

---

## Si algo no jala

### "No bot token has been set in the config"

`DISCORD_TOKEN` está vacío en `.env`. Corre `mc setup`, y luego
`mc build && mc restart`.

### El bot sale en línea pero no pasa nada

1. ¿El `DISCORD_CHANNEL_CHAT` es el correcto? Vuelve a copiar el ID.
2. ¿El bot puede ver ese canal? Si es privado, hay que darle acceso
   explícitamente.
3. ¿Tiene permiso de **Send Messages** y **Embed Links** en ese canal? Los
   permisos del canal pueden estar por encima de los del servidor.

### Los mensajes de Discord no llegan al juego

Revisa `mc logs`. Si dice algo de intents, revisa que NO tengas prendidos los
privilegiados (DiscordSRV no los usa).

### Todos los mensajes salen con el nombre del bot

Le falta el permiso **Manage Webhooks**. Vuelve a generar la URL de invitación
con ese permiso y reinvítalo.

### Quiero que el bot deje de avisar

En `settings.yml`:

```yaml
discord:
  activo: false
```

Y `mc build && mc restart`.
