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
"""A settlement's name does not repeat its type: "City of Johnston" (type City) is "Johnston"; administrative units keep their word."""
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
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import Date, Event, EventType
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import gaps, ingest, names, plan as planlib, session as sess, writer     # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
from test_ingest import WORLD, typed                                                          # noqa: E402


class PlainNameTests(unittest.TestCase):
    def test_the_type_word_in_front_of_a_settlement_is_dropped_when_the_type_says_it(self):
        for text, value, expected in (("City of Johnston", 4, "Johnston"), ("Town of Ames", 15, "Ames"), ("Village of Oak Park", 16, "Oak Park"),
                                      ("Borough of Brooklyn", 13, "Brooklyn"), ("Hamlet of Foo", 17, "Foo"), ("Municipality of Bar", 14, "Bar")):
            self.assertEqual(names.plain_name(text, value), expected, text)

    def test_administrative_units_keep_their_word(self):
        """Consistent with "Polk County" and with the Hungarian "Bács-Bodrog vármegye" and "Zombori járás"."""
        for text, value in (("State of Iowa", 2), ("County of Polk", 3), ("Kingdom of Hungary", 1), ("Province of Ontario", 8),
                            ("District of Columbia", 12), ("Parish of X", 5), ("Region of Y", 9), ("Department of Z", 10)):
            self.assertEqual(names.plain_name(text, value), text, text)
        self.assertEqual(names.plain_name("County of Polk", None, "county"), "County of Polk")           # not even when an answer says county
        self.assertEqual(names.plain_name("Township of Webster", None, "township"), "Township of Webster")

    def test_the_type_text_of_an_answer_can_say_it_too(self):
        self.assertEqual(names.plain_name("City of Johnston", None, "city"), "Johnston")
        self.assertEqual(names.plain_name("Village of X", None, "large village / nagyközség"), "X")

    def test_a_different_type_leaves_the_name_alone(self):
        self.assertEqual(names.plain_name("City of Johnston", 16), "City of Johnston")             # a village is not a city
        self.assertEqual(names.plain_name("City of Johnston", None, ""), "City of Johnston")      # unknown type: no guess
        self.assertEqual(names.plain_name("City of Johnston", None, "unincorporated community"), "City of Johnston")

    def test_names_that_are_not_a_type_word_and_a_name_are_left_alone(self):
        for text in ("Bay of Pigs", "Isle of Man", "Gulf of Mexico", "Sea of Galilee", "Polk County", "Webster Township", "Bács-Bodrog vármegye",
                     "Zombori kerület", "Johnston", "United States of America", "Hungary"):
            self.assertEqual(names.plain_name(text, 4), text, text)

    def test_where_city_of_is_the_name_of_another_place_it_stays(self):
        self.assertEqual(names.plain_name("City of London", 4), "City of London")
        self.assertEqual(names.plain_name("City of Westminster", 4), "City of Westminster")

    def test_case_spaces_and_empty_values(self):
        self.assertEqual(names.plain_name("  CITY OF  Johnston ", 4), "Johnston")
        self.assertEqual(names.plain_name("", 4), "")
        self.assertEqual(names.plain_name(None, 4), "")
        self.assertEqual(names.plain_name("City of ", 4), "City of")                                # nothing is left: not touched


def tree(ptype=4, lang="en", **kw):
    t = Tree({"iowa": typed("iowa", "State of Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1),
              "city": typed("city", "City of Johnston", ptype, lang=lang)}, [])
    t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
    t.places["city"]["lat"], t.places["city"]["lon"] = "41.6", "-93.7"
    return t


ANSWER = """PLACE_NAME_ON_DATE: Johnston
LANGUAGE: en
SETTLEMENT_TYPE_ON_DATE: city
COORDINATES: 41.673, -93.6977
CONTAINERS:
1 | Polk County | county | 1846-present | Iowa
2 | State of Iowa | state | 1846-present | United States
STATE_ON_DATE: United States | 1776-present
"""


def analyse(t, text=ANSWER, year="1995"):
    return ingest.ingest(t, ingest.parse_structured(text), year, aliases=ingest.alias_map([WORLD]))


class IngestTests(unittest.TestCase):
    def test_the_answer_without_the_type_word_finds_the_place_that_has_it(self):
        r = analyse(tree())
        self.assertEqual(r["mode"], "existing")
        self.assertEqual([x["label"] for x in r["similar"]], ["City of Johnston [CITY]"])

    def test_and_the_answer_with_the_type_word_finds_the_place_without_it(self):
        t = tree()
        t.places["city"]["name"]["value"] = "Johnston"
        self.assertEqual(analyse(t, ANSWER.replace("PLACE_NAME_ON_DATE: Johnston", "PLACE_NAME_ON_DATE: City of Johnston"))["mode"], "existing")

    def test_a_new_container_is_created_with_the_simple_name_too(self):
        t = tree()
        del t.places["city"]
        text = ANSWER.replace("1 | Polk County | county | 1846-present | Iowa", "1 | Municipality of Ames | municipality | 1853-present | Iowa")
        r = analyse(t, text)                                                  # (a municipality above the city: a town above a city would break the levels)
        self.assertIn("Ames", [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"])

    def test_a_new_county_keeps_its_word(self):
        t = tree()
        del t.places["city"]
        r = analyse(t, ANSWER.replace("PLACE_NAME_ON_DATE: Johnston", "PLACE_NAME_ON_DATE: City of Johnston"))
        self.assertIn("Polk County", [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"])
        text = ANSWER.replace("1 | Polk County | county", "1 | County of Polk | county")
        self.assertIn("County of Polk", [p["names"][0]["value"] for p in analyse(t, text)["proposals"] if p["kind"] == "add-place"])

    def test_the_place_that_exists_with_the_long_name_gets_a_rename_to_choose(self):
        r = analyse(tree())
        (rename,) = [p for p in r["proposals"] if p["kind"] == "rename-place" and p["place"] == "city"]
        self.assertEqual((rename["value"], rename["new_value"], rename["lang"], rename["keep_old"], rename["index"]), ("City of Johnston", "Johnston", "en", True, 0))
        self.assertEqual((rename["basis"], rename["conflict"], rename["bundle"]), ("assumption", False, None))

    def test_so_does_a_settlement_of_the_chain_that_has_one_but_not_a_state(self):
        t = tree()
        t.places["ames"] = typed("ames", "Town of Ames", 15, lang="en")
        text = ANSWER.replace("1 | Polk County | county | 1846-present | Iowa", "1 | Ames | town | 1853-present | Iowa")
        r = analyse(t, text)
        self.assertTrue(any(p["kind"] == "rename-place" and p["place"] == "ames" and p["new_value"] == "Ames" for p in r["proposals"]))
        self.assertFalse(any(p["kind"] == "rename-place" and p["place"] == "iowa" for p in r["proposals"]))             # "State of Iowa" stays

    def test_no_rename_when_the_type_is_another_or_the_name_is_simple(self):
        self.assertFalse([p for p in analyse(tree(ptype=16))["proposals"] if p["kind"] == "rename-place" and p["place"] == "city"])
        t = tree()
        t.places["city"]["name"]["value"] = "Johnston"
        self.assertFalse([p for p in analyse(t)["proposals"] if p["kind"] == "rename-place" and p["place"] == "city"])


class SimulationTests(unittest.TestCase):
    def test_the_new_name_is_primary_and_the_old_one_is_kept_with_its_language_and_period(self):
        t = tree()
        t.places["city"]["name"]["date"] = {"modifier": 7, "quality": 0, "calendar": 0, "dateval": [0, 0, 1900, False], "text": "", "sortval": 1}
        rename = next(p for p in analyse(t)["proposals"] if p["kind"] == "rename-place" and p["place"] == "city")
        after = gaps.apply(t, [rename]).places["city"]
        self.assertEqual(after["name"]["value"], "Johnston")
        self.assertEqual([(n["value"], n["lang"], n["date"]["dateval"][2]) for n in after["alt_names"]], [("City of Johnston", "en", 1900)])
        self.assertEqual(t.places["city"]["name"]["value"], "City of Johnston")                  # the tree itself is not changed

    def test_the_old_name_is_not_added_twice(self):
        t = tree()
        t.places["city"]["alt_names"] = [{"value": "City of Johnston", "lang": "en", "date": EMPTY}]
        rename = next(p for p in analyse(t)["proposals"] if p["kind"] == "rename-place" and p["place"] == "city")
        self.assertEqual(len(gaps.apply(t, [rename]).places["city"]["alt_names"]), 1)


class SessionTests(unittest.TestCase):
    def session(self):
        s = sess.Session(tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(ANSWER)
        return s

    def test_it_is_a_choice_of_its_own_in_plain_words(self):
        renames = [c for c in self.session().changes() if c["flag"] == "renames place"]
        self.assertEqual([c["title"] for c in renames], [
            "Rename «City of Johnston [CITY]» to «Johnston» (previous name retained as alternative name)"])
        self.assertEqual(len(renames[0]["steps"]), 1)

    def test_choosing_it_changes_what_gramps_would_display_and_not_choosing_does_not(self):
        s = self.session()
        before = s.preview()[0]
        rename = next(c for c in s.changes() if "City of Johnston" in c["title"] and c["flag"] == "renames place")
        s.toggle_change(rename["id"])
        self.assertEqual(before.split(", ")[0], "City of Johnston")
        self.assertEqual(s.preview()[0].split(", ")[0], "Johnston")


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class WriterTests(unittest.TestCase):
    def open(self, t):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(t, path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        return db

    def renames(self, db):
        t = Tree.from_db(db)
        r = analyse(t)
        plan = planlib.make_plan(t, r["proposals"])
        return [p for p in plan["proposals"] if p["kind"] == "rename-place" and p["place"] == "city"], plan

    def test_the_name_is_simplified_and_the_old_one_is_kept_as_an_alternative(self):
        db = self.open(tree())
        chosen, _ = self.renames(db)
        results = writer.apply_proposals(db, chosen, dry_run=False)
        self.assertEqual([r["status"] for r in results], ["applied"])
        place = db.get_place_from_handle("city")
        self.assertEqual(place.get_name().get_value(), "Johnston")
        self.assertEqual([(a.get_value(), a.get_language()) for a in place.get_alternative_names()], [("City of Johnston", "en")])

    def test_gramps_displays_the_simple_name_afterwards(self):
        db = self.open(tree())
        chosen, _ = self.renames(db)
        writer.apply_proposals(db, chosen, dry_run=False)
        from gramps.gen.db import DbTxn
        ev = Event()
        ev.set_type(EventType.RESIDENCE)
        ev.set_place_handle("city")
        with DbTxn("event", db) as txn:
            db.add_event(ev, txn)
        self.assertEqual(place_displayer.display_event(db, ev), "Johnston, State of Iowa, USA")

    def test_it_is_one_undo(self):
        db = self.open(tree())
        _, plan = self.renames(db)
        picked = [p for p in plan["proposals"] if p["kind"] == "rename-place"]
        self.assertEqual(len(picked), 1)
        writer.apply_proposals(db, picked, dry_run=False)
        self.assertEqual(db.get_place_from_handle("city").get_name().get_value(), "Johnston")
        db.undo()
        self.assertEqual((db.get_place_from_handle("city").get_name().get_value(), db.get_place_from_handle("iowa").get_name().get_value()),
                         ("City of Johnston", "State of Iowa"))                                  # and the state was never touched

    def test_a_name_somebody_changed_meanwhile_is_not_renamed(self):
        db = self.open(tree())
        chosen, _ = self.renames(db)
        from gramps.gen.db import DbTxn
        place = db.get_place_from_handle("city")
        place.get_name().set_value("Johnston, Iowa")
        with DbTxn("somebody", db) as txn:
            db.commit_place(place, txn)
        results = writer.apply_proposals(db, chosen, dry_run=False)
        self.assertEqual([(r["status"], r["reason"]) for r in results], [("skipped", "place name was modified after analysis phase")])
        self.assertEqual(db.get_place_from_handle("city").get_name().get_value(), "Johnston, Iowa")

    def test_an_alternative_name_that_is_already_there_is_not_duplicated(self):
        t = tree()
        t.places["city"]["alt_names"] = [{"value": "City of Johnston", "lang": "en", "date": EMPTY}]
        db = self.open(t)
        chosen, _ = self.renames(db)
        writer.apply_proposals(db, chosen, dry_run=False)
        self.assertEqual(len(db.get_place_from_handle("city").get_alternative_names()), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
