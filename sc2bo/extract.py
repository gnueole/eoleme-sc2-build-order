"""
Lecture d'un replay StarCraft II et rendu de sa build order en Markdown.

Les chiffres d'économie ne sont pas recalculés à partir des unités produites : ils
viennent des relevés que le jeu écrit lui-même dans le replay toutes les ~160 frames
(ravitaillement utilisé et disponible, travailleurs actifs, ressources, revenus).
C'est ce qui permet de détecter les blocages de ravitaillement sans les deviner.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Options de rendu
# --------------------------------------------------------------------------


@dataclass
class Options:
    """Ce que l'appelant — CLI ou serveur web — choisit d'afficher."""

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
    En Coop et sur les cartes à camps neutres, le replay porte des améliorations
    appartenant à des joueurs absents de la table (forces d'Amon, civils).
    Tous les gestionnaires d'événements de spawningtool vérifient l'appartenance
    avant d'indexer — sauf add_upgrade_event, qui ne teste que le joueur 0 et lève
    un KeyError qui fait perdre le fichier entier. On lui ajoute le même garde-fou.
    Mesuré sur un corpus de 495 replays : 12 fichiers récupérés.
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
    """Renvoie (données spawningtool, relevés du jeu par joueur)."""
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

# Les capacités portent des noms internes peu lisibles ; identiques dans les deux
# langues, ce sont les termes que la communauté emploie tels quels.
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
    """Le fichier n'est pas un replay exploitable."""


def pretty(name: str | None, lang: str = "fr") -> str:
    """
    SupplyDepot -> Supply Depot ; SCV et « Combat Shields » restent intacts.
    Certaines unités Coop arrivent sans nom : on ne casse pas le rendu pour autant.
    """
    if not name:
        return labels(lang)["unknown_unit"]
    return name if " " in name else SPLIT_CAMEL.sub(" ", name)


def fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def parse_time(text: str) -> int:
    """« 8:00 » ou « 480 » -> 480 secondes."""
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
# Sélection des joueurs
# --------------------------------------------------------------------------


def select_players(data: dict, wanted: list[str], every: bool) -> list[tuple[int, dict]]:
    """
    Par défaut : les deux camps d'une partie à deux joueurs, sinon les seuls humains
    — ce qui écarte les forces d'Amon et les factions neutres en Coop.
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
    """Un relevé par tranche de `step` secondes, pris au dernier échantillon du jeu."""
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
    Plages où le ravitaillement utilisé atteint la capacité : la production est à
    l'arrêt. On ignore le plafond de 200, qui n'est pas une erreur de joueur.
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
    """Résumé court, pour l'interface et la télémétrie. Sans nom de joueur."""
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


def render_replay(data: dict, stats: dict[int, list[dict]], options: Options) -> str:
    L = labels(options.lang)
    lang = options.lang
    fps = data["frames_per_second"]
    duration = data["frames"] / fps
    cutoff = parse_time(options.cutoff) if options.cutoff else None
    horizon = min(cutoff, duration) if cutoff else duration
    chosen = select_players(data, options.player, options.all_players)
    step = 60 if horizon <= 15 * 60 else 120

    out: list[str] = []
    played = datetime.fromtimestamp(data["unix_timestamp"], tz=timezone.utc)

    # Le matchup décrit la partie, pas la sélection : il reste TvZ même si l'on
    # n'extrait qu'un seul camp. Au-delà de deux joueurs (Coop, 2v2) il ne veut
    # plus rien dire, on n'affiche que la carte.
    everyone = sorted(data["players"].items())
    if len(everyone) == 2:
        matchup = "v".join(RACE_LETTER.get(p["race"], (p["race"] or "?")[:1]) for _, p in everyone)
        out.append(f"# {data['map']} — {matchup}")
    else:
        out.append(f"# {data['map']}")
    out.append("")

    c = L["colon"]
    out.append(" · ".join([
        f"**{L['map']}{c}** {data['map']}",
        f"**{L['duration']}{c}** {fmt_time(duration)}",
        f"**{L['played']}{c}** {played:%Y-%m-%d %H:%M} UTC",
        f"**{L['patch']}{c}** build {data['build']}",
        f"**{L['kind']}{c}** {data.get('category', '?')} {data.get('game_type', '')}".strip(),
    ]))
    out.append("")

    verdicts = {"Win": L["win"], "Loss": L["loss"]}
    for _, p in everyone:
        verdict = verdicts.get(p["result"], p["result"] or "?")
        kind = "" if p["is_human"] else f" *({L['ai']})*"
        out.append(f"- **{p['name']}**{kind} — {p['race']} — {verdict}")
    out.append("")

    if cutoff and cutoff < duration:
        out.append("> " + L["truncated"].format(cut=fmt_time(cutoff), full=fmt_time(duration)))
        out.append("")

    for pid, p in chosen:
        out.append(f"## {p['name']} — {p['race']}")
        out.append("")

        rows = build_order_rows(p, fps, cutoff, options.workers)
        if not rows:
            out.append(f"_{L['no_build']}_")
            out.append("")
            continue

        if options.format == "table":
            out.append(f"| {L['col_supply']} | {L['col_time']} | {L['col_action']} |")
            out.append("|--:|--:|---|")
            for e in rows:
                mark = " ⚡" if e["is_chronoboosted"] else ""
                out.append(f"| {e['supply']} | {e['time']} | {pretty(e['name'], lang)}{mark} |")
        elif options.format == "list":
            for i, e in enumerate(rows, 1):
                mark = " ⚡" if e["is_chronoboosted"] else ""
                out.append(f"{i}. `{e['supply']} {L['supply_unit']} · {e['time']}` "
                           f"{pretty(e['name'], lang)}{mark}")
        else:
            width = max(len(str(e["supply"])) for e in rows)
            out.append("```text")
            for e in rows:
                mark = f" ({L['chrono']})" if e["is_chronoboosted"] else ""
                out.append(f"{str(e['supply']).rjust(width)}  {e['time']:>5}  "
                           f"{pretty(e['name'], lang)}{mark}")
            out.append("```")
        out.append("")

        if options.workers != "all":
            produced = sum(1 for e in p["buildOrder"] if e["is_worker"])
            if produced:
                out.append("_" + L["workers_folded"].format(n=produced) + "_")
                out.append("")

        samples = stats.get(pid, [])
        eco = economy_rows(samples, fps, horizon, step)
        if eco and options.workers != "none":
            out.append(f"### {L['economy']}")
            out.append("")
            out.append(f"| {L['col_time']} | {L['col_supply']} | {L['col_workers']} "
                       f"| {L['col_minerals']} | {L['col_gas']} | {L['col_income']} |")
            out.append("|--:|--:|--:|--:|--:|--:|")
            for row in eco:
                out.append(
                    f"| {row['at']} | {row['food_used']}/{row['food_made']} | {row['workers']} "
                    f"| {row['minerals']} | {row['vespene']} "
                    f"| {row['mineral_rate']}/{row['vespene_rate']} |"
                )
            out.append("")

        blocks = supply_blocks(samples, fps, horizon)
        if blocks:
            out.append(f"**{L['supply_blocked']} —** {' · '.join(blocks)}")
            out.append("")

        abilities = [e for e in p["abilities"] if cutoff is None or seconds_of(e, fps) <= cutoff]
        if abilities:
            counts = Counter(ABILITY_LABELS.get(e["name"], pretty(e["name"], lang)) for e in abilities)
            out.append(f"**{L['macro']} —** " + " · ".join(f"{n} ×{c}" for n, c in counts.most_common()))
            out.append("")

        losses = [e for e in p["unitsLost"] if cutoff is None or seconds_of(e, fps) <= cutoff]
        # killer=None : mutation en bâtiment ou sabordage, pas une perte au combat.
        killed = [e for e in losses if e["killer"] is not None and e["killer"] != pid]
        if killed:
            out.append(f"**{L['losses']} ({len(killed)}) —** " + summarise(killed, lang, top=12))
            out.append("")

    return "\n".join(out).rstrip() + "\n"


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
