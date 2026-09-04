import json
import logging
import os
import time
from pathlib import Path

import requests

from matcher import tokenize, suggest_path

QBIT_URL = os.environ.get("QBIT_URL", "http://localhost:8080").rstrip("/")
QBIT_USERNAME = os.environ.get("QBIT_USERNAME", "admin")
QBIT_PASSWORD = os.environ.get("QBIT_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "5"))
MIN_MATCH_TOKENS = int(os.environ.get("MIN_MATCH_TOKENS", "1"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
STATE_FILE = DATA_DIR / "state.json"
DECISIONS_LOG = DATA_DIR / "decisions.jsonl"

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("path-suggester")


class QbitClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.session = requests.Session()

    def login(self):
        resp = self.session.post(
            f"{self.base_url}/api/v2/auth/login",
            data={"username": self.username, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        # el nombre de la cookie de sesión incluye el puerto (p.ej.
        # QBT_SID_8080), así que comprobamos que se haya fijado alguna
        # cookie en vez de buscar un nombre fijo
        if not self.session.cookies:
            raise RuntimeError(f"Login a qBittorrent falló (sin cookie de sesión): {resp.text!r}")
        log.info("Sesión iniciada en %s", self.base_url)

    def torrents_info(self):
        resp = self.session.get(f"{self.base_url}/api/v2/torrents/info", timeout=10)
        if resp.status_code in (401, 403):
            self.login()
            resp = self.session.get(f"{self.base_url}/api/v2/torrents/info", timeout=10)
        resp.raise_for_status()
        return resp.json()

    # Deliberadamente NO hay ningún método que mueva torrents. Este servicio
    # solo sugiere -- nunca toca setLocation por su cuenta. Ver
    # decisions.jsonl y el campo "suggested_path" para decidir tú a mano.


def load_state() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_state(processed: set):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(sorted(processed)))


def log_decision(entry: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with DECISIONS_LOG.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_history(torrents: list, exclude_hash: str = None) -> dict:
    history = {}
    for t in torrents:
        if t["hash"] == exclude_hash:
            continue
        path = t.get("save_path")
        if not path:
            continue
        history.setdefault(path, set()).update(tokenize(t.get("name", "")))
    return history


def process_new_torrents(client: QbitClient, processed: set):
    torrents = client.torrents_info()

    for t in torrents:
        h = t["hash"]
        if h in processed:
            continue

        name = t.get("name", "")
        # los magnets sin metadata todavía muestran el hash como nombre;
        # los dejamos pendientes para el siguiente ciclo de polling
        if not name or name == h:
            continue

        history = build_history(torrents, exclude_hash=h)
        new_tokens = tokenize(name)
        path, score, matched = suggest_path(new_tokens, history, MIN_MATCH_TOKENS)
        current_path = t.get("save_path")

        decision = {
            "hash": h,
            "name": name,
            "current_path": current_path,
            "score": score,
            "matched_tokens": sorted(matched),
            "suggested_path": path,
            "ts": time.time(),
        }

        # Solo sugerimos: este servicio nunca llama a setLocation por su
        # cuenta. Revisa decisions.jsonl y mueve tú a mano si te convence.
        if path and (path != current_path):
            log.info("Torrent %r: sugerencia -> %s (ruta actual %r, score=%d, coincidencias=%s)",
                      name, path, current_path, score, sorted(matched))
        elif path:
            log.info("Torrent %r: ya está en la ruta que le tocaría, %r (score=%d, coincidencias=%s)",
                      name, path, score, sorted(matched))
        else:
            log.info("Torrent %r: sin coincidencia clara (ruta actual %r)", name, current_path)

        log_decision(decision)
        processed.add(h)


def main():
    if not QBIT_PASSWORD:
        raise SystemExit("QBIT_PASSWORD es obligatorio")

    client = QbitClient(QBIT_URL, QBIT_USERNAME, QBIT_PASSWORD)
    client.login()

    processed = load_state()
    log.info("Cargados %d torrents ya procesados desde el estado", len(processed))

    while True:
        try:
            process_new_torrents(client, processed)
            save_state(processed)
        except requests.RequestException as e:
            log.warning("Fallo al hablar con qBittorrent: %s", e)
        except Exception:
            log.exception("Error inesperado en el bucle de polling")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
