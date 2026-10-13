# Traducciones propias al español de México

Aquí viven los archivos de mensajes que **escribimos nosotros**, porque el
plugin no traía español o porque el que traía estaba en español de España.

`mc build` los copia a la carpeta de cada plugin. Casi todos los plugins le
dan prioridad al archivo que está en su propia carpeta sobre el que viene
dentro del jar, así que basta con dejarlo ahí.

## Qué hay aquí y por qué

| Archivo | Plugin | Por qué lo traducimos nosotros |
|---|---|---|
| `coreprotect-language.yml` | CoreProtect | El jar no trae ningún idioma más que inglés. |
| `chatsentinel-messages.yml` | ChatSentinel | El jar solo trae inglés. |
| `essentials-messages_es.properties` | EssentialsX | Sí trae `messages_es.properties`, pero es español de España. Corregimos los modismos. |
| `authme-messages_es.yml` | AuthMe Reloaded | Igual: trae `messages_es.yml` de España. |

## Lo que NO traducimos y por qué

- **Textos vanilla de Minecraft** (mensajes de muerte, logros, nombres de
  ítems, el kick por versión incompatible). Los traduce **cada cliente**
  según su propio idioma. Si los forzáramos a español aquí, alguien que
  juega en inglés los vería en español. En `paper-global.yml` se ve
  claramente: Paper usa `<lang:...>` justo para eso y nosotros lo dejamos.
- **Geyser y Floodgate**: traen `es_MX` completo dentro del jar (verificado
  en Geyser 2.11.3 y Floodgate 2.2.5). Solo les fijamos `default-locale`.
- **GSit**: trae `lang/es_es.yml`. Es español neutro y correcto; solo le
  fijamos `lang: es_es`.
- **SkinsRestorer**: trae `locales/locale_es.json`. Sus mensajes son casi
  todos de administración (`/skin set`, `/skin clear`).
- **LuckPerms**: no trae español y sus mensajes son **solo de
  administración** (`/lp user ... permission set`). Los ve únicamente quien
  administra el servidor, nunca un jugador. Lo dejamos en inglés a propósito
  en lugar de mantener una traducción de 700 líneas que nadie lee.
- **ViaVersion**: sus mensajes son de incompatibilidad de versión y se
  configuran en su propio `config.yml`, que `mc build` ya genera en español.

## Cómo revisar que no quedó nada en inglés

```bash
mc doctor --traducciones
```

Busca palabras que solo existen en inglés dentro de las configs generadas y
te dice archivo y línea.
