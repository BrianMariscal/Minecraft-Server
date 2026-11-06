# El logo del servidor

Pon aquí tu imagen con el nombre **`logo.png`**:

```
logo/logo.png
```

Es el iconito que aparece junto al nombre del servidor en la lista de
Minecraft, al lado del MOTD.

## Qué imagen funciona

- **Cuadrada.** Si no, se va a deformar.
- **PNG.** Otros formatos no los toma.
- Del tamaño que quieras: al arrancar, el servidor la convierte a 64×64
  sola (lo hace la imagen de Docker, por el `ICON` del `docker-compose.yml`).

## Si no pones logo

No pasa nada: el servidor arranca igual, solo sin icono. `mc doctor` te
lo va a recordar como aviso, no como error.

## Después de ponerlo

```bash
mc restart
```

El icono se cachea del lado del cliente, así que si acabas de cambiarlo y
sigues viendo el viejo, quita el servidor de tu lista de Minecraft y
vuélvelo a agregar.

---

`logo.png` está en `.gitignore` por diseño: la imagen es tuya y no tiene
por qué vivir en el repositorio.
