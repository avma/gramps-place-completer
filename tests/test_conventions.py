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
"""The custom place types of a tree: what comes with the addon is empty (the types of Gramps itself), the file of the user comes first, and an update of the addon does
not touch it. The author's own tree (in Hebrew) is an example, which the tests use to describe a tree."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import kinds                                                              # noqa: E402

EMPTY = {"province": "", "empire": "", "monarchy": "", "district": [], "rules": [], "settlements": []}
PROBE = """
import json, sys
sys.path.insert(0, %r)
from placecompleter import kinds
print(json.dumps({"canton": kinds._container_type("other (canton)"), "voivodeship": kinds._container_type("voivodeship"),
                  "kreis": kinds._container_type("Kreis"), "empire": kinds._state_type("Austro-Hungarian Empire"), "rules": len(kinds.TREE_TYPES["rules"])}))
""" % ROOT


def example():
    with open(os.path.join(ROOT, "data", "type-conventions.example-he.json"), encoding="utf-8") as fh:
        return json.load(fh)


def types_of_a_fresh_start(home, **env):
    """What the engine decides when it starts with this home and these variables (the conventions are read when it starts)."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith("PLACECOMPLETER_CONVENTIONS")}
    clean.update(HOME=home, **env)
    out = subprocess.run([sys.executable, "-c", PROBE], env=clean, capture_output=True, text=True, check=True).stdout
    return json.loads(out.strip().splitlines()[-1])


class ShippedTests(unittest.TestCase):
    def test_what_comes_with_the_addon_describes_no_tree(self):
        with open(os.path.join(ROOT, "data", "type-conventions.json"), encoding="utf-8") as fh:
            shipped = json.load(fh)
        self.assertEqual({k: v for k, v in shipped.items() if k != "description"}, EMPTY)
        self.assertTrue(shipped["description"].startswith("The custom place types that YOUR tree uses"))

    def test_the_example_is_a_tree_in_hebrew_and_has_the_same_shape(self):
        sample = example()
        self.assertEqual(set(sample), set(EMPTY) | {"description"})
        self.assertTrue(sample["province"] and sample["empire"] and sample["rules"] and sample["settlements"])


class WhereTheFileIsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        self.user_file = os.path.join(self.home, ".config", "placecompleter", "type-conventions.json")

    def write(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(data if isinstance(data, str) else json.dumps(data))

    def load(self, **env):
        with mock.patch.dict(os.environ, dict({"HOME": self.home, "PLACECOMPLETER_CONVENTIONS": ""}, **env)):
            return kinds.load_tree_types()

    def test_without_a_file_of_the_user_the_conventions_are_empty(self):
        self.assertEqual(self.load(), dict(EMPTY, rules=[]))

    def test_the_file_of_the_user_is_read(self):
        self.write(self.user_file, {"province": "Province-X", "rules": [{"words": ["Canton"], "value": 0, "string": "Canton-X"}], "settlements": ["Kibbutz"]})
        got = self.load()
        self.assertEqual((got["province"], got["settlements"]), ("Province-X", ["Kibbutz"]))
        self.assertEqual(got["rules"], [{"words": ["canton"], "value": 0, "string": "Canton-X"}])                   # (the words are folded)

    def test_the_variable_comes_before_the_file_of_the_user(self):
        self.write(self.user_file, {"province": "from the file of the user"})
        other = os.path.join(self.home, "other.json")
        self.write(other, {"province": "from the variable"})
        self.assertEqual(self.load(PLACECOMPLETER_CONVENTIONS=other)["province"], "from the variable")

    def test_a_variable_that_names_a_file_that_is_not_there_is_ignored(self):
        self.write(self.user_file, {"province": "from the file of the user"})
        self.assertEqual(self.load(PLACECOMPLETER_CONVENTIONS=os.path.join(self.home, "missing.json"))["province"], "from the file of the user")

    def test_a_damaged_file_does_not_stop_anything(self):
        self.write(self.user_file, "{ this is not json")
        self.assertEqual(self.load(), dict(EMPTY, rules=[]))
        self.write(self.user_file, "[1, 2, 3]")                                           # (JSON, but not a description)
        self.assertEqual(self.load(), dict(EMPTY, rules=[]))

    def test_the_tests_themselves_describe_a_tree_with_the_example(self):
        self.assertEqual(kinds.TREE_TYPES["province"], example()["province"])


class WhatItDoesTests(unittest.TestCase):
    """The types that a unit of the answer is given, in an engine that starts without conventions and in one that starts with the example."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name

    def test_a_user_without_conventions_gets_the_types_of_gramps_and_the_word_of_the_answer(self):
        got = types_of_a_fresh_start(self.home)
        self.assertEqual(got["rules"], 0)
        self.assertEqual(got["canton"], {"value": 0, "string": "Canton"})                 # Gramps has no canton: the word of the answer
        self.assertEqual(got["voivodeship"], {"value": 8, "string": ""})                  # Province of Gramps
        self.assertEqual(got["kreis"], {"value": 12, "string": ""})                       # District of Gramps
        self.assertEqual(got["empire"], {"value": 1, "string": ""})                       # Country of Gramps
        self.assertNotRegex(json.dumps(got, ensure_ascii=False), r"[\u0590-\u05ff]")      # never a word of somebody else's language

    def test_a_user_with_the_example_gets_the_types_of_that_tree(self):
        sample = example()
        got = types_of_a_fresh_start(self.home, PLACECOMPLETER_CONVENTIONS=os.path.join(ROOT, "data", "type-conventions.example-he.json"))
        canton = next(r["string"] for r in sample["rules"] if "canton" in r["words"])
        self.assertEqual(got["canton"], {"value": 0, "string": canton})
        self.assertEqual(got["voivodeship"], {"value": 0, "string": sample["province"]})
        self.assertEqual(got["empire"], {"value": 0, "string": sample["empire"]})

    def test_the_file_of_the_user_in_the_config_folder_is_what_an_engine_finds_when_it_starts(self):
        path = os.path.join(self.home, ".config", "placecompleter", "type-conventions.json")
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"province": "Province-X"}, fh)
        got = types_of_a_fresh_start(self.home)
        self.assertEqual(got["voivodeship"], {"value": 0, "string": "Province-X"})


if __name__ == "__main__":
    unittest.main()
