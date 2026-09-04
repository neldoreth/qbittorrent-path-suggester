# qBittorrent Path Suggester

> 🟡 **Estado: beta.** Probado primero en una instancia aislada y ahora en
> uso real en producción, contra una biblioteca de varios cientos de
> torrents ya organizados. El primer despliegue en producción sí llegó a
> mover mal 3 torrents por falsos positivos del matching (ver "Incidente" más
> abajo) — desde entonces, **ninguna pieza de este proyecto mueve nada por su
> cuenta**: `path-suggester/` solo registra una sugerencia en
> `decisions.jsonl`, nunca llama a `setLocation`, y la parte de interfaz
> (`webui/`) solo rellena un campo de texto editable. Aun así, revisa las
> sugerencias antes de fiarte del todo — el matching sigue siendo un
> solapamiento de palabras simple, no magia.

Complemento para [qBittorrent](https://www.qbittorrent.org/) que mejora la
selección de carpeta al añadir un torrent nuevo. qBittorrent solo recuerda la
*última* ruta usada; esto, en cambio, mira el nombre del torrent y lo compara
contra el histórico de rutas donde ya has guardado cosas parecidas, para
**sugerir** la carpeta más probable — nunca para moverla por su cuenta.

Hay dos formas de verlo funcionar, y ambas comparten el mismo criterio de
comparación (mismo algoritmo, una copia en Python y otra en JavaScript):

- **En la propia interfaz** (`webui/`): el campo *"Save files to location"*
  del diálogo de "Añadir torrent" aparece ya relleno con la ruta sugerida en
  cuanto qBittorrent conoce el nombre del torrent — **antes** de que le des a
  Añadir. Sigue siendo un campo de texto normal: si la sugerencia no te
  convence, la cambias a mano y ya. Esta es la forma que pediste, y la única
  que decide algo por ti (rellenar un campo que de todas formas ibas a
  revisar antes de confirmar).
- **En segundo plano** (`path-suggester/`): un servicio aparte que vigila
  torrents añadidos por *cualquier otra vía* (RSS, Sonarr/Radarr, otro
  cliente WebUI, un script) y **anota** en un log qué ruta les habría tocado,
  para que la muevas tú a mano si te convence. No toca nada él solo.

## Qué hace

- Extrae del nombre del torrent las palabras que probablemente identifican
  la serie/película (filtrando calidad, codec, idioma, sitios de descarga,
  marcadores de temporada/episodio en formato inglés y español, extensiones
  de archivo, y palabras genéricas EN/ES).
- Compara esas palabras contra el histórico de palabras vistas en cada
  `save_path` que ya usas (construido a partir de los torrents que ya tienes
  en qBittorrent).
- Si una ruta destaca claramente (sin empates) con al menos `N` palabras en
  común, la sugiere. Si no hay coincidencia clara, no sugiere nada.
- La pieza de fondo (`path-suggester`) registra cada sugerencia (con las
  palabras que coincidieron) en `path-suggester/data/decisions.jsonl` — y
  **solo** eso. No llama a `setLocation` ni mueve ningún archivo.

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

## Incidente (2026-09-04)

Al desplegar `path-suggester` por primera vez contra una instancia de
producción real (con cientos de torrents ya organizados), el servicio
procesó de golpe *todos* los torrents existentes — no solo los nuevos — y
**aplicó** (esta versión sí llamaba a `setLocation` automáticamente) 3
movimientos equivocados por palabras demasiado genéricas que no estaban en
la lista de ruido:

- `mkv` — la extensión del archivo, presente en casi cualquier torrent de un
  solo fichero, contaba como palabra significativa.
- `ing` — abreviatura de "inglés" en release en español (p. ej. `ESP-ING`),
  no estaba filtrada como sí lo estaba `eng`.
- Palabras genéricas de una sola coincidencia (`star`, `hombre`) bastaban
  para mover algo con el umbral por defecto (`MIN_MATCH_TOKENS=1`).

Resultado: una película se coló en la carpeta de una serie sin ninguna
relación real, dos veces. Se corrigió a mano en cuestión de minutos (mismo
mecanismo, `setLocation` de vuelta a la ruta original), pero fue exactamente
el escenario que este README ya avisaba como riesgo teórico en la sección
"Qué NO hace" — y pasó la primera vez que se probó con una biblioteca real
grande, no con los pocos torrents sintéticos usados hasta entonces.

Cambios a raíz de esto: `mkv`/`mp4`/`avi`/etc. e `ing` añadidos al ruido, y
sobre todo, **se eliminó la capacidad de `path-suggester` de mover nada por
su cuenta** — ahora solo sugiere. Si en el futuro se quiere recuperar el
modo "aplica automáticamente", que sea explícito y opt-in, nunca el
comportamiento por defecto.

## Cómo funciona por dentro

Tres piezas:

- **`qbittorrent-pruebas`** — una instancia de qBittorrent
  ([`linuxserver/qbittorrent`](https://github.com/linuxserver/docker-qbittorrent))
  aislada, opcional, para probar esto por primera vez sin tocar tu instancia
  real. El autor la usó durante el desarrollo y ya no la necesita — corre
  esto directamente contra su qBittorrent de producción — pero se mantiene
  en el repo como la forma recomendada de probarlo tú por primera vez antes
  de apuntarlo a tu propia instancia.
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
   | `MIN_MATCH_TOKENS` | `1` | Mínimo de palabras en común para sugerir una ruta. Súbelo a `2` si ves falsos positivos |

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
  `MIN_MATCH_TOKENS`, el desempate (si dos rutas empatan en puntuación, no se
  sugiere nada) y la lista de ruido — que, como demostró el incidente de
  arriba, no es exhaustiva. Revisa siempre antes de mover a mano.
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

Este repositorio (todo salvo `webui/`) está bajo [GPLv3](LICENSE).

`webui/` es una copia vendorizada de la WebUI oficial de qBittorrent
(versión 5.2.3, con `addtorrent.js` y el nuevo `pathSuggester.js` como único
cambio) y conserva la licencia original de esos archivos tal cual la trae el
proyecto qBittorrent: la mayoría bajo GPLv2 (con la excepción de enlazado
con OpenSSL que usa el propio qBittorrent), y algún archivo puntual —
`addtorrent.js` entre ellos— bajo MIT, según su propia cabecera. No se
reclama copyright sobre ese código salvo por las líneas añadidas.
