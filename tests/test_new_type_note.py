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
"""M52: a type of the user's own that the proposals give and that no place of the tree uses yet is told on the screen, once for each type (a note: nothing changes)."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, rules, screen                                              # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
import test_ingest as ti                                                                      # noqa: E402
import test_type_notes as tn                                                                  # noqa: E402

CANTON = tn.CANTON
BERN = """Name: K\u00f6niz | Language: de | From: UNKNOWN | Source: https://de.wikipedia.org/wiki/K%C3%B6niz
Alternatives: NONE
Category | Value/Name | Year Range | Level Type | Explanation | Source
Place Type | town | | | x | https://de.wikipedia.org/wiki/K%C3%B6niz
Level 1 | Bern | 1803-present | canton | x | https://de.wikipedia.org/wiki/Kanton_Bern
Sovereign state | Switzerland | 1848-present | country | x | https://de.wikipedia.org/wiki/Schweiz
Latitude | 46.92 | | | | https://de.wikipedia.org/wiki/K%C3%B6niz
Longitude | 7.41 | | | | https://de.wikipedia.org/wiki/K%C3%B6niz
"""


def swiss(*others):
    t = Tree({"ch": ti.typed("ch", "Switzerland", 1, lang="en")}, [])
    for i, (value, string) in enumerate(others):
        t.places["o%d" % i] = ti.typed("o%d" % i, "Other %d" % i, value, string, lang="en")
    return t


def notes(result):
    return [n for n in result["needs"] if n.startswith("the type \u00ab")]


def given(result):
    return sorted((p["kind"], p.get("type_value"), p.get("type_string")) for p in result["proposals"] if p["kind"] in ("add-place", "set-type", "change-type"))


class NewTypeNoteTests(unittest.TestCase):
    def test_a_new_place_with_a_type_of_your_own_that_the_tree_does_not_use_gets_the_note(self):
        result = tn.run(swiss(), BERN)
        self.assertIn(("add-place", 0, CANTON), given(result))                                  # the file of the tests (the author's) gives a canton this type
        self.assertEqual(len(notes(result)), 1)
        self.assertEqual(notes(result)[0], "the type \u00ab%s\u00bb is not used by any place of your tree yet; approving \u00abBern\u00bb adds it as a new type of your own" % CANTON)
        self.assertEqual(len(result["needs_local"]), len(result["needs"]))

    def test_no_note_when_a_place_of_the_tree_uses_the_type_in_any_writing(self):
        for writing in (CANTON, " " + CANTON + " ", CANTON + "\u200f"):
            self.assertEqual(notes(tn.run(swiss((0, writing)), BERN)), [], repr(writing))

    def test_a_type_of_gramps_has_no_note(self):
        with mock.patch.dict(ingest.TREE_TYPES, {"rules": []}):
            result = tn.run(swiss(), BERN.replace("| canton |", "| county |"))
        self.assertTrue(any(k == "add-place" and v == 3 for k, v, _s in given(result)))          # County (3)
        self.assertEqual(notes(result), [])

    def test_a_word_of_the_answer_that_becomes_a_type_of_your_own_gets_the_note_with_that_word(self):
        with mock.patch.dict(ingest.TREE_TYPES, {"rules": []}):
            result = tn.run(swiss(), BERN)
        self.assertEqual(len(notes(result)), 1)
        self.assertTrue(notes(result)[0].startswith("the type \u00abCanton\u00bb is not used"))

    def test_a_type_that_a_place_without_a_type_is_given_gets_the_note_too(self):
        with mock.patch.dict(ingest.TREE_TYPES, {"rules": [{"words": ["town"], "value": 0, "string": "Stadt"}]}):
            result = tn.run(tn.tree(-1))
            self.assertIn(("set-type", 0, "Stadt"), given(result))
            self.assertEqual(len(notes(result)), 1)
            self.assertIn("\u00abStadt\u00bb is not used by any place of your tree yet; approving \u00ab%s\u00bb adds it" % tn.tree(-1).label("bl"), notes(result)[0])
            t = tn.tree(-1)
            t.places["x"] = ti.typed("x", "Elsewhere", 0, " STADT ", lang="en")
            self.assertEqual(notes(tn.run(t)), [])

    def test_the_note_changes_nothing_that_is_proposed(self):
        on = tn.run(swiss(), BERN)
        with rules.disabled("M52"):
            off = tn.run(swiss(), BERN)
        self.assertEqual(notes(off), [])
        self.assertEqual(on["proposals"], off["proposals"])
        self.assertEqual(len(notes(on)), 1)
        self.assertEqual(rules.message_id("the type \u00ab%s\u00bb is not used by any place of your tree yet; approving %s adds it ..."), "M52")

    def test_a_tree_without_new_types_is_read_only_when_needed(self):
        """The types of the places are counted only when a proposal gives a type of your own."""
        with mock.patch.object(screen, "census", wraps=screen.census) as census:
            tn.run(tn.tree(-1))                                                                   # a town of Gramps
            self.assertEqual(census.call_count, 0)
            tn.run(swiss(), BERN)
            self.assertEqual(census.call_count, 1)


class FunctionTests(unittest.TestCase):
    def call(self, proposals, tree=None):
        out = {"needs": [], "needs_local": []}
        screen._new_types(out, proposals, tree or swiss())
        return out["needs"]

    @staticmethod
    def place(string, name, value=0):
        return {"kind": "add-place", "type_value": value, "type_string": string, "names": [{"value": name}]}

    def test_one_note_for_each_type_with_all_the_places_that_get_it(self):
        got = self.call([self.place("Kanton", "A"), self.place(" kanton ", "B"), self.place("Bezirk", "C")])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0], "the type \u00abKanton\u00bb is not used by any place of your tree yet; approving \u00abA\u00bb, \u00abB\u00bb adds it as a new type of your own")
        self.assertIn("\u00abBezirk\u00bb", got[1])

    def test_more_than_three_places_are_counted(self):
        got = self.call([self.place("Kanton", n) for n in "ABCDE"])
        self.assertIn("\u00abA\u00bb, \u00abB\u00bb, \u00abC\u00bb +2 adds it", got[0])

    def test_the_same_place_twice_is_named_once(self):
        self.assertIn("approving \u00abA\u00bb adds it", self.call([self.place("Kanton", "A"), self.place("Kanton", "A")])[0])

    def test_blank_types_and_types_of_gramps_are_not_new(self):
        self.assertEqual(self.call([self.place("", "A"), self.place("  ", "B", 0), self.place("", "C", 15), self.place("x", "D", 15)]), [])

    def test_a_type_that_the_tree_uses_is_not_new_and_the_other_is(self):
        got = self.call([self.place("Kanton", "A"), self.place("Bezirk", "B")], swiss((0, "KANTON ")))
        self.assertEqual(len(got), 1)
        self.assertIn("\u00abBezirk\u00bb", got[0])

    def test_a_proposal_of_an_existing_place_is_named_by_its_label(self):
        t = swiss()
        got = self.call([{"kind": "set-type", "place": "ch", "type_value": 0, "type_string": "Kanton"}], t)
        self.assertIn("approving \u00ab%s\u00bb adds it" % t.label("ch"), got[0])


if __name__ == "__main__":
    unittest.main()
