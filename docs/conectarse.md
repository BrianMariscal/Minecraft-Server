# Cómo entrar al servidor

La dirección y el puerto cambian según en qué juegues.

| Juegas en | Dirección | Puerto |
|---|---|---|
| **Java** (PC) | `tu-direccion.com` | `25565` |
| **Bedrock** (celular, tablet, Windows 10/11, consola) | `tu-direccion.com` | `19132` |

Cambia `tu-direccion.com` por la de tu servidor (ve `docs/vps.md` si todavía
no tienes una).

---

## Antes de nada: pide que te agreguen

El servidor tiene whitelist. Si no estás en la lista, te saca con este
mensaje:

> Todavía no estás en la lista. Pídele a un admin que te agregue.

Dile a un admin tu nombre:

- **Si juegas en Java**, tu nombre de Minecraft tal cual.
- **Si juegas en Bedrock**, tu **gamertag de Xbox**.

---

## Lo primero que pasa al entrar (en cualquier plataforma)

El servidor es no premium, o sea que Mojang no verifica a nadie. Tu personaje
es tuyo porque tienes una contraseña.

**La primera vez** te sale una ventanita que dice **"Registrarte"**: escribe
una contraseña, repítela y dale a **Registrarme**. **Apúntatela**: si se te
olvida, un admin tiene que borrar tu registro y empiezas de nuevo.

**Las siguientes veces** sale la ventanita **"Entrar"**: tu contraseña y
listo.

Si por alguna razón no te sale la ventanita (versiones viejas de Minecraft),
el chat te dice qué escribir:

```
/register tuContraseña tuContraseña     ← la primera vez
/login tuContraseña                     ← las demás
```

Hasta que no entres, no puedes moverte, hablar ni abrir tu inventario. Es a
propósito: así nadie puede entrar con tu nombre y llevarse tus cosas.

Si se te cae el internet y vuelves en menos de 10 minutos, no tienes que
escribir la contraseña otra vez.

---

## Java (PC)

1. Abre Minecraft. Tiene que ser la versión **26.1.2**.
2. **Multijugador** → **Añadir servidor**.
3. Nombre: lo que quieras. Dirección: `tu-direccion.com`
4. Entra.

Si el servidor tiene registro SRV, no hace falta poner `:25565`. Si no,
escribe `tu-direccion.com:25565`.

### Si tu Minecraft es más nuevo

El servidor trae **ViaVersion**, así que aguanta clientes un poco más nuevos
que 26.1.2. Si de todas formas te rechaza, cambia tu versión a 26.1.2 desde
el launcher (Instalaciones → Nueva → escoge 26.1.2).

---

## Bedrock en celular o tablet

1. Abre Minecraft.
2. **Jugar** → pestaña **Servidores** → baja hasta el final →
   **Añadir servidor**.
3. Llena:
   - **Nombre del servidor:** Minecraft HD
   - **Dirección del servidor:** `tu-direccion.com`
   - **Puerto:** `19132`
4. **Guardar** y entra.

### Para escribir comandos en celular

Pícale al **icono del chat** (el bocadillo de arriba) y escribe el comando
con su diagonal, igual que en PC:

```
/register miClave123 miClave123
```

### Si te sale "No se pudo conectar al mundo"

Lo más común, en orden:

1. **El puerto.** Tiene que ser `19132`, no `25565`.
2. **La red.** Prueba con datos móviles en lugar de wifi; algunos módems de
   casa bloquean UDP.
3. **No estás en la whitelist.** Pide que te agreguen con tu gamertag.

---

## Bedrock en Windows 10/11

Igual que en celular: **Jugar** → **Servidores** → **Añadir servidor**, con
el puerto `19132`.

---

## Consolas: Xbox, PlayStation y Switch

Las consolas **no dejan escribir una dirección de servidor**. Sony,
Microsoft y Nintendo solo permiten sus servidores destacados.

La vuelta es **BedrockConnect**: cambias el DNS de la consola y entonces la
lista de servidores destacados se reemplaza por una donde sí puedes escribir
tu dirección.

### Los DNS de BedrockConnect

Usa uno de estos (si el primero no jala, prueba el otro):

```
104.238.130.180
172.93.102.100
```

### Xbox One / Series X|S

1. **Configuración** → **General** → **Configuración de red**
2. **Configuración avanzada** → **Configuración de DNS** → **Manual**
3. **DNS principal:** `104.238.130.180`
4. **DNS secundario:** `8.8.8.8`
5. Guarda y acepta reiniciar la red.
6. Abre Minecraft → **Jugar** → **Servidores**.
7. Entra a **cualquier** servidor destacado (Lifeboat, Mineplex, el que sea).
   En lugar de ese servidor te va a salir el menú de BedrockConnect.
8. **Connect to a Server** → escribe `tu-direccion.com` y el puerto `19132`.

### PlayStation 4 / 5

1. **Ajustes** → **Red** → **Configurar conexión a Internet**
2. Escoge tu conexión (wifi o cable) → **Personalizada**
3. Deja todo en automático **menos el DNS**: ponlo en **Manual**
4. **DNS primario:** `104.238.130.180`
5. **DNS secundario:** `8.8.8.8`
6. El resto en automático, y guarda.
7. Minecraft → **Servidores** → entra a cualquiera → te sale
   BedrockConnect → **Connect to a Server**.

### Nintendo Switch

1. **Configuración de la consola** → **Internet** → **Configuración de
   Internet**
2. Escoge tu red → **Cambiar configuración**
3. **Configuración de DNS** → **Manual**
4. **DNS primario:** `104.238.130.180`
5. **DNS secundario:** `8.8.8.8`
6. Guarda y conéctate.
7. Minecraft → **Servidores** → entra a cualquiera → BedrockConnect.

### Cosas que saber de BedrockConnect

- **No lo hacemos nosotros.** Es un servicio de terceros, gratis. Si un día
  deja de funcionar, no es tu configuración.
- **Deja el DNS puesto.** No hay que cambiarlo cada vez.
- **Si la consola deja de navegar**, regresa el DNS a automático. Es lo
  primero que hay que probar si algo de la red falla.
- La primera vez que entras a BedrockConnect tarda un poco. Es normal.

---

## Si juegas en Java Y en Bedrock

Puedes tener **el mismo personaje** en los dos: el mismo inventario, las
mismas casas, la misma XP.

Ve a **[docs/vincular-cuentas.md](vincular-cuentas.md)**.

---

## Lo que puedes hacer ya dentro

| Comando | Qué hace |
|---|---|
| `/sethome` | Guarda tu casa aquí |
| `/home` | Te lleva a tu casa |
| `/sethome cueva` | Guarda otro lugar con nombre (puedes tener 5) |
| `/home cueva` | Te lleva ahí |
| `/spawn` | Te lleva al spawn |
| `/back` | Te regresa a donde estabas, **incluido donde te moriste** |
| `/tpa Pepe` | Le pides a Pepe que te deje teletransportarte con él |
| `/tpaccept` | Aceptas que alguien venga contigo |
| `/msg Pepe hola` | Mensaje privado |
| `/r hola` | Le contestas al último que te escribió |
| `/skin Notch` | Te pones la skin de otro nombre |
| `/linkaccount` | Vinculas tus cuentas de Java y Bedrock |

### Cosas que tiene el servidor

- **Tumbas.** Al morir tus cosas y tu XP se quedan en una tumba con tu
  cabeza. Dura **1 hora** y **cualquiera puede abrirla**, así que si un
  amigo llega antes, te las puede guardar.
- **Dormir solo.** Con que **una** persona se duerma, amanece.
- **Talar de un golpe.** Rompes un tronco y se cae el árbol completo.
- **Sentarse.** Clic derecho en escalones, losas y alfombras (con la mano
  vacía).
- **Cabezas de mobs.** Los mobs sueltan su cabeza al morir.
- **Mundo más bonito.** Terralith, Incendium y Nullscape cambian los biomas,
  el Nether y el End. Dungeons and Taverns y Towns and Towers agregan
  estructuras y aldeas.
- **No hay protección de terrenos.** Compartimos todo. Hay registro de quién
  movió qué, así que si alguien se pasa de listo, se revierte.
