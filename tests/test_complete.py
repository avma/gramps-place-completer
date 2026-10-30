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
"""complete-place on REAL Wikidata answers (tests/data/wikidata_mini.json), without network."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import cli, complete, gaps, packs, plan as planlib, wikidata   # noqa: E402
from placecompleter.dates import M_NONE                                          # noqa: E402
from placecompleter.model import Tree                                            # noqa: E402
from test_engine import D, EMPTY, event, place                                   # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json")


def client(*searches):
    c = wikidata.Client(cache_path=FIXTURE)
    for text, language, ids in searches:
        url = "%s?action=wbsearchentities&search=%s&language=%s&limit=5&format=json" % (wikidata.API, urllib.parse.quote(text), language)
        c.answers[url] = {"search": [{"id": i} for i in ids]}
    return c


def yugoslav_tree(**extra):
    t = Tree({"y": place("y", "Socialist Federal Republic of Yugoslavia", 1)}, [])
    for k, v in extra.items():
        t.places[k] = v
    return t


SUBOTICA = ("Subotica City", "en", ["Q1041949"])


class DateTests(unittest.TestCase):
    def test_dates_keep_their_precision(self):
        d, sv = complete.parse_date("1850")
        self.assertEqual(d["dateval"], [0, 0, 1850, False])
        self.assertEqual(sv, complete.parse_date("1850-01-01")[1])
        with self.assertRaises(ValueError):
            complete.parse_date("185x")

    def test_a_claim_is_valid_on_its_dates_only(self):
        c = {"start": "1944-07-31", "end": "1990-09-28"}
        self.assertTrue(complete.valid_at(c, complete.parse_date("1950")[1]))
        self.assertFalse(complete.valid_at(c, complete.parse_date("1850")[1]))
        self.assertTrue(complete.valid_at({"start": "1804", "end": "1867"}, complete.parse_date("1867-12-31")[1]))
        self.assertFalse(complete.valid_at({"start": "1804", "end": "1867"}, complete.parse_date("1868")[1]))


class NewPlaceTests(unittest.TestCase):
    def setUp(self):
        self.r = complete.complete_place(yugoslav_tree(), "Subotica City", "1950", client(SUBOTICA))

    def test_the_place_is_identified_with_its_coordinates(self):
        self.assertEqual((self.r["selected"]["qid"], self.r["mode"]), ("Q1041949", "new"))
        self.assertIn("46.0475", next(x["value"] for x in self.r["rows"] if x["field"] == "coordinates"))

    def test_the_hierarchy_on_that_date_runs_up_to_the_first_place_the_tree_has(self):
        self.assertEqual([(s["child"], s["parent"], s["start"], s["end"], s["stop"]) for s in self.r["chain"]], [
            ("Q1041949", "Q843919", "1944-07-31", "1990-09-28", False),
            ("Q843919", "Q269864", "1945-04-09", "1990-09-28", False),
            ("Q269864", "Q83286", "1945-11-29", "1992-04-27", True)])

    def test_the_names_follow_the_language_of_the_state_on_that_date(self):
        self.assertEqual(self.r["preview"], ["Град Суботица", "Социјалистичка Аутономна Покрајина Војводина", "СР Србија",
                                             "Socialist Federal Republic of Yugoslavia"])
        names = [p["names"][0] for p in self.r["proposals"] if p["kind"] == "add-place"]
        self.assertTrue(all(n["lang"] == "sr" for n in names))

    def test_new_places_and_links_form_one_bundle_that_the_writer_understands(self):
        kinds = sorted(p["kind"] for p in self.r["proposals"])
        self.assertEqual(kinds, ["add-link"] * 3 + ["add-place"] * 3)
        self.assertEqual(len({p["bundle"] for p in self.r["proposals"]}), 1)
        links = {p["parent"] for p in self.r["proposals"] if p["kind"] == "add-link"}
        self.assertIn("y", links)                                   # the last link goes to the place that already exists
        plan = planlib.make_plan(yugoslav_tree(), self.r["proposals"])
        self.assertEqual(len(planlib.select(plan, ids={plan["proposals"][0]["id"]})), 6)   # all or nothing

    def test_the_urls_of_the_new_places_are_their_wikidata_items(self):
        for p in self.r["proposals"]:
            if p["kind"] == "add-place":
                self.assertTrue(p["urls"][0]["path"].startswith("https://www.wikidata.org/wiki/Q"))

    def test_the_screen_is_rendered(self):
        text = complete.render(self.r)
        self.assertIn("GRAMPS WOULD DISPLAY: Град Суботица", text)
        self.assertIn("HIERARCHY ON 1950", text)
        self.assertIn("(already in the tree)", text)

    def test_the_language_can_be_forced(self):
        r = complete.complete_place(yugoslav_tree(), "Subotica City", "1950", client(SUBOTICA), language="hu")
        self.assertEqual(r["preview"][0], "Szabadka község")


class DateWithoutHierarchyTests(unittest.TestCase):
    def test_without_dated_statements_the_screen_says_what_is_missing(self):
        r = complete.complete_place(yugoslav_tree(), "Subotica City", "1850", client(SUBOTICA))
        self.assertEqual(r["chain"], [])
        self.assertTrue(any("no dated hierarchy" in n for n in r["needs"]))
        self.assertEqual([p["kind"] for p in r["proposals"]], ["add-place"])           # the place itself, no links
        self.assertEqual(r["proposals"][0]["names"][0]["value"], "Subotica City")      # the name as typed: no state rule
        self.assertEqual(r["preview"], ["Subotica City"])


class AmbiguityTests(unittest.TestCase):
    ZOMBOR = [("Zombor", "en", ["Q204475", "Q219814"]), ("Zombor", "hu", ["Q204475", "Q219814"])]

    def test_two_places_with_one_name_are_not_guessed(self):
        r = complete.complete_place(yugoslav_tree(), "Zombor", "1950", client(*self.ZOMBOR))
        self.assertIsNone(r["selected"])
        self.assertEqual({c["qid"] for c in r["candidates"]}, {"Q204475", "Q219814"})
        self.assertTrue(any("--pick" in n for n in r["needs"]))
        self.assertIn("candidates in Wikidata", complete.render(r))

    def test_a_region_word_decides(self):
        r = complete.complete_place(yugoslav_tree(), "Zombor", "1950", client(*self.ZOMBOR), region="Serbia")
        self.assertEqual(r["selected"]["qid"], "Q204475")

    def test_an_explicit_pick_decides(self):
        r = complete.complete_place(yugoslav_tree(), "Zombor", "1950", client(*self.ZOMBOR), pick="Q219814")
        self.assertEqual(r["selected"]["qid"], "Q219814")

    def test_an_unknown_name_is_reported(self):
        r = complete.complete_place(yugoslav_tree(), "Nowhere-on-Sea", "1950", client())
        self.assertIsNone(r["selected"])
        self.assertTrue(any("was found in Wikidata" in n for n in r["needs"]))


class DuplicateTests(unittest.TestCase):
    def test_a_place_that_looks_the_same_is_reported_before_anything_is_created(self):
        near = place("s", "Суботица", 4)
        near["lat"], near["lon"] = "46.1", "19.66"
        r = complete.complete_place(yugoslav_tree(s=near), "Subotica City", "1950", client(SUBOTICA))
        self.assertTrue(any(x["label"].startswith("Суботица") and "km away" in " ".join(x["reasons"]) for x in r["similar"]))
        self.assertIn("SIMILAR PLACES ALREADY IN THE TREE", complete.render(r))

    def test_a_place_with_the_same_wikidata_link_is_used_instead_of_a_new_one(self):
        known = place("k", "Szabadka", 4)
        known["urls"] = ["https://www.wikidata.org/wiki/Q1041949"]
        r = complete.complete_place(yugoslav_tree(k=known), "Subotica City", "1950", client(SUBOTICA))
        self.assertEqual(r["mode"], "existing")
        self.assertNotIn("add-place", [p["kind"] for p in r["proposals"] if p.get("handle") == "new:wd-Q1041949"])
        self.assertEqual(next(p for p in r["proposals"] if p["kind"] == "add-link")["child"], "k")


class CommandLineTests(unittest.TestCase):
    def test_the_command_prints_the_screen_and_writes_a_plan(self):
        from test_agent_loop import write_db
        with tempfile.TemporaryDirectory() as tmp:
            db, extra, out = os.path.join(tmp, "t.db"), os.path.join(tmp, "x.json"), os.path.join(tmp, "plan.json")
            write_db(yugoslav_tree(), db)
            with open(extra, "w", encoding="utf-8") as fh:
                json.dump(client(SUBOTICA).answers, fh)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(["complete-place", "Subotica City", "--date", "1950", "--db", db, "--seed", FIXTURE,
                                 "--seed", extra, "--cache", os.path.join(tmp, "c.json"), "--out", out])
            self.assertEqual(code, 0)
            self.assertIn("GRAMPS WOULD DISPLAY: Град Суботица", buf.getvalue())
            plan = planlib.load_plan(out)
            self.assertEqual(len(plan["proposals"]), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
