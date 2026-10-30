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
"""ID1: a place of the tree with the name of the answer, and coordinates, that is far from the coordinates of the answer is another place (Johnston in Iowa, Johnston in Rhode Island)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, rules                                                      # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
import test_ingest as ti                                                                      # noqa: E402

IOWA = (41.673, -93.698)

ANSWER = """PLACE_NAME_ON_DATE: Johnston
LANGUAGE: en
SETTLEMENT_TYPE_ON_DATE: town
COORDINATES: %s, %s
CONTAINERS:
1 | %s | county | 1790-present | United States
2 | %s | state | 1790-present | United States
3 | United States | sovereign state | 1776-present | United States
STATE_ON_DATE: United States | 1776-present
NOTES: NONE
SOURCES: https://en.wikipedia.org/wiki/Johnston | SETTLEMENT_TYPE_ON_DATE, CONTAINERS
NOT_SURE: NONE
"""


def answer(coordinates, county, state):
    return ANSWER % (coordinates[0], coordinates[1], county, state)


RHODE_ISLAND = answer((41.82, -71.50), "Providence County", "Rhode Island")
IOWA_ANSWER = answer(IOWA, "Polk County", "Iowa")


def tree(coordinates=IOWA, second=None):
    t = Tree({"usa": ti.typed("usa", "United States", 1, lang="en"), "ia": ti.typed("ia", "Iowa", 2, lang="en"),
              "polk": ti.typed("polk", "Polk County", 3, lang="en"), "jo": ti.typed("jo", "Johnston", 15, lang="en")}, [])
    for handle, parent in (("ia", "usa"), ("polk", "ia"), ("jo", "polk")):
        t.places[handle]["refs"] = [{"ref": parent, "date": EMPTY}]
    if coordinates:
        t.places["jo"]["lat"], t.places["jo"]["lon"] = str(coordinates[0]), str(coordinates[1])
    if second:
        t.places["jo2"] = ti.typed("jo2", "Johnston", 15, lang="en")
        t.places["jo2"]["lat"], t.places["jo2"]["lon"] = str(second[0]), str(second[1])
        t.places["jo2"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    return t


def run(t, text, date="1950"):
    return ingest.ingest(t, ingest.parse_structured(text), date)


def touches(screen, handle):
    return [p for p in screen["proposals"] if handle in (p.get("place"), p.get("handle"), p.get("child"), p.get("parent"))]


class IdentityTests(unittest.TestCase):
    def test_a_johnston_that_is_far_away_is_another_place_and_the_one_of_the_tree_is_not_touched(self):
        screen = run(tree(), RHODE_ISLAND)
        self.assertTrue(screen["child"].startswith("new:"))
        self.assertEqual(touches(screen, "jo"), [])                                          # nothing is proposed for the Johnston of Iowa
        self.assertTrue(any(p["kind"] == "add-place" and p["handle"] == screen["child"] for p in screen["proposals"]))
        self.assertTrue(any("treated as a distinct place and left unchanged" in n and "1" in n for n in screen["needs"]))

    def test_the_same_place_is_still_the_same_place(self):
        screen = run(tree(), IOWA_ANSWER)
        self.assertEqual(screen["child"], "jo")
        self.assertFalse(any("another place with the same name" in n for n in screen["needs"]))

    def test_the_distance_decides_not_the_names_of_the_places_above(self):
        screen = run(tree(), answer((41.70, -93.70), "Another County", "Another State"))            # other names above, a few km away
        self.assertEqual(screen["child"], "jo")

    def test_thirty_kilometres_is_the_limit(self):
        near = run(tree(), answer((IOWA[0] + 0.2, IOWA[1]), "Polk County", "Iowa"))                   # about 22 km
        far = run(tree(), answer((IOWA[0] + 0.4, IOWA[1]), "Polk County", "Iowa"))                    # about 44 km
        self.assertEqual(near["child"], "jo")
        self.assertTrue(far["child"].startswith("new:"))

    def test_a_place_that_cannot_be_compared_is_taken_as_before(self):
        self.assertEqual(run(tree(coordinates=None), RHODE_ISLAND)["child"], "jo")                    # no coordinates in the tree
        no_coordinates = RHODE_ISLAND.replace("COORDINATES: 41.82, -71.5\n", "")
        self.assertEqual(run(tree(), no_coordinates)["child"], "jo")                                  # no coordinates in the answer

    def test_of_two_places_with_the_name_the_near_one_is_chosen_without_asking(self):
        screen = run(tree(second=(41.82, -71.50)), RHODE_ISLAND)
        self.assertEqual(screen["child"], "jo2")
        self.assertFalse(any("have this name: choose" in n for n in screen["needs"]))
        screen = run(tree(second=(41.82, -71.50)), IOWA_ANSWER)
        self.assertEqual(screen["child"], "jo")

    def test_with_the_rule_off_the_place_of_the_tree_is_taken_as_before(self):
        with rules.disabled("ID1"):
            screen = run(tree(), RHODE_ISLAND)
        self.assertEqual(screen["child"], "jo")
        self.assertFalse(any("another place with the same name" in n for n in screen["needs"]))


if __name__ == "__main__":
    unittest.main()
