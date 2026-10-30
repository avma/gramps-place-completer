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
"""The source code holds no text of another language: the texts the user reads are English in the code (the Hebrew is in po/he-local.po), and what
depends on the language or the conventions of a tree is in the data files (data/). This test looks at every program of the add-on."""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HEBREW = re.compile("[\u0590-\u05ff\ufb1d-\ufb4f]")
SKIP_DIRS = {"__pycache__", ".git", "po", "data", "packs", "locale", "locale.off"}


def programs():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(root, name)


class SourceLanguageTests(unittest.TestCase):
    def test_no_program_has_a_letter_of_hebrew(self):
        found = []
        for path in programs():
            with open(path, encoding="utf-8") as fh:
                for number, line in enumerate(fh, 1):
                    if HEBREW.search(line):
                        found.append("%s:%d: %s" % (os.path.relpath(path, ROOT), number, line.strip()[:80]))
        self.assertEqual(found, [], "Hebrew in the source: use an English text (the Hebrew goes to po/he-local.po) or a data file (data/)")

    def test_the_test_looks_at_the_programs_and_would_see_hebrew(self):
        files = [os.path.relpath(p, ROOT) for p in programs()]
        self.assertIn("placecompleter_tool.py", files)
        self.assertIn(os.path.join("placecompleter", "ingest.py"), files)
        self.assertIn(os.path.join("tests", "test_source_language.py"), files)
        self.assertTrue(HEBREW.search("\u05e9\u05dc\u05d5\u05dd"))                       # (written with escapes: this file has no Hebrew either)

    def test_what_depends_on_the_language_of_a_tree_is_in_the_data_files(self):
        from placecompleter import ingest, prompts
        self.assertTrue(all(ingest.TREE_TYPES[k] for k in ("province", "empire", "monarchy")))
        self.assertTrue(ingest.TREE_TYPES["district"])
        self.assertGreaterEqual(len(prompts.NO_ANSWER), 3)
        self.assertTrue(any(HEBREW.search(p) for p in prompts.NO_ANSWER))                # the phrases of the pages in Hebrew


if __name__ == "__main__":
    unittest.main(verbosity=2)
