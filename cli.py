#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["spawningtool>=3.0.0"]
# ///
"""
Extract a StarCraft II replay's build order as Markdown, ready to paste into Claude.

    uv run cli.py --last
    uv run cli.py --last 3 --cutoff 8:00 --clip
    uv run cli.py "/path/game.SC2Replay" --output bo.md
    uv run cli.py --list 20

The replay folder is found on its own (including through OneDrive under WSL);
SC2_REPLAY_DIR or --replay-dir override it.

Same engine as the sc2.eole.me site: it all lives in the sc2bo/ package.
"""

from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime

from sc2bo.extract import Options, build_coach_prompt, patch_spawningtool, read_replay, render_replay

REPLAY_DIR_PATTERNS = [
    "/mnt/c/Users/*/OneDrive/Documents/StarCraft II/Accounts/*/*/Replays",
    "/mnt/c/Users/*/Documents/StarCraft II/Accounts/*/*/Replays",
    "~/Documents/StarCraft II/Accounts/*/*/Replays",
    "~/Library/Application Support/Blizzard/StarCraft II/Accounts/*/*/Replays",
]


def find_replay_dirs(override: str | None = None) -> list[str]:
    if override:
        return [os.path.expanduser(override)]
    env = os.environ.get("SC2_REPLAY_DIR")
    if env:
        return [os.path.expanduser(env)]
    found: list[str] = []
    for pattern in REPLAY_DIR_PATTERNS:
        found.extend(sorted(glob.glob(os.path.expanduser(pattern))))
    return found


def recent_replays(dirs: list[str], limit: int) -> list[str]:
    files: list[str] = []
    for d in dirs:
        files.extend(glob.glob(os.path.join(d, "**", "*.SC2Replay"), recursive=True))
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return files[:limit]


def copy_to_clipboard(text: str) -> str | None:
    for tool in (["clip.exe"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["pbcopy"]):
        if shutil.which(tool[0]):
            try:
                subprocess.run(tool, input=text.encode("utf-8"), check=True)
                return tool[0]
            except subprocess.SubprocessError:
                continue
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract a StarCraft II replay's build order as Markdown.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("replays", nargs="*", help=".SC2Replay files to read")
    parser.add_argument("--last", nargs="?", type=int, const=1, metavar="N",
                        help="read the N most recent replays (default: 1)")
    parser.add_argument("--list", nargs="?", type=int, const=15, metavar="N",
                        help="list the N most recent replays without reading them")
    parser.add_argument("--replay-dir", help="replay folder (else SC2_REPLAY_DIR, else auto-detected)")
    parser.add_argument("--player", action="append", default=[], metavar="NOM",
                        help="partial name or number of the player to extract; repeatable")
    parser.add_argument("--all-players", action="store_true",
                        help="include every side, AI and neutral forces too")
    parser.add_argument("--cutoff", metavar="MM:SS", help="keep only the start of the game")
    parser.add_argument("--workers", choices=["summary", "all", "none"], default="summary",
                        help="workers: summarised (default), listed one by one, or hidden")
    parser.add_argument("--format", choices=["table", "list", "raw"], default="table",
                        help="build order rendering (default: table)")
    parser.add_argument("--lang", choices=["fr", "en"], default="fr",
                        help="language of the generated Markdown (default: fr)")
    parser.add_argument("--no-prompt", action="store_true", help="omit the coaching prompt")
    parser.add_argument("--output", metavar="FILE", help="write to a file")
    parser.add_argument("--clip", action="store_true", help="copy the result to the clipboard")
    args = parser.parse_args()

    dirs = find_replay_dirs(args.replay_dir)

    if args.list is not None:
        if not dirs:
            sys.exit("Aucun dossier de replays trouvé. Utilisez --replay-dir ou SC2_REPLAY_DIR.")
        files = recent_replays(dirs, args.list)
        if not files:
            sys.exit(f"Aucun replay dans : {', '.join(dirs)}")
        for f in files:
            stamp = datetime.fromtimestamp(os.path.getmtime(f))
            print(f"{stamp:%Y-%m-%d %H:%M}  {os.path.basename(f)}")
        return

    targets = list(args.replays)
    if args.last:
        if not dirs:
            sys.exit("Aucun dossier de replays trouvé. Utilisez --replay-dir ou SC2_REPLAY_DIR.")
        found = recent_replays(dirs, args.last)
        if not found:
            sys.exit(f"Aucun replay dans : {', '.join(dirs)}")
        targets.extend(found)
    if not targets:
        parser.error("indiquez un fichier .SC2Replay, ou --last, ou --list")

    patch_spawningtool()
    options = Options(
        player=args.player,
        all_players=args.all_players,
        cutoff=args.cutoff,
        workers=args.workers,
        format=args.format,
        lang=args.lang,
    )

    documents: list[str] = []
    failures: list[str] = []
    for path in targets:
        if not os.path.exists(path):
            failures.append(f"{os.path.basename(path)} : fichier introuvable")
            continue
        try:
            data, stats = read_replay(path)
            documents.append(render_replay(data, stats, options))
        except Exception as exc:  # noqa: BLE001 — one unreadable replay must not kill the batch
            failures.append(f"{os.path.basename(path)} : {type(exc).__name__}: {exc}")

    for line in failures:
        print(f"échec — {line}", file=sys.stderr)
    if not documents:
        sys.exit("Aucun replay n'a pu être lu.")

    body = "\n\n---\n\n".join(documents)
    if not args.no_prompt:
        body = build_coach_prompt(len(documents), args.lang) + body
    text = body if body.endswith("\n") else body + "\n"

    lines = len(text.splitlines())
    if lines > 1200 and not args.cutoff:
        print(f"Sortie de {lines} lignes — « --cutoff 8:00 » la ramène à l'ouverture, "
              f"souvent le seul moment qui compte.", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"Écrit dans {args.output} ({lines} lignes)", file=sys.stderr)
    elif not args.clip:
        sys.stdout.write(text)

    if args.clip:
        tool = copy_to_clipboard(text)
        if tool:
            print(f"Copié dans le presse-papiers via {tool} — collez-le dans Claude.", file=sys.stderr)
        else:
            print("Aucun presse-papiers disponible ; sortie sur la sortie standard.", file=sys.stderr)
            sys.stdout.write(text)


if __name__ == "__main__":
    main()
