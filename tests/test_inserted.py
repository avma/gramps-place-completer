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
"""A level put in between: the new link is written BEFORE the old direct link, which is left exactly as it is. Real Gramps database."""
import os
import sys
import tempfile
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import Date, Event, EventType
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import ingest, plan as planlib, writer                                   # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
from test_ingest import WORLD, typed                                                          # noqa: E402

ANSWER = ("PLACE_NAME_ON_DATE: City of Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
          "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\n"
          "STATE_ON_DATE: United States | 1776-present\n")


def tree():
    t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
              "city": typed("city", "City of Johnston", 4, lang="en")}, [])
    t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
    return t


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class InsertedLinkTests(unittest.TestCase):
    def open(self):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(tree(), path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        return db

    def steps(self, db):
        t = Tree.from_db(db)
        r = ingest.ingest(t, ingest.parse_structured(ANSWER), "1995", aliases=ingest.alias_map([WORLD]))
        plan = planlib.make_plan(t, r["proposals"])
        return [p for p in plan["proposals"] if p["kind"] in ("add-place", "add-link")]

    def parents(self, db):
        return [r.ref for r in db.get_place_from_handle("city").get_placeref_list()]

    def show(self, db, year):
        ev = Event()
        ev.set_type(EventType.RESIDENCE)
        ev.set_place_handle("city")
        d = Date()
        d.set(modifier=Date.MOD_NONE, value=(0, 0, year, False))
        ev.set_date_object(d)
        with DbTxn("event %d" % year, db) as txn:
            db.add_event(ev, txn)
        return place_displayer.display_event(db, ev)

    def test_the_proposals_are_the_place_and_two_links_and_nothing_cuts_the_old_one(self):
        db = self.open()
        steps = self.steps(db)
        self.assertEqual(sorted(p["kind"] for p in steps), ["add-link", "add-link", "add-place"])
        first = next(p for p in steps if p["kind"] == "add-link" and p["child"] == "city")
        self.assertEqual((first["position"], first["above"]), (0, "iowa"))

    def test_the_new_link_is_written_before_the_old_one_and_the_old_one_is_untouched(self):
        db = self.open()
        old = db.get_place_from_handle("city").get_placeref_list()[0]
        old_date = (old.get_date_object().get_modifier(), old.get_date_object().get_year())
        results = writer.apply_proposals(db, self.steps(db), dry_run=False)
        self.assertEqual({r["status"] for r in results}, {"applied"})
        parents = self.parents(db)
        self.assertEqual(len(parents), 2)
        self.assertNotEqual(parents[0], "iowa")                                           # the new level is first
        self.assertEqual(parents[1], "iowa")                                              # the old direct link is second
        after = db.get_place_from_handle("city").get_placeref_list()[1]
        self.assertEqual((after.get_date_object().get_modifier(), after.get_date_object().get_year()), old_date)
        self.assertEqual(db.get_place_from_handle(parents[0]).get_name().get_value(), "Polk County")
        self.assertEqual(db.get_place_from_handle(parents[0]).get_name().get_language(), "en")

    def test_gramps_shows_the_new_level_for_its_years_and_the_old_chain_for_the_others(self):
        db = self.open()
        writer.apply_proposals(db, self.steps(db), dry_run=False)
        self.assertEqual(self.show(db, 1995), "City of Johnston, Polk County, Iowa, USA")
        self.assertEqual(self.show(db, 1800), "City of Johnston, Iowa, USA")

    def test_it_is_one_undo(self):
        db = self.open()
        writer.apply_proposals(db, self.steps(db), dry_run=False)
        db.undo()
        self.assertEqual(self.parents(db), ["iowa"])
        self.assertEqual(len(list(db.iter_place_handles())), 3)                           # the new place is gone too

    def test_a_position_beyond_the_list_puts_the_link_last(self):
        db = self.open()
        steps = self.steps(db)
        next(p for p in steps if p["kind"] == "add-link" and p["child"] == "city")["position"] = 99
        writer.apply_proposals(db, steps, dry_run=False)
        self.assertEqual(self.parents(db)[0], "iowa")

    def test_a_dry_run_writes_nothing(self):
        db = self.open()
        writer.apply_proposals(db, self.steps(db), dry_run=True)
        self.assertEqual(self.parents(db), ["iowa"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
