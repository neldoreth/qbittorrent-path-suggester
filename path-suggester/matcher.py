import re

_BRACKETS_RE = re.compile(r"[\[\]{}()]+")
_SEPARATORS_RE = re.compile(r"[.\-_+,;:!?'\"/\\|]+")

# Marcadores de temporada/episodio en cualquiera de sus formas habituales
# (s01e01, s01, e01, 1x01, cap103, capitulo103, t01...): aparecen en casi
# cualquier serie, así que nunca deben contar como coincidencia real.
_EPISODE_MARKER_RE = re.compile(
    r"^(s\d{1,3}e\d{1,3}|s\d{1,3}|e\d{1,3}|\d{1,2}x\d{1,3}"
    r"|t\d{1,3}|cap\d{1,4}|capitulo\d{1,4}|ep\d{1,4})$"
)

# Ruido típico de nombres de release: calidad, codec, audio, idioma, sitios
# de descarga y palabras genéricas que no identifican la serie/película.
_NOISE_TOKENS = {
    "480p", "576p", "720p", "1080p", "1440p", "2160p", "4320p", "4k", "8k",
    "hdtv", "pdtv", "sdtv", "webrip", "webdl", "web", "dl", "bluray", "bd",
    "bdrip", "brrip", "dvdrip", "dvdscr", "hdrip", "remux", "hdr", "hdr10",
    "sdr", "dolby", "vision", "atmos",
    "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "divx",
    "aac", "ac3", "eac3", "dts", "flac", "mp3", "opus", "10bit", "8bit",
    "multi", "dual", "audio", "sub", "subs", "subbed", "dubbed", "vose",
    "vosi", "latino", "castellano", "espanol", "spanish", "english", "eng",
    "esp", "cast", "ing",
    "proper", "repack", "internal", "extended", "uncut", "remastered",
    "complete", "season", "episode", "temporada", "temp", "capitulo",
    "cap", "caps", "episodio", "ep", "eps",
    "nf", "amzn", "dsnp", "hmax", "atvp", "ddp",
    "yts", "mx", "rarbg", "eztv", "yify", "torrentgalaxy", "tgx",
    "1337x", "kickass", "galaxyrg",
    # extensiones de archivo: en un torrent de un solo fichero, el nombre
    # trae la extensión pegada y sería ruido común a casi cualquier release
    "mkv", "mp4", "avi", "mov", "wmv", "flv", "ts", "m2ts", "iso",
    "srt", "idx", "nfo",
    "the", "a", "an", "of", "and", "el", "la", "los", "las", "de", "y",
    "un", "una",
}


def tokenize(text: str) -> set[str]:
    """Extrae del nombre de un torrent las palabras que probablemente
    identifican la serie/película, descartando ruido de release."""
    if not text:
        return set()
    text = text.lower()
    text = _BRACKETS_RE.sub(" ", text)
    text = _SEPARATORS_RE.sub(" ", text)

    tokens = set()
    for word in text.split():
        if len(word) < 3:
            continue
        if word.isdigit():
            continue
        if word in _NOISE_TOKENS:
            continue
        if _EPISODE_MARKER_RE.match(word):
            continue
        tokens.add(word)
    return tokens


def suggest_path(new_tokens: set[str], history: dict[str, set[str]], min_matches: int = 1):
    """Compara los tokens del torrent nuevo contra el histórico de tokens
    vistos en cada save_path existente.

    history: {save_path: {tokens vistos alguna vez en ese path}}

    Devuelve (path, score, matched_tokens). Si nadie llega al umbral, o si
    hay empate entre dos o más paths con la misma puntuación máxima, devuelve
    (None, 0, set()) -- en caso de duda, mejor no adivinar y dejar la ruta
    por defecto para que la corrija el usuario.
    """
    if not new_tokens:
        return None, 0, set()

    scored = []
    for path, path_tokens in history.items():
        matched = new_tokens & path_tokens
        if matched:
            scored.append((len(matched), path, matched))

    if not scored:
        return None, 0, set()

    scored.sort(key=lambda x: x[0], reverse=True)
    top_score = scored[0][0]
    if top_score < min_matches:
        return None, 0, set()

    tied = [s for s in scored if s[0] == top_score]
    if len(tied) > 1:
        return None, 0, set()

    _, path, matched = scored[0]
    return path, top_score, matched
