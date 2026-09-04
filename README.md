# qBittorrent Path Suggester

> ⚠️ **Estado: alpha muy temprana, sin probar con uso real.** Solo se ha
> verificado con torrents sintéticos (magnets falsos sin datos reales) en una
> instancia de pruebas aislada. No se ha usado todavía con tráfico ni
> descargas reales, ni contra una instancia de producción. Revisa
> `path-suggester/data/decisions.jsonl` tras cada torrent nuevo hasta que
> confíes en el criterio, y no lo apuntes a tu qBittorrent de producción sin
> antes entender qué hace `setLocation`.

Servicio complementario para [qBittorrent](https://www.qbittorrent.org/) que
mejora la selección de carpeta al añadir un torrent nuevo. qBittorrent solo
recuerda la *última* ruta usada; este servicio, en cambio, mira el nombre del
torrent y lo compara contra el histórico de rutas donde ya has guardado cosas
parecidas, para proponer (y aplicar) automáticamente la carpeta más probable.

## Qué hace

- Sondea la API WebUI de qBittorrent cada pocos segundos buscando torrents
  nuevos.
- Por cada torrent nuevo, extrae del nombre las palabras que probablemente
  identifican la serie/película (filtrando calidad, codec, idioma, sitios de
  descarga, marcadores de temporada/episodio y palabras genéricas EN/ES).
- Compara esas palabras contra el histórico de palabras vistas en cada
  `save_path` que ya usas (construido a partir de los torrents que ya tienes
  en qBittorrent).
- Si una ruta destaca claramente (sin empates) con al menos `N` palabras en
  común, mueve el torrent ahí con `torrents/setLocation` — como esto ocurre
  antes de que se descarguen datos, el movimiento es instantáneo.
- Si no hay una coincidencia clara, no toca nada: se queda la ruta por
  defecto de qBittorrent, igual que si esto no existiera, y la cambias a mano
  como siempre.
- Registra cada decisión (aplicada o no, con las palabras que coincidieron)
  en `path-suggester/data/decisions.jsonl`, para poder auditar por qué movió
  (o no movió) cada torrent.

## Qué NO hace (todavía)

- No toca la interfaz web de qBittorrent ni añade nada visual al diálogo de
  "añadir torrent" — actúa después, moviendo el torrent recién añadido.
- No aprende de tus correcciones manuales de forma activa; simplemente la
  próxima vez que ese torrent (o cualquier otro) esté en esa carpeta,
  contribuye al histórico.
- El matching es un solapamiento de palabras simple, sin pesos ni
  aprendizaje. Dos títulos distintos que compartan una palabra poco común
  (o el mismo grupo de release) pueden coincidir por error.

## Cómo funciona por dentro

Dos piezas, pensadas para correr como contenedores separados en el mismo
`docker-compose.yml`:

- **`qbittorrent-pruebas`** — una instancia de qBittorrent
  ([`linuxserver/qbittorrent`](https://github.com/linuxserver/docker-qbittorrent))
  aislada, pensada para probar esto sin tocar tu instancia real. Puedes
  apuntar el servicio de abajo a tu propio qBittorrent en vez de usar esta.
- **`path-suggester`** — el servicio en Python que hace el sondeo y el
  matching (`path-suggester/main.py` y `path-suggester/matcher.py`).

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

6. Añade un torrent nuevo desde la WebUI de qBittorrent como siempre, y
   revisa qué decidió:

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

## Licencia

Sin licencia definida todavía — de momento, todos los derechos reservados.
