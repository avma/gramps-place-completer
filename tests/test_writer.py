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
"""Writing a plan into a real Gramps database: dry run, one transaction, Undo, stale targets.

Needs the Gramps library. Skipped without it. Everything happens in a temporary folder.
"""
import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="pc-writer-")
os.environ["GRAMPSHOME"] = os.path.join(TMP, "home")
os.environ["LANGUAGE"] = "en"

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import Date, Event, EventType, Place, PlaceName, PlaceRef, PlaceType
    HAVE_GRAMPS = True
except Exception:                        # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import cli, gaps, packs, plan as planlib             # noqa: E402
from placecompleter.model import Tree                                   # noqa: E402


def build(path):
    db = make_database("sqlite")
    os.makedirs(path)
    db.load(path)

    def span(a, b):
        d = Date()
        d.set(modifier=Date.MOD_SPAN, value=(0, 0, a, False, 0, 0, b, False))
        return d

    with DbTxn("build", db) as txn:
        def make(name, ptype, name_date=None, lang=""):
            p, n = Place(), PlaceName()
            n.set_value(name)
            n.set_language(lang)
            if name_date:
                n.set_date_object(name_date)
            p.set_name(n)
            p.set_type(ptype)
            return p

        def link(child, parent, mod=None, value=None):
            ref = PlaceRef()
            ref.ref = parent.get_handle()
            if mod is not None:
                d = Date()
                d.set(modifier=mod, value=value)
                ref.set_date_object(d)
            child.add_placeref(ref)

        empire = make("Kaisertum Österreich", PlaceType.UNKNOWN, span(1804, 1867))
        monarchy = make("Austro-Hungarian Monarchy", PlaceType.UNKNOWN, span(1867, 1918))
        hungary = make("Hungary", PlaceType.COUNTRY)
        db.add_place(empire, txn)
        db.add_place(monarchy, txn)
        link(hungary, monarchy, Date.MOD_FROM, (0, 0, 1867, False))
        link(hungary, empire, Date.MOD_NONE, (0, 0, 1859, False))
        db.add_place(hungary, txn)
        village = make("Berechiu", PlaceType.VILLAGE, None, "ro")
        d = Date()
        d.set(modifier=Date.MOD_FROM, value=(0, 0, 1920, False))
        village.get_name().set_date_object(d)
        link(village, hungary)
        db.add_place(village, txn)
        for place, year in ((hungary, 1810), (hungary, 1850), (hungary, 1925), (village, 1900), (village, 1950)):
            ev = Event()
            ev.set_type(EventType.RESIDENCE)
            ev.set_place_handle(place.get_handle())
            dd = Date()
            dd.set_yr_mon_day(year, 5, 1)
            ev.set_date_object(dd)
            db.add_event(ev, txn)
    db.close()
    with open(os.path.join(path, "name.txt"), "w") as fh:
        fh.write("TEST COPY")


def displays(path):
    db = make_database("sqlite")
    db.load(path, mode="r")
    try:
        return {h: place_displayer.display_event(db, db.get_event_from_handle(h)) for h in db.get_event_handles()}
    finally:
        db.close()


def sha(path):
    with open(os.path.join(path, "sqlite.db"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


PACK = {"schema": packs.SCHEMA, "pack": {"id": "t", "origin": "user"},
        "places": [{"key": "h", "names": ["Hungary"], "type_value": 1},
                   {"key": "e", "names": ["Kaisertum Österreich"]},
                   {"key": "v", "names": ["Berechiu", {"name": "Alsóberekszó", "language": "hu", "valid_from": "1700",
                                                       "valid_to": "1919", "basis": "lifetime"}]}],
        "edges": [{"child": "h", "parent": "e", "valid_from": "1804", "valid_to": "1867", "origin": "user"}]}


def make_plan(path):
    tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
    rows = gaps.analyse(tree)
    props = gaps.propose_end_clips(tree, rows)
    found, _ = packs.propose_from_pack(gaps.apply(tree, props), packs.validate(PACK))
    return tree, props + found, planlib.make_plan(tree, props + found)


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class WriterTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "tree%d" % id(self))
        build(self.path)

    def open_db(self, write=True):
        db = make_database("sqlite")
        db.load(self.path, mode="w" if write else "r")
        return db

    def test_the_plan_has_three_kinds_of_basis(self):
        _tree, _props, plan = make_plan(self.path)
        self.assertEqual(sorted(p["basis"] for p in plan["proposals"]), ["assumption", "evidence", "tree"])

    def test_a_dry_run_changes_nothing(self):
        from placecompleter import writer
        _tree, _props, plan = make_plan(self.path)
        before = sha(self.path)
        db = self.open_db(write=False)
        try:
            results = writer.apply_proposals(db, plan["proposals"], dry_run=True)
        finally:
            db.close()
        self.assertEqual({r["status"] for r in results}, {"dry-run"})
        self.assertEqual(sha(self.path), before)

    def test_applying_gives_exactly_the_simulated_display_and_undo_reverts_it_all(self):
        from placecompleter import writer
        tree, props, plan = make_plan(self.path)
        simulated = {r["event"]["handle"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(tree, props))}
        original = displays(self.path)
        self.assertNotEqual(original, simulated)
        db = self.open_db()
        try:
            results = writer.apply_proposals(db, plan["proposals"], dry_run=False)
            self.assertEqual({r["status"] for r in results}, {"applied"})
            self.assertTrue(db.undo())                     # ONE undo step reverts every change
            self.assertTrue(db.redo())
        finally:
            db.close()
        self.assertEqual(displays(self.path), simulated)

    def test_undo_alone_restores_the_original(self):
        from placecompleter import writer
        _tree, _props, plan = make_plan(self.path)
        original = displays(self.path)
        db = self.open_db()
        try:
            writer.apply_proposals(db, plan["proposals"], dry_run=False)
            self.assertTrue(db.undo())
        finally:
            db.close()
        self.assertEqual(displays(self.path), original)

    def test_a_target_that_changed_since_the_analysis_is_skipped(self):
        from placecompleter import writer
        tree, _props, plan = make_plan(self.path)
        hungary = next(h for h, p in tree.places.items() if p["name"]["value"] == "Hungary")
        db = self.open_db()
        try:
            with DbTxn("someone edits", db) as txn:
                place = db.get_place_from_handle(hungary)
                d = Date()
                d.set(modifier=Date.MOD_FROM, value=(0, 0, 1870, False))
                place.get_placeref_list()[0].set_date_object(d)
                db.commit_place(place, txn)
            results = {r["id"]: r for r in writer.apply_proposals(db, plan["proposals"], dry_run=False)}
        finally:
            db.close()
        end_link = next(p["id"] for p in plan["proposals"] if p["kind"] == "end-link")
        self.assertEqual(results[end_link]["status"], "skipped")
        self.assertIn("after analysis", results[end_link]["reason"])
        others = [r for i, r in results.items() if i != end_link]
        self.assertTrue(all(r["status"] == "applied" for r in others))

    def test_applying_twice_adds_nothing(self):
        from placecompleter import writer
        _tree, _props, plan = make_plan(self.path)
        for _ in range(2):
            db = self.open_db()
            try:
                results = writer.apply_proposals(db, plan["proposals"], dry_run=False)
            finally:
                db.close()
        self.assertTrue(all(r["status"] == "skipped" for r in results))


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class NewPlaceWriterTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "newplace%d" % id(self))
        build(self.path)
        db = make_database("sqlite")                    # like Bajmok: the village's only link ends in 1920
        db.load(self.path)
        with DbTxn("limit the link", db) as txn:
            for handle in db.get_place_handles():
                place = db.get_place_from_handle(handle)
                if place.get_name().get_value() == "Berechiu":
                    d = Date()
                    d.set(modifier=Date.MOD_TO, value=(0, 0, 1920, False))
                    place.get_placeref_list()[0].set_date_object(d)
                    db.commit_place(place, txn)
        db.close()
        self.pack = {"schema": packs.SCHEMA, "pack": {"id": "np", "origin": "user"},
                     "places": [{"key": "v", "names": ["Berechiu"]},
                                {"key": "n", "create": True, "type_value": 3, "wikidata_qid": "Q1", "coordinates": {"lat": 47.2, "lon": 23.0},
                                 "names": [{"name": "Salaj County", "language": "en", "valid_from": "1950", "valid_to": "2100"}]}],
                     "edges": [{"child": "v", "parent": "n", "valid_from": "1950", "valid_to": "2100", "origin": "user"}]}

    def plan(self):
        tree = Tree.from_sqlite(os.path.join(self.path, "sqlite.db"))
        props, _ = packs.propose_from_pack(tree, packs.validate(self.pack))
        return tree, props, planlib.make_plan(tree, props)

    def open_db(self, write=True):
        db = make_database("sqlite")
        db.load(self.path, mode="w" if write else "r")
        return db

    def test_a_new_place_and_its_link_are_written_in_one_transaction_and_undone_together(self):
        from placecompleter import writer
        tree, props, plan = self.plan()
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "add-place"])
        simulated = {r["event"]["handle"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(tree, props))}
        original, places_before = displays(self.path), len(tree.places)
        db = self.open_db()
        try:
            results = writer.apply_proposals(db, plan["proposals"], dry_run=False)
            self.assertEqual({r["status"] for r in results}, {"applied"})
            self.assertEqual(db.get_number_of_places(), places_before + 1)
            created = [db.get_place_from_handle(h) for h in db.get_place_handles()
                       if db.get_place_from_handle(h).get_name().get_value() == "Salaj County"][0]
            self.assertEqual((int(created.get_type()), created.get_latitude(), created.get_url_list()[0].get_path()),
                             (PlaceType.COUNTY, "47.2", "https://www.wikidata.org/wiki/Q1"))
            self.assertTrue(db.undo())
            self.assertEqual(db.get_number_of_places(), places_before)       # the new place is gone with its link
            self.assertTrue(db.redo())
        finally:
            db.close()
        self.assertEqual(displays(self.path), simulated)
        self.assertNotEqual(displays(self.path), original)

    def test_applying_the_bundle_twice_creates_the_place_once(self):
        from placecompleter import writer
        _tree, _props, plan = self.plan()
        for _ in range(2):
            db = self.open_db()
            try:
                writer.apply_proposals(db, plan["proposals"], dry_run=False)
                count = db.get_number_of_places()
            finally:
                db.close()
        self.assertEqual(count, len(Tree.from_sqlite(os.path.join(self.path, "sqlite.db")).places))
        names = [p["name"]["value"] for p in Tree.from_sqlite(os.path.join(self.path, "sqlite.db")).places.values()]
        self.assertEqual(names.count("Salaj County"), 1)


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class CompletePlaceWriterTests(unittest.TestCase):
    def test_a_completed_place_is_written_and_an_event_there_shows_exactly_the_preview(self):
        import urllib.parse
        from placecompleter import complete, wikidata, writer
        path = os.path.join(TMP, "complete")
        db = make_database("sqlite")
        os.makedirs(path)
        db.load(path)
        with DbTxn("build", db) as txn:
            yu = Place()
            yn = PlaceName()
            yn.set_value("Socialist Federal Republic of Yugoslavia")
            yu.set_name(yn)
            yu.set_type(PlaceType.COUNTRY)
            db.add_place(yu, txn)
        db.close()
        fixture = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json")
        client = wikidata.Client(cache_path=fixture)
        client.answers["%s?action=wbsearchentities&search=%s&language=en&limit=5&format=json" % (
            wikidata.API, urllib.parse.quote("Subotica City"))] = {"search": [{"id": "Q1041949"}]}
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        screen = complete.complete_place(tree, "Subotica City", "1950", client)
        plan = planlib.make_plan(tree, screen["proposals"])
        db = make_database("sqlite")
        db.load(path)
        try:
            results = writer.apply_proposals(db, plan["proposals"], dry_run=False)
            self.assertEqual({r["status"] for r in results}, {"applied"})
            town = next(db.get_place_from_handle(h) for h in db.get_place_handles()
                        if db.get_place_from_handle(h).get_name().get_value() == "Град Суботица")
            self.assertEqual(town.get_name().get_language(), "sr")
            self.assertEqual(town.get_latitude(), "46.0475")
            with DbTxn("an event on that date", db) as txn:
                ev = Event()
                ev.set_type(EventType.RESIDENCE)
                ev.set_place_handle(town.get_handle())
                d = Date()
                d.set_yr_mon_day(1950, 0, 0)
                ev.set_date_object(d)
                db.add_event(ev, txn)
            shown = place_displayer.display_event(db, ev)
        finally:
            db.close()
        self.assertEqual(shown, ", ".join(screen["preview"]))


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class IngestWriterTests(unittest.TestCase):
    def build_from(self, tree, path):
        from placecompleter import writer
        db = make_database("sqlite")
        os.makedirs(path)
        db.load(path)
        with DbTxn("build", db) as txn:
            objects = {}
            for handle, p in tree.places.items():
                place = Place()
                place.set_handle(handle)
                place.set_gramps_id(p["id"])
                name = PlaceName()
                name.set_value(p["name"]["value"])
                name.set_language(p["name"].get("lang") or "")
                name.set_date_object(writer.date_from_dict(p["name"].get("date") or {}))
                place.set_name(name)
                for a in p["alt_names"]:
                    alt = PlaceName()
                    alt.set_value(a["value"])
                    alt.set_language(a.get("lang") or "")
                    alt.set_date_object(writer.date_from_dict(a.get("date") or {}))
                    place.add_alternative_name(alt)
                place.set_type((p["type"]["value"], p["type"].get("string", "")) if p["type"].get("string") else p["type"]["value"])
                objects[handle] = place
            for handle, p in tree.places.items():
                for r in p["refs"]:
                    ref = PlaceRef()
                    ref.ref = r["ref"]
                    ref.set_date_object(writer.date_from_dict(r.get("date") or {}))
                    objects[handle].add_placeref(ref)
                db.add_place(objects[handle], txn)
        db.close()

    def test_the_real_answer_applied_in_gramps_shows_what_the_preview_promised(self):
        from placecompleter import ingest, writer
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_ingest
        path = os.path.join(TMP, "ingest")
        self.build_from(test_ingest.tree(), path)
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        screen = ingest.ingest(tree, test_ingest.answer(), "1850", skip={2})
        plan = planlib.make_plan(tree, screen["proposals"])
        everything = {p["id"] for p in plan["proposals"]}
        db = make_database("sqlite")
        db.load(path)
        try:
            results = writer.apply_proposals(db, planlib.select(plan, ids=everything), dry_run=False)
            self.assertEqual({r["status"] for r in results}, {"applied"})
            baj = next(h for h in db.get_place_handles() if db.get_place_from_handle(h).get_name().get_value() == "Bajmok")
            with DbTxn("events", db) as txn:
                shown = {}
                for year in (1845, 1850, 1900):
                    ev = Event()
                    ev.set_type(EventType.RESIDENCE)
                    ev.set_place_handle(baj)
                    d = Date()
                    d.set_yr_mon_day(year, 5, 1)
                    ev.set_date_object(d)
                    db.add_event(ev, txn)
                    shown[year] = place_displayer.display_event(db, ev)
        finally:
            db.close()
        self.assertEqual(shown[1850], ", ".join(screen["preview"]))
        self.assertEqual(shown[1845], "Bajmok, Bácsalmási járás")
        self.assertEqual(shown[1900], "Bajmok, Bácsalmási járás, Bács-Bodrog vármegye, Magyarország")


    def test_a_county_that_exists_is_completed_and_no_second_one_is_made(self):
        """Deva is linked to Județul Hunedoara; the answer calls the county Hunedoara (1925-1938): written for real, the county is the same one,
        it gets its type, the language and the period of its name, and the place gets the start of its own name; no place is added."""
        from placecompleter import ingest, writer
        from placecompleter.dates import describe
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_ingest
        from test_engine import EMPTY
        t = Tree({"ro": test_ingest.typed("ro", "România", 1, lang="ro"), "hun": test_ingest.typed("hun", "Județul Hunedoara", -1),
                  "deva": test_ingest.typed("deva", "Deva", 4)}, [])
        t.places["hun"]["refs"] = [{"ref": "ro", "date": EMPTY}]
        t.places["deva"]["refs"] = [{"ref": "hun", "date": EMPTY}]
        path = os.path.join(TMP, "hunedoara")
        self.build_from(t, path)
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        answer = ("PLACE_NAME_ON_DATE: Deva\nLANGUAGE: ro\nSETTLEMENT_TYPE_ON_DATE: city (oraș)\nCONTAINERS:\n"
                  "1 | Hunedoara | county (județ) | 1925-1938 | Romania\nSTATE_ON_DATE: Romania | 1918-present\n")
        screen = ingest.ingest(tree, ingest.parse_structured(answer), "1930", aliases={})
        plan = planlib.make_plan(tree, screen["proposals"])
        self.assertFalse([q for q in plan["proposals"] if q["kind"] == "add-place"])
        chosen = planlib.select(plan, ids={q["id"] for q in plan["proposals"] if q["kind"] in ("set-type", "set-name-language", "set-name-date")})
        db = make_database("sqlite")
        db.load(path)
        try:
            before = db.get_number_of_places()
            done = writer.apply_proposals(db, chosen, dry_run=False)
            self.assertEqual({r["status"] for r in done}, {"applied"})
            self.assertEqual(db.get_number_of_places(), before)                                    # no second Hunedoara
            now = Tree.from_db(db)
            county, deva = now.places["hun"], now.places["deva"]
            self.assertEqual((county["type"]["value"], county["name"]["lang"]), (3, "ro"))
            self.assertEqual(describe(county["name"]["date"]), "span 1925..1938")
            self.assertEqual(describe(deva["name"]["date"]), "from 1918")
        finally:
            db.close()


    def test_a_confirmed_name_is_added_to_the_place_and_no_existing_place_changes_its_id_or_handle(self):
        """The answer says Lietuvos Respublika, the tree has Lithuania: after the user confirmed it, no second state is made, the name is added to
        Lithuania, and every place that existed keeps its Gramps ID (here the IDs of an import: Osm_relation...) and its handle."""
        from placecompleter import ingest, writer
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_ingest
        from test_engine import EMPTY
        t = Tree({"lt": test_ingest.typed("lt", "Lithuania", 1, lang="en"), "kc": test_ingest.typed("kc", "Kaunas County", 3, lang="en"),
                  "k": test_ingest.typed("k", "Kaunas", 4, lang="en")}, [])
        t.places["kc"]["refs"] = [{"ref": "lt", "date": EMPTY}]
        t.places["k"]["refs"] = [{"ref": "kc", "date": EMPTY}]
        ids = {"lt": "Osm_relation365331", "kc": "Osm_relation42611", "k": "Osm_relation43452"}
        for handle, gramps_id in ids.items():
            t.places[handle]["id"] = gramps_id
        path = os.path.join(TMP, "confirmed")
        self.build_from(t, path)
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        screen = ingest.ingest(tree, ingest.parse_structured(test_ingest.AnotherNameOfAHigherLevelTests.ANSWER), "1995", aliases={},
                               choices={"c1": "kc", "c2": "lt"})
        plan = planlib.make_plan(tree, screen["proposals"])
        self.assertFalse([q for q in plan["proposals"] if q["kind"] == "add-place"])
        db = make_database("sqlite")
        db.load(path)
        try:
            before = db.get_number_of_places()
            done = writer.apply_proposals(db, planlib.select(plan, ids={q["id"] for q in plan["proposals"]}), dry_run=False)
            self.assertEqual({r["status"] for r in done}, {"applied"})
            self.assertEqual(db.get_number_of_places(), before)                                       # no second Lithuania
            for handle, gramps_id in ids.items():
                self.assertEqual(db.get_place_from_handle(handle).get_gramps_id(), gramps_id)         # nothing is renumbered
            self.assertEqual(sorted(db.get_place_handles()), sorted(ids))                              # and no handle is new or gone
            lt = db.get_place_from_handle("lt")
            self.assertIn("Lietuvos Respublika", [n.get_value() for n in lt.get_alternative_names()])
            self.assertEqual(lt.get_name().get_value(), "Lithuania")                                   # its own name is as it was
        finally:
            db.close()


    def _sissa_tree(self, links):
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_ingest
        from test_engine import EMPTY
        t = Tree({"it": test_ingest.typed("it", "Italy", 1, lang="en"), "er": test_ingest.typed("er", "Emilia-Romagna", 9, lang="en"),
                  "parma": test_ingest.typed("parma", "Parma", 4, lang="en"), "prov": test_ingest.typed("prov", "Provincia di Parma", 8, lang="en"),
                  "sissa": test_ingest.typed("sissa", "Sissa", 15, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["sissa"]["refs"] = [{"ref": parent, "date": date} for parent, date in links]
        return t

    def _run_sissa(self, path, text, choose):
        """One run of the analysis and the writing of what `choose` picks ('additions' or 'everything'); the links of Sissa, what Gramps shows for 1990."""
        from placecompleter import ingest, writer
        from placecompleter.dates import describe, interval, sdn
        db = make_database("sqlite")
        db.load(path)
        try:
            tree = Tree.from_db(db)
            screen = ingest.ingest(tree, ingest.parse_structured(text), "1990", aliases={})
            plan = planlib.make_plan(tree, screen["proposals"])
            ids = {q["id"] for q in plan["proposals"] if choose == "everything" or not q["existing"]}
            statuses = {r["status"] for r in writer.apply_proposals(db, planlib.select(plan, ids=ids), dry_run=False)} if ids else set()
            now = Tree.from_db(db)
            links = [(now.places[r["ref"]]["name"]["value"], describe(r["date"])) for r in now.places["sissa"]["refs"]]
            day = sdn(1990, 6, 15)
            shown = next((now.places[r["ref"]]["name"]["value"] for r in now.places["sissa"]["refs"]
                          if interval(r["date"] or {}) is None or interval(r["date"])[0] <= day <= interval(r["date"])[1]), None)
            return plan, statuses, links, shown
        finally:
            db.close()

    def test_sissa_is_disconnected_from_the_city_and_put_under_the_province_in_a_real_database(self):
        """The addition is chosen by itself; the disconnect from the city is a change to what exists, chosen by the user. Applied for real: Sissa is under the province
        only, the city and the province stay as places with their own links, and no existing place changes its ID or its handle."""
        from placecompleter.dates import M_FROM  # noqa: F401
        from test_engine import EMPTY
        t = self._sissa_tree([("parma", EMPTY)])
        ids = {h: t.places[h]["id"] for h in t.places}
        path = os.path.join(TMP, "sissa-moved")
        self.build_from(t, path)
        text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_sissa_1990_v2.txt"), encoding="utf-8").read()
        plan, statuses, links, shown = self._run_sissa(path, text, "additions")
        self.assertEqual(statuses, {"applied"})
        self.assertEqual(links, [("Provincia di Parma", "from 1861"), ("Parma", "(no date)")])    # the old link is there: nothing that exists is changed by itself
        self.assertEqual(shown, "Provincia di Parma")                                             # (the new link stands first)
        plan, statuses, links, shown = self._run_sissa(path, text, "everything")
        self.assertEqual((statuses, links, shown), ({"applied"}, [("Provincia di Parma", "from 1861")], "Provincia di Parma"))
        self.assertEqual(self._run_sissa(path, text, "everything")[0]["proposals"], [])           # the second run has nothing to do
        db = make_database("sqlite")
        db.load(path)
        try:
            self.assertEqual(sorted(db.get_place_handles()), sorted(list(ids) + [h for h in db.get_place_handles() if h not in ids]))
            for handle, gramps_id in ids.items():
                self.assertEqual(db.get_place_from_handle(handle).get_gramps_id(), gramps_id)
            self.assertEqual(db.get_number_of_places(), len(ids) + 0)
        finally:
            db.close()

    def test_the_messy_links_of_sissa_are_put_right_when_the_user_chooses_and_not_before(self):
        """Direct link to the region first, the province with a period that runs backwards, the link to the city: by itself nothing that exists is changed;
        when every change is chosen Sissa is under the province only, and the second run changes nothing."""
        from placecompleter.dates import M_FROM, M_SPAN, M_TO
        from test_engine import D
        t = self._sissa_tree([("er", D(M_FROM, 1946)), ("prov", D(M_SPAN, 1969, y2=1861)), ("parma", D(M_TO, 1861))])
        ids = {h: t.places[h]["id"] for h in t.places}
        path = os.path.join(TMP, "messy-links")
        self.build_from(t, path)
        text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_sissa_1990_v2.txt"), encoding="utf-8").read()
        plan, statuses, links, shown = self._run_sissa(path, text, "additions")
        self.assertEqual(links, [("Emilia-Romagna", "from 1946"), ("Provincia di Parma", "span 1969..1861"), ("Parma", "to 1861")])        # untouched
        self.assertEqual(shown, "Emilia-Romagna")
        plan, statuses, links, shown = self._run_sissa(path, text, "everything")
        self.assertEqual((statuses, links, shown), ({"applied"}, [("Provincia di Parma", "from 1861")], "Provincia di Parma"))
        again = self._run_sissa(path, text, "everything")
        self.assertEqual((again[0]["proposals"], again[2]), ([], links))
        db = make_database("sqlite")
        db.load(path)
        try:
            self.assertEqual(sorted(db.get_place_handles()), sorted(ids))                          # no place is deleted: only links
            for handle, gramps_id in ids.items():
                self.assertEqual(db.get_place_from_handle(handle).get_gramps_id(), gramps_id)
        finally:
            db.close()

    def test_a_move_of_a_link_is_not_made_when_the_order_changed_since_the_analysis(self):
        from placecompleter import writer
        from placecompleter.dates import M_FROM
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import test_ingest
        from test_engine import EMPTY, D
        t = Tree({"er": test_ingest.typed("er", "Emilia-Romagna", 9, lang="en"), "prov": test_ingest.typed("prov", "Provincia di Parma", 8, lang="en"),
                  "sissa": test_ingest.typed("sissa", "Sissa", 15, lang="en")}, [])
        t.places["sissa"]["refs"] = [{"ref": "prov", "date": D(M_FROM, 1861)}, {"ref": "er", "date": D(M_FROM, 1946)}]      # already in the order the move wants
        path = os.path.join(TMP, "stale-move")
        self.build_from(t, path)
        proposal = {"id": "m1", "kind": "move-link", "child": "sissa", "parent": "prov", "index": 1, "position": 0, "above": "er", "old": D(M_FROM, 1861),
                    "new": D(M_FROM, 1861), "conflict": False, "label": "x"}
        db = make_database("sqlite")
        db.load(path)
        try:
            done = writer.apply_proposals(db, [proposal], dry_run=False)
            self.assertEqual([(r["status"], r["reason"]) for r in done], [("skipped", "parent hierarchy link position has shifted")])
        finally:
            db.close()


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def plan_file(self, tmp):
        path = os.path.join(tmp, "tree")
        os.makedirs(path)
        planfile = os.path.join(tmp, "plan.json")
        planlib.save_plan({"schema": planlib.PLAN_SCHEMA, "proposals": [
            {"id": 1, "kind": "end-link", "basis": "tree", "label": "x", "old": {}, "new": {}, "events": 1, "worse": 0,
             "conflict": False, "child": "a", "parent": "b", "index": 0}]}, planfile)
        return path, planfile

    def test_a_tree_inside_dropbox_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            _path, planfile = self.plan_file(tmp)
            drop = os.path.expanduser("~/Dropbox/__pc_test_never_created__")
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", drop, "--basis", "tree")
            self.assertEqual(code, 2)
            self.assertIn("live data", out)
        self.assertIn("Dropbox", out)

    def test_a_locked_tree_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, planfile = self.plan_file(tmp)
            open(os.path.join(path, "sqlite.db"), "w").close()
            open(os.path.join(path, "lock"), "w").close()
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", path, "--basis", "tree")
            self.assertEqual(code, 2)
            self.assertIn("locked", out)

    def test_nothing_is_applied_without_a_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, planfile = self.plan_file(tmp)
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", path)
            self.assertEqual(code, 2)
            self.assertIn("choose what to apply", out)

    def test_a_folder_without_a_database_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, planfile = self.plan_file(tmp)
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", path, "--basis", "tree")
            self.assertEqual(code, 2)
            self.assertIn("no sqlite.db", out)

    @unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
    def test_plan_then_a_dry_run_and_a_real_apply_on_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "copy")
            build(path)
            planfile = os.path.join(tmp, "plan.json")
            code, out = self.run_cli("plan", os.path.join(path, "sqlite.db"), "--no-packs", "--out", planfile)
            self.assertEqual(code, 0)
            self.assertIn("end-link", out)
            before = sha(path)
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", path, "--basis", "tree,evidence")
            self.assertEqual((code, sha(path)), (0, before))
            self.assertIn("DRY RUN", out)
            self.assertIn("1 people" if False else "0 people", out)
            code, out = self.run_cli("apply", "--plan", planfile, "--tree-dir", path, "--basis", "tree", "--yes")
            self.assertEqual(code, 0)
            self.assertIn("WRITTEN in one transaction", out)
            self.assertNotEqual(sha(path), before)
            self.assertFalse(os.path.exists(os.path.join(path, "lock")))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
