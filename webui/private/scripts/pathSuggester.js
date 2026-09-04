"use strict";

/*
 * qBittorrent Path Suggester (alpha, sin probar)
 *
 * Compara el nombre de un torrent nuevo contra el historial de palabras
 * vistas en cada save_path ya existente, y sugiere la ruta con más
 * coincidencias. Misma lógica que path-suggester/matcher.py -- si cambias
 * el criterio en uno, cámbialo en el otro.
 */

window.qBittorrent ??= {};
window.qBittorrent.PathSuggester ??= (() => {
    const exports = () => {
        return {
            suggestSavePath: suggestSavePath
        };
    };

    const BRACKETS_RE = /[[\]{}()]+/g;
    const SEPARATORS_RE = /[.\-_+,;:!?'"/\\|]+/g;

    // Marcadores de temporada/episodio en cualquiera de sus formas habituales
    // (s01e01, s01, e01, 1x01, cap103, capitulo103, t01...): aparecen en casi
    // cualquier serie, así que nunca deben contar como coincidencia real.
    const EPISODE_MARKER_RE = /^(s\d{1,3}e\d{1,3}|s\d{1,3}|e\d{1,3}|\d{1,2}x\d{1,3}|t\d{1,3}|cap\d{1,4}|capitulo\d{1,4}|ep\d{1,4})$/;

    // Ruido típico de nombres de release: calidad, codec, audio, idioma,
    // sitios de descarga y palabras genéricas que no identifican la
    // serie/película.
    const NOISE_TOKENS = new Set([
        "480p", "576p", "720p", "1080p", "1440p", "2160p", "4320p", "4k", "8k",
        "hdtv", "pdtv", "sdtv", "webrip", "webdl", "web", "dl", "bluray", "bd",
        "bdrip", "brrip", "dvdrip", "dvdscr", "hdrip", "remux", "hdr", "hdr10",
        "sdr", "dolby", "vision", "atmos",
        "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "divx",
        "aac", "ac3", "eac3", "dts", "flac", "mp3", "opus", "10bit", "8bit",
        "multi", "dual", "audio", "sub", "subs", "subbed", "dubbed", "vose",
        "vosi", "latino", "castellano", "espanol", "spanish", "english", "eng",
        "esp", "cast",
        "proper", "repack", "internal", "extended", "uncut", "remastered",
        "complete", "season", "episode", "temporada", "temp", "capitulo",
        "cap", "caps", "episodio", "ep", "eps",
        "nf", "amzn", "dsnp", "hmax", "atvp", "ddp",
        "yts", "mx", "rarbg", "eztv", "yify", "torrentgalaxy", "tgx",
        "1337x", "kickass", "galaxyrg",
        "the", "a", "an", "of", "and", "el", "la", "los", "las", "de", "y",
        "un", "una",
    ]);

    const tokenize = (text) => {
        const tokens = new Set();
        if (!text)
            return tokens;

        let normalized = text.toLowerCase();
        normalized = normalized.replace(BRACKETS_RE, " ");
        normalized = normalized.replace(SEPARATORS_RE, " ");

        for (const word of normalized.split(/\s+/)) {
            if (word.length < 3)
                continue;
            if (/^\d+$/.test(word))
                continue;
            if (NOISE_TOKENS.has(word))
                continue;
            if (EPISODE_MARKER_RE.test(word))
                continue;
            tokens.add(word);
        }
        return tokens;
    };

    const buildHistory = (torrents, excludeHash) => {
        const history = new Map();
        for (const t of torrents) {
            if ((excludeHash !== undefined) && (t.hash === excludeHash))
                continue;
            if (!t.save_path)
                continue;

            if (!history.has(t.save_path))
                history.set(t.save_path, new Set());
            const pathTokens = history.get(t.save_path);
            for (const tok of tokenize(t.name))
                pathTokens.add(tok);
        }
        return history;
    };

    // Devuelve {path, score, matched} o null si nadie llega al umbral, o si
    // hay empate entre dos o más paths con la misma puntuación máxima -- en
    // caso de duda, mejor no sugerir nada que sugerir mal.
    const pickBestPath = (newTokens, history, minMatches) => {
        if (newTokens.size === 0)
            return null;

        const scored = [];
        for (const [path, pathTokens] of history) {
            const matched = [...newTokens].filter((tok) => pathTokens.has(tok));
            if (matched.length > 0)
                scored.push({ score: matched.length, path, matched });
        }
        if (scored.length === 0)
            return null;

        scored.sort((a, b) => b.score - a.score);
        const topScore = scored[0].score;
        if (topScore < minMatches)
            return null;

        const tied = scored.filter((s) => s.score === topScore);
        if (tied.length > 1)
            return null;

        return tied[0];
    };

    // name: nombre del torrent nuevo (metadata.info.name)
    // minMatches: mínimo de palabras en común para sugerir algo (por defecto 1)
    const suggestSavePath = async (name, minMatches = 1) => {
        if (!name)
            return null;

        let torrents;
        try {
            const response = await fetch("api/v2/torrents/info", { method: "GET", cache: "no-store" });
            if (!response.ok)
                return null;
            torrents = await response.json();
        }
        catch (error) {
            console.error("PathSuggester: no se pudo obtener la lista de torrents", error);
            return null;
        }

        const history = buildHistory(torrents);
        const newTokens = tokenize(name);
        return pickBestPath(newTokens, history, minMatches);
    };

    return exports();
})();
Object.freeze(window.qBittorrent.PathSuggester);
