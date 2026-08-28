"""
Map a build-order entry to a StarCraft II button icon.

The game names its icons in a shape that only half matches what spawningtool
reports, so a plain normalisation covers the units and buildings but misses most
upgrades. The rules below close that gap; `icons.json` is the generated index of
what is actually shipped in public/icons/.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_INDEX_PATH = Path(__file__).with_name("icons.json")

RACE_PREFIX = re.compile(r"^(terran|protoss|zerg)")

# Names the game spells in a way no rule reaches. Kept short on purpose: every
# entry here is a mapping nobody can derive, so each one has to be looked up.
ALIASES = {
    "voidray": "btn-unit-protoss-voidray-hero",
    "sensortower": "btn-building-terran-sensortower-silver",
    "barrackstechlab": "btn-building-terran-techlab",
    "factorytechlab": "btn-building-terran-techlab",
    "starporttechlab": "btn-building-terran-techlab",
    "barracksreactor": "btn-building-terran-reactor",
    "factoryreactor": "btn-building-terran-reactor",
    "starportreactor": "btn-building-terran-reactor",
}


@lru_cache(maxsize=1)
def index() -> dict[str, str]:
    try:
        return json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def normalise(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def candidates(name: str | None):
    """The keys worth trying, most specific first."""
    base = normalise(name)
    if not base:
        return
    yield base
    # "Terran Infantry Weapons Level 1" is filed as infantryweaponslevel1.
    stripped = RACE_PREFIX.sub("", base)
    if stripped and stripped != base:
        yield stripped
    # "Combat Shields" is filed as combatshield.
    for key in (base, stripped):
        if key.endswith("s"):
            yield key[:-1]
    # Zerg says "attacks" where spawningtool says "weapons":
    # "Zerg Melee Weapons Level 1" is filed as meleeattacks-level1.
    for key in (base, stripped):
        if "weapons" in key:
            yield key.replace("weapons", "attacks")


def icon_for(name: str | None) -> str | None:
    """The icon basename for a build-order entry, or None when we have none."""
    base = normalise(name)
    if base in ALIASES:
        return ALIASES[base]
    table = index()
    for key in candidates(name):
        if key in table:
            return table[key]
    return None
