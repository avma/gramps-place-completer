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
"""SETTLEMENT_TYPE_ON_DATE is one word of a closed list: the size class of the settlement, not its legal status (ST1-ST5 of docs/ANALYZER_RULES.md)."""
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

TMP = tempfile.mkdtemp(prefix="pc-types-")
os.environ["GRAMPSHOME"] = os.path.join(TMP, "home")
try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.lib import Place, PlaceName, PlaceType
    HAVE_GRAMPS = True
except Exception:                        # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import confidence, ingest, plan as planlib, prompts, session as sess, writer   # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
import test_ingest as ti                                                                      # noqa: E402

CITY, TOWN, VILLAGE, HAMLET, NEIGHBORHOOD, LOCALITY, MUNICIPALITY = 4, 15, 16, 17, 11, 6, 14


def parse(line):
    rec = ingest.parse_structured("PLACE_NAME_ON_DATE: X\nSETTLEMENT_TYPE_ON_DATE: %s\nCOORDINATES: 1.5, 2.5\n" % line)
    return rec["type_value"], rec["type_string"]


class ParseTests(unittest.TestCase):
    def test_each_word_of_the_list_is_one_type_of_gramps(self):
        for word, value in (("metropolis", CITY), ("city", CITY), ("town", TOWN), ("village", VILLAGE), ("hamlet", HAMLET),
                            ("neighborhood", NEIGHBORHOOD), ("locality", LOCALITY)):
            self.assertEqual(parse(word), (value, ""), word)

    def test_case_and_what_follows_the_word_do_not_matter(self):
        self.assertEqual(parse("Town"), (TOWN, ""))
        self.assertEqual(parse("town (Stadt)"), (TOWN, ""))
        self.assertEqual(parse("VILLAGE | falu"), (VILLAGE, ""))

    def test_the_legal_status_in_the_local_term_cannot_change_the_class(self):
        for line, value in (("village | commune", VILLAGE), ("village | municipality", VILLAGE), ("city | commune", CITY), ("town | city", TOWN),
                            ("hamlet | comune", HAMLET)):
            self.assertEqual(parse(line), (value, ""), line)

    def test_answers_of_the_old_forms_are_read_as_before(self):
        self.assertEqual(parse("municipality"), (MUNICIPALITY, ""))
        self.assertEqual(parse("market town | mezőváros"), (TOWN, ""))
        self.assertEqual(parse("city (commune)"), (CITY, ""))
        self.assertEqual(parse("unincorporated community"), (LOCALITY, ""))
        self.assertEqual(parse("commune"), (None, "Commune"))                                    # a word that is not in the list: the custom type of the answer's word

    def test_a_rule_of_the_tree_comes_first_and_sees_whole_words_of_the_whole_answer(self):
        rules = [{"words": ["metropolis"], "value": 0, "string": "Metropolis"}, {"words": ["moshav ovdim", "moshav"], "value": 0, "string": "Moshav"}]
        with mock.patch.dict(ingest.TREE_TYPES, {"rules": rules + ingest.TREE_TYPES["rules"]}):
            self.assertEqual(parse("metropolis | paris"), (0, "Metropolis"))
            self.assertEqual(parse("village | moshav ovdim"), (0, "Moshav"))
            self.assertEqual(parse("town"), (TOWN, ""))                                            # nothing for the others
            self.assertEqual(parse("village | moshavim of the north"), (VILLAGE, ""))              # whole words only: "moshavim" is not "moshav"

    def test_without_a_rule_of_the_tree_a_metropolis_is_a_city_and_nothing_is_made_up(self):
        self.assertEqual(parse("metropolis"), (CITY, ""))

    def test_the_type_reaches_the_place_that_is_created(self):
        text = ("PLACE_NAME_ON_DATE: Hadad\nCOORDINATES: 47.1, 23.0\nSETTLEMENT_TYPE_ON_DATE: village | kisközség\n"
                "CONTAINERS: 1 | Silvania Region | Region | 1850-1900 | Hungary")
        screen = ingest.ingest(ti.tree(), ingest.parse_structured(text), "1870")
        made = next(p for p in screen["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Hadad")
        self.assertEqual(made["type_value"], VILLAGE)


class PromptTests(unittest.TestCase):
    FORMS = ("classic", "short", "dated", "long")

    def test_the_list_of_the_prompt_and_the_list_of_the_parser_are_the_same(self):
        words = {w.strip() for w in prompts.SETTLEMENT_WORDS.split("|")}
        self.assertEqual(words, set(ingest.SETTLEMENT_CLASSES))

    def test_every_form_gives_the_closed_list_and_asks_for_one_word(self):
        for form in self.FORMS:
            text = prompts.build_prompt("Ausson", "1980", form)
            self.assertIn("exactly one of", text, form)
            for word in ingest.SETTLEMENT_CLASSES:
                self.assertIn(word, text, (form, word))

    def test_every_form_says_that_it_is_about_size_and_gives_the_anchors(self):
        for form in self.FORMS:
            text = prompts.build_prompt("Ausson", "1980", form)
            self.assertIn("legal status", text, form)
            for anchor in ("500,000", "30,000", "2,000", "100"):
                self.assertIn(anchor, text, (form, anchor))

    def test_the_long_forms_ask_to_judge_the_size_in_the_year_of_the_question(self):
        for form in ("classic", "dated", "long"):
            text = prompts.build_prompt("Ausson", "1980", form)
            self.assertIn("IN 1980", text, form)

    def test_the_old_mixed_list_is_gone_from_every_form(self):
        for form in self.FORMS:
            text = prompts.build_prompt("Ausson", "1980", form)
            self.assertNotIn("borough, municipality", text, form)
            self.assertNotIn("market town, town, city", text, form)

    def test_nothing_of_the_template_is_left_unfilled_and_every_form_is_still_a_question_and_not_an_answer(self):
        for form in self.FORMS:
            text = prompts.build_prompt("Ausson", "1980", form)
            self.assertNotIn("[[GUIDE]]", text, form)
            self.assertNotRegex(text, r"\{[a-z_]+\}", form)
            self.assertTrue(prompts.looks_like_echo(text), form)

    def test_the_short_form_stays_short(self):
        self.assertLess(len(prompts.build_prompt("Ausson", "1980", "short")), 1400)


BLAGNAC = ("PLACE_NAME_ON_DATE: Blagnac\nLANGUAGE: fr\nSETTLEMENT_TYPE_ON_DATE: %s\nCOORDINATES: 43.6364, 1.3906\n"
           "CONTAINERS: 1 | Haute-Garonne | county | 1790-present | France\nSTATE_ON_DATE: France | 1944-present\n"
           "SOURCES: https://example.org/blagnac | SETTLEMENT_TYPE_ON_DATE\nNOT_SURE: %s\n")


def blagnac_tree(value, string=""):
    return Tree({"bla": ti.typed("bla", "Blagnac", value, string, lang="fr")}, [])


def type_proposals(value, line, string="", unsure="NONE"):
    screen = ingest.ingest(blagnac_tree(value, string), ingest.parse_structured(BLAGNAC % (line, unsure)), "1980")
    return [p for p in screen["proposals"] if p["kind"] in ("set-type", "change-type")]


class ExistingPlaceTests(unittest.TestCase):
    """ST6: the type of a place that exists is changed only as a proposal, only between types of Gramps that are settlements, and only for an answer of the closed kind."""
    def test_a_municipality_becomes_a_town_as_a_change_to_what_exists(self):
        (change,) = type_proposals(MUNICIPALITY, "town | commune")
        self.assertEqual((change["kind"], change["place"], change["old_type_value"], change["type_value"]), ("change-type", "bla", MUNICIPALITY, TOWN))
        self.assertEqual(change["fields"], ["SETTLEMENT_TYPE_ON_DATE"])

    def test_the_same_type_proposes_nothing_and_an_empty_type_is_filled_as_before(self):
        self.assertEqual(type_proposals(TOWN, "town | commune"), [])
        (fill,) = type_proposals(-1, "town | commune")
        self.assertEqual((fill["kind"], fill["type_value"]), ("set-type", TOWN))

    def test_a_type_of_the_user_and_a_place_that_is_not_a_settlement_are_left_alone(self):
        self.assertEqual(type_proposals(0, "village | moshav", "\u05de\u05d5\u05e9\u05d1"), [])                  # a type of the user's own: never
        self.assertEqual(type_proposals(8, "town | commune"), [])                            # a province is not a settlement: it may be another place of the same name

    def test_an_answer_of_the_old_kind_never_changes_a_type_because_its_words_may_be_a_legal_status(self):
        self.assertEqual(type_proposals(TOWN, "municipality, commune"), [])
        self.assertEqual(type_proposals(CITY, "town, commune"), [])

    def test_a_rule_of_the_tree_for_a_metropolis_can_change_a_city_to_its_own_type(self):
        rules = [{"words": ["metropolis"], "value": 0, "string": "Metropolis"}]
        with mock.patch.dict(ingest.TREE_TYPES, {"rules": rules + ingest.TREE_TYPES["rules"]}):
            (change,) = type_proposals(CITY, "metropolis")
        self.assertEqual((change["old_type_value"], change["type_value"], change["type_string"]), (CITY, 0, "Metropolis"))

    def test_it_is_a_change_to_what_exists_chosen_one_by_one_and_the_window_says_what_it_is(self):
        s = sess.Session(blagnac_tree(MUNICIPALITY), tempfile.mkdtemp())
        s.begin("Blagnac", "1980", engine="manual")
        s.receive(BLAGNAC % ("town | commune", "NONE"))
        change = next(p for p in s.plan["proposals"] if p["kind"] == "change-type")
        self.assertTrue(change["existing"])                                                  # P0
        s.select_all()
        self.assertNotIn(change["id"], s.selected)                                           # not chosen by itself
        chosen, _left = s.selectable_by_all()
        self.assertIn(change["id"], chosen)                                                  # the user's button chooses it
        text = next(r["text"] for r in s.rows() if r["id"] == change["id"])
        self.assertTrue(text.startswith("Change administrative place type of «Blagnac"), text)
        self.assertIn("Municipality", text)
        self.assertIn("Town", text)

    def test_when_the_answer_is_not_sure_of_the_type_the_change_is_marked_unsure(self):
        (change,) = type_proposals(MUNICIPALITY, "town | commune", unsure="SETTLEMENT_TYPE_ON_DATE")
        self.assertEqual(confidence.level_of(change, {"SETTLEMENT_TYPE_ON_DATE"})[0], confidence.UNSURE)
        (change,) = type_proposals(MUNICIPALITY, "town | commune")
        self.assertEqual(confidence.level_of(change, set())[0], confidence.REPORTED)         # it cites a page for the field


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class WriterTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "db-%d" % id(self))
        self.db = make_database("sqlite")
        os.makedirs(self.path)
        self.db.load(self.path)
        with DbTxn("build", self.db) as txn:
            place, name = Place(), PlaceName()
            name.set_value("Blagnac")
            place.set_name(name)
            place.set_type(PlaceType.MUNICIPALITY)
            self.handle = self.db.add_place(place, txn)

    def tearDown(self):
        self.db.close()

    def proposal(self):
        return {"id": 1, "kind": "change-type", "place": self.handle, "type_value": TOWN, "type_string": "", "old_type_value": MUNICIPALITY,
                "old_type_string": "", "basis": "assumption", "old": {}, "new": {}}

    def type_now(self):
        return self.db.get_place_from_handle(self.handle).get_type().value

    def test_the_change_is_written_in_one_undo(self):
        self.assertEqual(writer.apply_proposals(self.db, [self.proposal()], dry_run=False)[0]["status"], "applied")
        self.assertEqual(self.type_now(), TOWN)
        self.db.undo()
        self.assertEqual(self.type_now(), MUNICIPALITY)

    def test_a_type_that_was_changed_in_the_meantime_is_never_overwritten(self):
        with DbTxn("somebody", self.db) as txn:
            place = self.db.get_place_from_handle(self.handle)
            place.set_type(PlaceType.HAMLET)
            self.db.commit_place(place, txn)
        result = writer.apply_proposals(self.db, [self.proposal()], dry_run=False)[0]
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(self.type_now(), HAMLET)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
