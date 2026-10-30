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
"""The place type is a hint, never the decision: a wrong type must not hide a real place."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import wikidata                                      # noqa: E402
from placecompleter.dates import M_NONE                                  # noqa: E402
from placecompleter.model import Tree                                    # noqa: E402
from test_engine import D, EMPTY, event, place                           # noqa: E402

BUILDING, STREET, LOCALITY, COUNTY = 19, 7, 6, 3


def run(tree, handles):
    calls = []
    client = wikidata.Client(fetch=lambda url: calls.append(url) or {"search": []}, pause=0)
    pack, notes = wikidata.build_pack(tree, handles, client)
    return calls, notes


class AddressDetectionTests(unittest.TestCase):
    def test_real_addresses_are_skipped_whatever_their_type(self):
        names = ["Strada Andrei Mocioni 3", "Kruspér u. 7", "Ajtósi Dürer sor 7", "Batthanyi 16", "Dózsa György utca 12"]
        for ptype in (STREET, LOCALITY, COUNTY):
            t = Tree({"a%d" % i: place("a%d" % i, n, ptype) for i, n in enumerate(names)}, [])
            calls, notes = run(t, list(t.places))
            self.assertEqual(calls, [], "type %s" % ptype)
            self.assertEqual(sum("an address, not looked up" in n for n in notes), len(names))

    def test_a_county_typed_as_a_building_is_still_looked_up(self):
        t = Tree({"c": place("c", "Bács-Bodrog vármegye", BUILDING)}, [event("e", "c", D(M_NONE, 1900))])
        calls, notes = run(t, ["c"])
        self.assertTrue(calls, "it was never looked up")
        self.assertTrue(any(n.startswith("TYPE CHECK") and "typed as Building" in n for n in notes))

    def test_a_place_with_places_under_it_is_never_an_address(self):
        t = Tree({"b": place("b", "Alsoberekszo 3", BUILDING), "x": place("x", "Some farm", 18, refs=[("b", EMPTY)])}, [])
        self.assertFalse(wikidata.is_address(t, "b"))
        calls, notes = run(t, ["b"])
        self.assertTrue(calls)

    def test_a_leaf_typed_as_a_street_without_any_digit_is_looked_up(self):
        t = Tree({"s": place("s", "Zombor", STREET)}, [])
        self.assertFalse(wikidata.is_address(t, "s"))
        self.assertTrue(run(t, ["s"])[0])

    def test_a_village_with_a_number_in_a_roman_name_is_not_mistaken_for_an_address(self):
        t = Tree({"v": place("v", "Nemesvid", 16)}, [])
        self.assertFalse(wikidata.is_address(t, "v"))

    def test_the_type_of_a_resolved_place_is_checked_against_wikidata(self):
        c = wikidata.Client(cache_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json"))
        import urllib.parse
        url = "%s?action=wbsearchentities&search=%s&language=hu&limit=5&format=json" % (wikidata.API, urllib.parse.quote("Bács-Bodrog vármegye"))
        c.answers[url] = {"search": [{"id": "Q852564"}]}
        c.entity_cache["Q28575"] = {"id": "Q28575", "labels": {"en": {"language": "en", "value": "county"}}, "claims": {}}
        c.entity_cache["Q852564"] = dict(c.entity_cache["Q852564"], claims=dict(c.entity_cache["Q852564"]["claims"], P31=[
            {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": "Q28575"}}}}]))
        county = place("c", "Bács-Bodrog vármegye", BUILDING, lang="hu")
        county["lat"], county["lon"] = "45.7736", "19.5301"
        t = Tree({"c": county}, [event("e", "c", D(M_NONE, 1900))])
        pack, notes = wikidata.build_pack(t, ["c"], c)
        self.assertTrue(any("the tree says Building, Wikidata says County" in n for n in notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
