# qBittorrent Path Suggester

> ⚠️ **Estado: alpha, probado solo en una instancia de pruebas aislada.** La
> sugerencia en el diálogo de "Añadir torrent" (`webui/`) y el servicio de
> fondo (`path-suggester/`) ya se han verificado funcionando con torrents
> reales sobre `qbittorrent-pruebas`. Sigue sin probarse contra una
> instancia de producción, con volúmenes de historial grandes, o con
> magnets lentos de resolver. Revisa `path-suggester/data/decisions.jsonl`
> tras cada torrent nuevo hasta que confíes en el criterio, y no lo apuntes
> a tu qBittorrent de producción sin antes entender qué hace `setLocation`.

Complemento para [qBittorrent](https://www.qbittorrent.org/) que mejora la
selección de carpeta al añadir un torrent nuevo. qBittorrent solo recuerda la
*última* ruta usada; esto, en cambio, mira el nombre del torrent y lo compara
contra el histórico de rutas donde ya has guardado cosas parecidas, para
proponer automáticamente la carpeta más probable.

Hay dos formas de verlo funcionar, y ambas comparten el mismo criterio de
comparación (mismo algoritmo, una copia en Python y otra en JavaScript):

- **En la propia interfaz** (`webui/`): el campo *"Save files to location"*
  del diálogo de "Añadir torrent" aparece ya relleno con la ruta sugerida en
  cuanto qBittorrent conoce el nombre del torrent — **antes** de que le des a
  Añadir. Sigue siendo un campo de texto normal: si la sugerencia no te
  convence, la cambias a mano y ya. Esta es la forma que pediste.
- **En segundo plano** (`path-suggester/`): un servicio aparte que vigila
  torrents añadidos por *cualquier otra vía* (RSS, Sonarr/Radarr, otro
  cliente WebUI, un script) y los reubica después de añadidos, por si no
  pasaron por el diálogo de arriba.

## Qué hace

- Extrae del nombre del torrent las palabras que probablemente identifican
  la serie/película (filtrando calidad, codec, idioma, sitios de descarga,
  marcadores de temporada/episodio en formato inglés y español, y palabras
  genéricas EN/ES).
- Compara esas palabras contra el histórico de palabras vistas en cada
  `save_path` que ya usas (construido a partir de los torrents que ya tienes
  en qBittorrent).
- Si una ruta destaca claramente (sin empates) con al menos `N` palabras en
  común, la propone. Si no hay coincidencia clara, no sugiere nada y se queda
  el comportamiento normal de qBittorrent.
- La pieza de fondo (`path-suggester`) además *aplica* la sugerencia con
  `torrents/setLocation` y registra cada decisión (aplicada o no, con las
  palabras que coincidieron) en `path-suggester/data/decisions.jsonl`, para
  poder auditar por qué movió (o no movió) cada torrent.

## Qué NO hace (todavía)

- No aprende de tus correcciones manuales de forma activa; simplemente la
  próxima vez que ese torrent (o cualquier otro) esté en esa carpeta,
  contribuye al histórico.
- El matching es un solapamiento de palabras simple, sin pesos ni
  aprendizaje. Dos títulos distintos que compartan una palabra poco común
  (o el mismo grupo de release) pueden coincidir por error.
- El umbral de coincidencias mínimas no es configurable desde la interfaz
  todavía — en `webui/` está fijo en el código (`pathSuggester.js`); en
  `path-suggester/` sí es una variable de entorno (`MIN_MATCH_TOKENS`).

## Cómo funciona por dentro

Tres piezas:

- **`qbittorrent-pruebas`** — una instancia de qBittorrent
  ([`linuxserver/qbittorrent`](https://github.com/linuxserver/docker-qbittorrent))
  aislada, pensada para probar esto sin tocar tu instancia real. Puedes
  apuntar las otras dos piezas a tu propio qBittorrent en vez de usar esta.
- **`webui/`** — una copia local de la WebUI oficial de qBittorrent (versión
  5.2.3, bajada de su repositorio) con dos archivos tocados:
  `private/scripts/addtorrent.js` (engancha la sugerencia justo cuando
  qBittorrent conoce el nombre del torrent nuevo, en `populateMetadata`) y el
  nuevo `private/scripts/pathSuggester.js` (la lógica de comparación, en
  JavaScript). Se sirve usando la función nativa de qBittorrent **"Use
  alternative WebUI"** — no es un fork que haya que mantener aparte del
  cliente oficial, solo una carpeta de archivos estáticos que sustituye a la
  WebUI integrada.
- **`path-suggester/`** — el servicio en Python que hace el sondeo en
  segundo plano y el matching (`main.py` y `matcher.py`).

## Instalación

### Requisitos

- Docker y Docker Compose.
- Una instancia de qBittorrent con la WebUI activada (la de este repo, o una
  ya existente tuya).

### Pasos

1. Clona el repositorio:

   ```bash
   git clone https://github.com/neldoreth/qbittorrent-path-suggester.git
   cd qbittorrent-path-suggester
   ```

2. Copia `.env.example` a `.env` y pon la contraseña de la WebUI de
   qBittorrent:

   ```bash
   cp .env.example .env
   ```

   Edita `.env` con la contraseña que quieras. **Importante:** por defecto
   qBittorrent genera una contraseña temporal distinta cada vez que arranca
   si no le has fijado una tuya (verás algo como *"A temporary password is
   provided for this session"* en sus logs). Antes de usar este servicio,
   entra a la WebUI y fija tú una contraseña fija en **Herramientas → Opciones
   → WebUI**, o dejar que el propio `docker-compose.yml` te levante una
   instancia limpia y fija la contraseña vía API (ver `path-suggester/main.py`,
   método `login`, para el flujo que usa).

3. Ajusta `docker-compose.yml` a tu situación:

   - Si vas a usar la instancia de pruebas incluida (`qbittorrent-pruebas`):
     cambia los volúmenes (`/nas`, `/nas2`, …) por las rutas reales de tu
     sistema, y el puerto publicado si `8097`/`6891` ya están en uso.
   - Si prefieres apuntar contra tu qBittorrent **ya existente** en vez de
     levantar uno nuevo: elimina el servicio `qbittorrent-pruebas` del
     compose y cambia `QBIT_URL` en el servicio `path-suggester` a la URL de
     tu instancia real (por ejemplo `http://qbittorrent:8080` si está en la
     misma red de Docker, o `http://<host>:<puerto>` si es externa).

4. Ajusta, si quieres, las variables de entorno del servicio
   `path-suggester` en `docker-compose.yml`:

   | Variable | Por defecto | Qué hace |
   |---|---|---|
   | `QBIT_URL` | — | URL base de la WebUI de qBittorrent a vigilar |
   | `QBIT_USERNAME` | `admin` | Usuario de la WebUI |
   | `QBIT_PASSWORD` | — | Contraseña de la WebUI (desde `.env`) |
   | `POLL_INTERVAL_SECONDS` | `5` | Cada cuánto se sondean torrents nuevos |
   | `MIN_MATCH_TOKENS` | `1` | Mínimo de palabras en común para mover el torrent. Súbelo a `2` si ves falsos positivos |

5. Levanta todo:

   ```bash
   docker compose up -d --build
   ```

6. Activa la WebUI alternativa (la carpeta `webui/` con la sugerencia
   integrada en el diálogo de añadir torrent). Puedes hacerlo desde la
   propia interfaz, en **Herramientas → Opciones → WebUI → Use alternative
   WebUI**, apuntando a `/webui-custom` (la ruta interna del contenedor
   donde se monta `./webui`); o por API:

   ```bash
   curl -c /tmp/cj --data-urlencode "username=admin" --data-urlencode "password=<tu-contraseña>" \
     http://localhost:8097/api/v2/auth/login
   curl -b /tmp/cj -X POST http://localhost:8097/api/v2/app/setPreferences \
     --data-urlencode 'json={"alternative_webui_enabled": true, "alternative_webui_path": "/webui-custom"}'
   ```

   Si apuntas `path-suggester`/la WebUI a tu propio qBittorrent en vez del
   de este repo, monta tú `./webui` como volumen en tu contenedor (o
   cópialo a donde corra tu instancia) antes de activar la opción.

7. Prueba: añade un torrent nuevo desde la WebUI (por magnet o archivo
   `.torrent`) y mira el campo *"Save files to location"* del diálogo antes
   de confirmar — si hay coincidencia con el histórico, ya debería aparecer
   rellenado. Si además tienes `path-suggester` corriendo, comprueba también
   qué decidió por su lado:

   ```bash
   docker compose logs -f path-suggester
   cat path-suggester/data/decisions.jsonl
   ```

## Notas técnicas / limitaciones conocidas

- qBittorrent valida el header `Host` de las peticiones a la WebUI contra su
  puerto **interno** (el que fija `WEBUI_PORT`), no contra el puerto que
  publiques por fuera. Si ambos no coinciden, cualquier acceso desde fuera
  del contenedor (navegador incluido) recibe `401 Unauthorized` sin más
  explicación (en el log de qBittorrent aparece como "Invalid Host header,
  port mismatch"). Por eso en `docker-compose.yml` el puerto publicado y
  `WEBUI_PORT` son siempre el mismo número (`8097:8097`) — si cambias el
  puerto, cambia los dos a la vez.
- El nombre de la cookie de sesión de la WebUI incluye el puerto (p. ej.
  `QBT_SID_8097`), no es simplemente `SID`.
- El matching solo mira el **nombre** del torrent, no los archivos internos
  todavía.
- No hay protección contra falsos positivos más allá del umbral
  `MIN_MATCH_TOKENS` y el desempate (si dos rutas empatan en puntuación, no
  se mueve nada, por seguridad).
- `webui/` es una copia de la WebUI oficial **fijada a la versión 5.2.3**. Si
  actualizas qBittorrent a una versión con la WebUI distinta, esta copia se
  queda desactualizada (puede faltarle funcionalidad nueva, o directamente
  no cargar) hasta que se vuelva a generar contra la versión nueva y se
  reapliquen los dos cambios (`addtorrent.js` y `pathSuggester.js`) a mano.
- La sugerencia en `webui/` se recalcula cada vez que llega nueva
  información de metadata (puede ser varias veces mientras se resuelve un
  magnet), y dejamos de tocar el campo en cuanto detectamos que el usuario
  lo ha editado a mano. No debería pisar lo que escribas, pero como el resto
  de esto: sin probar a fondo todavía, especialmente con magnets lentos de
  resolver.

## Licencia

Sin licencia definida todavía — de momento, todos los derechos reservados.
