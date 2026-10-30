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
"""Principle P0: a change to data that exists is chosen one by one, never by itself. The disconnect of a link, its dependency on the new link, the
button that chooses them all, and the writing of it on a real database."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from gramps.gen.db.utils import make_database                                                 # noqa: E402
from placecompleter import gaps, plan as planlib, session as sess, writer                     # noqa: E402
from placecompleter.dates import describe, M_FROM                                             # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import D, EMPTY                                                              # noqa: E402
from test_ingest import typed                                                                 # noqa: E402
import test_writer as tw                                                                      # noqa: E402


def sissa_tree(parents=("parma", "er", "it")):
    t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "parma": typed("parma", "Parma", 4, lang="en"),
              "prov": typed("prov", "Provincia di Parma", 8, lang="en"), "sissa": typed("sissa", "Sissa", 15, lang="en")}, [])
    t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
    t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
    t.places["prov"]["refs"] = [{"ref": "er", "date": EMPTY}]
    t.places["sissa"]["refs"] = [{"ref": p, "date": EMPTY} for p in parents]
    return t


def proposals():
    """The new link and the disconnects that need it: what the analysis of Sissa makes (the three old links are wrong)."""
    base = {"basis": "assumption", "confidence": "assumption", "origin": "ai-answer", "evidence": [], "events": 0, "worse": 0, "bundle": None,
            "child": "sissa", "old": {}, "new": {}, "conflict": False, "refines": False}
    new = dict(base, kind="add-link", parent="prov", index=3, new=D(M_FROM, 1861), key="link:sissa:prov")
    cuts = [dict(base, kind="remove-link", parent=parent, index=i, old={}, new={}, existing=True, inferred=True, requires_key="link:sissa:prov")
            for i, parent in enumerate(("parma", "er", "it"))]
    return [new] + cuts


class SessionTests(unittest.TestCase):
    def make(self):
        s = sess.Session(sissa_tree(), tempfile.mkdtemp(), pack_files=[])
        s.tree = sissa_tree()
        s.plan = planlib.make_plan(s.tree, proposals())
        s.rec, s.result = None, {"child": "sissa", "needs": [], "proposals": []}
        s.selected = set()
        return s

    def ids(self, s, kind):
        return {p["id"] for p in s.plan["proposals"] if p["kind"] == kind}

    def test_the_plan_keeps_the_marks(self):
        s = self.make()
        cut = next(p for p in s.plan["proposals"] if p["kind"] == "remove-link")
        self.assertEqual((cut["existing"], cut["requires_key"], cut["inferred"]), (True, "link:sissa:prov", True))
        self.assertEqual(next(p for p in s.plan["proposals"] if p["kind"] == "add-link")["key"], "link:sissa:prov")

    def test_what_the_window_selects_by_itself_is_the_addition_and_never_a_change_to_existing_data(self):
        s = self.make()
        s.select_all()
        self.assertEqual(s.selected, self.ids(s, "add-link"))

    def test_the_button_chooses_every_change_to_existing_data(self):
        s = self.make()
        s.select_all()
        self.assertTrue(s.has_existing())
        s.select_existing()
        self.assertEqual(s.selected, {p["id"] for p in s.plan["proposals"]})

    def test_choosing_a_disconnect_chooses_the_new_link_too(self):
        s = self.make()
        s.clear_selection()
        cut = sorted(self.ids(s, "remove-link"))[0]
        s.toggle(cut)
        self.assertEqual(s.selected, {cut} | self.ids(s, "add-link"))

    def test_unchoosing_the_new_link_unchooses_every_disconnect(self):
        s = self.make()
        s.select_existing()
        s.toggle(next(iter(self.ids(s, "add-link"))))
        self.assertEqual(s.selected, set())

    def test_unchoosing_one_disconnect_leaves_the_others_and_the_new_link(self):
        s = self.make()
        s.select_existing()
        cut = sorted(self.ids(s, "remove-link"))[0]
        s.toggle(cut)
        self.assertEqual(s.selected, {p["id"] for p in s.plan["proposals"]} - {cut})

    def test_the_changes_say_what_they_are_and_what_they_need(self):
        s = self.make()
        s.select_all()
        rows = s.changes()
        cuts = [c for c in rows if c["title"].startswith("Disconnect ")]
        self.assertEqual(len(cuts), 3)
        for c in cuts:
            self.assertTrue(c["existing"] and not c["selected"])
            self.assertEqual(c["flag"], "disconnects place link")
            self.assertIn("Requires the new link: selecting this option automatically checks the dependent link", c["why"])
        self.assertEqual(cuts[0]["title"], "Disconnect «Sissa [SISSA]» from «Parma [PARMA]» (removes hierarchy link; retains place entities)")
        self.assertFalse(next(c for c in rows if not c["existing"])["existing"])

    def test_the_preview_shows_the_place_without_the_disconnected_links(self):
        t = sissa_tree()
        out = gaps.apply(t, planlib.make_plan(t, proposals())["proposals"])
        self.assertEqual([r["ref"] for r in out.places["sissa"]["refs"]], ["prov"])
        self.assertEqual(len(t.places["sissa"]["refs"]), 3)                                       # the tree itself is not changed


class WriterTests(unittest.TestCase):
    def test_the_links_are_disconnected_on_a_real_database_and_nothing_else_is_deleted(self):
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        t = sissa_tree()
        ids = {h: t.places[h]["id"] for h in t.places}
        path = os.path.join(tw.TMP, "disconnect")
        helper.build_from(t, path)
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            plan = planlib.make_plan(tree, proposals())
            done = writer.apply_proposals(db, planlib.select(plan, ids={p["id"] for p in plan["proposals"]}), dry_run=False)
            self.assertEqual({r["status"] for r in done}, {"applied"}, done)
            now = Tree.from_db(db)
            self.assertEqual([(r["ref"], describe(r["date"])) for r in now.places["sissa"]["refs"]], [("prov", "from 1861")])
            self.assertEqual(sorted(db.get_place_handles()), sorted(ids))                          # no place is deleted
            for handle, gramps_id in ids.items():
                self.assertEqual(db.get_place_from_handle(handle).get_gramps_id(), gramps_id)
            self.assertEqual([r["ref"] for r in now.places["parma"]["refs"]], ["er"])               # the other links of the places are as they were
        finally:
            db.close()

    def test_a_disconnect_is_not_made_when_the_link_is_no_longer_there(self):
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        path = os.path.join(tw.TMP, "disconnect-stale")
        helper.build_from(sissa_tree(parents=("er",)), path)                                       # the tree has only one link, not the three
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            plan = planlib.make_plan(tree, proposals())
            done = writer.apply_proposals(db, planlib.select(plan, ids={p["id"] for p in plan["proposals"] if p["kind"] == "remove-link"}), dry_run=False)
            self.assertEqual({r["reason"] for r in done if r["status"] == "skipped"}, {"parent hierarchy link position has shifted"})
            self.assertEqual(len(Tree.from_db(db).places["sissa"]["refs"]), 1)
        finally:
            db.close()


class TypeChangeTests(unittest.TestCase):
    """The region Emilia-Romagna is typed State (or Country) in the tree and the answer says region: a type of Gramps that is not the kind of unit the answer
    names is offered to be changed, as a change to data that exists (chosen one by one)."""
    ANSWER = os.path.join(HERE, "data", "answer_sissa_1990_v2.txt")

    def run_it(self, region_type, region_string=""):
        from placecompleter import ingest
        t = sissa_tree(parents=())
        t.places["er"]["type"] = {"value": region_type, "string": region_string}
        with open(self.ANSWER, encoding="utf-8") as fh:
            return t, ingest.ingest(t, ingest.parse_structured(fh.read()), "1990", aliases={})

    def changes(self, r):
        return [p for p in r["proposals"] if p["kind"] == "change-type"]

    def test_a_region_typed_state_or_country_is_offered_a_change_to_region(self):
        for held in (2, 1):
            _t, r = self.run_it(held)
            found = [(p["place"], p["old_type_value"], p["type_value"], p["existing"], p["inferred"]) for p in self.changes(r)]
            self.assertIn(("er", held, 9, True, True), found, held)

    def test_a_type_of_the_same_kind_is_left_alone(self):
        for held in (9, 8, 3, 12, 10):                                                           # region, province, county, district, department
            self.assertEqual([p for p in self.changes(self.run_it(held)[1]) if p["place"] == "er"], [], held)

    def test_a_custom_type_of_the_tree_is_never_changed(self):
        self.assertEqual([p for p in self.changes(self.run_it(0, "a type of ours")[1]) if p["place"] == "er"], [])

    def test_the_country_typed_state_is_not_offered_a_change(self):                              # Gramps' Hebrew calls both of them the same word
        t, r = self.run_it(9)
        t.places["it"]["type"] = {"value": 2, "string": ""}
        from placecompleter import ingest
        with open(self.ANSWER, encoding="utf-8") as fh:
            r = ingest.ingest(t, ingest.parse_structured(fh.read()), "1990", aliases={})
        self.assertEqual([p for p in self.changes(r) if p["place"] == "it"], [])

    def test_a_type_that_is_empty_is_filled_and_not_changed(self):
        _t, r = self.run_it(-1)
        self.assertEqual(self.changes(r), [])
        self.assertTrue([p for p in r["proposals"] if p["kind"] == "set-type" and p["place"] == "er"])

    def test_the_change_is_one_box_that_is_not_chosen_by_itself(self):
        t, r = self.run_it(2)
        s = sess.Session(t, tempfile.mkdtemp(), pack_files=[])
        s.tree, s.plan, s.rec, s.result = t, planlib.make_plan(t, r["proposals"]), None, {"child": "sissa", "needs": [], "proposals": []}
        s.select_all()
        row = next(c for c in s.changes() if c["title"].startswith("Change administrative place type of"))
        self.assertEqual(row["title"], "Change administrative place type of «Emilia-Romagna [ER]» from State to Region")
        self.assertEqual((row["selected"], row["existing"], row["flag"], row["confidence_level"]), (False, True, "modifies place type", "inferred"))

    def test_the_type_is_changed_on_a_real_database_and_only_if_it_is_still_the_one_that_was_seen(self):
        from placecompleter import ingest
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        t = sissa_tree(parents=())
        t.places["er"]["type"] = {"value": 2, "string": ""}
        path = os.path.join(tw.TMP, "type-change")
        helper.build_from(t, path)
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            with open(self.ANSWER, encoding="utf-8") as fh:
                screen = ingest.ingest(tree, ingest.parse_structured(fh.read()), "1990", aliases={})
            plan = planlib.make_plan(tree, screen["proposals"])
            ids = {q["id"] for q in plan["proposals"] if q["kind"] == "change-type"}
            self.assertEqual(len(ids), 1)
            done = writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)
            self.assertEqual({r["status"] for r in done}, {"applied"})
            self.assertEqual(db.get_place_from_handle("er").get_type().value, 9)
            self.assertEqual(db.get_place_from_handle("er").get_gramps_id(), tree.places["er"]["id"])
            again = writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)             # the type is not the one that was seen any more
            self.assertEqual([(r["status"], r["reason"]) for r in again], [("skipped", "place type was modified after analysis phase")])
        finally:
            db.close()


class DamagedTreeTests(unittest.TestCase):
    """The tree of the user as the screenshots show it, after runs of an older analysis: the link to the province was cut to the years until 1945 and Sissa was linked
    directly to the region (from 1970) and to the state (from 1946). Gramps showed Sissa under the region, also for 1990."""
    ANSWER = """PLACE_NAME_ON_DATE: Sissa
LANGUAGE: it
OTHER_NAMES: eml: S\u00e9sa (1860-present)
SETTLEMENT_TYPE_ON_DATE: municipality, comune
COORDINATES: 44.9614, 10.2589
CONTAINERS: 1 | Sissa | municipality, comune | 1861-2013 | Italia
2 | Provincia di Parma | province, provincia | 1861-present | Italia
3 | Emilia-Romagna | region, regione | 1970-present | Italia
4 | Italia | sovereign state | 1946-present | Italia
STATE_ON_DATE: Italia | 1946-present
SOURCES: https://en.wikipedia.org/wiki/Sissa,_Sissa_Trecasali | supports name, coordinates, status, history
NOT_SURE: NONE
"""

    def tree(self):
        from placecompleter.dates import M_FROM, M_SPAN
        t = sissa_tree(parents=())
        t.places["it"]["type"], t.places["er"]["type"] = {"value": 1, "string": ""}, {"value": 2, "string": ""}
        t.places["prov"]["refs"] = [{"ref": "er", "date": D(M_FROM, 1970)}]
        t.places["sissa"]["refs"] = [{"ref": "prov", "date": D(M_SPAN, 1861, 1, 2, y2=1945)}, {"ref": "er", "date": D(M_FROM, 1970)}, {"ref": "it", "date": D(M_FROM, 1946)}]
        return t

    def shown(self, db, year=None):
        from gramps.gen.display.place import displayer
        from gramps.gen.lib import Date
        day = None
        if year:
            day = Date()
            day.set_yr_mon_day(year, 6, 15)
        return displayer.display(db, db.get_place_from_handle("sissa"), day)

    def run_once(self, path, choose):
        from placecompleter import ingest
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
            screen = ingest.ingest(tree, ingest.parse_structured(self.ANSWER), "1990", aliases=ingest.alias_map([world]))
            plan = planlib.make_plan(tree, screen["proposals"])
            ids = {q["id"] for q in plan["proposals"] if choose == "everything" or not q["existing"]}
            if ids:
                writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)
            now = Tree.from_db(db)
            return plan, [(now.places[r["ref"]]["name"]["value"], describe(r["date"])) for r in now.places["sissa"]["refs"]], self.shown(db, 1990)
        finally:
            db.close()

    def test_the_tree_shows_the_region_before_and_the_province_after_the_changes_are_chosen(self):
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        path = os.path.join(tw.TMP, "damaged")
        helper.build_from(self.tree(), path)
        db = make_database("sqlite")
        db.load(path)
        self.assertEqual(self.shown(db, 1990), "Sissa, Emilia-Romagna, Italy")                       # what the screenshots show
        db.close()
        plan, links, shown = self.run_once(path, "additions")
        kinds = sorted((q["kind"], q.get("parent") or q.get("place"), q["existing"]) for q in plan["proposals"] if q["existing"])
        self.assertEqual(kinds, [("change-type", "er", True), ("remove-link", "er", True), ("remove-link", "it", True), ("set-link", "prov", True)])
        self.assertEqual(shown, "Sissa, Emilia-Romagna, Italy")                                       # by itself nothing that exists is changed
        plan, links, shown = self.run_once(path, "everything")
        self.assertEqual(links, [("Provincia di Parma", "from 1861")])                                # the year of the answer, not a year before
        self.assertEqual(shown, "Sissa, Provincia di Parma, Emilia-Romagna, Italy")
        self.assertEqual(self.run_once(path, "everything")[0]["proposals"], [])

    def test_the_disconnects_need_the_widened_link_so_that_no_year_is_left_without_a_parent(self):
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        path = os.path.join(tw.TMP, "damaged-deps")
        helper.build_from(self.tree(), path)
        db = make_database("sqlite")
        db.load(path)
        try:
            from placecompleter import ingest
            tree = Tree.from_db(db)
            world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
            screen = ingest.ingest(tree, ingest.parse_structured(self.ANSWER), "1990", aliases=ingest.alias_map([world]))
            s = sess.Session(tree, tempfile.mkdtemp(), pack_files=[])
            s.tree, s.plan, s.rec, s.result = tree, planlib.make_plan(tree, screen["proposals"]), None, {"child": "sissa", "needs": [], "proposals": []}
            s.clear_selection()
            cut = next(p["id"] for p in s.plan["proposals"] if p["kind"] == "remove-link" and p["parent"] == "er")
            fix = next(p["id"] for p in s.plan["proposals"] if p["kind"] == "set-link" and p["parent"] == "prov")
            s.toggle(cut)
            self.assertEqual(s.selected, {cut, fix})                                                  # choosing the disconnect chooses the widening
            s.toggle(fix)
            self.assertEqual(s.selected, set())                                                       # unchoosing the widening unchooses the disconnect
        finally:
            db.close()


class NamePeriodTests(unittest.TestCase):
    """The period that the answer gives to the place itself (the municipality of Sissa 1806-2013) is not the period of its name: the village goes on being called Sissa.
    With the end in the name, Gramps showed the dialect name for today."""
    def answer(self, first="1806-2013", other="eml: S\u00e9sa (1806-present)"):
        return DamagedTreeTests.ANSWER.replace("1861-2013", first).replace("eml: S\u00e9sa (1860-present)", other)

    def run_it(self, tree, text):
        from placecompleter import ingest
        world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
        return ingest.ingest(tree, ingest.parse_structured(text), "1990", aliases=ingest.alias_map([world]))

    def named_tree(self, name_date):
        t = sissa_tree(parents=())
        t.places["sissa"]["name"]["date"] = name_date
        t.places["sissa"]["name"]["lang"] = "it"                                                    # the language of the answer, as in the tree of the user
        return t

    def test_a_new_place_gets_its_name_from_the_start_of_the_place_and_no_end(self):
        r = self.run_it(Tree({}, []), self.answer())
        place = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Sissa")
        self.assertEqual(describe(place["names"][0]["date"]), "from 1806")
        self.assertTrue(any("name «Sissa» period end date remains open" in n for n in r["needs"]), r["needs"])

    def test_a_later_name_in_the_answer_ends_the_name(self):
        text = self.answer(other="sk: Nuova Sissa (2014-present)")
        place = next(p for p in self.run_it(Tree({}, []), text)["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Sissa")
        self.assertEqual(describe(place["names"][0]["date"]), "span 1806..2013")                      # a name that follows it: the end is real

    def test_a_name_in_the_tree_that_ends_with_the_place_is_offered_to_be_opened(self):
        from placecompleter.dates import M_SPAN
        t = self.named_tree(D(M_SPAN, 1806, y2=2013))
        r = self.run_it(t, self.answer())
        fix = [p for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "sissa"]
        self.assertEqual([(p["value"], describe(p["old"]), describe(p["new"]), p["existing"]) for p in fix], [("Sissa", "span 1806..2013", "from 1806", True)])
        self.assertTrue(any("name «Sissa» end date (2013) matches response boundary without successor name" in n for n in r["needs"]))

    def test_a_name_that_ends_at_another_time_or_has_a_later_name_is_left_alone(self):
        from placecompleter.dates import M_SPAN
        for date, text in ((D(M_SPAN, 1806, y2=1999), self.answer()),
                           (D(M_SPAN, 1806, y2=2013), self.answer(other="sk: Nuova Sissa (2014-present)"))):
            fix = [p for p in self.run_it(self.named_tree(date), text)["proposals"] if p["kind"] == "set-name-date" and p["place"] == "sissa" and p["existing"]]
            self.assertEqual(fix, [])

    def test_a_name_that_is_open_or_has_no_period_gets_nothing_new(self):
        from placecompleter.dates import M_FROM
        fix = [p for p in self.run_it(self.named_tree(D(M_FROM, 1806)), self.answer())["proposals"] if p["kind"] == "set-name-date" and p["place"] == "sissa"]
        self.assertEqual(fix, [])

    def test_gramps_shows_sissa_and_not_the_dialect_name_once_the_name_is_open(self):
        from placecompleter.dates import M_FROM, M_SPAN
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        t = self.named_tree(D(M_SPAN, 1806, y2=2013))
        t.places["sissa"]["alt_names"] = [{"_class": "PlaceName", "value": "S\u00e9sa", "lang": "eml", "date": D(M_FROM, 1806)}]
        path = os.path.join(tw.TMP, "name-open")
        helper.build_from(t, path)
        checker = DamagedTreeTests()

        def title():
            db = make_database("sqlite")
            db.load(path)
            try:
                return checker.shown(db)
            finally:
                db.close()
        self.assertTrue(title().startswith("S\u00e9sa"))                                              # the dialect name, as in the tree of the user
        db = make_database("sqlite")
        db.load(path)
        try:
            from placecompleter import ingest
            tree = Tree.from_db(db)
            screen = self.run_it(tree, self.answer())
            plan = planlib.make_plan(tree, screen["proposals"])
            ids = {q["id"] for q in plan["proposals"] if q["kind"] == "set-name-date" and q["place"] == "sissa"}
            self.assertEqual(len(ids), 1)
            done = writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)
            self.assertEqual({r["status"] for r in done}, {"applied"})
        finally:
            db.close()
        self.assertTrue(title().startswith("Sissa"), title())                                           # and Sissa after the change


class TheYearDecidesTests(unittest.TestCase):
    """The year decides which hierarchy Gramps shows: an existing hierarchy that is not wrong is kept, and the hierarchy of the year of the question is added before it, so
    that the place is inside two parents, each for its own years (Sissa in 2026, Kfar Hess in 1948)."""
    def display(self, path, handle, year=None):
        from gramps.gen.display.place import displayer
        from gramps.gen.lib import Date
        db = make_database("sqlite")
        db.load(path)
        try:
            day = None
            if year:
                day = Date()
                day.set_yr_mon_day(year, 6, 15)
            return displayer.display(db, db.get_place_from_handle(handle), day)
        finally:
            db.close()

    def apply(self, path, text, date, choose="additions"):
        from placecompleter import ingest
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
            screen = ingest.ingest(tree, ingest.parse_structured(text), date, aliases=ingest.alias_map([world]))
            plan = planlib.make_plan(tree, screen["proposals"])
            ids = {q["id"] for q in plan["proposals"] if choose == "everything" or not q["existing"]}
            if ids:
                writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)
            return plan
        finally:
            db.close()

    def test_sissa_in_2026_is_inside_the_municipality_and_in_1990_inside_the_province(self):
        from placecompleter.dates import M_FROM
        text = ("PLACE_NAME_ON_DATE: Sissa\nLANGUAGE: it\nSETTLEMENT_TYPE_ON_DATE: frazione, village\nCONTAINERS: 1 | Sissa Trecasali | municipality, comune | 2014-present | Italia\n"
                "2 | Provincia di Parma | province, provincia | 1861-present | Italia\n3 | Emilia-Romagna | region, regione | 1970-present | Italia\n"
                "4 | Italia | sovereign state | 1946-present | Italia\nSTATE_ON_DATE: Italia | 1946-present\nSOURCES: https://en.wikipedia.org/wiki/Sissa | supports name\n")
        t = sissa_tree(parents=("prov",))
        t.places["prov"]["refs"] = [{"ref": "er", "date": D(M_FROM, 1970)}]
        t.places["sissa"]["refs"] = [{"ref": "prov", "date": D(M_FROM, 1861)}]
        path = os.path.join(tw.TMP, "sissa-2026")
        tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle").build_from(t, path)
        self.assertEqual(self.display(path, "sissa", 2026), "Sissa, Provincia di Parma, Emilia-Romagna, Italy")
        plan = self.apply(path, text, "2026")
        self.assertEqual(self.display(path, "sissa", 2026), "Sissa, Sissa Trecasali, Provincia di Parma, Emilia-Romagna, Italy")      # the year of the question
        self.assertEqual(self.display(path, "sissa", 1990), "Sissa, Provincia di Parma, Emilia-Romagna, Italy")                       # the old hierarchy for its years
        self.assertEqual([(q["kind"], q["parent"]) for q in plan["proposals"] if q["existing"]], [("set-link", "prov")])               # the cut is offered, not made
        self.apply(path, text, "2026", "everything")
        self.assertEqual(self.display(path, "sissa", 1990), "Sissa, Provincia di Parma, Emilia-Romagna, Italy")
        self.assertEqual(self.apply(path, text, "2026", "everything")["proposals"], [])

    def test_kfar_hess_in_1948_is_in_two_parents_each_for_its_years(self):
        text = ("PLACE_NAME_ON_DATE: Kfar Hess\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: village\nCONTAINERS: 1 | Central District | district | 1948-1953 | Israel\n"
                "STATE_ON_DATE: Israel | 1948-present\nSOURCES: https://en.wikipedia.org/wiki/Kfar_Hess | supports name\n")
        t = Tree({"il": typed("il", "Israel", 1, lang="en"), "sharon": typed("sharon", "HaSharon", 12, lang="en"), "lev": typed("lev", "Lev HaSharon", 14, lang="en"),
                  "kh": typed("kh", "Kfar Hess", 16, lang="en")}, [])
        t.places["sharon"]["refs"] = [{"ref": "il", "date": EMPTY}]
        t.places["lev"]["refs"] = [{"ref": "sharon", "date": EMPTY}]
        t.places["kh"]["refs"] = [{"ref": "lev", "date": EMPTY}]                                     # a hierarchy with no dates: right for 2026
        path = os.path.join(tw.TMP, "kfar-hess")
        tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle").build_from(t, path)
        plan = self.apply(path, text, "1948")
        self.assertFalse([q for q in plan["proposals"] if q["existing"]])                            # nothing that exists is cut or disconnected
        self.assertEqual(self.display(path, "kh", 1948), "Kfar Hess, Central District, Israel")                    # the hierarchy of the year of the question
        self.assertEqual(self.display(path, "kh", 2026), "Kfar Hess, Lev HaSharon, HaSharon, Israel")


class TopPlaceTests(unittest.TestCase):
    """Standing on a place, the window gets the highest place above it as the Region hint: Trecasali brings Italy."""
    def tree(self):
        from placecompleter.dates import M_FROM, M_SPAN
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "prov": typed("prov", "Provincia di Parma", 8, lang="en"),
                  "st": typed("st", "Sissa Trecasali", 14, lang="en"), "tre": typed("tre", "Trecasali", 17, lang="en"), "old": typed("old", "Duchy of Parma", 2, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["st"]["refs"] = [{"ref": "prov", "date": EMPTY}]
        t.places["tre"]["refs"] = [{"ref": "st", "date": D(M_FROM, 2014)}, {"ref": "old", "date": D(M_SPAN, 1814, y2=1859)}]
        return t

    def db(self):
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        path = os.path.join(tempfile.mkdtemp(dir=tw.TMP), "top-place")
        helper.build_from(self.tree(), path)
        db = make_database("sqlite")
        db.load(path)
        return db

    def test_the_highest_place_above_is_the_country(self):
        from placecompleter import grampslink
        db = self.db()
        try:
            self.assertEqual(grampslink.top_name(db, db.get_place_from_handle("tre")), "Italy")
            self.assertEqual(grampslink.top_name(db, db.get_place_from_handle("prov")), "Italy")
            self.assertEqual(grampslink.top_name(db, db.get_place_from_handle("it")), "")                  # the country itself has none above it
        finally:
            db.close()

    def test_it_follows_the_date_of_the_event(self):
        from gramps.gen.lib import Date
        from placecompleter import grampslink
        db = self.db()
        try:
            place = db.get_place_from_handle("tre")
            day = Date()
            day.set_yr_mon_day(1850, 6, 15)
            self.assertEqual(grampslink.top_name(db, place, day), "Duchy of Parma")                       # the hierarchy of the year of the event
            day.set_yr_mon_day(2026, 6, 15)
            self.assertEqual(grampslink.top_name(db, place, day), "Italy")
            self.assertEqual(grampslink.top_name(db, place, Date()), "Italy")                             # an event with no date: as the list shows it
        finally:
            db.close()

    def test_the_summaries_carry_it(self):
        from gramps.gen.lib import Date, Event
        from placecompleter import grampslink
        db = self.db()
        try:
            self.assertEqual(grampslink.place_summary(db, db.get_place_from_handle("tre"))["top_name"], "Italy")
            event = Event()
            event.set_place_handle("tre")
            when = Date()
            when.set_yr_mon_day(1850, 6, 15)
            event.set_date_object(when)
            self.assertEqual(grampslink.event_summary(db, event)["top_name"], "Duchy of Parma")
            event.set_place_handle("")
            self.assertEqual(grampslink.event_summary(db, event)["top_name"], "")
        finally:
            db.close()


class NameCoversTheDateTests(unittest.TestCase):
    """Trecasali: a run for 2026 gave the name the years of the parent (Sissa Trecasali, from 2014). The name must be valid on the date of the question."""
    ANSWER_2026 = """PLACE_NAME_ON_DATE: Trecasali
LANGUAGE: it
SETTLEMENT_TYPE_ON_DATE: frazione, village
COORDINATES: 44.9225, 10.2725
CONTAINERS: 1 | Sissa Trecasali | municipality, comune | 2014-present | Italy
2 | Provincia di Parma | province, provincia | 1861-present | Italy
3 | Emilia-Romagna | region, regione | 1970-present | Italy
4 | Italy | country | 1946-present | Italy
STATE_ON_DATE: Italy | 1946-present
SOURCES: https://it.wikipedia.org/wiki/Trecasali | supports name
"""
    ANSWER_1990 = """PLACE_NAME_ON_DATE: Trecasali
LANGUAGE: it
OTHER_NAMES: pms: Trecasali (1861-present)
SETTLEMENT_TYPE_ON_DATE: municipality, comune
COORDINATES: 44.9225, 10.2725
CONTAINERS: 1 | Provincia di Parma | province, provincia | 1861-present | Italy
2 | Emilia-Romagna | region, regione | 1970-present | Italy
3 | Italy | country | 1946-present | Italy
STATE_ON_DATE: Italy | 1946-present
NOTES: Trecasali was an independent municipality in 1990.
SOURCES: https://it.wikipedia.org/wiki/Trecasali | supports name, location
NOT_SURE: NONE
"""

    def run_it(self, tree, text, date):
        from placecompleter import ingest
        world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
        return ingest.ingest(tree, ingest.parse_structured(text), date, aliases=ingest.alias_map([world]))

    def test_a_new_place_does_not_take_the_years_of_its_parent_as_the_years_of_its_name(self):
        r = self.run_it(Tree({}, []), self.ANSWER_2026, "2026")
        place = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Trecasali")
        self.assertEqual(describe(place["names"][0]["date"]), "from 1946")                           # when the state began, not 2014
        self.assertTrue(any("name «Trecasali» applies from 1946 (establishment of ruling state" in n for n in r["needs"]), r["needs"])

    def test_a_name_that_covers_the_date_or_ends_before_it_is_left_alone(self):
        from placecompleter.dates import M_FROM, M_SPAN
        for date in (D(M_FROM, 1900), D(M_SPAN, 1800, y2=1950), EMPTY):
            t = sissa_tree(parents=())
            t.places["sissa"]["name"] = {"value": "Trecasali", "lang": "it", "date": date}
            fix = [p for p in self.run_it(t, self.ANSWER_1990, "1990")["proposals"] if p["kind"] == "set-name-date" and p["place"] == "sissa" and p.get("existing")]
            self.assertEqual(fix, [], describe(date))

class ParmaTests(unittest.TestCase):
    """The city Parma sits directly under the region; the answer puts it under the Provincia di Parma, under the Regione Emilia-Romagna. The region is the region of the tree
    (the word "Regione" says what it is): no second region is made, and Parma goes under the province."""
    ANSWER = os.path.join(HERE, "data", "answer_parma_1990.txt")

    def tree(self, prov_type=8):
        from placecompleter.dates import M_FROM
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "parma": typed("parma", "Parma", 4, lang="en"),
                  "prov": typed("prov", "Provincia di Parma", prov_type, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": D(M_FROM, 1946)}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er", "date": D(M_FROM, 1970)}]
        return t

    def run_it(self, tree, choices=None):
        from placecompleter import ingest
        world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
        with open(self.ANSWER, encoding="utf-8") as fh:
            return ingest.ingest(tree, ingest.parse_structured(fh.read()), "1990", aliases=ingest.alias_map([world]), choices=choices)

    def test_the_region_with_the_word_regione_is_the_region_of_the_tree(self):
        r = self.run_it(self.tree())
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]], [("Provincia di Parma", "prov"), ("Regione Emilia-Romagna", "er"), ("Italia", "it")])
        self.assertEqual([p for p in r["proposals"] if p["kind"] == "add-place"], [])                        # no second region
        self.assertEqual(r["ambiguous"], [])

    def test_parma_is_linked_under_the_province_before_its_link_to_the_region(self):
        r = self.run_it(self.tree())
        links = [(p["child"], p["parent"], p.get("position"), p.get("above")) for p in r["proposals"] if p["kind"] == "add-link"]
        self.assertEqual(links, [("parma", "prov", 0, "er")])                                                  # the other two links exist already

    def test_the_words_that_say_what_a_unit_is_do_not_make_a_second_place(self):
        for with_word, plain in (("Regione Emilia-Romagna", "Emilia-Romagna"), ("Land Salzburg", "Salzburg"), ("Departement Nord", "Nord"), ("Contea di Parma", "Parma"),
                                 ("Provincia di Parma", "Parma"), ("Comunidad de Madrid", "Madrid"), ("Landkreis Ansbach", "Ansbach")):
            from placecompleter import ingest
            self.assertEqual(set(ingest._tokens(with_word)), set(ingest._tokens(plain)), with_word)
        from placecompleter import ingest
        self.assertNotEqual(set(ingest._tokens("Regione Lazio")), set(ingest._tokens("Regione Lombardia")))

    def test_a_word_that_is_not_known_makes_the_tree_suggest_the_region_and_ask(self):
        from placecompleter import ingest
        with open(self.ANSWER, encoding="utf-8") as fh:
            text = fh.read().replace("Regione Emilia-Romagna", "Zona Emilia-Romagna")
        world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
        r = ingest.ingest(self.tree(), ingest.parse_structured(text), "1990", aliases=ingest.alias_map([world]))
        self.assertEqual([(a["name"], [c["label"].split(" [")[0] for c in a["candidates"]]) for a in r["ambiguous"]], [("Zona Emilia-Romagna", ["Emilia-Romagna"])])
        self.assertEqual([p for p in r["proposals"] if p["kind"] == "add-place"], [])                          # nothing is made until the answer

    def test_gramps_shows_parma_under_the_province_after_the_run_and_the_second_run_adds_nothing(self):
        from gramps.gen.display.place import displayer
        from placecompleter import ingest
        helper = tw.IngestWriterTests("test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle")
        path = os.path.join(tempfile.mkdtemp(dir=tw.TMP), "parma")
        helper.build_from(self.tree(), path)

        def run_once():
            db = make_database("sqlite")
            db.load(path)
            try:
                tree = Tree.from_db(db)
                screen = self.run_it(tree)
                plan = planlib.make_plan(tree, screen["proposals"])
                ids = {q["id"] for q in plan["proposals"] if not q["existing"]}
                if ids:
                    done = writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)
                    self.assertEqual({r["status"] for r in done}, {"applied"})
                return plan, displayer.display(db, db.get_place_from_handle("parma")), db.get_number_of_places()
            finally:
                db.close()
        plan, title, count = run_once()
        self.assertEqual(title, "Parma, Provincia di Parma, Emilia-Romagna, Italy")
        self.assertEqual(count, 4)                                                                          # no place was made
        plan, title, count = run_once()
        self.assertEqual((title, count), ("Parma, Provincia di Parma, Emilia-Romagna, Italy", 4))
        self.assertEqual([q["kind"] for q in plan["proposals"] if not q["existing"] and q["kind"] in ("add-link", "add-place")], [])     # nothing more to add


class DuplicateAndLoopNotesTests(unittest.TestCase):
    """Two things that earlier runs left in a tree and that the analysis must say: a second place for the same level (Regione Emilia-Romagna beside Emilia-Romagna), and a
    level that would make a loop (the province inside the city that the answer puts inside it)."""
    ANSWER = ParmaTests.ANSWER

    def run_it(self, tree, choices=None):
        from placecompleter import ingest
        world = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")
        with open(self.ANSWER, encoding="utf-8") as fh:
            return ingest.ingest(tree, ingest.parse_structured(fh.read()), "1990", aliases=ingest.alias_map([world]), choices=choices)

    def duplicates(self, r):
        return [n for n in r["needs"] if "appears identical to" in n]

    def test_a_second_place_for_the_same_level_is_said(self):
        t = ParmaTests().tree()
        t.places["er2"] = typed("er2", "Regione Emilia-Romagna", 9, lang="it")
        t.places["er2"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er2", "date": EMPTY}, {"ref": "er", "date": D(__import__("placecompleter.dates", fromlist=["M_FROM"]).M_FROM, 1970)}]
        asked = self.run_it(t)
        self.assertEqual([(a["slot"], a["name"]) for a in asked["ambiguous"]], [("c2", "Regione Emilia-Romagna")])      # both are candidates: the window asks which one
        found = self.duplicates(self.run_it(t, choices={"c2": "er"}))                                                   # the user says: Emilia-Romagna
        self.assertEqual(found, ["Provincia di Parma [PROV] is also linked to Regione Emilia-Romagna [ER2], which appears identical to Emilia-Romagna [ER] "
                                 "(same name and type). Merge them in Gramps (Edit > Merge Places) to consolidate this hierarchy level"])

    def test_another_region_or_another_kind_is_not_a_duplicate(self):
        for name, kind in (("Lazio", 9), ("Emilia-Romagna", 4)):
            t = ParmaTests().tree()
            t.places["x"] = typed("x", name, kind, lang="it")
            t.places["prov"]["refs"].append({"ref": "x", "date": EMPTY})
            self.assertEqual(self.duplicates(self.run_it(t)), [], name)

    def test_a_tree_without_a_duplicate_says_nothing(self):
        self.assertEqual(self.duplicates(self.run_it(ParmaTests().tree())), [])

    def test_a_level_that_would_make_a_loop_is_left_out_with_a_note(self):
        t = ParmaTests().tree()
        t.places["prov"]["refs"].append({"ref": "parma", "date": EMPTY})                              # the province is inside the city: Parma cannot go inside it
        r = self.run_it(t)
        self.assertTrue(any("Parma [PARMA] -> Provincia di Parma excluded from hierarchy chain: this would create a circular hierarchy loop" in n for n in r["needs"]), r["needs"])
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "add-link" and p["child"] == "parma" and p["parent"] == "prov"])


class PeriodTests(unittest.TestCase):
    def test_a_period_that_starts_a_year_starts_at_that_year_and_not_the_one_before(self):
        from placecompleter import ingest
        from placecompleter.dates import interval, sdn, ymd
        lo = ingest._bound("1861", False)
        self.assertEqual(describe(ingest._piece(lo, ingest.INF)), "from 1861")                          # it was "from 1860"
        self.assertEqual(ymd(interval(ingest._piece(lo, ingest.INF))[0])[0], 1861)
        self.assertEqual(describe(ingest._piece(sdn(1861, 1, 2), sdn(1945, 12, 31))), "span 1861..1945")  # not "1861-1-2"
        self.assertEqual(describe(ingest._piece(sdn(1861, 3, 5), ingest.INF)), "from 1861-3-4")           # a day inside a year is kept
        self.assertEqual(describe(ingest._piece(-ingest.INF, sdn(1860, 12, 31))), "to 1861")



class SelectExistingButtonTests(unittest.TestCase):
    """The button \"Select all changes to existing data\" chooses what it can and says what it leaves out (a conflict is checked one by one)."""
    def fake(self, proposals):
        import types
        return types.SimpleNamespace(plan={"proposals": proposals}, selected=set(), _enforce=lambda selecting: None)

    def run_button(self, proposals, selected=()):
        from placecompleter import session as sess
        fake = self.fake(proposals)
        fake.selected = set(selected)
        return fake, sess.Session.select_existing(fake)

    def test_a_change_in_conflict_is_not_chosen_and_is_counted(self):
        fake, done = self.run_button([{"id": 1, "kind": "set-link", "existing": True, "conflict": True},
                                      {"id": 2, "kind": "set-name-date", "existing": True, "conflict": True}])
        self.assertEqual((fake.selected, done), (set(), {"chosen": 0, "already": 0, "conflicts": 2}))

    def test_the_others_are_chosen_and_the_conflict_is_still_counted(self):
        fake, done = self.run_button([{"id": 1, "kind": "set-link", "existing": True, "conflict": False},
                                      {"id": 2, "kind": "rename-place", "existing": True, "conflict": True},
                                      {"id": 3, "kind": "add-link", "existing": False, "conflict": False}])
        self.assertEqual((fake.selected, done), ({1}, {"chosen": 1, "already": 0, "conflicts": 1}))            # an addition is not touched by this button

    def test_what_was_chosen_before_is_reported_and_not_chosen_again(self):
        fake, done = self.run_button([{"id": 1, "kind": "set-link", "existing": True, "conflict": False}], selected={1})
        self.assertEqual((fake.selected, done), ({1}, {"chosen": 0, "already": 1, "conflicts": 0}))


class SelectAllButtonTests(unittest.TestCase):
    """The one button "Select all": it chooses everything that can be chosen, leaves for the user what it must, and pressed again unchecks everything."""
    def session(self, proposals):
        import tempfile
        from placecompleter import session as sess
        from placecompleter.model import Tree
        from test_ingest import WORLD
        s = sess.Session(Tree({}, []), tempfile.mkdtemp(), pack_files=[WORLD])
        s.plan = {"proposals": proposals}
        s.selected = set()
        return s

    @staticmethod
    def p(pid, kind="add-place", **kw):
        base = {"id": pid, "kind": kind, "existing": False, "conflict": False, "optional": False, "bundle": None, "key": "", "requires_key": ""}
        base.update(kw)
        return base

    def mixed(self):
        return [self.p(1), self.p(2, "add-url"), self.p(3, "add-url", optional=True),
                self.p(4, "set-link", existing=True, child="a", parent="b", index=0, new={"x": 1}),
                self.p(5, "set-name-date", existing=True, conflict=True, place="a", index=0, value="n", lang="", new={"x": 2})]

    def test_everything_that_can_be_chosen_is_chosen_changes_to_what_exists_too(self):
        s = self.session(self.mixed())
        done = s.toggle_all()
        self.assertEqual(s.selected, {1, 2, 4})
        self.assertEqual((done["action"], done["chosen"], done["conflicts"], done["optional"], done["exclusive"]), ("selected", 3, 1, 1, 0))

    def test_pressed_again_it_unchecks_everything_even_what_was_checked_by_hand(self):
        s = self.session(self.mixed())
        s.toggle_all()
        s.selected.add(3)                                                           # the user also checked the unknown site by hand
        self.assertTrue(s.all_selected())
        self.assertEqual(s.toggle_all()["action"], "cleared")
        self.assertEqual(s.selected, set())
        self.assertFalse(s.all_selected())
        self.assertEqual(s.toggle_all()["action"], "selected")                      # and once more, it chooses again

    def test_what_is_chosen_by_hand_before_is_kept_when_it_chooses(self):
        s = self.session(self.mixed())
        s.selected = {3}
        s.toggle_all()
        self.assertEqual(s.selected, {1, 2, 3, 4})

    def test_two_changes_that_decide_the_same_thing_differently_are_left_for_the_user(self):
        both = [self.p(1, "set-name-date", place="a", index=0, value="n", lang="", new={"d": 1}),
                self.p(2, "set-name-date", place="a", index=0, value="n", lang="", new={"d": 2}),
                self.p(3, "set-coordinates", place="a", lat="1", lon="2")]
        s = self.session(both)
        done = s.toggle_all()
        self.assertEqual((s.selected, done["exclusive"]), ({3}, 2))

    def test_checking_one_of_two_rivals_by_hand_unchecks_the_other(self):
        both = [self.p(1, "set-coordinates", place="a", lat="1", lon="2"), self.p(2, "set-coordinates", place="a", lat="3", lon="4")]
        s = self.session(both)
        s.toggle(1)
        self.assertEqual(s.selected, {1})
        s.toggle(2)
        self.assertEqual(s.selected, {2})                                           # one or the other, never both
        s.toggle(2)
        self.assertEqual(s.selected, set())

    def test_the_same_decision_twice_is_not_a_rivalry(self):
        from placecompleter import plan as planlib
        same = [self.p(1, "set-coordinates", place="a", lat="1", lon="2"), self.p(2, "set-coordinates", place="a", lat="1", lon="2"),
                self.p(3, "set-coordinates", place="b", lat="9", lon="9")]
        self.assertEqual(planlib.rivals(same), {})
        other = [self.p(1, "set-type", place="a", type_value=4), self.p(2, "change-type", place="a", type_value=8)]
        self.assertEqual(planlib.rivals(other), {1: {2}, 2: {1}})                    # two types for the same place

    def test_a_step_is_left_when_the_step_it_needs_is_left_and_a_bundle_is_chosen_whole(self):
        steps = [self.p(1, "add-link", key="new", conflict=True), self.p(2, "remove-link", requires_key="new", existing=True),
                 self.p(3, "add-place", bundle="b1"), self.p(4, "add-link", bundle="b1", conflict=True), self.p(5)]
        s = self.session(steps)
        done = s.toggle_all()
        self.assertEqual(s.selected, {5})
        self.assertEqual((done["conflicts"], done["needs"]), (2, 2))

    def test_nothing_to_choose_means_nothing_chosen(self):
        s = self.session([self.p(1, "add-url", optional=True)])
        self.assertEqual((s.toggle_all()["chosen"], s.selected, s.all_selected()), (0, set(), False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
