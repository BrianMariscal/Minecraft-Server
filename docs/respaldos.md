# Respaldos

Hay dos formas de respaldar, y las dos están puestas:

1. **Automática**, cada 6 horas, sin apagar el servidor. Es la que trabaja
   sola.
2. **A mano**, con `mc backup now`, para antes de tocar algo.

---

## Los automáticos

Los hace el contenedor `respaldos` (`itzg/mc-backup`) y no hay que hacer
nada.

| | |
|---|---|
| Cada cuándo | **6 horas** |
| Se conservan | **7 días** |
| Dónde | `backups/` |
| ¿Apaga el servidor? | **No** |
| Si no hay nadie conectado | Se salta el respaldo (no tiene caso repetir lo mismo) |

Se cambian en `settings.yml`:

```yaml
respaldos:
  intervalo: "6h"
  conservar_dias: 7
```

### Cómo respalda sin apagar nada

1. Le dice al servidor `save-off`: deja de escribir al disco.
2. `save-all flush`: guarda lo que trae en memoria.
3. Copia los archivos, que en ese momento están quietos.
4. `save-on`: el servidor sigue normal.

Nadie se desconecta y nadie pierde nada.

### Qué entra en el respaldo

- El mundo completo (`world`, `world_nether`, `world_the_end`), con los
  datapacks.
- Las configs de todos los plugins.
- Las bases de datos: CoreProtect, AuthMe, LuckPerms y la vinculación de
  cuentas de Floodgate.
- La base de datos del **bot de pagos** (`pagos-datos/`), más una foto que
  el bot saca cada hora con la API de SQLite. Si la base principal de un
  respaldo saliera dañada, `mc backup restore` usa la foto.
- El `settings.yml` con el que se hizo.

### Qué NO entra, y por qué

Los jars de los plugins, `cache/`, `logs/`, `libraries/`, y
`versions/`.

Todo eso **se regenera solo** con `mc build` y pesa muchísimo. Un respaldo
que también guarda 110 MB de jars es un respaldo que vas a borrar por falta
de espacio justo cuando lo necesites.

---

## A mano

```bash
mc backup now
```

Hazlo **antes** de:

- Actualizar un plugin
- Cambiar algo grande en `settings.yml`
- Un `mc world reset`
- Un rollback grande de CoreProtect

`mc world reset` y `mc backup restore` ya hacen uno solos antes de tocar
nada, pero uno extra no sobra.

---

## Ver los que hay

```bash
mc backup list
```

```
                  Respaldos
  id                Cuándo                           Tamaño
  20260930-180000   30 de septiembre 2026, 18:00     1.2 GB
  20260930-120000   30 de septiembre 2026, 12:00     1.2 GB
  20260930-060000   30 de septiembre 2026, 06:00     1.1 GB

  3 respaldo(s), se conservan 7 días.
  Restaurar: mc backup restore 20260930-180000  (o `ultimo`)
```

---

## Restaurar

```bash
mc backup restore ultimo --dry-run   # primero mira qué trae
mc backup restore ultimo
```

Acepta varias formas de decir cuál:

```bash
mc backup restore ultimo             # el más reciente
mc backup restore 20260930-180000    # el id completo
mc backup restore 20260930           # un prefijo, si no es ambiguo
```

Lo que hace, en orden:

1. Te dice **qué respaldo es, de cuándo y cuánto pesa**.
2. Te pide **doble confirmación**: un sí/no y luego teclear `RESTAURAR`.
3. Hace un **respaldo de lo que hay ahora** (por si te arrepientes).
4. Apaga el servidor.
5. Borra los mundos de ahorita y extrae los del respaldo.
6. Te dice dónde quedó el respaldo de antes.

Luego:

```bash
mc start
```

### `settings.yml` no se restaura solo

El respaldo lo trae adentro, pero **no se escribe encima del tuyo**. Si
cambiaste la configuración a propósito, pisártela sin avisar sería una
grosería.

Si lo quieres de vuelta, sácalo a mano:

```bash
tar xzf backups/world-20260930-180000.tgz settings.yml -O > settings-del-respaldo.yml
diff settings.yml settings-del-respaldo.yml
```

### La base de datos del bot de pagos sí se restaura

Esa sí, junto con el mundo: si restauras, lo coherente es que las cuentas del
mes también regresen a ese punto.

---

## Una copia fuera del VPS

Un respaldo que vive en el mismo disco que el servidor **no es un respaldo**:
si el VPS se muere, se van los dos.

Esto viene **apagado** por defecto porque necesita que configures una cuenta.

### 1. Instalar rclone en el VPS

```bash
curl https://rclone.org/install.sh | sudo bash
```

### 2. Configurarlo

```bash
rclone config
```

Es un menú interactivo. Para Google Drive:

1. `n` (new remote)
2. Nombre: `gdrive`
3. Escoge `drive` de la lista
4. Deja client_id y client_secret vacíos (dale Enter)
5. Scope: `1` (acceso completo)
6. Lo demás en blanco
7. **`Use web browser to automatically authenticate? → n`** ← importante en
   un VPS sin navegador
8. Te da un comando para correr **en tu computadora**. Córrelo, te abre el
   navegador, autorizas, y te da un token.
9. Pega el token en el VPS.

Para Backblaze B2 es más simple: escoge `b2` y pon tu Key ID y Application
Key.

### 3. Probar que jala

```bash
rclone lsd gdrive:
rclone mkdir gdrive:minecraft-hd
```

### 4. Prenderlo

En `settings.yml`:

```yaml
respaldos:
  remoto:
    activo: true
    destino: "gdrive:minecraft-hd"
```

    intervalo: "24h"      # cada cuándo sube una copia
```

Y:

```bash
mc build      # revisa que exista ~/.config/rclone/rclone.conf
mc restart
```

`mc build` parte el destino en remoto (`gdrive`) y carpeta (`minecraft-hd`)
y prende un contenedor aparte, `respaldos-remoto`, que lee el
`rclone.conf` de tu usuario en el VPS. No hay nada que poner en `.env`.

Los respaldos locales en `backups/` siguen igual: el remoto es **además**,
no en vez de.

### 5. Comprobar

```bash
mc status                     # debe salir respaldos-remoto corriendo
mc logs -s respaldos-remoto   # el primero sale a los 2 minutos de arrancar
rclone ls gdrive:minecraft-hd
```

Si en el log ves que rclone no encuentra el remoto, revisa que el nombre
antes de los dos puntos en `destino` sea exactamente el que le pusiste en
`rclone config` (`rclone listremotes` te los dice).

---

## Si algo no jala

### "no hay carpeta data/ que respaldar"

Corre `mc build` primero.

### El respaldo pesa muchísimo

Lo normal es 1–3 GB con el mundo pregenerado. Si pesa mucho más:

```bash
du -sh data/*  | sort -h | tail -5
```

Si ves algo grande que se regenera solo, agrégalo a `EXCLUDES` en el
`docker-compose.yml`.

### No quedan respaldos de hace días

Revisa `conservar_dias` en `settings.yml`, y que el contenedor esté arriba:

```bash
mc status
mc logs -s respaldos
```

### "¡OJO! No pude volver a prender el guardado automático"

Esto sale si `mc backup now` falló justo después del `save-off`. El servidor
quedó sin guardar al disco. Arréglalo ya:

```bash
mc console
mc> save-on
mc> save-all
```

### Quiero más margen

```yaml
respaldos:
  intervalo: "3h"        # cada 3 horas
  conservar_dias: 14     # dos semanas
```

Ojo con el disco: el doble de respaldos, el doble de espacio. `mc doctor` te
avisa si se está llenando.
