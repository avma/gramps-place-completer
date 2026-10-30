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
"""A place of the tree whose type is not a settlement (a canton, a type of the user's own): the type is not changed, and the screen says why (rule ST6, note M51)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, rules, table, writer                                       # noqa: E402
from placecompleter.kinds import has_no_type                                                  # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
import test_ingest as ti                                                                      # noqa: E402
import test_fill as tf                                                                        # noqa: E402

TABLE = """Name: Blagnac | Language: fr | From: UNKNOWN | Source: https://en.wikipedia.org/wiki/Blagnac
Alternatives: NONE
Category | Value/Name | Year Range | Level Type | Explanation | Source
Place Type | town | | | x | https://en.wikipedia.org/wiki/Blagnac
Level 1 | Haute-Garonne | 1790-present | department | x | https://fr.wikipedia.org/wiki/Haute-Garonne
Sovereign state | France | 1958-present | country | x | https://fr.wikipedia.org/wiki/France
Latitude | 43.6364 | | | | https://en.wikipedia.org/wiki/Blagnac
Longitude | 1.3906 | | | | https://en.wikipedia.org/wiki/Blagnac
"""
CANTON = "\u05e7\u05e0\u05d8\u05d5\u05df"
KIBBUTZ = ingest.TREE_TYPES["settlements"][0]


def tree(value, string=""):
    t = Tree({"fr": ti.typed("fr", "France", 1, lang="en"), "hg": ti.typed("hg", "Haute-Garonne", 10, lang="fr"), "bl": ti.typed("bl", "Blagnac", value, string, lang="fr")}, [])
    t.places["hg"]["refs"] = [{"ref": "fr", "date": EMPTY}]
    t.places["bl"]["refs"] = [{"ref": "hg", "date": EMPTY}]
    t.places["bl"]["lat"], t.places["bl"]["lon"] = "43.6364", "1.3906"
    return t


def run(t, text=TABLE):
    rec = ingest.parse_structured(table.convert(text)[0])
    return ingest.ingest(t, rec, "1999")


def kinds(screen):
    return [p["kind"] for p in screen["proposals"] if p.get("place") == "bl"]


def note(screen):
    return [n for n in screen["needs"] if n.startswith("the type of")]


class TypeNoteTests(unittest.TestCase):
    def test_a_type_of_the_users_own_that_is_not_a_settlement_is_not_changed_and_the_note_says_why(self):
        screen = run(tree(0, CANTON))
        self.assertEqual([k for k in kinds(screen) if k in ("set-type", "change-type")], [])
        self.assertEqual(len(note(screen)), 1)
        self.assertIn("«%s» but the response specifies town" % CANTON, note(screen)[0])
        self.assertIn("non-settlement types are not modified automatically here", note(screen)[0])

    def test_an_area_of_gramps_gets_the_note_with_its_name(self):
        screen = run(tree(12))                                                                       # District
        self.assertIn("«District» but the response specifies town:", note(screen)[0])
        self.assertEqual([k for k in kinds(screen) if k in ("set-type", "change-type")], [])

    def test_a_town_that_has_no_type_is_given_one_and_there_is_no_note(self):
        screen = run(tree(-1))
        self.assertIn("set-type", kinds(screen))
        self.assertEqual(note(screen), [])

    def test_a_settlement_of_gramps_with_another_size_is_offered_a_change_and_there_is_no_note(self):
        screen = run(tree(14))                                                                       # Municipality
        self.assertIn("change-type", kinds(screen))
        self.assertEqual(note(screen), [])

    def test_a_type_of_the_user_that_is_a_settlement_by_his_convention_gets_no_note(self):
        screen = run(tree(0, KIBBUTZ))
        self.assertEqual(note(screen), [])

    def test_the_same_type_as_the_answer_gets_no_note_and_no_change(self):
        screen = run(tree(15))
        self.assertEqual(note(screen), [])
        self.assertEqual([k for k in kinds(screen) if k in ("set-type", "change-type")], [])

    def test_an_answer_with_no_type_gives_no_note(self):
        screen = run(tree(0, CANTON), TABLE.replace("Place Type | town", "Place Type | "))
        self.assertEqual(note(screen), [])

    def test_the_note_is_a_rule_that_can_be_switched_off(self):
        with rules.disabled("M51"):
            self.assertEqual(note(run(tree(0, CANTON))), [])
        self.assertEqual(rules.message_id("the type of %s in the tree is «%s» and the answer says %s: ..."), "M51")


class BlankTypeTests(unittest.TestCase):
    """In Gramps two types show as an empty field in the Type column: Unknown, and a type of the user's own with no text. Both are 'no type'."""
    def test_what_is_no_type(self):
        for kind in (None, {}, {"value": -1}, {"value": -1, "string": ""}, {"value": 0, "string": ""}, {"value": 0}, {"value": 0, "string": "  "}, {"value": None}):
            self.assertTrue(has_no_type(kind), kind)
        for kind in ({"value": 0, "string": CANTON}, {"value": 15, "string": ""}, {"value": 4}, {"value": 14, "string": ""}, {"value": 12}):
            self.assertFalse(has_no_type(kind), kind)

    def test_a_town_with_a_blank_type_of_its_own_is_given_the_type_of_the_answer_and_there_is_no_note(self):
        for string in ("", "  "):
            screen = run(tree(0, string))
            given = [p for p in screen["proposals"] if p["kind"] == "set-type" and p.get("place") == "bl"]
            self.assertEqual([(p["type_value"], p["type_string"]) for p in given], [(15, "")], string)
            self.assertEqual(note(screen), [])

    def test_a_level_with_a_blank_type_of_its_own_is_given_the_type_of_the_answer(self):
        t = tree(-1)
        t.places["hg"]["type"] = {"value": 0, "string": ""}
        screen = run(t)
        given = [(p["type_value"], p["type_string"]) for p in screen["proposals"] if p["kind"] == "set-type" and p.get("place") == "hg"]
        self.assertEqual(given, [(10, "")])                                                          # Department

    def test_a_type_of_the_user_with_a_text_is_still_not_changed(self):
        t = tree(-1)
        t.places["hg"]["type"] = {"value": 0, "string": "Departement"}
        screen = run(t)
        self.assertEqual([p for p in screen["proposals"] if p["kind"] == "set-type" and p.get("place") == "hg"], [])


class WriterBlankTypeTests(unittest.TestCase):
    """The writer gives a type to a place that shows none, and keeps one that was given in the meantime. (It uses the helpers of the writer tests of the fill.)"""
    def setUp(self):
        self.w = tf.WriterTests("test_a_dry_run_reports_without_writing")
        self.addCleanup(self.w.doCleanups)                                                           # the helper closes its databases and removes its folders

    def open(self, t):
        return self.w.open(t)

    def plan(self, db):
        return self.w.plan(db)

    def chosen(self, plan, *kinds):
        return self.w.chosen(plan, *kinds)

    def test_a_blank_type_of_the_users_own_is_filled_when_the_proposal_is_applied(self):
        db = self.open(tf.tree(lang="en", lat="41.67", lon="-93.7", ptype=0, string=""))
        plan = self.plan(db)
        self.assertEqual([p["kind"] for p in plan["proposals"] if p["kind"] == "set-type"], ["set-type"])
        results = writer.apply_proposals(db, self.chosen(plan, "set-type"), dry_run=False)
        self.assertEqual([r["status"] for r in results], ["applied"])
        self.assertEqual(db.get_place_from_handle("city").get_type().value, 4)

    def test_a_type_with_a_text_given_in_the_meantime_is_respected(self):
        db = self.open(tf.tree(lang="en", lat="41.67", lon="-93.7"))
        plan = self.plan(db)
        from gramps.gen.db import DbTxn
        place = db.get_place_from_handle("city")
        place.set_type((0, "Commune"))
        with DbTxn("somebody", db) as txn:
            db.commit_place(place, txn)
        results = writer.apply_proposals(db, self.chosen(plan, "set-type"), dry_run=False)
        self.assertEqual([r["reason"] for r in results], ["place entity already has an administrative type assigned"])

    def test_a_blank_type_of_the_users_own_is_shown_by_the_gramplet_as_a_type_that_is_missing(self):
        from placecompleter import grampslink
        db = self.open(tf.tree(lang="en", lat="41.67", lon="-93.7", ptype=0, string=""))
        self.assertIn("type", grampslink.place_summary(db, db.get_place_from_handle("city"))["missing"])
        db2 = self.open(tf.tree(lang="en", lat="41.67", lon="-93.7", ptype=15))
        self.assertNotIn("type", grampslink.place_summary(db2, db2.get_place_from_handle("city"))["missing"])


if __name__ == "__main__":
    unittest.main()
