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
"""Creating places that the tree lacks: a new parent and its links are one bundle."""
import os
import sys
import unittest
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import gaps, packs, plan as planlib, wikidata        # noqa: E402
from placecompleter.dates import M_NONE                                  # noqa: E402
from placecompleter.model import Tree                                    # noqa: E402
from test_engine import D, EMPTY, event, place                           # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json")


def pack_with_new_country(with_edge=True):
    p = {"schema": packs.SCHEMA, "pack": {"id": "yu", "origin": "user"},
         "places": [{"key": "v", "names": ["Bajmok"]},
                    {"key": "y", "create": True, "type_value": 1, "wikidata_qid": "Q191077", "coordinates": {"lat": 44.8, "lon": 20.5},
                     "names": [{"name": "Kingdom of Yugoslavia", "language": "en", "valid_from": "1929", "valid_to": "1945"}]}],
         "edges": []}
    if with_edge:
        p["edges"].append({"child": "v", "parent": "y", "valid_from": "1929", "valid_to": "1941", "origin": "user"})
    return packs.validate(p)


def village():
    # like Bajmok in the user's tree: its only link ended in 1920, so after that the chain stops
    from placecompleter.dates import M_TO
    return Tree({"v": place("v", "Bajmok", 16, refs=[("d", D(M_TO, 1920))]),
                 "d": place("d", "Bacsalmasi jaras", 0, name_date=D(M_TO, 1920))},
                [event("e1", "v", D(M_NONE, 1935, 5, 1)), event("e2", "v", D(M_NONE, 1900, 5, 1))])


class PackCreationTests(unittest.TestCase):
    def test_a_new_parent_and_its_link_are_proposed_as_one_bundle(self):
        t = village()
        props, notes = packs.propose_from_pack(t, pack_with_new_country())
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "add-place"])
        self.assertEqual(len({p["bundle"] for p in props}), 1)
        new = next(p for p in props if p["kind"] == "add-place")
        self.assertEqual((new["names"][0]["value"], new["type_value"], new["lat"]), ("Kingdom of Yugoslavia", 1, "44.8"))
        self.assertEqual(new["urls"][0]["path"], "https://www.wikidata.org/wiki/Q191077")
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}
        self.assertEqual(after["E1"], "Bajmok, Kingdom of Yugoslavia")
        self.assertEqual(after["E2"], "Bajmok, Bacsalmasi jaras")
        self.assertNotIn("new:y", t.places)                                   # the tree itself is untouched

    def test_a_place_without_a_link_is_not_created(self):
        props, notes = packs.propose_from_pack(village(), pack_with_new_country(with_edge=False))
        self.assertEqual(props, [])
        self.assertTrue(any("fixes none" in n for n in notes))

    def test_an_existing_place_is_reused_instead_of_created(self):
        t = village()
        t.places["yug"] = place("yug", "Kingdom of Yugoslavia", 1, name_date=D(5, 1929, y2=1945))
        props, notes = packs.propose_from_pack(t, pack_with_new_country())
        self.assertEqual([p["kind"] for p in props], ["add-link"])
        self.assertEqual(props[0]["parent"], "yug")

    def test_a_bundle_is_selected_as_a_whole(self):
        t = village()
        props, _ = packs.propose_from_pack(t, pack_with_new_country())
        plan = planlib.make_plan(t, props)
        link = next(p for p in plan["proposals"] if p["kind"] == "add-link")
        chosen = planlib.select(plan, ids={link["id"]})
        self.assertEqual(sorted(p["kind"] for p in chosen), ["add-link", "add-place"])


class WikidataCreationTests(unittest.TestCase):
    def client(self):
        c = wikidata.Client(cache_path=FIXTURE)
        url = "%s?action=wbsearchentities&search=%s&language=en&limit=5&format=json" % (wikidata.API, urllib.parse.quote("Subotica City"))
        c.answers[url] = {"search": [{"id": "Q1041949"}]}
        return c

    def test_the_historical_parents_of_a_municipality_are_offered_as_new_places(self):
        t = Tree({"s": place("s", "Subotica City", 14)}, [event("a", "s", D(M_NONE, 1950, 5, 1)), event("b", "s", D(M_NONE, 1991, 5, 1)),
                                                          event("c", "s", D(M_NONE, 1900, 5, 1))])
        pack, notes = wikidata.build_pack(t, ["s"], self.client())
        keys = {p["key"] for p in pack["places"] if p.get("create")}
        self.assertEqual(keys, {"wd-Q843919", "wd-Q44749"})
        props, _ = packs.propose_from_pack(t, pack)
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "add-link", "add-place", "add-place"])
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}
        self.assertEqual(after["A"], "Subotica City, Socialist Autonomous Province of Vojvodina")
        self.assertEqual(after["B"], "Subotica City, Vojvodina")
        self.assertEqual(after["C"], "Subotica City")                        # 1900: Wikidata knows nothing for that time
        for p in props:
            if p["kind"] == "add-place":
                self.assertEqual(p["origin"], "wikidata")
                self.assertTrue(p["urls"][0]["path"].startswith("https://www.wikidata.org/wiki/Q"))
                self.assertTrue(p["evidence"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
