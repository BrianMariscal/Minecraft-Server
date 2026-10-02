# El bot que cobra el VPS

Este bot le recuerda a la banda que toca pagar el VPS, lleva la cuenta de
quién ya pagó y avisa cuando ya está cubierto.

**Es un bot DISTINTO al de DiscordSRV.** Necesita su propia aplicación en
Discord y su propio token. Si usas el mismo, ninguno de los dos funciona
bien.

---

## 1. Crear la aplicación

1. **[discord.com/developers/applications](https://discord.com/developers/applications)**
2. **New Application**
3. Nombre: `Pagos VPS` (o lo que quieras)
4. **Create**

## 2. Convertirla en bot y sacar el token

1. Menú izquierdo: **Bot**
2. Ponle un nombre, por ejemplo `Cobrador`
3. **Reset Token** → confirma → **copia el token**

> No lo pegues en Discord ni lo subas a git. Si se te sale, **Reset Token** y
> el viejo deja de servir.

### Intents

Este bot tampoco necesita ninguno de los **Privileged Gateway Intents**.
Déjalos apagados: funciona solo con comandos slash y botones.

## 3. Invitarlo

1. **OAuth2** → **URL Generator**
2. **Scopes:**
   - ✅ `bot`
   - ✅ `applications.commands` ← **este sí hace falta**, es lo que permite
     los comandos con `/`
3. **Bot Permissions:**
   - ✅ View Channels
   - ✅ Send Messages
   - ✅ Embed Links
   - ✅ Read Message History
4. Copia la **GENERATED URL**, ábrela y escoge tu servidor.

## 4. Sacar los tres IDs

Prende el modo desarrollador: **Ajustes de usuario** → **Avanzado** →
**Modo desarrollador**.

| Qué | Cómo |
|---|---|
| **ID del servidor** | Clic derecho en el nombre del servidor (arriba a la izquierda) → **Copiar ID del servidor** |
| **ID del canal #pagos** | Crea un canal `#pagos` → clic derecho → **Copiar ID del canal** |
| **ID de cada persona** | Clic derecho en su nombre o su avatar → **Copiar ID de usuario** |

Pídele a cada quien su ID, o saca el tuyo y los de ellos desde la lista de
miembros.

## 5. Llenar los datos

### En `.env`

```bash
mc setup
```

O a mano:

```bash
PAGOS_BOT_TOKEN=el-token-de-ESTE-bot
PAGOS_GUILD_ID=1234567890123456789
PAGOS_CANAL_ID=9876543210987654321
```

### En `settings.yml`

Esta es la parte que **hay que llenar a mano**, porque son los datos de tu
banda. Busca la sección `pagos`:

```yaml
pagos:
  activo: true
  zona_horaria: "America/Mexico_City"

  # Día del mes en que se paga el VPS.
  dia_de_pago: 5

  # Lo que cuesta el VPS en total, al mes, en pesos.
  monto_total_mxn: "450.00"

  # "iguales" divide el total entre todos.
  # "personalizado" usa el monto_mxn de cada quien.
  reparto: "iguales"

  participantes:
    - nombre: "Ana"
      discord_id: 111111111111111111
    - nombre: "Pepe"
      discord_id: 222222222222222222
    - nombre: "Lupita"
      discord_id: 333333333333333333
    - nombre: "Juan"
      discord_id: 444444444444444444

  # Quién paga el VPS y confirma los pagos de los demás.
  tesorero:
    nombre: "Ana"
    discord_id: 111111111111111111

  # Rol de Discord que también puede confirmar pagos.
  # Déjalo en 0 si solo el tesorero debe poder.
  rol_admin_id: 0

  avisos:
    dias_antes: 3          # el primer aviso, 3 días antes
    cada_dias_despues: 2   # después de la fecha, recordar cada 2 días
```

**El `discord_id` va sin comillas**: es un número, no texto.

### Arrancarlo

```bash
mc build
mc restart
```

En `mc logs -s pagos-bot` deberías ver `conectado como Cobrador#1234`.

---

## Cómo funciona

### El mes arranca solo

El día 1 de cada mes, el bot abre un periodo nuevo con todos en pendiente.
Nadie tiene que acordarse de nada.

### Los avisos

Con `dia_de_pago: 5`, `dias_antes: 3` y `cada_dias_despues: 2`:

| Día | Qué manda | A quién menciona |
|---|---|---|
| **2** | "El VPS se paga el 5 de octubre, o sea en 3 días. Tocan $112.50 por cabeza." | A nadie: todavía no deben nada |
| **5** | "Hoy 5 de octubre se paga el VPS." | Solo a los que faltan |
| **7, 9, 11...** | "Ya pasaron 2 días del 5 de octubre y todavía falta gente." | Solo a los que faltan |

Los avisos salen a las **11 de la mañana**, hora de México.

Cuando todos pagan, el bot manda:

> Listo, ya está cubierto el VPS de octubre de 2026. Gracias, banda. 🫡

Y deja de molestar hasta el mes que entra.

### Marcar que ya pagaste

Dos formas:

- **El botón "💸 Ya pagué"** que viene pegado a cada aviso.
- **El comando `/pague`**.

Cualquiera de las dos te pone en **🕓 por confirmar** y le avisa al tesorero.

### Confirmar

El tesorero (o quien tenga el rol configurado) confirma con:

- **El botón "✅ Sí me llegó"**
- **`/confirmar @persona`**

Hasta que no se confirma, ese dinero **no cuenta como juntado**. Es a
propósito: si el tesorero no lo vio, el dinero no está.

---

## Los comandos

### Para todos

| Comando | Qué hace |
|---|---|
| `/pagos` | Cómo va el mes: quién pagó, quién falta, cuánto se juntó |
| `/pague` | Avisas que ya pagaste tu parte |
| `/historial` | Los meses anteriores y quién pagó cada uno |

### Solo para el tesorero

| Comando | Qué hace |
|---|---|
| `/confirmar @persona` | Confirmas que te llegó su pago |
| `/desmarcar @persona` | La regresas a pendiente (se equivocó, se devolvió el pago) |
| `/eximir @persona` | Este mes no le toca pagar, y no cuenta como que debe |

---

## Cambiar cosas

Todo se cambia en `settings.yml` y luego:

```bash
mc build && mc restart
```

### Cambiar el monto del VPS

```yaml
monto_total_mxn: "520.00"
```

El mes que **ya está abierto** no se recalcula: eso descuadraría lo que ya
pagaron. El monto nuevo aplica desde el mes siguiente.

### Agregar a alguien

Agrégalo a `participantes`. Si el mes ya está corriendo, el bot lo mete al
mes en curso con su cuota.

### Quitar a alguien

Quítalo de `participantes`. **Del mes que ya está corriendo NO se borra**: si
ya pagó, ese dinero cuenta, y borrarlo descuadraría el total. Desde el mes
siguiente ya no aparece.

Si lo que quieres es que no pague **este** mes, usa `/eximir @persona`.

### Cambiar el día de pago

```yaml
dia_de_pago: 15
```

Si pones **31** y el mes tiene 30, el bot usa el **último día del mes**. En
febrero usa el 28 (o el 29 si es bisiesto). Eso ya está resuelto.

### Montos distintos por persona

```yaml
reparto: "personalizado"
participantes:
  - nombre: "Ana"
    discord_id: 111111111111111111
    monto_mxn: "200.00"
  - nombre: "Pepe"
    discord_id: 222222222222222222
    monto_mxn: "125.00"
  - nombre: "Lupita"
    discord_id: 333333333333333333
    monto_mxn: "125.00"
```

Con `personalizado`, **cada participante necesita su `monto_mxn`**. Si a
alguien le falta, el bot no arranca y te dice a quién.

### Cambiar los avisos

```yaml
avisos:
  dias_antes: 5          # avisa 5 días antes
  cada_dias_despues: 3   # después de la fecha, cada 3 días
```

### Que deje de cobrar

```yaml
pagos:
  activo: false
```

---

## Cómo está hecho (para quien le interese)

- **El dinero se guarda en centavos como entero.** Nunca en `float`: un float
  no puede representar 0.10 exacto y después de sumar quince veces te sobran
  o te faltan centavos.
- **El reparto no pierde centavos.** $100 entre 3 no da tres de $33.33 (eso
  suma $99.99): da $33.34, $33.33 y $33.33. La suma **siempre** da el total.
- **Los recordatorios no se repiten.** Antes de mandar un aviso, el bot
  revisa en su base de datos si ya mandó ese mismo aviso hoy. Si el VPS se
  reinicia tres veces el día de pago, el aviso sale **una** vez.
- **Los botones sobreviven los reinicios.** Son vistas persistentes, así que
  el botón de un mensaje de hace una semana sigue funcionando.
- **Si Discord o la base de datos fallan, el bot sigue vivo.** Lo anota en el
  log y vuelve a intentar: un bot caído no le cobra a nadie.
- **La base de datos es SQLite** en un volumen, y **entra en los respaldos**
  automáticos junto con el mundo.

---

## Si algo no jala

### "faltan variables de entorno"

```
ERROR pagos: no puedo arrancar:
faltan variables de entorno: PAGOS_BOT_TOKEN, PAGOS_GUILD_ID, PAGOS_CANAL_ID.
```

Corre `mc setup`, llénalas, y `mc build && mc restart`.

### "Discord rechazó el token"

El token está mal, o estás usando el de DiscordSRV. Son bots distintos.
Saca el token de la aplicación de **este** bot (**Reset Token**).

### "la sección pagos de settings.yml todavía trae CAMBIAME"

Falta llenar los participantes y el tesorero. Ve la sección 5 de arriba.

### Los comandos `/pagos` no aparecen en Discord

1. ¿Invitaste el bot con el scope **`applications.commands`**? Si no, vuelve
   a generar la URL con ese scope marcado y reinvítalo.
2. ¿El `PAGOS_GUILD_ID` es el correcto? El bot registra los comandos solo en
   ese servidor, para que aparezcan al instante.
3. Reinícialo: `mc restart`.

### El bot no manda los avisos

1. ¿El `PAGOS_CANAL_ID` es el correcto?
2. ¿El bot puede ver y escribir en ese canal? Si es privado, hay que darle
   acceso.
3. Los avisos salen a las 11 AM, hora de México. Revisa `mc logs -s pagos-bot`.

### Quiero ver cómo va sin esperar al aviso

```
/pagos
```

Desde cualquier canal donde esté el bot.
