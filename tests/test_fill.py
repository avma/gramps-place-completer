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
"""Filling the EMPTY fields of a place that exists: coordinates, the language of its name, its type. A filled field is never touched."""
import os
import sys
import tempfile
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db.utils import make_database
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import gaps, ingest, plan as planlib, session as sess, writer          # noqa: E402
from placecompleter.dates import describe, is_empty                                          # noqa: E402
from placecompleter.model import Tree                                                       # noqa: E402
from test_engine import EMPTY                                                               # noqa: E402
from test_ingest import WORLD, typed                                                        # noqa: E402

ANSWER = """PLACE_NAME_ON_DATE: City of Johnston
LANGUAGE: en
SETTLEMENT_TYPE_ON_DATE: city
COORDINATES: 41.673, -93.6977
CONTAINERS:
1 | Polk County | county | 1846-present | Iowa
2 | Iowa | state | 1846-present | United States
STATE_ON_DATE: United States | 1776-present
"""


def tree(lang="", lat="", lon="", ptype=-1, string=""):
    t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
              "city": typed("city", "City of Johnston", ptype, string, lang=lang)}, [])
    t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
    t.places["city"]["lat"], t.places["city"]["lon"] = lat, lon
    return t


def fills(t, text=ANSWER):
    r = ingest.ingest(t, ingest.parse_structured(text), "1995", aliases=ingest.alias_map([WORLD]))
    return r, {p["kind"]: p for p in r["proposals"] if p["kind"] in planlib.FILL_KINDS}


class ProposalTests(unittest.TestCase):
    def test_a_place_without_coordinates_gets_those_of_the_answer(self):
        _, f = fills(tree(lang="en", ptype=4))
        self.assertEqual((f["set-coordinates"]["lat"], f["set-coordinates"]["lon"], f["set-coordinates"]["place"]), ("41.673", "-93.6977", "city"))
        self.assertEqual(f["set-coordinates"]["basis"], "assumption")
        self.assertNotIn("set-name-language", f)
        self.assertNotIn("set-type", f)

    def test_a_place_with_coordinates_keeps_them(self):
        r, f = fills(tree(lang="en", ptype=4, lat="41.68559", lon="-93.71725"))
        self.assertNotIn("set-coordinates", f)
        self.assertTrue(any("km apart" in x["value"] for x in r["rows"] if x["field"] == "coordinates"))      # still compared, never replaced

    def test_only_one_of_the_two_coordinates_present_is_also_not_touched(self):
        self.assertNotIn("set-coordinates", fills(tree(lang="en", ptype=4, lat="41.6"))[1])

    def test_the_name_without_a_language_gets_the_language_of_the_answer(self):
        _, f = fills(tree(lat="41.67", lon="-93.7", ptype=4))
        self.assertEqual((f["set-name-language"]["place"], f["set-name-language"]["index"], f["set-name-language"]["value"], f["set-name-language"]["lang"]),
                         ("city", 0, "City of Johnston", "en"))

    def test_a_name_that_has_a_language_keeps_it(self):
        self.assertNotIn("set-name-language", fills(tree(lang="hu", lat="41.67", lon="-93.7", ptype=4))[1])

    def test_a_name_that_is_not_the_one_of_the_answer_is_not_given_its_language(self):
        text = ANSWER.replace("PLACE_NAME_ON_DATE: City of Johnston", "PLACE_NAME_ON_DATE: Johnston")
        t = tree(lat="41.67", lon="-93.7", ptype=4)
        t.places["city"]["alt_names"] = [{"value": "Johnston", "lang": "", "date": EMPTY}]
        _, f = fills(t, text)
        self.assertEqual((f["set-name-language"]["index"], f["set-name-language"]["value"]), (1, "Johnston"))      # the alternative name that matches

    def test_a_place_of_unknown_type_gets_the_type_of_the_answer(self):
        _, f = fills(tree(lang="en", lat="41.67", lon="-93.7"))
        self.assertEqual((f["set-type"]["type_value"], f["set-type"]["type_string"]), (4, ""))

    def test_a_type_that_is_set_is_not_touched_even_a_custom_one(self):
        self.assertNotIn("set-type", fills(tree(lang="en", lat="41.67", lon="-93.7", ptype=16))[1])
        self.assertNotIn("set-type", fills(tree(lang="en", lat="41.67", lon="-93.7", ptype=0, string="custom city"))[1])

    def test_no_type_in_the_answer_no_proposal(self):
        text = ANSWER.replace("SETTLEMENT_TYPE_ON_DATE: city\n", "")
        self.assertNotIn("set-type", fills(tree(lang="en", lat="41.67", lon="-93.7"), text)[1])

    def test_nothing_is_proposed_for_a_place_that_is_new(self):
        t = tree()
        del t.places["city"]
        r, f = fills(t)
        self.assertEqual(f, {})                                                         # the new place carries them in its own creation
        made = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Johnston")        # not "City of Johnston"
        self.assertEqual((made["lat"], made["lon"]), ("41.673", "-93.6977"))

    def test_a_complete_place_has_nothing_to_complete(self):
        _, f = fills(tree(lang="en", lat="41.6", lon="-93.7", ptype=4))
        self.assertEqual(f, {})


class ChainLanguageTests(unittest.TestCase):
    """The names of the places of the chain that exist and have no language get the language of the state they belonged to (the convention of the
    tree: the language of a name follows the state that ruled): English for an English answer, Romanian for Romania, Hungarian for the Kingdom of
    Hungary. A state that has no single language gives nothing."""
    def chain_tree(self):
        t = tree(lang="en", lat="41.67", lon="-93.7", ptype=4)
        t.places["usa"]["name"]["lang"] = t.places["iowa"]["name"]["lang"] = ""
        return t

    def langs(self, text=ANSWER):
        return sorted((p["place"], p["value"], p["lang"]) for p in fills_all(self.chain_tree(), text) if p["kind"] == "set-name-language")

    def test_an_english_answer_gives_them_english(self):
        self.assertEqual(self.langs(), [("iowa", "Iowa", "en"), ("usa", "USA", "en")])

    def test_an_answer_in_another_language_gives_the_language_of_the_state(self):
        text = ANSWER.replace("LANGUAGE: en", "LANGUAGE: de")
        self.assertEqual(self.langs(text), [("iowa", "Iowa", "en"), ("usa", "USA", "en")])           # the state is the United States

    def test_a_state_with_no_single_language_gives_nothing(self):
        text = (ANSWER.replace("LANGUAGE: en", "LANGUAGE: de").replace("| United States", "| Austria-Hungary")
                .replace("STATE_ON_DATE: United States", "STATE_ON_DATE: Austria-Hungary"))
        self.assertEqual(self.langs(text), [])

    def test_a_name_that_has_a_language_is_not_touched(self):
        self.assertFalse([p for p in fills_all(tree(lang="en", lat="41.67", lon="-93.7", ptype=4)) if p["kind"] == "set-name-language"])

    def test_a_new_unit_is_created_with_the_language_of_its_state(self):
        t = tree(lang="en", lat="41.67", lon="-93.7", ptype=4)
        r = ingest.ingest(t, ingest.parse_structured(ANSWER), "1995", aliases=ingest.alias_map([WORLD]))
        county = next(p for p in r["proposals"] if p["kind"] == "add-place")
        self.assertEqual((county["names"][0]["value"], county["names"][0]["lang"]), ("Polk County", "en"))
        romanian = ("PLACE_NAME_ON_DATE: Deva\nLANGUAGE: ro\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
                    "1 | Județul Hunedoara | county (județ) | 1925-1938 | Romania\nSTATE_ON_DATE: Romania | 1918-present\n")
        r = ingest.ingest(t, ingest.parse_structured(romanian), "1930", aliases={})
        made = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Județul Hunedoara")
        self.assertEqual((made["names"][0]["lang"], describe(made["names"][0]["date"])), ("ro", "span 1925..1938"))
        unknown = romanian.replace("| Romania", "| Austria-Hungary").replace("STATE_ON_DATE: Romania", "STATE_ON_DATE: Austria-Hungary")
        r = ingest.ingest(t, ingest.parse_structured(unknown), "1930", aliases={})
        made = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Județul Hunedoara")
        self.assertEqual(made["names"][0]["lang"], "")


class NamePeriodTests(unittest.TestCase):
    """A name that has no period gets the period its unit has in the answer: a choice, because a dated name stops showing before its date."""
    def periods(self, t, text=ANSWER):
        return [p for p in fills_all(t, text) if p["kind"] == "set-name-date"]

    def full_tree(self):
        return tree(lang="en", lat="41.67", lon="-93.7", ptype=4)

    def test_the_undated_names_of_the_chain_get_the_period_of_their_unit(self):
        got = sorted((p["place"], p["value"], describe(p["new"])) for p in self.periods(self.full_tree()))
        self.assertEqual(got, [("iowa", "Iowa", "from 1846"), ("usa", "USA", "from 1776")])

    def test_the_old_value_is_empty_so_that_nothing_that_was_written_since_is_overwritten(self):
        for p in self.periods(self.full_tree()):
            self.assertTrue(is_empty(p["old"]))

    def test_a_name_that_has_a_period_is_not_given_another(self):
        t = self.full_tree()
        t.places["iowa"]["name"]["date"] = {"modifier": 7, "quality": 0, "calendar": 0, "dateval": [0, 0, 1800, False], "text": "", "sortval": 1}
        self.assertEqual([p["place"] for p in self.periods(t)], ["usa"])

    def test_a_unit_without_a_period_in_the_answer_gives_nothing(self):
        text = ANSWER.replace("1 | Polk County | county | 1846-present | Iowa", "1 | Polk County | county | UNKNOWN | Iowa") \
                     .replace("2 | Iowa | state | 1846-present | United States", "2 | Iowa | state | UNKNOWN | United States") \
                     .replace("STATE_ON_DATE: United States | 1776-present", "STATE_ON_DATE: United States | UNKNOWN")
        self.assertEqual(self.periods(self.full_tree(), text), [])

    def test_what_gramps_would_show_before_that_date_is_a_question_mark(self):
        t = self.full_tree()
        r = ingest.ingest(t, ingest.parse_structured(ANSWER), "1995", aliases=ingest.alias_map([WORLD]))
        iowa = next(p for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "iowa")
        without = [p for p in r["proposals"] if p["kind"] != "set-name-date"]
        self.assertNotIn("?", ingest.preview_for(t, without, r["child"], "1800")[0])
        self.assertIn("?", ingest.preview_for(t, without + [iowa], r["child"], "1800")[0])


def fills_all(t, text=ANSWER):
    return ingest.ingest(t, ingest.parse_structured(text), "1995", aliases=ingest.alias_map([WORLD]))["proposals"]


class SimulationTests(unittest.TestCase):
    def test_what_gramps_would_hold_after_the_fill(self):
        t = tree()
        r, f = fills(t)
        after = gaps.apply(t, list(f.values()))
        city = after.places["city"]
        self.assertEqual((city["lat"], city["lon"], city["name"]["lang"], city["type"]["value"]), ("41.673", "-93.6977", "en", 4))
        self.assertEqual((t.places["city"]["lat"], t.places["city"]["name"]["lang"]), ("", ""))     # the tree itself is not changed

    def test_the_plan_carries_what_is_needed_to_write_each(self):
        t = tree()
        r, f = fills(t)
        plan = planlib.make_plan(t, r["proposals"])
        items = {i["kind"]: i for i in plan["proposals"] if i["kind"] in planlib.FILL_KINDS}
        self.assertEqual((items["set-coordinates"]["lat"], items["set-coordinates"]["lon"]), ("41.673", "-93.6977"))
        self.assertEqual((items["set-name-language"]["lang"], items["set-name-language"]["index"]), ("en", 0))
        self.assertEqual(items["set-type"]["type_value"], 4)
        self.assertTrue(all(i["label"] == "City of Johnston [CITY]" for i in items.values()))


class SessionTests(unittest.TestCase):
    def session(self, t=None):
        s = sess.Session(t or tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
        s.begin("City of Johnston", "1995", engine="manual")
        s.receive(ANSWER)
        return s

    def test_each_fill_is_a_choice_of_its_own_in_plain_words(self):
        s = self.session()
        fills_ = [c for c in s.changes() if c["flag"] == "populates unassigned field"]
        titles = sorted(c["title"] for c in fills_)
        self.assertEqual(len(fills_), 5)
        self.assertIn("Set missing coordinates for «City of Johnston [CITY]»: 41.673, -93.6977 (from AI response: verify accuracy (coordinates may deviate slightly))", titles)
        self.assertIn("Set language tag for name «City of Johnston» (primary name) of «City of Johnston [CITY]» to en", titles)
        self.assertIn("Set administrative place type of «City of Johnston [CITY]» to City", titles)
        self.assertIn("Assign date period to name «Iowa» (primary name, language: en) of «Iowa [IOWA]»: from 1846", titles)
        self.assertIn("Assign date period to name «USA» (primary name, language: en) of «USA [USA]»: from 1776", titles)
        self.assertTrue(all(len(c["steps"]) == 1 and c["why"] == "" for c in fills_))

    def test_checking_the_coordinates_checks_nothing_else(self):
        s = self.session()
        coords = next(c for c in s.changes() if c["title"].startswith("Set missing coordinates"))
        s.toggle_change(coords["id"])
        self.assertEqual(sum(c["selected"] for c in s.changes()), 1)

    def test_a_fill_does_not_change_the_hierarchy_shown(self):
        s = self.session()
        before = s.preview()[0]
        for c in s.changes():
            if c["flag"] == "populates unassigned field":
                s.toggle_change(c["id"])
        self.assertEqual(s.preview()[0], before)


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class WriterTests(unittest.TestCase):
    """With a real Gramps database: the fields are written in one step with the rest, and what was written meanwhile is respected."""
    def open(self, t):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(t, path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        return db

    def plan(self, db):
        t = Tree.from_db(db)
        r, _ = fills(t)
        return planlib.make_plan(t, r["proposals"])

    def chosen(self, plan, *kinds):
        return [p for p in plan["proposals"] if p["kind"] in kinds]

    def test_the_three_fields_are_written(self):
        db = self.open(tree())
        results = writer.apply_proposals(db, self.chosen(self.plan(db), *planlib.FILL_KINDS), dry_run=False)
        self.assertEqual({r["status"] for r in results}, {"applied"})
        place = db.get_place_from_handle("city")
        self.assertEqual((place.get_latitude(), place.get_longitude(), place.get_name().get_language(), place.get_type().value), ("41.673", "-93.6977", "en", 4))

    def test_it_is_one_undo_with_the_hierarchy_change_in_the_same_step(self):
        db = self.open(tree())
        plan = self.plan(db)
        writer.apply_proposals(db, plan["proposals"], dry_run=False)               # the level in between AND the three fields
        self.assertEqual(db.get_place_from_handle("city").get_latitude(), "41.673")
        self.assertGreater(len(db.get_place_from_handle("city").get_placeref_list()), 1)
        db.undo()
        place = db.get_place_from_handle("city")
        self.assertEqual((place.get_latitude(), place.get_name().get_language(), place.get_type().value, len(place.get_placeref_list())), ("", "", -1, 1))

    def test_coordinates_written_in_the_meantime_are_never_overwritten(self):
        db = self.open(tree())
        plan = self.plan(db)
        from gramps.gen.db import DbTxn
        place = db.get_place_from_handle("city")
        place.set_latitude("41.68559")
        place.set_longitude("-93.71725")
        with DbTxn("somebody", db) as txn:
            db.commit_place(place, txn)
        results = writer.apply_proposals(db, self.chosen(plan, "set-coordinates"), dry_run=False)
        self.assertEqual([(r["status"], r["reason"]) for r in results], [("skipped", "place already contains spatial coordinates")])
        self.assertEqual(db.get_place_from_handle("city").get_latitude(), "41.68559")

    def test_a_language_or_a_type_set_in_the_meantime_is_respected(self):
        db = self.open(tree())
        plan = self.plan(db)
        from gramps.gen.db import DbTxn
        place = db.get_place_from_handle("city")
        place.get_name().set_language("hu")
        place.set_type(16)
        with DbTxn("somebody", db) as txn:
            db.commit_place(place, txn)
        results = writer.apply_proposals(db, self.chosen(plan, "set-name-language", "set-type"), dry_run=False)
        self.assertEqual(sorted(r["reason"] for r in results), ["place entity already has an administrative type assigned", "place name already has a language tag assigned"])
        self.assertEqual((db.get_place_from_handle("city").get_name().get_language(), db.get_place_from_handle("city").get_type().value), ("hu", 16))

    def test_a_dry_run_reports_without_writing(self):
        db = self.open(tree())
        results = writer.apply_proposals(db, self.chosen(self.plan(db), *planlib.FILL_KINDS), dry_run=True)
        self.assertEqual({r["status"] for r in results}, {"dry-run"})
        self.assertEqual(db.get_place_from_handle("city").get_latitude(), "")

    def test_a_period_for_a_name_is_written_and_one_written_meanwhile_is_not_overwritten(self):
        db = self.open(tree())
        t = Tree.from_db(db)
        r, _ = fills(t)
        plan = planlib.make_plan(t, r["proposals"])
        iowa = [p for p in plan["proposals"] if p["kind"] == "set-name-date" and p["place"] == "iowa"]
        results = writer.apply_proposals(db, iowa, dry_run=False)
        self.assertEqual([r["status"] for r in results], ["applied"])
        date = db.get_place_from_handle("iowa").get_name().get_date_object()
        self.assertEqual((date.get_year(), date.get_modifier()), (1846, 7))                  # from 1846
        again = writer.apply_proposals(db, iowa, dry_run=False)                              # the name has a period now
        self.assertEqual([r["status"] for r in again], ["skipped"])
        self.assertEqual(again[0]["reason"], "place name date range was modified after analysis phase")

    def test_the_tree_read_back_holds_the_values(self):
        db = self.open(tree())
        writer.apply_proposals(db, self.chosen(self.plan(db), *planlib.FILL_KINDS), dry_run=False)
        city = Tree.from_db(db).places["city"]
        self.assertEqual((city["lat"], city["lon"], city["name"]["lang"]), ("41.673", "-93.6977", "en"))
        self.assertEqual(fills(Tree.from_db(db))[1].keys(), set())                       # nothing is left to complete


if __name__ == "__main__":
    unittest.main(verbosity=2)
