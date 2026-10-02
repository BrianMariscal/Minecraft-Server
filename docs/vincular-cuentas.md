# Tener el mismo personaje en Java y en Bedrock

Si juegas en PC y también en el celular, por defecto serías **dos jugadores
distintos**: dos inventarios, dos casas, dos niveles de XP.

Vincular las cuentas los junta en uno. Entras desde donde quieras y es
siempre el mismo personaje.

Esto lo hace **Floodgate**, y en este servidor la vinculación es **local**:
los datos se quedan en una base de datos del VPS, no se van a ningún servicio
de afuera.

---

## Antes de empezar

Las dos cuentas tienen que:

1. **Estar en la whitelist.** Pídele al admin que te agregue las dos:
   ```
   mc whitelist add TuNombreDeJava
   mc whitelist add TuGamertag --bedrock
   ```
2. **Estar registradas con `/register`.** Entra una vez desde cada lado y
   regístrate. Pueden tener contraseñas distintas, da igual.

---

## Cómo se vincula

Son dos pasos y hay **5 minutos** para hacerlos.

### Paso 1: desde la cuenta que quieres CONSERVAR

Decide cuál personaje te quedas: el de Java o el de Bedrock. **El otro se va
a perder**, con todo lo que tenga.

Casi siempre quieres conservar el de Java (es donde más se juega), así que
entra en Java y escribe:

```
/linkaccount TuGamertagDeBedrock
```

El servidor te contesta con un **código de 4 dígitos**. Algo así:

```
Para terminar de vincular, entra desde Bedrock y escribe:
/linkaccount TuNombreDeJava 1234
```

### Paso 2: desde la otra cuenta

Sin cerrar nada, entra desde Bedrock (celular, consola, lo que sea) y
escribe lo que te dijo, con el código:

```
/linkaccount TuNombreDeJava 1234
```

Listo. El servidor te saca para aplicar el cambio.

### Paso 3: vuelve a entrar

Vuelve a entrar desde cualquiera de los dos. Vas a aparecer con el personaje
que conservaste, con sus cosas, sus casas y su XP.

---

## Un ejemplo completo

Ana juega en PC como `Admin_HD` y en el celular con el gamertag
`BedrockUser`. Quiere conservar su personaje de PC.

```
# 1. Entra en PC (Java) y escribe:
/linkaccount BedrockUser

# El servidor contesta con el código: 7391

# 2. Entra en el celular (Bedrock) y escribe:
/linkaccount Admin_HD 7391

# 3. Lo saca. Vuelve a entrar y ya es el mismo personaje.
```

---

## Desvincular

```
/unlinkaccount
```

Desde cualquiera de las dos. Vuelven a ser personajes separados, pero **el
que se había perdido no regresa**.

---

## Dudas comunes

**¿Pierdo mis cosas?**
Sí, las de la cuenta que NO conservas. Antes de vincular, pásale lo que
quieras salvar a un cofre y luego recógelo con el personaje bueno.

**¿Necesito Minecraft de paga en las dos?**
No. El servidor es no premium.

**¿Y las skins?**
Cada cliente usa la suya: en Bedrock la que tengas puesta, en Java la de
SkinsRestorer (`/skin TuNombre`). La skin no se vincula, el personaje sí.

**¿Desde consola también?**
Sí. Entra como dice [docs/conectarse.md](conectarse.md) y escribe el comando
en el chat.

**¿Se me acabaron los 5 minutos?**
Empieza otra vez con el paso 1. Te da un código nuevo.

**¿Me da error "ya estás vinculado"?**
Haz `/unlinkaccount` primero.

---

## Para el admin: cómo está montado

- **Floodgate 2.2.5** con `enable-own-linking: true`.
- La base de datos es **SQLite**, en un archivo del volumen del servidor, así
  que entra en los respaldos automáticos.
- El vínculo **global** de GeyserMC está **apagado** a propósito: funciona sin
  internet hacia GeyserMC y los datos no salen del VPS.
- Para que esto no truene, `mc build` instala
  `floodgate-sqlite-database.jar` en `plugins/floodgate/`. **Sin ese jar,
  Floodgate no arranca** (da un `CreationException` de Guice al cargar).
- La carpeta `plugins/floodgate/` tiene que ser escribible por el usuario del
  contenedor. Si ves un `AccessDeniedException: plugins/floodgate/config.yml`
  en el log, es eso:
  ```bash
  sudo chown -R $USER:$USER data
  ```
  Y revisa que `UID` y `GID` en `.env` sean los tuyos (`id -u`, `id -g`).
