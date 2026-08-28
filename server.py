"""
Service HTTP de sc2.eole.me : on dépose un .SC2Replay, on récupère sa build order
en Markdown. Rien n'est conservé — le fichier est écrit dans un temporaire le temps
du parsing, puis supprimé dans un `finally`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from sc2bo.extract import (
    LANGUAGES,
    Options,
    ReplayError,
    build_coach_prompt,
    describe_replay,
    patch_spawningtool,
    read_replay,
    render_replay,
)

# Un replay de 40 minutes pèse ~2 Mo ; 12 Mo laissent large sans permettre à un
# envoi de plusieurs gigaoctets de saturer le VPS. Ce n'est pas une restriction
# d'accès, c'est ce qui garde le service debout.
MAX_UPLOAD_BYTES = int(os.environ.get("SC2BO_MAX_UPLOAD_BYTES", 12 * 1024 * 1024))
PARSE_TIMEOUT_S = float(os.environ.get("SC2BO_PARSE_TIMEOUT_S", 45))
TELEMETRY_WEBHOOK_URL = os.environ.get("TELEMETRY_WEBHOOK_URL", "")

# Le site est ouvert à tous ; ce seuil n'interdit rien, il déclenche un événement
# quand l'usage quotidien décolle, pour décider en connaissance de cause s'il faut
# ajouter des limites. Compteur en mémoire : un redémarrage le remet à zéro, ce qui
# est acceptable pour un signal d'ordre de grandeur.
FEEDBACK_THRESHOLD = int(os.environ.get("SC2BO_FEEDBACK_THRESHOLD", 50))

# Résolu par rapport au fichier, pas au répertoire courant : les tests tournent
# depuis la racine du dépôt, le conteneur depuis /app.
_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
VERSION = open(_VERSION_FILE).read().strip() if os.path.exists(_VERSION_FILE) else "0.0.0"

# Les messages d'erreur suivent la langue de l'interface : une page en anglais
# qui répond en français est une demi-traduction.
MESSAGES = {
    "fr": {
        "too_big": "Fichier trop lourd : la limite est de {mb} Mo. Un replay StarCraft II "
                   "dépasse rarement 3 Mo — vérifiez le fichier envoyé.",
        "empty": "Fichier vide.",
        "bad_workers": "Valeur de « workers » inconnue.",
        "bad_format": "Valeur de « format » inconnue.",
        "bad_cutoff": "Le repère de temps doit s'écrire MM:SS, par exemple 8:00.",
        "timeout": "Le replay a mis trop de temps à être lu. Réessayez, ou coupez "
                   "l'extraction avec un repère de temps.",
        "unreadable": "Ce fichier n'a pas pu être lu comme un replay StarCraft II. "
                      "Vérifiez qu'il s'agit bien d'un .SC2Replay non tronqué.",
    },
    "en": {
        "too_big": "File too large: the limit is {mb} MB. A StarCraft II replay rarely "
                   "goes past 3 MB — check what you sent.",
        "empty": "Empty file.",
        "bad_workers": "Unknown value for \u201cworkers\u201d.",
        "bad_format": "Unknown value for \u201cformat\u201d.",
        "bad_cutoff": "The time marker must read MM:SS, for example 8:00.",
        "timeout": "The replay took too long to read. Try again, or cut the extraction "
                   "short with a time marker.",
        "unreadable": "This file could not be read as a StarCraft II replay. Check that "
                      "it really is an untruncated .SC2Replay.",
    },
}


def say(lang: str, key: str, **fields) -> str:
    catalogue = MESSAGES.get(lang, MESSAGES["fr"])
    return catalogue[key].format(**fields)


patch_spawningtool()

app = FastAPI(title="SC2 Build Order Extractor", version=VERSION)

_usage = {"day": "", "count": 0, "announced": False}


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def record_usage() -> bool:
    """Incrémente le compteur du jour. Renvoie True au franchissement du seuil."""
    day = _today()
    if _usage["day"] != day:
        _usage.update(day=day, count=0, announced=False)
    _usage["count"] += 1
    if not _usage["announced"] and _usage["count"] >= FEEDBACK_THRESHOLD:
        _usage["announced"] = True
        return True
    return False


def emit(event: str, **fields) -> None:
    """
    Journalise sur stdout — Vector récupère par label et pousse vers Axiom — et
    pousse en plus l'événement au webhook de télémétrie s'il est configuré.
    Aucun nom de joueur ni contenu de replay ne sort d'ici : la carte, le matchup
    et les durées suffisent à mesurer l'usage.
    """
    payload = {
        "event": event,
        "service": "sc2-build-order",
        "version": VERSION,
        "at": datetime.now(tz=timezone.utc).isoformat(),
        **fields,
    }
    print(json.dumps(payload, ensure_ascii=False), flush=True)

    if not TELEMETRY_WEBHOOK_URL:
        return
    try:
        request = urllib.request.Request(
            TELEMETRY_WEBHOOK_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(request, timeout=2).close()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # La télémétrie ne doit jamais faire échouer une extraction.
        print(json.dumps({"event": "telemetry_failed", "reason": str(exc)}), flush=True)


async def read_capped(upload: UploadFile, lang: str = "fr") -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1 << 20)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail=say(lang, "too_big", mb=MAX_UPLOAD_BYTES // (1024 * 1024)),
            )
        chunks.append(chunk)
    if not total:
        raise HTTPException(status_code=400, detail=say(lang, "empty"))
    return b"".join(chunks)


def extract_markdown(path: str, options: Options, with_prompt: bool) -> tuple[str, dict]:
    data, stats = read_replay(path)
    markdown = render_replay(data, stats, options)
    if with_prompt:
        markdown = build_coach_prompt(1, options.lang) + markdown
    return markdown, describe_replay(data)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "usage_today": _usage["count"] if _usage["day"] == _today() else 0,
    }


@app.post("/api/extract")
async def extract(
    replay: UploadFile = File(...),
    cutoff: str = Form(""),
    workers: str = Form("summary"),
    format: str = Form("table"),
    players: str = Form(""),
    prompt: str = Form("true"),
    lang: str = Form("fr"),
):
    if lang not in LANGUAGES:
        lang = "fr"
    if workers not in {"summary", "all", "none"}:
        raise HTTPException(status_code=400, detail=say(lang, "bad_workers"))
    if format not in {"table", "list", "raw"}:
        raise HTTPException(status_code=400, detail=say(lang, "bad_format"))

    options = Options(
        player=[p.strip() for p in players.split(",") if p.strip()],
        all_players=False,
        cutoff=cutoff.strip() or None,
        workers=workers,
        format=format,
        lang=lang,
    )
    if options.cutoff:
        try:
            from sc2bo.extract import parse_time

            parse_time(options.cutoff)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=say(lang, "bad_cutoff")) from None

    payload = await read_capped(replay, lang)
    started = time.monotonic()

    handle, path = tempfile.mkstemp(suffix=".SC2Replay")
    try:
        with os.fdopen(handle, "wb") as fh:
            fh.write(payload)
        try:
            markdown, meta = await asyncio.wait_for(
                run_in_threadpool(extract_markdown, path, options, prompt.lower() != "false"),
                timeout=PARSE_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            emit("extract_failed", reason="timeout", size=len(payload))
            raise HTTPException(status_code=504, detail=say(lang, "timeout")) from None
        except ReplayError as exc:
            emit("extract_failed", reason="replay_error", size=len(payload))
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except Exception as exc:  # noqa: BLE001 — un fichier illisible n'est pas une panne
            emit("extract_failed", reason=type(exc).__name__, size=len(payload))
            raise HTTPException(status_code=422, detail=say(lang, "unreadable")) from None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    elapsed_ms = int((time.monotonic() - started) * 1000)
    crossed = record_usage()
    emit("extract_ok", ms=elapsed_ms, size=len(payload), lang=lang,
         lines=len(markdown.splitlines()), **meta)
    if crossed:
        emit("usage_threshold_crossed", threshold=FEEDBACK_THRESHOLD, count=_usage["count"])

    return JSONResponse({"markdown": markdown, "meta": meta, "ms": elapsed_ms})


# Monté en dernier : le catch-all statique ne doit pas masquer les routes /api.
_PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
app.mount("/", StaticFiles(directory=_PUBLIC_DIR, html=True), name="public")
