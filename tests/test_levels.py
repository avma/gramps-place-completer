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
"""The levels of the types of places and the rules of what may be inside what (T1-T5 of docs/ANALYZER_RULES.md)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, levels as lv                                               # noqa: E402

CONV = ingest.TREE_TYPES                                                                  # the types of the tree that ships with the addon (data/)
EMPIRE, MONARCHY, PROVINCE_T, DISTRICT_T, CANTON = CONV["empire"], CONV["monarchy"], CONV["province"], CONV["district"][0], CONV["rules"][0]["string"]
KIBBUTZ, MOSHAV, SMALL_VILLAGE = CONV["settlements"][:3]
NONE = {"province": "", "empire": "", "monarchy": "", "district": [], "rules": [], "settlements": []}


def t(value, string=""):
    return {"value": value, "string": string}


COUNTRY, STATE, COUNTY, CITY, STREET, PROVINCE, REGION, NEIGHBORHOOD, DISTRICT, BOROUGH, MUNICIPALITY, TOWN, VILLAGE, HAMLET = 1, 2, 3, 4, 7, 8, 9, 11, 12, 13, 14, 15, 16, 17


class LevelTests(unittest.TestCase):
    def test_the_types_of_gramps_have_their_levels(self):
        expected = {COUNTRY: 1, STATE: 2, COUNTY: 2, PROVINCE: 2, REGION: 2, DISTRICT: 2, 10: 2, MUNICIPALITY: 3, CITY: 4, TOWN: 4, VILLAGE: 4, HAMLET: 4,
                    NEIGHBORHOOD: 5, BOROUGH: 5, STREET: 6, 18: 7, 19: 7, 20: 7}
        for value, found in expected.items():
            self.assertEqual(lv.level(t(value), NONE), found, value)

    def test_a_type_with_no_level_is_unknown(self):
        for ptype in (None, {}, t(-1), t(5), t(6), t(0, "something of ours"), t(0, "")):
            self.assertIsNone(lv.level(ptype, CONV), ptype)

    def test_the_custom_types_of_the_tree_have_their_levels(self):
        for text, found in ((EMPIRE, 1), (MONARCHY, 1), (PROVINCE_T, 2), (DISTRICT_T, 2), (CONV["district"][1], 2), (CANTON, 2), (KIBBUTZ, 4), (MOSHAV, 4), (SMALL_VILLAGE, 4)):
            self.assertEqual(lv.level(t(0, text), CONV), found, text)
        self.assertIsNone(lv.level(t(0, KIBBUTZ), NONE))                                          # a tree without the conventions has none


class RuleTests(unittest.TestCase):
    def bad(self, parent, child, conv=CONV):
        return bool(lv.violation(t(*parent) if isinstance(parent, tuple) else t(parent), t(*child) if isinstance(child, tuple) else t(child), conv))

    def test_a_city_is_not_inside_a_city_nor_a_province_inside_a_province(self):
        self.assertTrue(self.bad(CITY, CITY))
        self.assertTrue(self.bad(PROVINCE, PROVINCE))
        self.assertTrue(self.bad(MUNICIPALITY, MUNICIPALITY))
        self.assertIn("type", lv.violation(t(CITY), t(CITY), CONV))

    def test_countries_may_be_inside_countries(self):
        self.assertFalse(self.bad(COUNTRY, COUNTRY))
        self.assertFalse(self.bad((0, EMPIRE), COUNTRY))
        self.assertFalse(self.bad(COUNTRY, (0, MONARCHY)))

    def test_settlements_are_on_one_level(self):
        for parent, child in ((CITY, TOWN), (TOWN, VILLAGE), (VILLAGE, HAMLET), (CITY, (0, KIBBUTZ)), ((0, MOSHAV), (0, KIBBUTZ)), ((0, KIBBUTZ), (0, MOSHAV)),
                              (CITY, (0, SMALL_VILLAGE))):
            self.assertTrue(self.bad(parent, child), (parent, child))
        self.assertIn("single tier", lv.violation(t(CITY), t(TOWN), CONV))

    def test_an_area_is_not_inside_a_settlement(self):
        for child in (PROVINCE, COUNTY, REGION, STATE, MUNICIPALITY):
            self.assertTrue(self.bad(CITY, child), child)                                         # Parma the city and the Provincia di Parma
        self.assertIn("level", lv.violation(t(CITY), t(PROVINCE), CONV))

    def test_what_may_be_inside_what(self):
        for parent, child in ((COUNTRY, STATE), (STATE, COUNTY), (COUNTRY, PROVINCE), (PROVINCE, MUNICIPALITY), (REGION, PROVINCE), (PROVINCE, TOWN),
                              (MUNICIPALITY, CITY), (MUNICIPALITY, VILLAGE), (CITY, NEIGHBORHOOD), (CITY, STREET), (STREET, 20), (CITY, BOROUGH),
                              ((0, CANTON), (0, DISTRICT_T)), ((0, PROVINCE_T), MUNICIPALITY), ((0, EMPIRE), (0, PROVINCE_T)), (COUNTRY, (0, KIBBUTZ))):
            self.assertFalse(self.bad(parent, child), (parent, child))

    def test_a_place_is_not_inside_a_lower_level(self):
        for parent, child in ((STREET, CITY), (NEIGHBORHOOD, CITY), (CITY, COUNTRY), (TOWN, STATE), (19, CITY)):
            self.assertTrue(self.bad(parent, child), (parent, child))

    def test_no_rule_applies_to_a_type_with_no_level(self):
        for parent, child in ((-1, CITY), (CITY, -1), (5, 5), (6, TOWN), ((0, "something"), PROVINCE), (CITY, (0, "something"))):
            self.assertFalse(self.bad(parent, child), (parent, child))

    def test_the_rules_are_read_by_the_analysis_with_the_conventions_of_the_tree(self):
        self.assertIn("settlements", ingest.TREE_TYPES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
