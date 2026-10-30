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
"""The names of the types of places are those that Gramps itself shows (they differ between the versions of Gramps and the translations), not a translation of the addon."""
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import kinds, session as sess                                             # noqa: E402


class TypeNameTests(unittest.TestCase):
    def test_the_name_of_every_type_is_the_name_that_gramps_shows(self):
        from gramps.gen.lib import PlaceType
        for value, english in kinds.TYPE_NAMES.items():
            self.assertEqual(kinds.type_name(value), str(PlaceType(value)), english)

    def test_in_english_they_are_the_words_of_the_addon(self):
        self.assertEqual([kinds.type_name(v) for v in (4, 14, 15, 16, 17)], ["City", "Municipality", "Town", "Village", "Hamlet"])

    def test_without_gramps_the_english_word_is_used_and_a_value_that_is_not_known_is_shown_as_it_is(self):
        with mock.patch.dict(sys.modules, {"gramps.gen.lib": None}):
            self.assertEqual(kinds.type_name(15), "Town")
        self.assertEqual(kinds.type_name(99), "99")

    def test_a_name_that_gramps_translates_is_what_the_screen_shows(self):
        """Gramps says 'Town' in Hebrew 'ir'a' and 'ayarah': the screen must say what the Type column says, so the change of a type is read by the user as written there."""
        from gramps.gen.lib import PlaceType
        with mock.patch.object(PlaceType, "__str__", lambda self: "TRANSLATED-%d" % self.value):
            self.assertEqual(kinds.type_name(15), "TRANSLATED-15")
            change = {"kind": "set-type", "place": "p", "type_value": 15, "type_string": ""}
            text = sess.describe_change(change, lambda h: "Blagnac") if hasattr(sess, "describe_change") else None
            if text is not None:
                self.assertIn("TRANSLATED-15", text)

    def test_the_twenty_words_are_no_longer_texts_of_the_catalog(self):
        template = open(os.path.join(os.path.dirname(HERE), "po", "template.pot"), encoding="utf-8").read()
        for word in ("Town", "Hamlet", "Municipality"):
            self.assertNotIn('msgid "%s"\n' % word, template)


if __name__ == "__main__":
    unittest.main()
