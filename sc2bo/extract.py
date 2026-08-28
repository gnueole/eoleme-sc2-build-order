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
RESULT_FR = {"Win": "Victoire", "Loss": "Défaite"}
ABILITY_LABELS = {
    "CalldownMULE": "MULE",
    "ChronoBoostEnergyCost": "Chrono Boost",
    "SpawnLarva": "Injection",
    "SupplyDrop": "Supply Drop",
    "ScannerSweep": "Scan",
}
SUPPLY_CAP_MAX = 200


class ReplayError(ValueError):
    """Le fichier n'est pas un replay exploitable."""


def pretty(name: str | None) -> str:
    """
    SupplyDepot -> Supply Depot ; SCV et « Combat Shields » restent intacts.
    Certaines unités Coop arrivent sans nom : on ne casse pas le rendu pour autant.
    """
    if not name:
        return "unité inconnue"
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


def summarise(entries: list[dict], top: int | None = None) -> str:
    counts = Counter(pretty(e["name"]) for e in entries)
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

    out.append(" · ".join([
        f"**Carte :** {data['map']}",
        f"**Durée :** {fmt_time(duration)}",
        f"**Joué le :** {played:%Y-%m-%d %H:%M} UTC",
        f"**Patch :** build {data['build']}",
        f"**Type :** {data.get('category', '?')} {data.get('game_type', '')}".strip(),
    ]))
    out.append("")

    for _, p in everyone:
        verdict = RESULT_FR.get(p["result"], p["result"] or "?")
        kind = "" if p["is_human"] else " *(IA)*"
        out.append(f"- **{p['name']}**{kind} — {p['race']} — {verdict}")
    out.append("")

    if cutoff and cutoff < duration:
        out.append(f"> Tronqué à {fmt_time(cutoff)} sur une partie de {fmt_time(duration)}.")
        out.append("")

    for pid, p in chosen:
        out.append(f"## {p['name']} — {p['race']}")
        out.append("")

        rows = build_order_rows(p, fps, cutoff, options.workers)
        if not rows:
            out.append("_Aucune construction enregistrée pour ce joueur._")
            out.append("")
            continue

        if options.format == "table":
            out.append("| Ravit. | Temps | Action |")
            out.append("|--:|--:|---|")
            for e in rows:
                mark = " ⚡" if e["is_chronoboosted"] else ""
                out.append(f"| {e['supply']} | {e['time']} | {pretty(e['name'])}{mark} |")
        elif options.format == "list":
            for i, e in enumerate(rows, 1):
                mark = " ⚡" if e["is_chronoboosted"] else ""
                out.append(f"{i}. `{e['supply']} ravit. · {e['time']}` {pretty(e['name'])}{mark}")
        else:
            width = max(len(str(e["supply"])) for e in rows)
            out.append("```text")
            for e in rows:
                mark = " (chrono)" if e["is_chronoboosted"] else ""
                out.append(f"{str(e['supply']).rjust(width)}  {e['time']:>5}  {pretty(e['name'])}{mark}")
            out.append("```")
        out.append("")

        if options.workers != "all":
            produced = sum(1 for e in p["buildOrder"] if e["is_worker"])
            if produced:
                out.append(f"_Les {produced} travailleurs produits sont résumés ci-dessous "
                           f"plutôt que listés ligne à ligne._")
                out.append("")

        samples = stats.get(pid, [])
        eco = economy_rows(samples, fps, horizon, step)
        if eco and options.workers != "none":
            out.append("### Économie")
            out.append("")
            out.append("| Temps | Ravit. | Travailleurs | Minerais | Gaz | Revenu min/gaz |")
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
            out.append(f"**Ravitaillement bloqué —** {' · '.join(blocks)}")
            out.append("")

        abilities = [e for e in p["abilities"] if cutoff is None or seconds_of(e, fps) <= cutoff]
        if abilities:
            counts = Counter(ABILITY_LABELS.get(e["name"], pretty(e["name"])) for e in abilities)
            out.append("**Macro —** " + " · ".join(f"{n} ×{c}" for n, c in counts.most_common()))
            out.append("")

        losses = [e for e in p["unitsLost"] if cutoff is None or seconds_of(e, fps) <= cutoff]
        # killer=None : mutation en bâtiment ou sabordage, pas une perte au combat.
        killed = [e for e in losses if e["killer"] is not None and e["killer"] != pid]
        if killed:
            out.append(f"**Pertes au combat ({len(killed)}) —** " + summarise(killed, top=12))
            out.append("")

    return "\n".join(out).rstrip() + "\n"


COACH_PROMPT = """\
Voici {subject} StarCraft II, extraite du replay. Analyse comme un coach :

1. Mes timings d'ouverture et mes ravitaillements tiennent-ils la route face à ce matchup ?
2. Ma courbe de travailleurs décroche-t-elle, et à quelle minute exactement ?
3. Que disent mes minerais en banque et mes blocages de ravitaillement sur ma macro ?
4. Qu'est-ce qui m'a coûté la partie, et quelles sont les deux corrections les plus rentables ?

Le symbole ⚡ marque une production accélérée au Chrono Boost. « Ravit. » donne le
ravitaillement utilisé sur la capacité disponible ; les deux se touchent quand la
production est à l'arrêt.

---

"""


def build_coach_prompt(count: int) -> str:
    subject = "une de mes parties" if count == 1 else f"{count} de mes parties"
    return COACH_PROMPT.format(subject=subject)
