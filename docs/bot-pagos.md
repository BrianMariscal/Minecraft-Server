# El bot que cobra el VPS

Este bot le recuerda a la banda que toca pagar el VPS, lleva la cuenta de
quién ya pagó y avisa cuando ya está cubierto.

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
# Opcional, ver "Alertas de caída del servidor":
ALERTAS_CANAL_ID=
```

### En `settings.yml` (solo para el primer arranque)

La sección `pagos` de `settings.yml` es el **punto de partida**: la primera
vez que arranca, el bot la copia a su base de datos. **De ahí en adelante
todo se cambia desde Discord** (`/miembro` y `/ajustes`, más abajo) y
`settings.yml` ya no se vuelve a leer para esto. Solo `activo` y
`zona_horaria` siguen saliendo de ahí.

Así se ve:

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

### Lo que se queda debiendo no se olvida

Si octubre se cierra con alguien sin pagar, al cambiar a noviembre esa
deuda **sigue ahí**:

- `/pagos` la enseña en "⏳ Pendiente de meses anteriores".
- El recordatorio tardío de octubre sigue saliendo cada `cada_dias_despues`
  días, mencionando solo a quien falta, hasta que se pague o el tesorero lo
  exima (`/eximir @persona mes:2026-10`).

### Marcar que ya pagaste

Dos formas:

- **El botón "💸 Ya pagué"** que viene pegado a cada aviso.
- **El comando `/pague`**.

Cualquiera de las dos te pone en **🕓 por confirmar** y le avisa al tesorero.

El pago se anota en el **mes más viejo que debas**: primero se salda lo
atrasado. Si ya estás al corriente y el aviso previo del mes que viene ya
salió (con `dia_de_pago: 2` sale el 30 del mes anterior), cuenta como pago
**adelantado** de ese mes.

Si ya avisaste y el tesorero todavía no confirma, picarle otra vez no lo
vuelve a etiquetar: el bot solo te avisa de que sigue pendiente.

### Confirmar

El tesorero (o quien tenga el rol configurado) confirma con:

- **El botón "✅ Sí me llegó"**, que sigue funcionando aunque el bot se
  haya reiniciado (los botones de antes de la versión 1.1 no: esos te
  piden usar `/confirmar`).
- **`/confirmar @persona`**, que confirma lo más viejo que esa persona
  tenga pendiente. Para un mes en concreto: `/confirmar @persona mes:2026-10`.

Hasta que no se confirma, ese dinero **no cuenta como juntado**. Es a
propósito: si el tesorero no lo vio, el dinero no está.

---

## Los comandos

### Para todos

| Comando | Qué hace |
|---|---|
| `/pagos` | La tarjeta del mes: quién pagó, quién falta, cuánto se juntó y lo atrasado |
| `/pague` | Avisas que ya pagaste tu parte (igual que el botón "💸 Ya pagué") |
| `/historial` | Los meses anteriores y quién quedó debiendo |

### Para el tesorero (o el rol de admin del cobro)

**Pagos**

| Comando | Qué hace |
|---|---|
| `/confirmar @persona [mes]` | Te llegó su pago (sin `mes`: lo más viejo que deba) |
| `/desmarcar @persona [mes]` | La regresas a pendiente (se equivocó, se devolvió el pago) |
| `/eximir @persona [mes]` | Ese mes no le toca pagar, y no cuenta como que debe |
| `/auditoria [cuantos]` | Los últimos movimientos del cobro: quién confirmó, desmarcó, eximió o cambió un ajuste |

`mes` se escribe como `2026-10`. Si no lo pones, `/desmarcar` y `/eximir`
usan el mes actual.

**La banda** — `/miembro`

| Comando | Qué hace |
|---|---|
| `/miembro agregar @persona [monto] [nombre]` | La mete a la banda. Entra al cobro de **este** mes |
| `/miembro quitar @persona` | La saca. Si ya pagó este mes, se respeta; si no, este mes ya no se le cobra |
| `/miembro monto @persona monto [este_mes]` | Cambia lo que paga. Por defecto desde el mes que viene |
| `/miembro nombre @persona nombre` | Cómo aparece en las listas |

**Cómo se cobra** — `/ajustes`

| Comando | Qué hace |
|---|---|
| `/ajustes ver` | Toda la configuración y la lista de la banda, en una tarjeta |
| `/ajustes dia 2` | El día del mes en que se paga (si el mes es corto, el último día) |
| `/ajustes total 240` | Cuánto cuesta el VPS |
| `/ajustes reparto iguales\|personalizado` | El total dividido entre todos, o cada quien su monto |
| `/ajustes avisos 3 2` | Avisar 3 días antes, y si se pasa la fecha, cada 2 días |
| `/ajustes hora 11` | A qué hora salen los recordatorios |
| `/ajustes tesorero @persona` | Quién recibe el dinero y confirma |
| `/ajustes rol @rol` | Un rol que también puede administrar (vacío = solo el tesorero) |

Los montos se escriben como quieras: `40`, `40.50`, `$40,50`.

**¿Quién ve estos comandos?** Discord los esconde a quien no tiene el
permiso de *Gestionar servidor*. Si el tesorero no lo tiene, dáselo a ese
comando en **Ajustes del servidor → Integraciones → (el bot) → Comandos**.
Aparte de eso, el bot revisa siempre que quien los usa sea el tesorero o
tenga el rol de admin del cobro: aunque alguien los vea, no los puede usar.

---

## Alertas de caída del servidor (opcional)

El mismo bot puede avisar en Discord si el servidor de Minecraft se cae.
Pon el ID de un canal en `.env` (puede ser el mismo `#pagos`, o uno de
admins):

```bash
ALERTAS_CANAL_ID=1234567890123456789
```

Y `mc restart`. Cada minuto revisa si el servidor contesta. Si lleva **5
minutos** sin contestar avisa una vez, y cuando vuelve avisa otra. No avisa
mientras el servidor está arrancando (por ejemplo después de un `mc
restart`), solo si se cae después de haber estado arriba.

Necesita que el bot de pagos esté prendido (`pagos.activo: true`).

---

## Cambiar cosas

Todo desde Discord, sin tocar archivos ni reiniciar nada. Revisa cómo
quedó con `/ajustes ver`.

| Quieres… | Escribe |
|---|---|
| Meter a alguien | `/miembro agregar @Pepe 40` |
| Sacar a alguien | `/miembro quitar @Pepe` |
| Que alguien pague otra cantidad | `/miembro monto @Pepe 50` (o con `este_mes: True`) |
| Que alguien no pague un mes | `/eximir @Pepe` |
| Cambiar el día de pago | `/ajustes dia 5` |
| Cambiar lo que cuesta el VPS | `/ajustes total 300` |
| Avisar antes o más seguido | `/ajustes avisos 5 1` |
| Cambiar de tesorero | `/ajustes tesorero @Tesorero` |

### Revisar quién movió qué

Cada confirmación, desmarque, exención, alta o cambio de ajuste se guarda en
una tabla de **solo agregar** (`auditoria`). `/auditoria` enseña los últimos
movimientos con la fecha, quién los hizo, el mes y los valores del cambio.
No se editan ni se borran: si alguien confirma un pago por error, queda el
movimiento y después el contrario (`/desmarcar`), no un hueco. El bot también
apunta lo que hace solo, como actualizar el precio de los meses abiertos, con
el actor `sistema`.

### Que deje de cobrar

En `settings.yml`:

```yaml
pagos:
  activo: false
```

Y `mc build && mc restart`. El contenedor del bot ya no arranca.

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
- **Los botones sobreviven los reinicios.** Cada botón lleva en su
  identificador lo que necesita (el de "Sí me llegó", de quién y de qué mes
  es el pago), así que el de un mensaje de hace una semana sigue jalando.
- **La configuración vive en la base de datos**, en la tabla `ajustes`. Cada
  cambio desde Discord se valida completo antes de guardarse: si el
  resultado no tiene sentido, no se guarda nada.
- **Los mensajes son tarjetas** con el diseño nuevo de Discord (contenedor
  con franja de color, separadores y los botones adentro). El texto está en
  `discord_ui/textos.py` y el acomodo en `discord_ui/tarjetas.py`.
- **Si Discord o la base de datos fallan, el bot sigue vivo.** Lo anota en el
  log y vuelve a intentar: un bot caído no le cobra a nadie.
- **La base de datos es SQLite** en un volumen, y **entra en los respaldos**
  automáticos junto con el mundo.
- **El libro de movimientos solo crece.** La tabla `auditoria` no tiene
  `UPDATE` ni `DELETE`: cada acción del tesorero o del bot deja un renglón con
  actor, fecha, mes y detalle. Así se puede reconstruir qué pasó sin depender
  de los logs del contenedor, que se rotan.

---

## Si algo no jala

### "faltan variables de entorno"

```
ERROR pagos: no puedo arrancar:
faltan variables de entorno: PAGOS_BOT_TOKEN, PAGOS_GUILD_ID, PAGOS_CANAL_ID.
```

Corre `mc setup`, llénalas, y `mc build && mc restart`.

### "Discord rechazó el token"

El token está mal: vuelve a copiarlo del Developer Portal (Bot > Reset Token).
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
