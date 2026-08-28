"""
The HTTP service behind sc2.eole.me: drop a .SC2Replay, get its build order as
Markdown. Nothing is kept — the file is written to a temporary path for the
duration of the parse, then removed in a `finally`.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
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
    build_report,
    describe_replay,
    labels,
    patch_spawningtool,
    read_replay,
    render_markdown,
)

# A 40-minute replay weighs ~2 MB; 12 MB leaves plenty of room without letting a
# multi-gigabyte upload swamp the VPS. This is not an access restriction, it is
# what keeps the service standing.
MAX_UPLOAD_BYTES = int(os.environ.get("SC2BO_MAX_UPLOAD_BYTES", 12 * 1024 * 1024))
PARSE_TIMEOUT_S = float(os.environ.get("SC2BO_PARSE_TIMEOUT_S", 45))
TELEMETRY_WEBHOOK_URL = os.environ.get("TELEMETRY_WEBHOOK_URL", "")

# The site is open to everyone; this threshold forbids nothing, it emits an event
# when daily usage takes off, so the call on adding limits can be made on evidence.
# In-memory counter: a restart resets it, which is fine for an order of magnitude.
FEEDBACK_THRESHOLD = int(os.environ.get("SC2BO_FEEDBACK_THRESHOLD", 50))

# Resolved against the file, not the working directory: the tests run from the
# repository root, the container from /app.
_VERSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
VERSION = open(_VERSION_FILE).read().strip() if os.path.exists(_VERSION_FILE) else "0.0.0"

# Error messages follow the interface language: an English page answering in
# French is a half-translation.
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
    """Bump today's counter. Returns True on the crossing of the threshold."""
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
    Log to stdout — Vector collects by label and ships to Axiom — and also push
    the event to the telemetry webhook when one is configured.
    No player name and no replay content leaves here: map, matchup and durations
    are enough to measure usage.
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
        # Telemetry must never make an extraction fail.
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


def extract_markdown(path: str, options: Options, with_prompt: bool) -> tuple[str, dict, dict]:
    """Return (markdown to copy, report to display, summary for telemetry)."""
    data, stats = read_replay(path)
    report = build_report(data, stats, options)
    markdown = render_markdown(report, options)
    if with_prompt:
        markdown = build_coach_prompt(1, options.lang) + markdown
    return markdown, report, describe_replay(data)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "version": VERSION,
        "max_upload_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
        "usage_today": _usage["count"] if _usage["day"] == _today() else 0,
    }


@app.get("/api/prompt")
def prompt_text(lang: str = "fr") -> dict:
    """
    The coaching prompt the page offers to prepend. Served rather than restated
    in the interface: a second copy in translations.js would drift from this one
    the first time the wording changes.
    """
    if lang not in LANGUAGES:
        lang = "fr"
    return {"lang": lang, "prompt": build_coach_prompt(1, lang).rstrip()}


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
            markdown, report, meta = await asyncio.wait_for(
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

    # The labels travel with the report: the client renders its HTML in exactly
    # the Markdown's words, without holding a second copy.
    return JSONResponse({
        "markdown": markdown,
        "report": report,
        "labels": labels(lang),
        "meta": meta,
        "ms": elapsed_ms,
    })


# Mounted last: the static catch-all must not shadow the /api routes.
# Python's mimetypes table does not know .webp on every base image, and
# StaticFiles trusts it: without this the icons go out as octet-stream.
mimetypes.add_type("image/webp", ".webp")

_PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
app.mount("/", StaticFiles(directory=_PUBLIC_DIR, html=True), name="public")
