#!/usr/bin/env python3
#
# Place Completer - a Gramps tool that completes the hierarchy of a place
# from the answer of an AI (type, levels with years, coordinates)
#
# Copyright (C) 2026       Avi Markovitz <avi.markovitz@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
"""The form "table": a short question, a table answer, read into the lines of the core (TB1-TB6 of docs/ANALYZER_RULES.md)."""
import os
import sys
import tempfile
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, prompts, session as sess, table                            # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
import test_citations                                                                         # noqa: E402
import test_ingest as ti                                                                      # noqa: E402

CANTON = "\u05e7\u05e0\u05d8\u05d5\u05df"
EXPLANATION = "\u05d4\u05e1\u05d1\u05e8 \u05e7\u05e6\u05e8"                                    # a short explanation in Hebrew


def tsv(rows, part_one=None, header="Category\tValue/Name\tYear Range\tLevel Type\tExplanation\tSource"):
    lines = list(part_one if part_one is not None else ["Name: Aussonne | Language: fr | From: UNKNOWN | Source: https://fr.wikipedia.org/wiki/Aussonne",
                                                        "Alternatives: NONE", ""])
    lines.append(header)
    lines += ["\t".join(row) for row in rows]
    return "\n".join(lines) + "\n"


ROWS = [("Place Type", "town", "", "", EXPLANATION, "https://fr.wikipedia.org/wiki/Aussonne"),
        ("Level 1", "Canton de Grenade", "1801-2015", "other (canton)", EXPLANATION, "https://fr.wikipedia.org/wiki/Canton_de_Grenade"),
        ("Level 2", "Arrondissement de Toulouse", "1800-present", "district", EXPLANATION, ""),
        ("Level 3", "Haute-Garonne", "1790-present", "department", EXPLANATION, ""),
        ("Level 4", "Midi-Pyr\u00e9n\u00e9es", "1982-2015", "region", EXPLANATION, ""),
        ("Sovereign state", "Republic of France", "1958-present", "country", EXPLANATION, ""),
        ("Latitude", "43.6847", "", "", EXPLANATION, "https://en.wikipedia.org/wiki/Aussonne"),
        ("Longitude", "1.3206", "", "", EXPLANATION, "https://en.wikipedia.org/wiki/Aussonne")]

EXPECTED = """PLACE_NAME_ON_DATE: Aussonne
LANGUAGE: fr
SETTLEMENT_TYPE_ON_DATE: town
COORDINATES: 43.6847, 1.3206
CONTAINERS:
1 | Canton de Grenade | canton | 1801-2015 | Republic of France
2 | Arrondissement de Toulouse | district | 1800-present | Republic of France
3 | Haute-Garonne | department | 1790-present | Republic of France
4 | Midi-Pyr\u00e9n\u00e9es | region | 1982-2015 | Republic of France
5 | Republic of France | sovereign state | 1958-present | Republic of France
STATE_ON_DATE: Republic of France | 1958-present
NOTES: NONE
SOURCES: https://en.wikipedia.org/wiki/Aussonne | COORDINATES
SOURCES: https://fr.wikipedia.org/wiki/Aussonne | PLACE_NAME_ON_DATE, SETTLEMENT_TYPE_ON_DATE
SOURCES: https://fr.wikipedia.org/wiki/Canton_de_Grenade | CONTAINERS
NOT_SURE: NONE
"""


class ConvertTests(unittest.TestCase):
    def test_the_answer_as_it_is_copied_becomes_the_lines_of_the_core(self):
        out, notes = table.convert(tsv(ROWS))
        self.assertEqual(sorted(out.splitlines()), sorted(EXPECTED.splitlines()))
        self.assertEqual(notes, [])

    def test_a_markdown_table_with_bars_is_read_the_same(self):
        lines = ["Name: Aussonne | Language: fr | From: UNKNOWN | Source: https://fr.wikipedia.org/wiki/Aussonne", "Alternatives: NONE", "",
                 "| Category | Value/Name | Year Range | Level Type | Explanation | Source |", "|---|---|---|---|---|---|"]
        lines += ["| " + " | ".join(row) + " |" for row in ROWS]
        out, _notes = table.convert("\n".join(lines))
        self.assertEqual(sorted(out.splitlines()), sorted(EXPECTED.splitlines()))

    def test_the_answer_that_has_only_part_two_is_read_with_the_place_that_was_asked(self):
        out, _notes = table.convert(tsv(ROWS, part_one=[""]), place="Aussonne")
        self.assertTrue(out.startswith("PLACE_NAME_ON_DATE: Aussonne\n"))

    def test_the_years_are_written_in_the_form_of_the_core(self):
        for written, wanted in (("1800-present", "1800-present"), ("1801 \u2013 2015", "1801-2015"), ("-1800 present", "1800-present"), ("1800 present", "1800-present"),
                                ("2015-\u05d4\u05d5\u05d5\u05d4", "2015-present"), ("1982-2015", "1982-2015"), ("", "UNKNOWN"), ("1790-now", "1790-present")):
            self.assertEqual(table._years(written), wanted, written)

    def test_the_type_of_a_level_is_the_generic_word_or_the_local_term_of_other(self):
        self.assertEqual([table._generic(t) for t in ("other (canton)", "department", "District", "other (Arrondissement)", "other", "")],
                         ["canton", "department", "district", "arrondissement", "unit", "unit"])

    def test_a_level_without_a_type_is_read_and_said(self):
        rows = [r if r[0] != "Level 2" else (r[0], r[1], r[2], "", r[4], r[5]) for r in ROWS]
        out, notes = table.convert(tsv(rows))
        self.assertIn("2 | Arrondissement de Toulouse | unit | 1800-present | Republic of France", out)
        self.assertEqual(notes, [("administrative level %d (%s) lacks type classification in response", (2, "Arrondissement de Toulouse"))])

    def test_a_site_that_is_not_an_address_is_said_and_not_cited(self):
        rows = [(r[0], r[1], r[2], r[3], r[4], "wikipedia.org") for r in ROWS]
        out, notes = table.convert(tsv(rows, part_one=["Name: Aussonne | Language: fr | From: UNKNOWN | Source: wikipedia.org", "Alternatives: NONE", ""]))
        self.assertNotIn("SOURCES:", out)
        self.assertEqual(notes, [("response references domain (%s) rather than direct page URL; citation omitted", ("wikipedia.org",))])

    def test_an_address_inside_a_markdown_link_is_the_address(self):
        rows = [(r[0], r[1], r[2], r[3], r[4], "[Wikipedia](https://en.wikipedia.org/wiki/Aussonne)" if r[0] == "Place Type" else "") for r in ROWS]
        out, _notes = table.convert(tsv(rows))
        self.assertIn("SOURCES: https://en.wikipedia.org/wiki/Aussonne | SETTLEMENT_TYPE_ON_DATE", out)

    def test_the_other_places_and_the_year_of_the_name_are_said_and_not_written(self):
        part_one = ["Name: Aussonne | Language: fr | From: 1200 | Source: https://fr.wikipedia.org/wiki/Aussonne",
                    "Alternatives: Aussonne | Gers | France; Ausson | Haute-Garonne | France", ""]
        out, notes = table.convert(tsv(ROWS, part_one=part_one))
        messages = [n[0] for n in notes]
        self.assertEqual(len(notes), 2)
        self.assertTrue(any("is active from" in m for m in messages) and any("alternative locations matching name" in m for m in messages))
        self.assertNotIn("1200", out)                                                          # nothing of it reaches the tree

    def test_a_coordinate_with_a_comma_for_the_decimal_point_is_read(self):
        rows = [(r[0], "43,6847" if r[0] == "Latitude" else "1,3206" if r[0] == "Longitude" else r[1]) + r[2:] for r in ROWS]
        out, _notes = table.convert(tsv(rows))
        self.assertIn("COORDINATES: 43.6847, 1.3206", out)

    def test_what_is_not_a_table_answer_is_left_alone(self):
        for text in ("PLACE_NAME_ON_DATE: Blagnac\nCOORDINATES: 1.0, 2.0\n", "Hello, no table here.", "", None):
            self.assertEqual(table.convert(text), (text, []))
        empty = "Category\tValue/Name\tYear Range\tLevel Type\tExplanation\tSource\n"            # the question given back: a header and no rows
        self.assertEqual(table.convert(empty), (empty, []))

    def test_the_converted_text_is_read_by_the_core(self):
        out, _notes = table.convert(tsv(ROWS))
        rec = ingest.parse_structured(out)
        self.assertEqual((rec["name"], rec["type_value"], rec["type_closed"], rec["coordinates"], rec["language"]), ("Aussonne", 15, True, (43.6847, 1.3206), "fr"))
        self.assertEqual([(c["name"], c["type"], c["from"], c["to"]) for c in rec["containers"]],
                         [("Canton de Grenade", "canton", "1801", "2015"), ("Arrondissement de Toulouse", "district", "1800", None),
                          ("Haute-Garonne", "department", "1790", None), ("Midi-Pyr\u00e9n\u00e9es", "region", "1982", "2015"),
                          ("Republic of France", "sovereign state", "1958", None)])


class QuestionTests(unittest.TestCase):
    def test_the_table_is_the_first_form_that_is_asked(self):
        self.assertEqual(prompts.AUTO_ORDER[0], "table")
        self.assertIn("table", prompts.FORMS)
        self.assertEqual(set(prompts.AUTO_ORDER), set(prompts.FORMS))

    def test_the_question_is_short_and_has_the_place_the_year_and_the_language_of_the_explanation(self):
        text = prompts.build_prompt("Aussonne", "1997", "table", language="he")
        self.assertIn("settlement Aussonne in 1997", text)
        self.assertIn("ISO code he", text)
        self.assertIn("ISO code en", prompts.build_prompt("Aussonne", "1997", "table"))
        self.assertLess(len(text), 2300)

    def test_the_question_gives_the_columns_the_rows_and_the_closed_lists(self):
        text = prompts.build_prompt("Aussonne", "1997", "table")
        self.assertIn("Category | Value/Name | Year Range | Level Type | Explanation | Source", text)
        self.assertIn("Place Type, Level 1, Level 2, ..., Sovereign state, Latitude, Longitude", text)
        self.assertIn("metropolis (over about 500,000 inhabitants) | city (30,000-500,000) | town (2,000-30,000) | village (100-2,000) | hamlet (under 100)", text)
        self.assertIn("country | state | region | province | department | county | district | municipality | other", text)
        for word in ingest.SETTLEMENT_CLASSES:
            if word not in ("neighborhood", "locality"):                                      # the two parts of a city and the places that are not settlements: the old forms
                self.assertIn(word, text, word)

    def test_the_first_level_is_the_unit_above_the_place_and_not_the_place_itself(self):
        text = prompts.build_prompt("Aussonne", "1997", "table")
        self.assertIn("Level 1 is the unit directly ABOVE the settlement", text)
        self.assertIn("do not list the settlement itself, or a municipality with the same name", text)
        self.assertLess(len(text), 2300)

    def test_the_question_keeps_the_legal_status_out_of_the_type_and_the_levels_nested(self):
        text = prompts.build_prompt("Aussonne", "1997", "table")
        self.assertIn("legal status of the place (for example commune) belongs only here", text)
        self.assertIn("only levels that nest inside each other", text)
        self.assertIn("full URL, written out as visible text", text)

    def test_nothing_is_left_unfilled_and_the_question_given_back_is_known_as_such(self):
        text = prompts.build_prompt("Aussonne", "1997", "table")
        self.assertNotRegex(text, r"\{[a-z_]+\}")
        self.assertTrue(prompts.looks_like_echo(text))


def french_tree():
    t = Tree({"fr": ti.typed("fr", "Republic of France", 1, lang="en"), "mp": ti.typed("mp", "Midi-Pyr\u00e9n\u00e9es", 9, lang="fr"),
              "hg": ti.typed("hg", "Haute-Garonne", 10, lang="fr")}, [])
    for handle, parent in {"mp": "fr", "hg": "mp"}.items():
        t.places[handle]["refs"] = [{"ref": parent, "date": EMPTY}]
    return t


class SessionTests(unittest.TestCase):
    def read(self, tree=None, text=None):
        s = sess.Session(tree or french_tree(), tempfile.mkdtemp(), pack_files=[ti.WORLD])
        s.begin("Aussonne", "1997", engine="manual")
        s.receive(text or tsv(ROWS))
        return s

    def test_the_table_is_analysed_like_any_other_answer(self):
        s = self.read()
        self.assertEqual(s.result["child"], "new:ai-aussonne")
        made = {p["names"][0]["value"]: p for p in s.plan["proposals"] if p["kind"] == "add-place"}
        self.assertEqual((made["Aussonne"]["type_value"], made["Aussonne"]["type_string"]), (15, ""))                   # a town, whatever its legal status
        self.assertEqual(made["Canton de Grenade"]["type_string"], CANTON)                                                 # the rule of the tree for a canton
        self.assertEqual(made["Arrondissement de Toulouse"]["type_value"], 12)                                           # district
        self.assertNotIn("Haute-Garonne", made)                                                                            # it is in the tree
        self.assertNotIn("Midi-Pyr\u00e9n\u00e9es", made)

    def test_what_the_answer_gave_and_is_not_written_is_said_with_the_other_needs(self):
        rows = [(r[0], r[1], r[2], r[3], r[4], "wikipedia.org") for r in ROWS]
        text = tsv(rows, part_one=["Name: Aussonne | Language: fr | From: 1200 | Source: wikipedia.org", "Alternatives: NONE", ""])
        s = self.read(text=text)
        needs = " | ".join(text for text, _level in s.needs())
        self.assertIn("references domain (wikipedia.org) rather than direct page", needs)
        self.assertIn("is active from 1200", needs)

    def test_the_answer_that_is_saved_is_the_one_the_core_reads(self):
        s = self.read()
        with open(s.saved_path, encoding="utf-8") as fh:
            saved = fh.read()
        self.assertTrue(saved.startswith("PLACE_NAME_ON_DATE: Aussonne"))
        self.assertEqual(ingest.parse_structured(saved)["name"], "Aussonne")

    def test_the_ask_carries_the_table_question_first(self):
        s = sess.Session(french_tree(), tempfile.mkdtemp(), pack_files=[ti.WORLD])
        action = s.begin("Aussonne", "1997", engine="google")
        self.assertEqual(action["form"], "table")
        question = urllib.parse.parse_qs(urllib.parse.urlparse(action["url"]).query)["q"][0]
        self.assertIn("Category | Value/Name | Year Range", question)

    def test_a_table_given_back_instead_of_an_answer_moves_to_the_next_form(self):
        s = sess.Session(french_tree(), tempfile.mkdtemp(), pack_files=[ti.WORLD])
        s.begin("Aussonne", "1997", engine="google")
        action = s.receive(prompts.build_prompt("Aussonne", "1997", "table"))
        self.assertEqual((action["action"], action["next"]["form"]), ("retry", "classic"))


class WrittenTests(unittest.TestCase):
    def test_the_levels_the_types_and_the_chain_are_written_and_a_second_run_changes_nothing(self):
        helper = test_citations.DatabaseTests("test_what_is_skipped_is_not_cited")
        db = helper.open(french_tree())
        for run in (1, 2):
            s = sess.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[ti.WORLD])
            s.begin("Aussonne", "1997", engine="manual")
            s.receive(tsv(ROWS))
            if run == 2:
                self.assertEqual([p["kind"] for p in s.plan["proposals"] if p["kind"] in ("add-place", "change-type", "set-type")], [])
                break
            s.toggle_all()
            s.apply(db)
        found = {}
        for handle in db.get_place_handles():
            place = db.get_place_from_handle(handle)
            kind = place.get_type()
            found[place.get_name().get_value()] = (kind.value or kind.string,
                                                   [db.get_place_from_handle(r.ref).get_name().get_value() for r in place.get_placeref_list()])
        self.assertEqual(found["Aussonne"], (15, ["Canton de Grenade"]))
        self.assertEqual(found["Canton de Grenade"], (CANTON, ["Arrondissement de Toulouse"]))
        self.assertEqual(found["Arrondissement de Toulouse"], (12, ["Haute-Garonne"]))
        self.assertEqual(found["Haute-Garonne"][0], 10)
        place = db.get_place_from_handle(next(h for h in db.get_place_handles() if db.get_place_from_handle(h).get_name().get_value() == "Aussonne"))
        self.assertEqual((place.get_latitude(), place.get_longitude()), ("43.6847", "1.3206"))


if __name__ == "__main__":
    unittest.main()
