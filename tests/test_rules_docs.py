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
"""The documents about the rules say what the registry of the rules (placecompleter/rules.py) says: the ids in their examples exist, the rules that are off by default
are those of DEFAULT_OFF, and the range of the notes is the range of the registry (docs/RULES_REVIEW.md, docs/ANALYZER_RULES.md)."""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import rules                                                              # noqa: E402


def read(name):
    with open(os.path.join(ROOT, "docs", name), encoding="utf-8") as fh:
        return fh.read()


def ids(text):
    return [i for i in re.split(r"[,\s]+", text.strip()) if i]


class RulesReviewTests(unittest.TestCase):
    def test_the_ids_in_the_examples_are_rules_that_exist(self):
        text = read("RULES_REVIEW.md")
        examples = re.findall(r"--without ([A-Z0-9,]+)", text) + re.findall(r"PLACECOMPLETER_RULES_OFF=([A-Z0-9,]+)", text)
        self.assertGreaterEqual(len(examples), 2)
        for example in examples:
            with rules.disabled(*ids(example)):                    # raises ValueError for an id that does not exist (a removed note, for example)
                pass

    def test_the_rules_that_are_off_by_default_are_those_of_the_registry(self):
        text = read("RULES_REVIEW.md")
        switch_on = re.findall(r"PLACECOMPLETER_RULES_ON=([A-Z0-9,]+)", text)
        self.assertEqual({frozenset(ids(s)) for s in switch_on}, {frozenset(rules.DEFAULT_OFF)})
        bullet = re.search(r"\*\*Default-Disabled Rules \(`DEFAULT_OFF`\):\*\*(.*)", text).group(1)
        self.assertEqual(set(re.findall(r"`((?:NP|NL)[0-9]*)`", bullet.split("PLACECOMPLETER_RULES_ON")[0])), set(rules.DEFAULT_OFF))

    def test_the_range_of_the_notes_is_the_range_of_the_registry(self):
        numbers = sorted(int(m[0][1:]) for m in rules.MESSAGES)
        first, last = re.search(r"Individual rules `(M\d\d)` through `(M\d\d)`", read("RULES_REVIEW.md")).groups()
        self.assertEqual((first, last), ("M%02d" % numbers[0], "M%02d" % numbers[-1]))

    def test_the_rules_that_the_review_removed_are_not_in_the_registry(self):
        table = read("ANALYZER_RULES.md")
        table = table[table.index("## Table 12"):table.index("**Kept, although")]
        removed = set(re.findall(r"\b(?:NP\d|M\d\d)\b", " ".join(re.findall(r"^\| ([^|]+) \|", table, re.M))))
        self.assertGreaterEqual(len(removed), 15)
        known = {r[0] for r in rules.BEHAVIOR} | {m[0] for m in rules.MESSAGES}
        self.assertEqual(sorted(removed & known), [])


class AnalyzerRulesTests(unittest.TestCase):
    def test_the_table_of_the_rules_that_are_off_by_default_names_them_all(self):
        text = read("ANALYZER_RULES.md")
        section = text[text.index("## Table 11"):text.index("## Table 12")]
        for rule_id in rules.DEFAULT_OFF:
            self.assertIn(rule_id, section)
        switch_on = re.findall(r"PLACECOMPLETER_RULES_ON=([A-Z0-9,]+)", section)
        self.assertEqual([frozenset(ids(s)) for s in switch_on], [frozenset(rules.DEFAULT_OFF)])

    def test_every_note_that_the_tables_mention_by_id_exists(self):
        text = read("ANALYZER_RULES.md")
        removed_section = text[text.index("## Table 12"):text.index("## What Is Still to Be Done")]
        outside = text.replace(removed_section, "")
        mentioned = set(re.findall(r"\bM\d\d\b", outside))
        self.assertTrue({"M51", "M52"} <= mentioned)
        missing = sorted(mentioned - {m[0] for m in rules.MESSAGES})
        self.assertEqual(missing, [], "notes that the tables mention and the registry does not have")


if __name__ == "__main__":
    unittest.main()
