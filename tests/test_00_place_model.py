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
"""The alarm: the place model of Gramps is the one that the addon was written for.

The first test of the suite on purpose. GEPS 045 (Place Model Enhancements) proposes another model: one list of names (no primary name, no alternative names), types
that are a list with dates and groups, a hierarchy type on each enclosure. It is stalled and none of it is in Gramps 6.0, 6.1 or master. If a version of Gramps
brings it, this test fails FIRST and says why, before many other tests fail for reasons that are hard to read. See MAINTENANCE.md, "Watch list"."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

WHY = ("The place model of Gramps is not the one that Place Completer was written for (GEPS 045, Place Model Enhancements?). "
       "writer.py, model.py and grampslink.py have to be adapted: see MAINTENANCE.md, 'Watch list'. Details: %s")

# what the addon uses today
USED = ("get_name", "set_name", "get_alternative_names", "add_alternative_name", "set_alternative_names", "get_type", "set_type", "get_placeref_list", "add_placeref")
# what the proposal adds or replaces (names taken from the page of GEPS 045)
NEW = ("add_name", "get_place_types", "add_place_type", "get_event_ref_list", "get_attribute_list", "get_abbreviation_list")


class PlaceModelTests(unittest.TestCase):
    def test_the_place_has_the_methods_that_the_addon_uses_and_none_of_the_new_model(self):
        from gramps.gen.lib import Place
        missing = [m for m in USED if not hasattr(Place, m)]
        new = [m for m in NEW if hasattr(Place, m)]
        self.assertEqual((missing, new), ([], []), WHY % ("missing %s; new %s" % (missing, new)))

    def test_the_name_and_the_type_are_one_name_and_one_type(self):
        from gramps.gen.lib import Place, PlaceName, PlaceType
        place = Place()
        name = PlaceName()
        name.set_value("Blagnac")
        place.set_name(name)
        place.set_type(PlaceType.TOWN)
        self.assertEqual(place.get_name().get_value(), "Blagnac", WHY % "the name")
        self.assertEqual(int(place.get_type()), int(PlaceType.TOWN), WHY % "the type")
        self.assertEqual(place.get_alternative_names(), [], WHY % "the alternative names")

    def test_no_group_of_place_types_exists(self):
        import gramps.gen.lib as lib
        self.assertFalse(hasattr(lib, "PlaceGroup") or hasattr(lib, "PlaceHierType"), WHY % "PlaceGroup or PlaceHierType exists")


if __name__ == "__main__":
    unittest.main()
