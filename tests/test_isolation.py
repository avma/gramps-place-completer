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
"""The tests are on their own (tests/__init__.py): the same on every computer, whatever the language of Gramps, the settings and the network of the user."""
import os
import socket
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests                                                                                  # noqa: E402,F401  (makes the environment)
from placecompleter import engines, i18n                                                      # noqa: E402


class IsolationTests(unittest.TestCase):
    def test_the_home_folder_is_an_empty_folder_of_the_tests(self):
        home = os.environ["HOME"]
        self.assertIn("placecompleter-tests-", home)
        self.assertEqual(os.path.expanduser("~"), home)
        # (some test modules give Gramps a home of their own, inside the temporary folder: what may not happen is the home of the user)
        grampshome = os.environ.get("GRAMPSHOME", "")
        self.assertTrue(not grampshome or os.path.realpath(grampshome).startswith(os.path.realpath(tempfile.gettempdir())), grampshome)

    def test_the_language_is_english_and_gramps_does_not_translate_the_texts(self):
        self.assertEqual(os.environ["LANGUAGE"], "en")
        for text in ("_Cancel", "Confidence", "Place", "Date", "Question", "Close"):
            self.assertEqual(i18n._(text), text, text)

    def test_the_settings_of_the_user_are_not_read(self):
        # (the folder of the tests, or a path that does not exist, which is what many modules set: never a file of the user)
        for path in (engines.models_path(), engines.config_path()):
            self.assertTrue(path.startswith(os.environ["HOME"]) or path.startswith("/nonexistent/"), path)
        self.assertEqual(engines.remembered_model("openai"), "")
        self.assertEqual(os.environ["PLACECOMPLETER_KEYSTORE"], "none")
        self.assertEqual([n for n in os.environ if n.endswith("_API_KEY")], [])

    def test_the_network_is_closed_but_this_computer_is_not(self):
        with self.assertRaises(OSError):
            socket.create_connection(("example.com", 80), timeout=1)
        with self.assertRaises(OSError):
            socket.create_connection(("93.184.216.34", 80), timeout=1)
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        try:
            socket.create_connection(("127.0.0.1", server.getsockname()[1]), timeout=1).close()
            socket.create_connection(("localhost", server.getsockname()[1]), timeout=1).close()
        finally:
            server.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
