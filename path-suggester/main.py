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

    def set_location(self, torrent_hash: str, location: str):
        resp = self.session.post(
            f"{self.base_url}/api/v2/torrents/setLocation",
            data={"hashes": torrent_hash, "location": location},
            timeout=10,
        )
        resp.raise_for_status()


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

        decision = {
            "hash": h,
            "name": name,
            "previous_path": t.get("save_path"),
            "score": score,
            "matched_tokens": sorted(matched),
            "ts": time.time(),
        }

        if path and path == t.get("save_path"):
            log.info("Torrent %r: ya está en la ruta sugerida %r (score=%d, coincidencias=%s)",
                      name, path, score, sorted(matched))
            decision["chosen_path"] = path
            decision["applied"] = False
        elif path:
            log.info("Torrent %r -> %s (score=%d, coincidencias=%s)",
                      name, path, score, sorted(matched))
            client.set_location(h, path)
            # reflejamos el cambio en memoria para que el resto de torrents
            # de este mismo ciclo vean la ruta nueva, no la de antes de mover
            t["save_path"] = path
            decision["chosen_path"] = path
            decision["applied"] = True
        else:
            log.info("Torrent %r: sin coincidencia clara, se deja la ruta por defecto %r",
                      name, t.get("save_path"))
            decision["chosen_path"] = None
            decision["applied"] = False

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
