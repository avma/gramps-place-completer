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
"""tools/po_exchange.py: the PO files of the texts for editing in Poedit, and the check of a file that comes back."""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

spec = importlib.util.spec_from_file_location("po_exchange", os.path.join(ROOT, "tools", "po_exchange.py"))
po_exchange = importlib.util.module_from_spec(spec)
spec.loader.exec_module(po_exchange)


def H(msgid):
    """The Hebrew that the addon has for a text (the tests do not write Hebrew: no program file has a letter of Hebrew)."""
    return po_exchange.hebrew()[msgid]


class MakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = tempfile.mkdtemp(prefix="pc-po-")
        cls.counts = po_exchange.make(cls.out)
        cls.he_header, cls.he = po_exchange.read_po(os.path.join(cls.out, "placecompleter-he.po"))
        cls.en_header, cls.en = po_exchange.read_po(os.path.join(cls.out, "placecompleter-en-edit.po"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_every_text_of_the_program_is_in_both_files_in_the_same_order(self):
        texts = [m for m, _r in po_exchange.catalog()]
        self.assertGreater(len(texts), 300)
        self.assertEqual([e["msgid"] for e in self.he], texts)
        self.assertEqual([e["msgid"] for e in self.en], texts)
        self.assertEqual(self.counts[0], len(texts))

    def test_the_hebrew_file_has_the_hebrew_that_the_addon_has(self):
        have = po_exchange.hebrew()
        self.assertEqual({e["msgid"]: e["msgstr"] for e in self.he}, {m: have.get(m, "") for m, _r in po_exchange.catalog()})
        self.assertEqual(sum(1 for e in self.he if not e["msgstr"]), 0)                              # none is empty: the Hebrew is complete

    def test_the_english_file_holds_the_same_english_in_the_box_for_editing(self):
        self.assertTrue(all(e["msgstr"] == e["msgid"] for e in self.en))

    def test_the_headers_say_the_language_and_the_encoding(self):
        self.assertIn("Language: he", self.he_header)
        self.assertIn("Language: en", self.en_header)
        self.assertIn("charset=UTF-8", self.he_header)

    def test_a_text_with_a_placeholder_is_marked_so_that_poedit_checks_it(self):
        for e in self.he:
            self.assertEqual("python-format" in e["flags"], bool(po_exchange.PLACEHOLDER.search(e["msgid"])), e["msgid"][:50])

    def test_each_text_says_where_it_is_used(self):
        self.assertTrue(all(e["refs"] for e in self.he))
        self.assertTrue(any(r.startswith("placecompleter_tool.py:") for e in self.he for r in e["refs"]))

    def test_what_a_placeholder_stands_for_is_written_where_the_code_says_it(self):
        by = {e["msgid"]: e for e in self.he}
        text = "Move %s from %s to %s"
        self.assertTrue(any("what each placeholder stands for" in c for c in by[text]["comments"]), by[text]["comments"])
        self.assertGreater(self.counts[2], 20)

    def test_a_text_with_line_breaks_and_one_with_a_space_at_the_end_survive_the_file(self):
        by = {e["msgid"]: e for e in self.he}
        with_breaks = next(m for m in by if m.count("\n") >= 3)
        self.assertEqual(by[with_breaks]["msgstr"].count("\n"), with_breaks.count("\n"))
        with_space = next(m for m in by if m.endswith(" ") and len(m) > 40)
        self.assertTrue(by[with_space]["msgstr"].endswith(" "))

    def test_the_files_made_are_read_back_as_they_were_written(self):
        header, again = po_exchange.read_po(os.path.join(self.out, "placecompleter-he.po"))
        self.assertEqual([(e["msgid"], e["msgstr"]) for e in again], [(e["msgid"], e["msgstr"]) for e in self.he])


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="pc-po-")
        po_exchange.make(self.out)
        self.he = os.path.join(self.out, "placecompleter-he.po")
        self.en = os.path.join(self.out, "placecompleter-en-edit.po")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def edit(self, path, old, new, count=1):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        assert old in text, old
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new, count))

    def test_the_files_as_they_were_made_are_fine(self):
        self.assertEqual(po_exchange.check(self.he)[2], 0)
        language, report, bad = po_exchange.check(self.en)
        self.assertEqual((language, bad), ("en", 0))
        self.assertIn("0 English texts were changed:", report[0])

    def test_a_placeholder_that_was_lost_is_found(self):
        self.edit(self.he, 'msgstr "%s"' % H("Move %s from %s to %s"), 'msgstr "%s"' % H("Move %s from %s to %s").rsplit(" ", 1)[0])
        language, report, bad = po_exchange.check(self.he)
        self.assertEqual(bad, 1)
        self.assertIn("are not the same", report[0])

    def test_a_line_break_that_was_lost_is_found(self):
        msgid = next(m for m in po_exchange.hebrew() if m.startswith("Target year for historical names"))
        self.edit(self.he, po_exchange._quote(H(msgid)), po_exchange._quote(H(msgid).replace("\n", " ")))
        self.assertIn("line breaks", " ".join(po_exchange.check(self.he)[1]))

    def test_a_space_at_the_end_that_was_removed_is_found(self):
        msgid = "These modification steps are interdependent: "
        self.assertTrue(msgid.endswith(" ") and H(msgid).endswith(" "))
        self.edit(self.he, po_exchange._quote(H(msgid)), po_exchange._quote(H(msgid).rstrip()))
        self.assertIn("a space at the beginning or at the end", " ".join(po_exchange.check(self.he)[1]))

    def test_a_prefix_with_a_hyphen_may_take_the_place_of_the_space_at_the_end(self):
        """In Hebrew 'from ' is 'm-' and 'to ' is 'ad l-': they join the year with a hyphen and no space."""
        self.assertEqual(po_exchange.problems_of("from ", "\u05de-"), [])
        self.assertEqual(po_exchange.problems_of("to ", "\u05e2\u05d3 \u05dc-"), [])
        self.assertTrue(po_exchange.problems_of("from ", "\u05de"))                                   # no hyphen, no space: wrong

    def test_an_empty_hebrew_text_and_a_fuzzy_one_are_found(self):
        self.edit(self.he, 'msgstr %s' % po_exchange._quote(H("a place cannot contain itself")), 'msgstr ""')
        text = " ".join(po_exchange.check(self.he)[1])
        self.assertIn("1 texts have no Hebrew yet", text)
        self.edit(self.he, '#, python-format\nmsgid "Move %s from %s to %s"', '#, fuzzy, python-format\nmsgid "Move %s from %s to %s"')
        self.assertIn("FUZZY", " ".join(po_exchange.check(self.he)[1]))

    def test_a_changed_source_is_said_to_be_not_a_text_of_the_program(self):
        self.edit(self.he, 'msgid "Move %s from %s to %s"', 'msgid "Shift %s from %s to %s"')
        text = " ".join(po_exchange.check(self.he)[1])
        self.assertIn("MISSING from the file", text)
        self.assertIn("NOT a text of the program", text)

    def test_the_english_that_was_changed_is_listed_with_the_old_and_the_new(self):
        self.edit(self.en, 'msgstr "Move %s from %s to %s"', 'msgstr "Shift %s from %s to %s"')
        language, report, bad = po_exchange.check(self.en)
        self.assertEqual(bad, 0)
        self.assertIn("1 English texts were changed:", report[0])
        self.assertIn("- Move %s from %s to %s", report[1])
        self.assertIn("+ Shift %s from %s to %s", report[1])

    def test_an_english_correction_that_loses_a_placeholder_is_a_problem(self):
        self.edit(self.en, 'msgstr "Move %s from %s to %s"', 'msgstr "Move it"')
        self.assertEqual(po_exchange.check(self.en)[2], 1)

    def test_the_exit_code_says_whether_something_is_wrong(self):
        self.assertEqual(po_exchange.main(["check", self.he, self.en]), 0)
        self.edit(self.he, 'msgstr %s' % po_exchange._quote(H("a place cannot contain itself")), 'msgstr ""')
        self.assertEqual(po_exchange.main(["check", self.he]), 1)


if __name__ == "__main__":
    unittest.main()
