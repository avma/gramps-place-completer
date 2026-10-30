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
"""The data files (data/): what the code reads from them, and what it does when they are missing or damaged."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import data as datalib, ingest, prompts                                   # noqa: E402
from placecompleter.model import Tree                                                           # noqa: E402
from test_ingest import typed                                                                   # noqa: E402


class LoadTests(unittest.TestCase):
    def folder(self, **files):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name, text in files.items():
            with open(os.path.join(tmp.name, name.replace("_", "-") + ".json"), "w", encoding="utf-8") as fh:
                fh.write(text)
        return tmp.name

    def test_a_file_is_read(self):
        self.assertEqual(datalib.load("x.json", None, self.folder(x='{"a": 1}')), {"a": 1})

    def test_a_missing_or_damaged_file_gives_the_default(self):
        self.assertEqual(datalib.load("nothing.json", {"d": 1}, self.folder()), {"d": 1})
        self.assertEqual(datalib.load("bad.json", [], self.folder(bad="{not json")), [])

    def test_the_shipped_files_are_json_with_a_description(self):
        for name in ("type-conventions.json", "no-answer-phrases.json"):
            with open(os.path.join(datalib.DATA_DIR, name), encoding="utf-8") as fh:
                self.assertTrue(json.load(fh)["description"], name)


class TreeTypesTests(unittest.TestCase):
    def test_the_shipped_conventions_are_read(self):
        types = ingest.load_tree_types()
        self.assertTrue(types["province"] and types["empire"] and types["monarchy"])
        self.assertEqual(len(types["district"]), 2)

    def test_without_the_file_the_types_of_gramps_are_used(self):
        empty = {"province": "", "empire": "", "monarchy": "", "district": [], "rules": [], "settlements": []}
        self.assertEqual(ingest.load_tree_types(tempfile.mkdtemp()), empty)
        with mock.patch.dict(ingest.TREE_TYPES, empty):
            self.assertEqual(ingest._custom("province", 8), {"value": 8, "string": ""})                  # Province
            self.assertEqual(ingest._state_type("Austrian Empire"), {"value": 1, "string": ""})           # Country
            for gramps_value, text in ((8, "voivodeship"), (1, "empire"), (12, "district")):
                tree = Tree({"p": typed("p", "A place", gramps_value)}, [])
                self.assertTrue(ingest._type_matches(tree, "p", text), text)
            custom = Tree({"p": typed("p", "A place", 0, "some custom type")}, [])
            self.assertFalse(ingest._type_matches(custom, "p", "voivodeship"))                           # an empty convention matches nothing

    def test_with_the_conventions_of_the_tree_its_custom_types_are_used_and_recognised(self):
        types = {"province": "my province", "empire": "my empire", "monarchy": "my monarchy", "district": ["my district", "my other district"]}
        with mock.patch.dict(ingest.TREE_TYPES, types):
            self.assertEqual(ingest._custom("province", 8), {"value": 0, "string": "my province"})
            self.assertEqual(ingest._state_type("Habsburg Monarchy"), {"value": 0, "string": "my monarchy"})
            self.assertEqual(ingest._state_type("Austrian Empire"), {"value": 0, "string": "my empire"})
            for string, text in (("my province", "crownland"), ("my empire", "kaisertum"), ("my other district", "district")):
                self.assertTrue(ingest._type_matches(Tree({"p": typed("p", "A place", 0, string)}, []), "p", text), text)
            self.assertFalse(ingest._type_matches(Tree({"p": typed("p", "A place", 0, "another type")}, []), "p", "district"))

    def test_a_damaged_file_gives_empty_conventions(self):
        folder = tempfile.mkdtemp()
        for text in ("{not json", "[1, 2]", '{"province": null, "district": "x"}'):
            with open(os.path.join(folder, "type-conventions.json"), "w", encoding="utf-8") as fh:
                fh.write(text)
            self.assertEqual(ingest.load_tree_types(folder), {"province": "", "empire": "", "monarchy": "", "district": [], "rules": [], "settlements": []}, text)


class OwnTypeTests(unittest.TestCase):
    """A unit that has no type in Gramps is not forced into an artificial one: it gets a type of its own, from the rules of the tree or from the answer."""
    NO_RULES = {"province": "", "empire": "", "monarchy": "", "district": [], "rules": [], "settlements": []}

    def test_the_rules_of_the_tree_name_a_canton_and_the_districts(self):
        self.assertEqual(ingest._container_type("Kanton, canton"), {"value": 0, "string": ingest.TREE_TYPES["rules"][0]["string"]})
        self.assertTrue(ingest._container_type("Kanton, canton")["string"])
        self.assertEqual(ingest._container_type("Bezirk, district")["string"], ingest._container_type("járás, district")["string"])      # one convention
        self.assertNotEqual(ingest._container_type("kerület")["string"], ingest._container_type("járás")["string"])                      # and another

    def test_without_rules_the_canton_is_a_canton_of_its_own(self):
        with mock.patch.dict(ingest.TREE_TYPES, self.NO_RULES):
            self.assertEqual(ingest._container_type("Kanton, canton"), {"value": 0, "string": "Canton"})           # the English generic word of the answer
            self.assertEqual(ingest._container_type("canton (Kanton)"), {"value": 0, "string": "Canton"})
            self.assertEqual(ingest._container_type("Bezirk, district"), {"value": 12, "string": ""})              # Gramps has District

    def test_a_word_that_nothing_knows_becomes_the_type_of_the_unit(self):
        with mock.patch.dict(ingest.TREE_TYPES, self.NO_RULES):
            self.assertEqual(ingest._container_type("Gespanschaft"), {"value": 0, "string": "Gespanschaft"})
            self.assertEqual(ingest._container_type("grand duchy"), {"value": 0, "string": "Grand duchy"})
            self.assertEqual(ingest._container_type("kingdom, Königreich"), {"value": 1, "string": ""})            # Gramps has Country
            self.assertIsNone(ingest._container_type(""))
            self.assertIsNone(ingest._container_type(None))

    def test_the_types_of_gramps_are_used_when_there_is_one(self):
        for text, value in (("province", 8), ("Region", 9), ("département, department", 10), ("municipality", 14), ("borough", 13)):
            self.assertEqual(ingest._container_type(text)["value"], value, text)

    def test_a_custom_type_of_a_place_of_the_tree_is_recognised_by_its_words(self):
        canton = ingest._container_type("canton")["string"]
        tree = Tree({"c": typed("c", "Zürich", 0, canton), "o": typed("o", "Zürich", 0, "something else"), "n": typed("n", "Zürich", 3)}, [])
        self.assertTrue(ingest._type_matches(tree, "c", "Kanton, canton"))
        self.assertFalse(ingest._type_matches(tree, "o", "Kanton, canton"))
        self.assertFalse(ingest._type_matches(tree, "n", "Kanton, canton"))

    def test_the_rules_are_checked_and_a_bad_one_is_left_out(self):
        folder = tempfile.mkdtemp()
        data = {"rules": [{"words": ["Kanton"], "value": 0, "string": "my canton"}, "text", {"words": []}, {"words": "x"}, {"words": ["ok"], "value": "x"}]}
        with open(os.path.join(folder, "type-conventions.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        rules = ingest.load_tree_types(folder)["rules"]
        self.assertEqual([r["string"] for r in rules], ["my canton", ""])
        self.assertEqual(rules[0]["words"], ["kanton"])                                                              # compared folded


class MainPlaceTypeTests(unittest.TestCase):
    """The lowest level that is a place gets the type the answer gives, even one that Gramps has no name for."""
    def parse(self, type_text):
        return ingest.parse_structured("PLACE_NAME_ON_DATE: X\nSETTLEMENT_TYPE_ON_DATE: %s\nCOORDINATES: 1, 2\n" % type_text)

    def test_a_type_of_gramps_is_kept(self):
        rec = self.parse("borough, Stadtbezirk")
        self.assertEqual((rec["type_value"], rec["type_string"]), (13, ""))
        self.assertEqual(self.parse("municipality")["type_value"], 14)

    def test_a_type_that_gramps_does_not_have_is_the_answers_own_word(self):
        rec = self.parse("census-designated place, CDP")
        self.assertEqual((rec["type_value"], rec["type_string"]), (None, "Census-designated place"))

    def test_a_new_main_place_is_made_with_its_own_type(self):
        rec = self.parse("census-designated place")
        r = ingest.ingest(Tree({}, []), rec, "1990", aliases={})
        place = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "X")
        self.assertEqual((place["type_value"], place["type_string"]), (0, "Census-designated place"))

    def test_an_existing_place_with_no_type_is_offered_it(self):
        rec = self.parse("census-designated place")
        t = Tree({"x": typed("x", "X", -1)}, [])
        r = ingest.ingest(t, rec, "1990", aliases={})
        fill = [p for p in r["proposals"] if p["kind"] == "set-type"]
        self.assertEqual([(p["type_value"], p["type_string"]) for p in fill], [(0, "Census-designated place")])


class NoAnswerPhraseTests(unittest.TestCase):
    def test_the_phrases_of_the_services_are_read_from_the_file(self):
        self.assertIn("no answer for this search", prompts.NO_ANSWER)
        self.assertTrue(any(not p.isascii() for p in prompts.NO_ANSWER))                               # the phrases of a page in another language
        self.assertTrue(prompts.looks_like_no_answer("Sorry: " + prompts.NO_ANSWER[0].upper()))

    def test_without_the_file_the_english_phrases_are_used(self):
        self.assertEqual(prompts.load_no_answer_phrases(tempfile.mkdtemp()), ("no answer for this search", "try asking something else"))

    def test_a_file_with_nothing_usable_gives_the_english_phrases_too(self):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "no-answer-phrases.json"), "w", encoding="utf-8") as fh:
            fh.write('{"phrases": []}')
        self.assertEqual(prompts.load_no_answer_phrases(folder), ("no answer for this search", "try asking something else"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
