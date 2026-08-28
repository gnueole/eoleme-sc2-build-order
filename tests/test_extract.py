"""
Tests des fonctions pures du moteur d'extraction.

Aucun replay n'est versionné : ce sont des parties privées, et un .SC2Replay
contient les pseudonymes des deux joueurs. Les tests qui ont besoin d'un vrai
fichier sont donc à lancer à la main via cli.py.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from sc2bo.extract import (
    LABELS,
    LANGUAGES,
    Options,
    ReplayError,
    build_coach_prompt,
    economy_rows,
    fmt_time,
    parse_time,
    labels,
    pretty,
    render_markdown,
    select_players,
    summarise,
    supply_blocks,
)


class TestPretty:
    def test_splits_camel_case(self):
        assert pretty("SupplyDepot") == "Supply Depot"
        assert pretty("BarracksTechLab") == "Barracks Tech Lab"

    def test_leaves_acronyms_alone(self):
        assert pretty("SCV") == "SCV"

    def test_leaves_already_spaced_names_alone(self):
        assert pretty("Terran Infantry Weapons Level 1") == "Terran Infantry Weapons Level 1"

    def test_survives_missing_name(self):
        # Certaines unités Coop arrivent sans nom ; le rendu ne doit pas casser.
        assert pretty(None) == "unité inconnue"
        assert pretty("") == "unité inconnue"


class TestTime:
    def test_formats(self):
        assert fmt_time(0) == "0:00"
        assert fmt_time(65) == "1:05"
        assert fmt_time(3600) == "60:00"

    def test_parses_both_notations(self):
        assert parse_time("8:00") == 480
        assert parse_time("480") == 480
        assert parse_time(" 12:34 ") == 754

    def test_rejects_nonsense(self):
        for bad in ["", "   ", "abc", "8:xx"]:
            with pytest.raises(ValueError):
                parse_time(bad)


class TestSupplyBlocks:
    def make(self, pairs):
        # (frame, utilisé, capacité) — 22.4 frames par seconde.
        return [{"frame": f, "food_used": u, "food_made": m} for f, u, m in pairs]

    def test_reports_a_sustained_block(self):
        samples = self.make([(0, 10, 15), (224, 15, 15), (448, 15, 15), (672, 16, 23)])
        assert supply_blocks(samples, 22.4, 120) == ["0:10→0:20"]

    def test_ignores_a_blip_shorter_than_the_minimum(self):
        samples = self.make([(0, 10, 15), (22, 15, 15), (44, 16, 23)])
        assert supply_blocks(samples, 22.4, 120) == []

    def test_ignores_the_200_cap(self):
        # Être à 200/200 n'est pas une erreur de joueur, c'est le plafond du jeu.
        samples = self.make([(0, 200, 200), (224, 200, 200), (448, 200, 200)])
        assert supply_blocks(samples, 22.4, 120) == []

    def test_closes_an_open_block_at_the_end(self):
        samples = self.make([(0, 10, 15), (224, 15, 15), (448, 15, 15)])
        assert supply_blocks(samples, 22.4, 120) == ["0:10→0:20"]


class TestEconomyRows:
    def test_reads_supply_and_workers_at_the_same_instant(self):
        # Le jeu n'échantillonne que toutes les 160 frames : la ligne d'une minute
        # doit reprendre le dernier relevé disponible, pas un mélange.
        samples = [
            {"frame": 1, "food_used": 12, "food_made": 15, "workers": 12,
             "minerals": 50, "vespene": 0, "mineral_rate": 0, "vespene_rate": 0},
            {"frame": 1280, "food_used": 13, "food_made": 23, "workers": 13,
             "minerals": 120, "vespene": 0, "mineral_rate": 615, "vespene_rate": 0},
            {"frame": 2688, "food_used": 17, "food_made": 31, "workers": 16,
             "minerals": 320, "vespene": 100, "mineral_rate": 643, "vespene_rate": 156},
        ]
        rows = economy_rows(samples, 22.4, 120, 60)
        assert [r["at"] for r in rows] == ["1:00", "2:00"]
        assert rows[0]["food_used"] == 13 and rows[0]["workers"] == 13
        assert rows[1]["food_used"] == 17 and rows[1]["workers"] == 16

    def test_no_samples_means_no_table(self):
        assert economy_rows([], 22.4, 600, 60) == []


class TestSelectPlayers:
    def data(self, players):
        return {"players": players}

    def test_two_players_returns_both(self):
        d = self.data({1: {"name": "Éole", "is_human": True}, 2: {"name": "sirhill", "is_human": True}})
        assert [pid for pid, _ in select_players(d, [], False)] == [1, 2]

    def test_many_players_keeps_only_humans(self):
        # En Coop, les forces d'Amon ne sont pas des adversaires à analyser.
        d = self.data({
            1: {"name": "Éole", "is_human": True},
            2: {"name": "Arkenston", "is_human": True},
            3: {"name": "Amon's Forces", "is_human": False},
            4: {"name": "Civilians", "is_human": False},
        })
        assert [pid for pid, _ in select_players(d, [], False)] == [1, 2]

    def test_all_players_overrides(self):
        d = self.data({
            1: {"name": "Éole", "is_human": True},
            2: {"name": "Amon's Forces", "is_human": False},
            3: {"name": "Civilians", "is_human": False},
        })
        assert len(select_players(d, [], True)) == 3

    def test_selects_by_partial_name_and_by_number(self):
        d = self.data({1: {"name": "Éole", "is_human": True}, 2: {"name": "sirhill", "is_human": True}})
        assert [pid for pid, _ in select_players(d, ["sir"], False)] == [2]
        assert [pid for pid, _ in select_players(d, ["1"], False)] == [1]

    def test_unknown_player_names_the_alternatives(self):
        d = self.data({1: {"name": "Éole", "is_human": True}, 2: {"name": "sirhill", "is_human": True}})
        with pytest.raises(ReplayError, match="sirhill"):
            select_players(d, ["zzz"], False)


class TestSummarise:
    def test_counts_and_orders(self):
        entries = [{"name": "Marine"}, {"name": "Marine"}, {"name": "Medivac"}]
        assert summarise(entries) == "Marine ×2 · Medivac"


class TestCoachPrompt:
    def test_singular_and_plural(self):
        assert "une de mes parties" in build_coach_prompt(1)
        assert "3 de mes parties" in build_coach_prompt(3)


class TestOptions:
    def test_defaults_are_safe(self):
        o = Options()
        assert o.player == [] and o.workers == "summary" and o.format == "table"

    def test_player_lists_are_not_shared_between_instances(self):
        a, b = Options(), Options()
        a.player.append("Éole")
        assert b.player == []


class TestLanguages:
    def test_both_catalogues_hold_the_same_keys(self):
        # Une clé oubliée d'un côté produit un libellé en dur dans l'autre langue.
        assert set(LABELS["fr"]) == set(LABELS["en"])

    def test_unknown_language_falls_back_to_french(self):
        assert labels("de") is LABELS["fr"]
        assert LANGUAGES == ("fr", "en")

    def test_missing_unit_name_follows_the_language(self):
        assert pretty(None, "fr") == "unité inconnue"
        assert pretty(None, "en") == "unknown unit"

    def test_camel_case_splitting_is_language_agnostic(self):
        assert pretty("SupplyDepot", "en") == pretty("SupplyDepot", "fr") == "Supply Depot"

    def test_french_keeps_the_space_before_colons(self):
        # Règle typographique française ; l'anglais ne la suit pas.
        assert LABELS["fr"]["colon"] == " :"
        assert LABELS["en"]["colon"] == ":"


class TestCoachPromptLanguages:
    def test_english_singular_and_plural_are_grammatical(self):
        one = build_coach_prompt(1, "en")
        many = build_coach_prompt(3, "en")
        assert one.startswith("Here is one of my StarCraft II games")
        assert many.startswith("Here are 3 of my StarCraft II games")

    def test_french_agrees_in_number(self):
        assert "extraite du replay" in build_coach_prompt(1, "fr")
        assert "extraites du replay" in build_coach_prompt(4, "fr")

    def test_unknown_language_falls_back(self):
        assert build_coach_prompt(1, "de") == build_coach_prompt(1, "fr")

    def test_both_languages_explain_the_chrono_symbol(self):
        for lang in LANGUAGES:
            assert "⚡" in build_coach_prompt(1, lang)


class TestOptionsLanguage:
    def test_defaults_to_french(self):
        assert Options().lang == "fr"

    def test_summarise_follows_the_language(self):
        entries = [{"name": None}, {"name": None}]
        assert summarise(entries, "en") == "unknown unit ×2"
        assert summarise(entries, "fr") == "unité inconnue ×2"


class TestReportContract:
    """
    Le HTML du client se construit à partir des libellés que le serveur renvoie.
    Si une clé disparaît côté Python, l'affichage casse sans que rien ne le dise :
    ce test relie les deux.
    """

    def client_keys(self):
        app = Path(__file__).resolve().parents[1] / "public" / "js" / "app.js"
        source = app.read_text(encoding="utf-8")
        # L.duration, L["col_time"], et les clés listées pour l'entête d'économie.
        keys = set(re.findall(r"\bL\.([a-z_]+)\b", source))
        keys |= set(re.findall(r'\bL\["([a-z_]+)"\]', source))
        keys |= set(re.findall(r'"(col_[a-z_]+)"', source))
        return keys

    def test_every_label_the_page_uses_exists_in_both_languages(self):
        missing_fr = sorted(self.client_keys() - set(LABELS["fr"]))
        missing_en = sorted(self.client_keys() - set(LABELS["en"]))
        assert not missing_fr, f"libellés absents en fr : {missing_fr}"
        assert not missing_en, f"libellés absents en en : {missing_en}"

    def test_the_page_actually_uses_labels(self):
        # Garde-fou du garde-fou : si l'extraction ne trouve rien, le test au-dessus
        # passerait pour de mauvaises raisons.
        assert len(self.client_keys()) >= 10


class TestRenderMarkdownFromReport:
    def report(self):
        return {
            "lang": "fr", "map": "Ley Lines", "matchup": "TvZ", "duration": "12:30",
            "played": "2026-08-28 15:00", "build": 97563, "category": "Ladder",
            "game_type": "1v1", "cutoff": None,
            "roster": [
                {"name": "Éole", "race": "Terran", "result": "Victoire", "won": True, "is_human": True},
                {"name": "A.I.", "race": "Zerg", "result": "Défaite", "won": False, "is_human": False},
            ],
            "sections": [{
                "name": "Éole", "race": "Terran", "result": "Victoire", "won": True, "is_human": True,
                "build": [
                    {"supply": 14, "time": "0:20", "action": "Supply Depot", "chrono": False, "worker": False},
                    {"supply": 16, "time": "0:42", "action": "Barracks", "chrono": True, "worker": False},
                ],
                "workers_folded": 12,
                "economy": [{"at": "1:00", "food_used": 15, "food_made": 15, "workers": 15,
                             "minerals": 120, "vespene": 0, "mineral_rate": 615, "vespene_rate": 0}],
                "supply_blocks": ["0:55→1:10"],
                "macro": [{"name": "MULE", "count": 3}],
                "losses": {"total": 2, "items": [{"name": "Marine", "count": 2}]},
            }],
        }

    def test_table_format_carries_every_section(self):
        md = render_markdown(self.report(), Options(format="table"))
        assert "# Ley Lines — TvZ" in md
        assert "| 14 | 0:20 | Supply Depot |" in md
        assert "⚡" in md                      # le chrono est signalé
        assert "### Économie" in md
        assert "Ravitaillement bloqué" in md
        assert "MULE ×3" in md
        assert "Pertes au combat (2)" in md
        assert "Les 12 travailleurs produits" in md

    def test_raw_format_aligns_the_columns(self):
        md = render_markdown(self.report(), Options(format="raw"))
        assert "```text" in md
        assert "(chrono)" in md

    def test_list_format_numbers_the_steps(self):
        md = render_markdown(self.report(), Options(format="list"))
        assert "1. `14 ravit. · 0:20` Supply Depot" in md

    def test_a_missing_matchup_leaves_the_heading_bare(self):
        r = self.report()
        r["matchup"] = None
        assert render_markdown(r, Options()).startswith("# Ley Lines\n")

    def test_english_report_uses_english_labels(self):
        r = self.report()
        r["lang"] = "en"
        md = render_markdown(r, Options(lang="en"))
        assert "**Map:**" in md and "### Economy" in md
