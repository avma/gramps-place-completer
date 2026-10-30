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
"""The rules that are off by default: the periods and the languages of the names of the LEVELS (NP5, NL). The tests run with them on (tests/__init__.py)."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, rules                                                      # noqa: E402
import test_ingest as ti                                                                      # noqa: E402

NOTHING_ON = {"PLACECOMPLETER_RULES_ON": ""}


def proposals_of(kind, levels):
    """The proposals of a kind, for the levels (places that are not the place of the question) or for the place itself, for the answer of 1900 and its tree."""
    screen = ingest.ingest(ti.plain_tree(), ti.answer_1900(), "1900", aliases=ingest.alias_map([ti.PACK]))
    return [p for p in screen["proposals"] if p["kind"] == kind and (p.get("place") != screen["child"]) == levels]


def unit_proposals(kind):
    return proposals_of(kind, True)


class DefaultTests(unittest.TestCase):
    def test_np5_and_nl_are_off_unless_somebody_switches_them_on(self):
        with mock.patch.dict(os.environ, NOTHING_ON):
            self.assertEqual(rules.DEFAULT_OFF, {"NP3", "NP5", "NL"})
            self.assertFalse(rules.on("NP5"))
            self.assertFalse(rules.on("NL"))
            self.assertTrue(all(rules.on(r["id"]) for r in rules.all_rules() if r["id"] not in rules.DEFAULT_OFF))
            with rules.enabled("NP5"):
                self.assertTrue(rules.on("NP5"))
                self.assertFalse(rules.on("NL"))
            self.assertFalse(rules.on("NP5"))
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_RULES_ON": "NL, NP5"}):
            self.assertTrue(rules.on("NP5") and rules.on("NL"))

    def test_a_rule_that_is_on_by_default_cannot_be_enabled_by_mistake_and_the_unknown_is_refused(self):
        with self.assertRaises(ValueError):
            with rules.enabled("NOPE"):
                pass

    def test_a_rule_can_be_off_and_on_at_once_only_in_favour_of_off(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_RULES_ON": "NP5", "PLACECOMPLETER_RULES_OFF": "NP5"}):
            self.assertFalse(rules.on("NP5"))                                                       # a switch off wins

    def test_the_registry_says_which_rules_are_off_by_default(self):
        flagged = {r["id"] for r in rules.all_rules() if r["default_off"]}
        self.assertEqual(flagged, rules.DEFAULT_OFF)

    def test_the_names_of_the_levels_are_not_given_a_language_by_default_and_the_name_of_the_place_still_is(self):
        with mock.patch.dict(os.environ, NOTHING_ON):
            self.assertEqual(unit_proposals("set-name-language"), [])
            of_the_place_off = proposals_of("set-name-language", False)
        self.assertTrue(unit_proposals("set-name-language"))                                        # with the rules on (the tests): they are offered
        self.assertEqual(proposals_of("set-name-language", False), of_the_place_off)               # the name of the place itself is the same either way

    def test_the_name_of_a_place_is_not_given_a_period_from_the_start_of_its_state_by_default(self):
        """NP3: a name that has one period and no other name shows as "?" in Gramps for an event that is earlier, so no period is better."""
        case = ti.RomanianCountyTests("test_the_name_of_the_place_is_given_the_time_the_state_that_ruled_began")

        def dates_of_the_place():
            screen = ingest.ingest(case.tree(), ingest.parse_structured(case.ANSWER.replace("OTHER_NAMES:\nhu: D\u00e9va (1867-1918)\n", "")), "1990")
            return [p for p in screen["proposals"] if p["kind"] == "set-name-date" and p["place"] == "deva"]
        with mock.patch.dict(os.environ, NOTHING_ON):
            self.assertEqual(dates_of_the_place(), [])                                              # the name of the place gets no period
            with rules.enabled("NP3"):
                self.assertTrue(dates_of_the_place())                                                # unless somebody asks for it
        self.assertTrue(dates_of_the_place())

    def test_the_names_of_the_levels_are_not_given_a_period_by_default(self):
        case = ti.RomanianCountyTests("test_the_name_of_the_place_is_given_the_time_the_state_that_ruled_began")
        text = case.ANSWER.replace("OTHER_NAMES:\nhu: D\u00e9va (1867-1918)\n", "")

        def fills():
            screen = ingest.ingest(case.tree(), ingest.parse_structured(text), "1990")
            return [p["place"] for p in screen["proposals"] if p["kind"] == "set-name-date" and p["place"] != "deva"]
        with mock.patch.dict(os.environ, NOTHING_ON):
            self.assertEqual(fills(), [])
            with rules.enabled("NP5"):
                self.assertTrue(fills())
        self.assertTrue(fills())


if __name__ == "__main__":
    unittest.main()
