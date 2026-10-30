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
"""Two levels with one name are two places (a canton and the commune that is its seat); an intercommunality is not a level of the chain."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, prompts, session as sess                                   # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
import test_citations                                                                         # noqa: E402
import test_ingest as ti                                                                      # noqa: E402

CANTON = "\u05e7\u05e0\u05d8\u05d5\u05df"
TOWN = 15

ANSWER = """PLACE_NAME_ON_DATE: Blagnac
LANGUAGE: fr
OTHER_NAMES: oc: Blanhac (1975-present)
SETTLEMENT_TYPE_ON_DATE: town | commune
COORDINATES: 43.6364, 1.3906
CONTAINERS:
1 | %(canton)s | canton and canton | 2015-present | Republic of France
2 | Toulouse M\u00e9tropole | intercommunality and m\u00e9tropole | 2015-present | Republic of France
3 | Arrondissement de Toulouse | district and arrondissement | 1800-present | Republic of France
4 | Haute-Garonne | county and d\u00e9partement | 1790-present | Republic of France
5 | Occitanie | region and r\u00e9gion | 2016-present | Republic of France
6 | Republic of France | sovereign state and pays | 1958-present | Republic of France
STATE_ON_DATE: Republic of France | 1958-present
NOTES: NONE
SOURCES: https://fr.wikipedia.org/wiki/Blagnac | SETTLEMENT_TYPE_ON_DATE, CONTAINERS
NOT_SURE: NONE
"""


def answer(canton="Canton de Blagnac"):
    return ANSWER % {"canton": canton}


def tree(with_commune=False):
    t = Tree({"fr": ti.typed("fr", "France", 1, lang="fr"), "occ": ti.typed("occ", "Occitanie", 9, lang="fr"),
              "hg": ti.typed("hg", "Haute-Garonne", 0, "D\u00e9partement", lang="fr"),
              "arr": ti.typed("arr", "Arrondissement de Toulouse", 0, "Arrondissement", lang="fr")}, [])
    parents = {"occ": "fr", "hg": "occ", "arr": "hg"}
    if with_commune:
        t.places["bla"] = ti.typed("bla", "Blagnac", 14, lang="fr")
        parents["bla"] = "arr"
    for handle, parent in parents.items():
        t.places[handle]["refs"] = [{"ref": parent, "date": EMPTY}]
    return t


def made(screen):
    return [p for p in screen["proposals"] if p["kind"] == "add-place"]


class OverlapTests(unittest.TestCase):
    def test_an_intercommunality_is_left_out_of_the_levels_and_the_answer_says_so(self):
        rec = ingest.parse_structured(answer())
        self.assertNotIn("Toulouse M\u00e9tropole", [c["name"] for c in rec["containers"]])
        self.assertEqual(len(rec["containers"]), 5)
        self.assertTrue(any("Toulouse M\u00e9tropole" in note and "overlaps" in note for note in rec["unit_notes"]))

    def test_a_metropolitan_city_that_is_a_real_level_is_kept(self):
        text = answer().replace("intercommunality and m\u00e9tropole", "metropolitan city and citt\u00e0 metropolitana")
        rec = ingest.parse_structured(text)
        self.assertIn("Toulouse M\u00e9tropole", [c["name"] for c in rec["containers"]])

    def test_the_chain_goes_from_the_canton_straight_to_the_arrondissement(self):
        screen = ingest.ingest(tree(), ingest.parse_structured(answer()), "2026")
        self.assertEqual([p["names"][0]["value"] for p in made(screen)], ["Blagnac", "Canton de Blagnac"])

    def test_every_form_of_the_question_asks_for_nested_divisions_only(self):
        for form in ("classic", "short", "dated", "long"):
            self.assertIn("nest", prompts.build_prompt("Blagnac", "2026", form), form)


class SameNameTests(unittest.TestCase):
    NAMES = ("Blagnac", "Blagnac (canton)")

    def test_a_canton_named_like_the_commune_is_a_place_of_its_own(self):
        for name in self.NAMES:
            screen = ingest.ingest(tree(), ingest.parse_structured(answer(name)), "2026")
            places = made(screen)
            self.assertEqual(len({p["handle"] for p in places}), len(places), name)               # one key for each place
            commune = next(p for p in places if p["handle"] == screen["child"])
            self.assertEqual((commune["names"][0]["value"], commune["type_value"], commune["type_string"]), ("Blagnac", TOWN, ""), name)
            canton = next(p for p in places if p["handle"] != screen["child"])
            self.assertEqual((canton["type_value"], canton["type_string"]), (0, CANTON), name)

    def test_the_commune_is_inside_its_canton_and_the_canton_is_not_the_commune(self):
        screen = ingest.ingest(tree(), ingest.parse_structured(answer("Blagnac")), "2026")
        canton = next(p["handle"] for p in made(screen) if p["handle"] != screen["child"])
        link = next(p for p in screen["proposals"] if p["kind"] == "add-link" and p["child"] == screen["child"])
        self.assertEqual(link["parent"], canton)

    def test_the_answer_says_that_a_level_has_the_name_of_the_place(self):
        screen = ingest.ingest(tree(), ingest.parse_structured(answer("Blagnac")), "2026")
        self.assertTrue(any("matches the name of child place" in n for n in screen["needs"]))
        screen = ingest.ingest(tree(), ingest.parse_structured(answer("Canton de Blagnac")), "2026")
        self.assertFalse(any("matches the name of child place" in n for n in screen["needs"]))

    def test_a_commune_that_exists_is_never_taken_for_its_canton(self):
        screen = ingest.ingest(tree(with_commune=True), ingest.parse_structured(answer("Blagnac")), "2026")
        self.assertEqual(screen["child"], "bla")
        canton = next(p for p in made(screen) if p["type_string"] == CANTON)
        self.assertNotEqual(canton["handle"], "bla")
        for p in screen["proposals"]:
            if p["kind"] in ("set-type", "change-type") and p.get("place") == "bla":
                self.assertEqual(p["type_value"], TOWN)                                           # the commune may become a Town; never a canton

    def test_a_province_with_the_name_of_the_city_is_not_a_candidate_for_the_city(self):
        t = tree()
        t.places["pp"] = ti.typed("pp", "Parma", 8, lang="it")                                      # the province
        t.places["pc"] = ti.typed("pc", "Parma", 4, lang="it")                                      # the city
        rec = ingest.parse_structured(answer().replace("Blagnac", "Parma").replace("town | commune", "city | comune"))
        screen = ingest.ingest(t, rec, "2026")
        self.assertEqual(screen["child"], "pc")
        self.assertFalse(any("match this name: select target place" in n for n in screen["needs"]))
        t.places["pc2"] = ti.typed("pc2", "Parma", 15, lang="it")                                   # two settlements of the name: the window still asks
        screen = ingest.ingest(t, rec, "2026")
        self.assertTrue(any("match this name: select target place" in n for n in screen["needs"]))

    def test_the_same_name_with_the_same_type_is_still_one_place(self):
        text = answer().replace("3 | Arrondissement de Toulouse | district and arrondissement", "3 | Haute-Garonne | county and d\u00e9partement")
        screen = ingest.ingest(tree(), ingest.parse_structured(text), "2026")
        names = [p["names"][0]["value"] for p in made(screen)]
        self.assertEqual(len(names), len(set(names)))


class WrittenTests(unittest.TestCase):
    """Written to a real database: the commune is a Town inside its canton, whatever the canton is called."""
    def run_answer(self, text, with_commune=False):
        helper = test_citations.DatabaseTests("test_what_is_skipped_is_not_cited")
        db = helper.open(tree(with_commune))
        s = sess.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[ti.WORLD])
        s.begin("Blagnac", "2026", engine="manual")
        s.receive(text)
        s.toggle_all()
        s.apply(db)
        found = {}
        for handle in db.get_place_handles():
            place = db.get_place_from_handle(handle)
            kind = place.get_type()
            parents = [db.get_place_from_handle(r.ref).get_name().get_value() for r in place.get_placeref_list()]
            found.setdefault(place.get_name().get_value(), []).append((kind.value or kind.string, parents))
        return found

    def test_the_pasted_answer_gives_a_town_in_its_canton_and_no_intercommunality(self):
        found = self.run_answer(answer())
        self.assertEqual(found["Blagnac"], [(TOWN, ["Canton de Blagnac"])])
        self.assertEqual(found["Canton de Blagnac"], [(CANTON, ["Arrondissement de Toulouse"])])
        self.assertNotIn("Toulouse M\u00e9tropole", found)

    def test_a_canton_with_the_name_of_the_commune_does_not_turn_the_commune_into_a_canton(self):
        found = self.run_answer(answer("Blagnac"))
        self.assertCountEqual([kind for kind, _parents in found["Blagnac"]], [TOWN, CANTON])                         # two places that share a name
        town = next(entry for entry in found["Blagnac"] if entry[0] == TOWN)
        self.assertEqual(town[1], ["Blagnac"])                                                    # inside the canton that has its name

    def test_the_second_run_on_the_same_answer_changes_nothing(self):
        helper = test_citations.DatabaseTests("test_what_is_skipped_is_not_cited")
        db = helper.open(tree())
        for run in (1, 2):
            s = sess.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[ti.WORLD])
            s.begin("Blagnac", "2026", engine="manual")
            s.receive(answer("Blagnac"))
            if run == 2:
                self.assertEqual([p["kind"] for p in s.plan["proposals"] if p["kind"] in ("add-place", "change-type", "set-type")], [])
                break
            s.toggle_all()
            s.apply(db)


if __name__ == "__main__":
    unittest.main()
