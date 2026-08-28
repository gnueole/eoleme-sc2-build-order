"""
Read a StarCraft II replay and render its build order as Markdown.

Economy figures are not recomputed from the units produced: they come from the
samples the game itself writes into the replay every ~160 frames (supply used and
available, active workers, resources, income). That is what makes supply-block
detection exact rather than guessed.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .icons import icon_for

# --------------------------------------------------------------------------
# Options de rendu
# --------------------------------------------------------------------------


@dataclass
class Options:
    """What the caller — command line or web service — chooses to show."""

    player: list[str] = field(default_factory=list)
    all_players: bool = False
    cutoff: str | None = None
    workers: str = "summary"   # summary | all | none
    format: str = "table"      # table | list | raw
    lang: str = "fr"           # fr | en


# --------------------------------------------------------------------------
# Garde-fou spawningtool
# --------------------------------------------------------------------------


def patch_spawningtool() -> None:
    """
    In co-op and on maps with neutral camps, a replay carries upgrades belonging
    to players absent from the table (Amon's forces, civilians). Every one of
    spawningtool's event handlers checks membership before indexing — except
    add_upgrade_event, which only tests for player 0 and raises a KeyError that
    loses the whole file. We give it the same guard.
    Measured on a 495-replay corpus: 12 files recovered.
    """
    from spawningtool.parser import GameParser

    if getattr(GameParser.add_upgrade_event, "_sc2bo_guarded", False):
        return

    original = GameParser.add_upgrade_event

    def add_upgrade_event(self, event):
        if event.pid not in self.parsed_data["players"]:
            return
        return original(self, event)

    add_upgrade_event._sc2bo_guarded = True
    GameParser.add_upgrade_event = add_upgrade_event


# --------------------------------------------------------------------------
# Lecture
# --------------------------------------------------------------------------


def read_replay(path: str) -> tuple[dict, dict]:
    """Return (spawningtool data, the game's own samples per player)."""
    from spawningtool.parser import GameParser

    parser = GameParser(path)
    data = parser.get_parsed_data()
    return data, sample_stats(parser.replay)


def sample_stats(replay) -> dict[int, list[dict]]:
    stats: dict[int, list[dict]] = defaultdict(list)
    for event in replay.tracker_events:
        if event.name != "PlayerStatsEvent":
            continue
        stats[event.pid].append({
            "frame": int(event.frame),
            "food_used": int(event.food_used),
            "food_made": int(event.food_made),
            "workers": int(event.workers_active_count),
            "minerals": int(event.minerals_current),
            "vespene": int(event.vespene_current),
            "mineral_rate": int(event.minerals_collection_rate),
            "vespene_rate": int(event.vespene_collection_rate),
        })
    return stats


# --------------------------------------------------------------------------
# Mise en forme
# --------------------------------------------------------------------------

SPLIT_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")

RACE_LETTER = {"Terran": "T", "Protoss": "P", "Zerg": "Z"}
SUPPLY_CAP_MAX = 200

# Abilities carry unreadable internal names. Identical in both languages: these
# are the terms the community uses as they are.
ABILITY_LABELS = {
    "CalldownMULE": "MULE",
    "ChronoBoostEnergyCost": "Chrono Boost",
    "SpawnLarva": "Inject",
    "SupplyDrop": "Supply Drop",
    "ScannerSweep": "Scan",
}

LANGUAGES = ("fr", "en")

LABELS = {
    "fr": {
        "colon": " :",
        "map": "Carte", "duration": "Durée", "played": "Joué le", "patch": "Patch",
        "kind": "Type", "ai": "IA", "win": "Victoire", "loss": "Défaite",
        "truncated": "Tronqué à {cut} sur une partie de {full}.",
        "col_supply": "Ravit.", "col_time": "Temps", "col_action": "Action",
        "no_build": "Aucune construction enregistrée pour ce joueur.",
        "supply_unit": "ravit.", "chrono": "chrono",
        "workers_folded": "Les {n} travailleurs produits sont résumés ci-dessous "
                          "plutôt que listés ligne à ligne.",
        "economy": "Économie", "col_workers": "Travailleurs",
        "col_minerals": "Minerais", "col_gas": "Gaz", "col_income": "Revenu min/gaz",
        "supply_blocked": "Ravitaillement bloqué",
        "macro": "Macro", "losses": "Pertes au combat",
        "unknown_unit": "unité inconnue",
    },
    "en": {
        "colon": ":",
        "map": "Map", "duration": "Length", "played": "Played", "patch": "Patch",
        "kind": "Kind", "ai": "AI", "win": "Win", "loss": "Loss",
        "truncated": "Cut at {cut} of a {full} game.",
        "col_supply": "Supply", "col_time": "Time", "col_action": "Action",
        "no_build": "No construction recorded for this player.",
        "supply_unit": "supply", "chrono": "chrono",
        "workers_folded": "The {n} workers produced are summarised below "
                          "rather than listed one by one.",
        "economy": "Economy", "col_workers": "Workers",
        "col_minerals": "Minerals", "col_gas": "Gas", "col_income": "Income min/gas",
        "supply_blocked": "Supply blocked",
        "macro": "Macro", "losses": "Combat losses",
        "unknown_unit": "unknown unit",
    },
}


def labels(lang: str) -> dict:
    return LABELS.get(lang, LABELS["fr"])


class ReplayError(ValueError):
    """The file is not a usable replay."""


def pretty(name: str | None, lang: str = "fr") -> str:
    """
    SupplyDepot -> Supply Depot; SCV and "Combat Shields" are left alone.
    Some co-op units arrive with no name: that must not bring the render down.
    """
    if not name:
        return labels(lang)["unknown_unit"]
    return name if " " in name else SPLIT_CAMEL.sub(" ", name)


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_time(text: str) -> int:
    """"8:00" or "480" -> 480 seconds."""
    text = str(text).strip()
    if not text:
        raise ValueError("durée vide")
    if ":" in text:
        minutes, _, secs = text.partition(":")
        return int(minutes) * 60 + int(secs)
    return int(text)


def seconds_of(entry: dict, fps: float) -> float:
    return entry["frame"] / fps


# --------------------------------------------------------------------------
# Player selection
# --------------------------------------------------------------------------


def select_players(data: dict, wanted: list[str], every: bool) -> list[tuple[int, dict]]:
    """
    By default: both sides of a two-player game, otherwise the humans only —
    which leaves out Amon's forces and the neutral factions in co-op.
    """
    players = sorted(data["players"].items())

    if wanted:
        chosen: list[tuple[int, dict]] = []
        for token in wanted:
            match = None
            if token.isdigit():
                match = next((it for it in players if it[0] == int(token)), None)
            if match is None:
                low = token.lower()
                match = next((it for it in players if low in it[1]["name"].lower()), None)
            if match is None:
                names = ", ".join(f"{pid}:{p['name']}" for pid, p in players)
                raise ReplayError(f"Joueur introuvable : {token!r}. Joueurs de ce replay — {names}")
            if match not in chosen:
                chosen.append(match)
        return chosen

    if every or len(players) <= 2:
        return players
    return [it for it in players if it[1]["is_human"]] or players


# --------------------------------------------------------------------------
# Analyse
# --------------------------------------------------------------------------


def build_order_rows(player: dict, fps: float, cutoff: int | None, workers: str) -> list[dict]:
    rows = []
    for entry in player["buildOrder"]:
        if cutoff is not None and seconds_of(entry, fps) > cutoff:
            break
        if entry["is_worker"] and workers != "all":
            continue
        rows.append(entry)
    return rows


def economy_rows(samples: list[dict], fps: float, end: float, step: int) -> list[dict]:
    """One reading per `step` seconds, taken at the game's last sample."""
    if not samples:
        return []
    rows = []
    for mark in range(step, int(end) + 1, step):
        target = mark * fps
        current = None
        for sample in samples:
            if sample["frame"] > target:
                break
            current = sample
        if current:
            rows.append({"at": fmt_time(mark), **current})
    return rows


def supply_blocks(samples: list[dict], fps: float, end: float, minimum: float = 5.0) -> list[str]:
    """
    Stretches where supply used meets the cap: production has stalled. The 200
    cap is ignored, since that is not a player mistake.
    """
    blocks, start, previous = [], None, None
    for sample in samples:
        moment = sample["frame"] / fps
        if moment > end:
            break
        blocked = (sample["food_used"] >= sample["food_made"]
                   and sample["food_made"] < SUPPLY_CAP_MAX)
        if blocked and start is None:
            start = moment
        elif not blocked and start is not None:
            if previous is not None and previous - start >= minimum:
                blocks.append(f"{fmt_time(start)}→{fmt_time(previous)}")
            start = None
        previous = moment
    if start is not None and previous is not None and previous - start >= minimum:
        blocks.append(f"{fmt_time(start)}→{fmt_time(previous)}")
    return blocks


def summarise(entries: list[dict], lang: str = "fr", top: int | None = None) -> str:
    counts = Counter(pretty(e["name"], lang) for e in entries)
    return " · ".join(f"{n} ×{c}" if c > 1 else n for n, c in counts.most_common(top))


def describe_replay(data: dict) -> dict:
    """Short summary, for the interface and telemetry. No player names."""
    fps = data["frames_per_second"]
    players = sorted(data["players"].items())
    matchup = None
    if len(players) == 2:
        matchup = "v".join(RACE_LETTER.get(p["race"], (p["race"] or "?")[:1]) for _, p in players)
    return {
        "map": data["map"],
        "matchup": matchup,
        "duration": fmt_time(data["frames"] / fps),
        "players": len(players),
        "build": data["build"],
        "category": data.get("category"),
        "game_type": data.get("game_type"),
    }


# --------------------------------------------------------------------------
# Rendu Markdown
# --------------------------------------------------------------------------


def build_report(data: dict, stats: dict[int, list[dict]], options: Options) -> dict:
    """
    The intermediate shape both the Markdown *and* the HTML view derive from.
    Without it the server would render Markdown while the client built its own
    HTML, and the two would drift on the first change.
    """
    L = labels(options.lang)
    lang = options.lang
    fps = data["frames_per_second"]
    duration = data["frames"] / fps
    cutoff = parse_time(options.cutoff) if options.cutoff else None
    horizon = min(cutoff, duration) if cutoff else duration
    chosen = select_players(data, options.player, options.all_players)
    step = 60 if horizon <= 15 * 60 else 120

    everyone = sorted(data["players"].items())
    matchup = None
    if len(everyone) == 2:
        matchup = "v".join(RACE_LETTER.get(p["race"], (p["race"] or "?")[:1]) for _, p in everyone)

    played = datetime.fromtimestamp(data["unix_timestamp"], tz=timezone.utc)
    verdicts = {"Win": L["win"], "Loss": L["loss"]}

    report = {
        "lang": lang,
        "map": data["map"],
        "matchup": matchup,
        "duration": fmt_time(duration),
        "played": played.strftime("%Y-%m-%d %H:%M"),
        "build": data["build"],
        "category": data.get("category") or "?",
        "game_type": data.get("game_type") or "",
        "cutoff": fmt_time(cutoff) if cutoff and cutoff < duration else None,
        "roster": [
            {
                "name": p["name"],
                "race": p["race"],
                "result": verdicts.get(p["result"], p["result"] or "?"),
                "won": p["result"] == "Win",
                "is_human": bool(p["is_human"]),
            }
            for _, p in everyone
        ],
        "sections": [],
    }

    for pid, p in chosen:
        rows = build_order_rows(p, fps, cutoff, options.workers)
        section = {
            "name": p["name"],
            "race": p["race"],
            "result": verdicts.get(p["result"], p["result"] or "?"),
            "won": p["result"] == "Win",
            "is_human": bool(p["is_human"]),
            "build": [
                {
                    "supply": e["supply"],
                    "time": e["time"],
                    "action": pretty(e["name"], lang),
                    "chrono": bool(e["is_chronoboosted"]),
                    "worker": bool(e["is_worker"]),
                    # The game's own button icon, when we ship one for this name.
                    "icon": icon_for(e["name"]),
                }
                for e in rows
            ],
            "workers_folded": 0,
            "economy": [],
            "supply_blocks": [],
            "macro": [],
            "losses": {"total": 0, "items": []},
        }

        if rows:
            if options.workers != "all":
                produced = sum(1 for e in p["buildOrder"] if e["is_worker"])
                section["workers_folded"] = produced

            samples = stats.get(pid, [])
            if options.workers != "none":
                section["economy"] = economy_rows(samples, fps, horizon, step)
            section["supply_blocks"] = supply_blocks(samples, fps, horizon)

            abilities = [e for e in p["abilities"] if cutoff is None or seconds_of(e, fps) <= cutoff]
            counts = Counter(ABILITY_LABELS.get(e["name"], pretty(e["name"], lang)) for e in abilities)
            section["macro"] = [{"name": n, "count": c} for n, c in counts.most_common()]

            losses = [e for e in p["unitsLost"] if cutoff is None or seconds_of(e, fps) <= cutoff]
            # killer=None: morphed into a building or self-destructed, not a combat loss.
            killed = [e for e in losses if e["killer"] is not None and e["killer"] != pid]
            lost = Counter(pretty(e["name"], lang) for e in killed)
            section["losses"] = {
                "total": len(killed),
                "items": [{"name": n, "count": c} for n, c in lost.most_common(12)],
            }

        report["sections"].append(section)

    return report


def render_markdown(report: dict, options: Options) -> str:
    """The Markdown, rendered from the report and nothing else."""
    L = labels(report["lang"])
    c = L["colon"]
    out: list[str] = []

    heading = f"# {report['map']}"
    if report["matchup"]:
        heading += f" — {report['matchup']}"
    out.append(heading)
    out.append("")

    facts = [
        f"**{L['map']}{c}** {report['map']}",
        f"**{L['duration']}{c}** {report['duration']}",
        f"**{L['played']}{c}** {report['played']} UTC",
        f"**{L['patch']}{c}** build {report['build']}",
        f"**{L['kind']}{c}** {report['category']} {report['game_type']}".strip(),
    ]
    out.append(" · ".join(facts))
    out.append("")

    for p in report["roster"]:
        kind = "" if p["is_human"] else f" *({L['ai']})*"
        out.append(f"- **{p['name']}**{kind} — {p['race']} — {p['result']}")
    out.append("")

    if report["cutoff"]:
        out.append("> " + L["truncated"].format(cut=report["cutoff"], full=report["duration"]))
        out.append("")

    for section in report["sections"]:
        out.append(f"## {section['name']} — {section['race']}")
        out.append("")

        rows = section["build"]
        if not rows:
            out.append(f"_{L['no_build']}_")
            out.append("")
            continue

        if options.format == "table":
            out.append(f"| {L['col_supply']} | {L['col_time']} | {L['col_action']} |")
            out.append("|--:|--:|---|")
            for e in rows:
                mark = " ⚡" if e["chrono"] else ""
                out.append(f"| {e['supply']} | {e['time']} | {e['action']}{mark} |")
        elif options.format == "list":
            for i, e in enumerate(rows, 1):
                mark = " ⚡" if e["chrono"] else ""
                out.append(f"{i}. `{e['supply']} {L['supply_unit']} · {e['time']}` {e['action']}{mark}")
        else:
            width = max(len(str(e["supply"])) for e in rows)
            out.append("```text")
            for e in rows:
                mark = f" ({L['chrono']})" if e["chrono"] else ""
                out.append(f"{str(e['supply']).rjust(width)}  {e['time']:>5}  {e['action']}{mark}")
            out.append("```")
        out.append("")

        if section["workers_folded"]:
            out.append("_" + L["workers_folded"].format(n=section["workers_folded"]) + "_")
            out.append("")

        if section["economy"]:
            out.append(f"### {L['economy']}")
            out.append("")
            out.append(f"| {L['col_time']} | {L['col_supply']} | {L['col_workers']} "
                       f"| {L['col_minerals']} | {L['col_gas']} | {L['col_income']} |")
            out.append("|--:|--:|--:|--:|--:|--:|")
            for row in section["economy"]:
                out.append(
                    f"| {row['at']} | {row['food_used']}/{row['food_made']} | {row['workers']} "
                    f"| {row['minerals']} | {row['vespene']} "
                    f"| {row['mineral_rate']}/{row['vespene_rate']} |"
                )
            out.append("")

        if section["supply_blocks"]:
            out.append(f"**{L['supply_blocked']} —** {' · '.join(section['supply_blocks'])}")
            out.append("")

        if section["macro"]:
            out.append(f"**{L['macro']} —** "
                       + " · ".join(f"{m['name']} ×{m['count']}" for m in section["macro"]))
            out.append("")

        losses = section["losses"]
        if losses["total"]:
            listed = " · ".join(f"{i['name']} ×{i['count']}" if i["count"] > 1 else i["name"]
                                for i in losses["items"])
            out.append(f"**{L['losses']} ({losses['total']}) —** " + listed)
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def render_replay(data: dict, stats: dict[int, list[dict]], options: Options) -> str:
    """Long-standing shortcut: report then Markdown, in one call."""
    return render_markdown(build_report(data, stats, options), options)


COACH_OPENING = {
    "fr": (
        "Voici une de mes parties StarCraft II, extraite du replay. Analyse comme un coach :",
        "Voici {n} de mes parties StarCraft II, extraites du replay. Analyse comme un coach :",
    ),
    "en": (
        "Here is one of my StarCraft II games, pulled from the replay. Coach me on it:",
        "Here are {n} of my StarCraft II games, pulled from the replay. Coach me on them:",
    ),
}

COACH_BODY = {
    "fr": """\

1. Mes timings d'ouverture et mes ravitaillements tiennent-ils la route face à ce matchup ?
2. Ma courbe de travailleurs décroche-t-elle, et à quelle minute exactement ?
3. Que disent mes minerais en banque et mes blocages de ravitaillement sur ma macro ?
4. Qu'est-ce qui m'a coûté la partie, et quelles sont les deux corrections les plus rentables ?

Le symbole ⚡ marque une production accélérée au Chrono Boost. « Ravit. » donne le
ravitaillement utilisé sur la capacité disponible ; les deux se touchent quand la
production est à l'arrêt.

---

""",
    "en": """\

1. Do my opening timings and supply counts hold up for this matchup?
2. Does my worker curve fall behind, and at exactly which minute?
3. What do my banked minerals and supply blocks say about my macro?
4. What lost me the game, and which two fixes would pay off most?

The ⚡ symbol marks production sped up with Chrono Boost. "Supply" gives supply
used over the cap available; the two meet when production has stalled.

---

""",
}


def build_coach_prompt(count: int, lang: str = "fr") -> str:
    one, many = COACH_OPENING.get(lang, COACH_OPENING["fr"])
    opening = one if count == 1 else many.format(n=count)
    return opening + "\n" + COACH_BODY.get(lang, COACH_BODY["fr"])
