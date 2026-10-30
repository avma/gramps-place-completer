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
"""Check the engine's place chains against Gramps' own place display.

Needs the Gramps library (run with the Gramps python, GRAMPS_RESOURCES set).
Builds random place trees with random dates in a temporary folder and compares,
event by event, the engine's chain with place_displayer.display_event().
It is skipped when Gramps cannot be imported.
"""
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp(prefix="pc-vs-gramps-")
os.environ["GRAMPSHOME"] = os.path.join(TMP, "home")
os.environ["LANGUAGE"] = "en"

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import Date, Event, EventType, Place, PlaceName, PlaceRef, PlaceType
    HAVE_GRAMPS = True
except Exception:                       # pragma: no cover - depends on the environment
    HAVE_GRAMPS = False

from placecompleter import gaps          # noqa: E402
from placecompleter.model import Tree    # noqa: E402


def rand_date(rng, allow_empty=True):
    kind = rng.choice(["empty", "none", "none", "none", "before", "after", "about", "range", "span",
                       "from", "to", "text", "textempty"])
    date = Date()
    if kind == "empty" and allow_empty:
        return date
    year = rng.randint(1800, 2000)
    month = rng.choice([0, 0, rng.randint(1, 12)])
    day = rng.randint(1, 28) if (month and rng.random() < 0.6) else 0
    quality = rng.choice([0, 0, 1, 2])
    if kind == "text":
        date.set_as_text("some words")
        return date
    if kind == "textempty":
        date.set_as_text("")
        return date
    simple = {"none": Date.MOD_NONE, "before": Date.MOD_BEFORE, "after": Date.MOD_AFTER,
              "about": Date.MOD_ABOUT, "from": Date.MOD_FROM, "to": Date.MOD_TO, "empty": Date.MOD_NONE}
    if kind in simple:
        date.set(quality=quality, modifier=simple[kind], calendar=0, value=(day, month, year, False))
        return date
    year2 = year + rng.randint(0, 40)
    month2 = rng.choice([0, rng.randint(1, 12)])
    day2 = rng.randint(1, 28) if (month2 and rng.random() < 0.6) else 0
    mod = Date.MOD_RANGE if kind == "range" else Date.MOD_SPAN
    date.set(quality=quality, modifier=mod, calendar=0,
             value=(day, month, year, False, day2, month2, year2, False))
    return date


def build(path, seed):
    rng = random.Random(seed)
    db = make_database("sqlite")
    os.makedirs(path)
    db.load(path)
    with DbTxn("build", db) as txn:
        places = []
        for i in range(7):
            p, n = Place(), PlaceName()
            n.set_value("P%d" % i)
            n.set_language(rng.choice(["", "hu", "de"]))
            if rng.random() < 0.6:
                n.set_date_object(rand_date(rng))
            p.set_name(n)
            p.set_type(rng.choice([PlaceType.VILLAGE, PlaceType.COUNTY, PlaceType.COUNTRY]))
            for j in range(rng.choice([0, 0, 1, 2])):
                alt = PlaceName()
                alt.set_value("P%d-alt%d" % (i, j))
                alt.set_language(rng.choice(["", "hu", "sr"]))
                if rng.random() < 0.6:
                    alt.set_date_object(rand_date(rng))
                p.add_alternative_name(alt)
            places.append(p)
        for i, p in enumerate(places):
            for parent in rng.sample(places[i + 1:], k=min(len(places) - i - 1, rng.choice([0, 1, 1, 2, 3]))):
                ref = PlaceRef()
                ref.ref = parent.get_handle()
                if rng.random() < 0.7:
                    ref.set_date_object(rand_date(rng))
                p.add_placeref(ref)
        for p in places:
            db.add_place(p, txn)
        for _ in range(150):
            ev = Event()
            ev.set_type(EventType.RESIDENCE)
            ev.set_place_handle(rng.choice(places).get_handle())
            ev.set_date_object(rand_date(rng))
            db.add_event(ev, txn)
    db.close()


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class AgainstGramps(unittest.TestCase):
    def test_chains_equal_what_gramps_displays(self):
        compared = 0
        for seed in range(1, 21):
            path = os.path.join(TMP, "tree%d" % seed)
            build(path, seed)
            db = make_database("sqlite")
            db.load(path, mode="r")
            try:
                rows = {r["event"]["handle"]: r
                        for r in gaps.analyse(Tree.from_sqlite(os.path.join(path, "sqlite.db")))}
                for handle in db.get_event_handles():
                    real = place_displayer.display_event(db, db.get_event_from_handle(handle))
                    mine = ", ".join(rows[handle]["chain"]["names"])
                    self.assertEqual(real, mine, "seed %d, event %s" % (seed, handle))
                    compared += 1
            finally:
                db.close()
        self.assertEqual(compared, 20 * 150)


def date_from_dict(d):
    date = Date()
    date.set(quality=d.get("quality", 0), modifier=d["modifier"], calendar=0, value=tuple(d["dateval"]))
    return date


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class ProposalAgainstGramps(unittest.TestCase):
    def test_a_proposal_changes_the_display_exactly_as_simulated(self):
        path = os.path.join(TMP, "proposal")
        db = make_database("sqlite")
        os.makedirs(path)
        db.load(path)
        with DbTxn("build", db) as txn:
            def make(name, ptype, parents=(), span=None, start=None):
                p, n = Place(), PlaceName()
                n.set_value(name)
                if span:
                    d = Date()
                    d.set(modifier=Date.MOD_SPAN, value=(0, 0, span[0], False, 0, 0, span[1], False))
                    n.set_date_object(d)
                p.set_name(n)
                p.set_type(ptype)
                for parent, kind in parents:
                    ref = PlaceRef()
                    ref.ref = parent.get_handle()
                    if kind:
                        d = Date()
                        d.set(modifier=Date.MOD_FROM, value=(0, 0, kind, False))
                        ref.set_date_object(d)
                    p.add_placeref(ref)
                db.add_place(p, txn)
                return p
            monarchy = make("Austro-Hungarian Monarchy", PlaceType.COUNTRY, span=(1867, 1918))
            hungary = make("Hungary", PlaceType.COUNTRY, parents=[(monarchy, 1867)])
            zombor = make("Zombor", PlaceType.CITY, parents=[(hungary, None)])
            for year in (1900, 1925, 1950):
                ev = Event()
                ev.set_type(EventType.RESIDENCE)
                ev.set_place_handle(zombor.get_handle())
                d = Date()
                d.set_yr_mon_day(year, 5, 1)
                ev.set_date_object(d)
                db.add_event(ev, txn)
        db.close()
        db_file = os.path.join(path, "sqlite.db")
        tree = Tree.from_sqlite(db_file)
        before = gaps.analyse(tree)
        proposals = gaps.propose_end_clips(tree, before)
        self.assertEqual(len(proposals), 1)
        after = {r["event"]["handle"]: ", ".join(r["chain"]["names"])
                 for r in gaps.analyse(gaps.apply(tree, proposals))}
        db = make_database("sqlite")
        db.load(path)
        with DbTxn("apply", db) as txn:
            for p in proposals:
                place = db.get_place_from_handle(p["child"])
                place.get_placeref_list()[p["index"]].set_date_object(date_from_dict(p["new"]))
                db.commit_place(place, txn)
        db.close()
        db = make_database("sqlite")
        db.load(path, mode="r")
        try:
            real = {h: place_displayer.display_event(db, db.get_event_from_handle(h))
                    for h in db.get_event_handles()}
        finally:
            db.close()
        self.assertEqual(real, after)
        self.assertNotIn("?", " ".join(real.values()))


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class PackProposalAgainstGramps(unittest.TestCase):
    def test_a_pack_link_changes_the_display_exactly_as_simulated(self):
        from placecompleter import packs
        path = os.path.join(TMP, "packproposal")
        db = make_database("sqlite")
        os.makedirs(path)
        db.load(path)

        def span(first, last):
            d = Date()
            d.set(modifier=Date.MOD_SPAN, value=(0, 0, first, False, 0, 0, last, False))
            return d

        with DbTxn("build", db) as txn:
            def make(name, ptype, name_date=None):
                p, n = Place(), PlaceName()
                n.set_value(name)
                if name_date:
                    n.set_date_object(name_date)
                p.set_name(n)
                p.set_type(ptype)
                return p
            empire = make("Kaisertum Österreich", PlaceType.UNKNOWN, span(1804, 1867))
            monarchy = make("Austro-Hungarian Monarchy", PlaceType.UNKNOWN, span(1867, 1918))
            hungary = make("Hungary", PlaceType.COUNTRY)
            db.add_place(empire, txn)
            db.add_place(monarchy, txn)
            for target, mod, value in ((monarchy, Date.MOD_FROM, (0, 0, 1867, False)),
                                       (empire, Date.MOD_NONE, (0, 0, 1859, False))):
                ref = PlaceRef()
                ref.ref = target.get_handle()
                d = Date()
                d.set(modifier=mod, value=value)
                ref.set_date_object(d)
                hungary.add_placeref(ref)
            db.add_place(hungary, txn)
            for year in (1790, 1810, 1850, 1859, 1866, 1900):
                ev = Event()
                ev.set_type(EventType.RESIDENCE)
                ev.set_place_handle(hungary.get_handle())
                d = Date()
                d.set_yr_mon_day(year, 5, 1)
                ev.set_date_object(d)
                db.add_event(ev, txn)
        db.close()
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        pack = {"schema": packs.SCHEMA, "pack": {"id": "t"},
                "places": [{"key": "h", "names": ["Hungary"], "type_value": 1},
                           {"key": "e", "names": ["Kaisertum Österreich"]}],
                "edges": [{"child": "h", "parent": "e", "valid_from": "1804", "valid_to": "1867", "origin": "user"}]}
        proposals, _notes = packs.propose_from_pack(tree, packs.validate(pack))
        self.assertEqual((len(proposals), proposals[0]["kind"]), (1, "set-link"))
        simulated = {r["event"]["handle"]: ", ".join(r["chain"]["names"])
                     for r in gaps.analyse(gaps.apply(tree, proposals))}
        db = make_database("sqlite")
        db.load(path)
        with DbTxn("apply", db) as txn:
            for p in proposals:
                place = db.get_place_from_handle(p["child"])
                place.get_placeref_list()[p["index"]].set_date_object(date_from_dict(p["new"]))
                db.commit_place(place, txn)
        db.close()
        db = make_database("sqlite")
        db.load(path, mode="r")
        try:
            real = {h: place_displayer.display_event(db, db.get_event_from_handle(h)) for h in db.get_event_handles()}
        finally:
            db.close()
        self.assertEqual(real, simulated)
        self.assertEqual(sum("Kaisertum" in v for v in real.values()), 4)    # 1810, 1850, 1859, 1866


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class NameProposalAgainstGramps(unittest.TestCase):
    def test_an_added_name_changes_the_display_exactly_as_simulated(self):
        from placecompleter import packs
        path = os.path.join(TMP, "nameproposal")
        db = make_database("sqlite")
        os.makedirs(path)
        db.load(path)
        with DbTxn("build", db) as txn:
            country = Place()
            cn = PlaceName()
            cn.set_value("Romania")
            country.set_name(cn)
            country.set_type(PlaceType.COUNTRY)
            db.add_place(country, txn)
            village = Place()
            vn = PlaceName()
            vn.set_value("Berechiu")
            vn.set_language("ro")
            d = Date()
            d.set(modifier=Date.MOD_FROM, value=(0, 0, 1920, False))
            vn.set_date_object(d)
            village.set_name(vn)
            village.set_type(PlaceType.VILLAGE)
            ref = PlaceRef()
            ref.ref = country.get_handle()
            village.add_placeref(ref)
            db.add_place(village, txn)
            for year in (1900, 1919, 1950):
                ev = Event()
                ev.set_type(EventType.RESIDENCE)
                ev.set_place_handle(village.get_handle())
                d = Date()
                d.set_yr_mon_day(year, 5, 1)
                ev.set_date_object(d)
                db.add_event(ev, txn)
        db.close()
        tree = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        pack = {"schema": packs.SCHEMA, "pack": {"id": "t", "origin": "user"},
                "places": [{"key": "v", "names": ["Berechiu", {"name": "Alsóberekszó", "language": "hu",
                                                               "valid_from": "1700", "valid_to": "1919"}]}],
                "edges": []}
        proposals, _notes = packs.propose_from_pack(tree, packs.validate(pack))
        self.assertEqual((len(proposals), proposals[0]["kind"]), (1, "add-name"))
        simulated = {r["event"]["handle"]: ", ".join(r["chain"]["names"])
                     for r in gaps.analyse(gaps.apply(tree, proposals))}
        db = make_database("sqlite")
        db.load(path)
        with DbTxn("apply", db) as txn:
            for p in proposals:
                place = db.get_place_from_handle(p["place"])
                alt = PlaceName()
                alt.set_value(p["value"])
                alt.set_language(p["lang"])
                alt.set_date_object(date_from_dict(p["new"]))
                place.add_alternative_name(alt)
                db.commit_place(place, txn)
        db.close()
        db = make_database("sqlite")
        db.load(path, mode="r")
        try:
            real = {h: place_displayer.display_event(db, db.get_event_from_handle(h)) for h in db.get_event_handles()}
        finally:
            db.close()
        self.assertEqual(real, simulated)
        self.assertEqual(sorted(real.values()), ["Alsóberekszó, Romania", "Alsóberekszó, Romania", "Berechiu, Romania"])


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
