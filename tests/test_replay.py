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
"""tools/replay_answers.py: the saved answers replayed through the analysis, to see which rules are ever used (docs/RULES_REVIEW.md)."""
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

import test_same_names as same                                                                # noqa: E402
import test_table as tab                                                                      # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402

spec = importlib.util.spec_from_file_location("replay_answers", os.path.join(ROOT, "tools", "replay_answers.py"))
replay_answers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_answers)


class SmallTests(unittest.TestCase):
    def test_the_place_and_the_date_come_from_the_name_of_the_file(self):
        self.assertEqual(replay_answers.name_and_date("/x/Johnston_1995.txt"), ("Johnston", "1995"))
        self.assertEqual(replay_answers.name_and_date("/x/Sissa_Trecasali_2014-05-01.txt"), ("Sissa Trecasali", "2014-05-01"))
        self.assertEqual(replay_answers.name_and_date("/x/notes.txt"), ("notes", ""))
        self.assertEqual(replay_answers.name_and_date("/x/Johnston_1950_v2.txt"), ("Johnston", "1950"))

    def test_a_message_is_the_shape_of_its_rule_without_names_and_numbers(self):
        a = replay_answers.shape("the level 'Toulouse M\u00e9tropole' (intercommunality and m\u00e9tropole) was left out: it overlaps")
        b = replay_answers.shape("the level 'Other Place' (intercommunality) was left out: it overlaps")
        self.assertEqual(a, b)
        self.assertNotIn("Toulouse", a)
        self.assertEqual(replay_answers.shape("sources listed by the answer: https://a.org/x; https://b.org/y"),
                         replay_answers.shape("sources listed by the answer: https://c.org/z"))


class ReplayTests(unittest.TestCase):
    def items(self):
        return [("Aussonne_1997.txt", "Aussonne", "1997", tab.tsv(tab.ROWS)),
                ("Blagnac_2026.txt", "Blagnac", "2026", same.answer()),
                ("garbage_1900.txt", "garbage", "1900", "this is not an answer"),
                ("nodate.txt", "nodate", "", same.answer())]

    def test_the_answers_are_read_counted_and_the_unreadable_ones_are_said(self):
        rows, kinds, shapes, errors = replay_answers.replay(Tree({}, []), self.items())
        self.assertEqual([r["file"] for r in rows], ["Aussonne_1997.txt", "Blagnac_2026.txt"])
        self.assertEqual(sorted(e[0] for e in errors), ["garbage_1900.txt", "nodate.txt"])
        self.assertEqual(rows[0]["type"], 15)                                                  # the table is read as the table
        self.assertGreater(kinds["add-place"][0], 4)
        self.assertEqual(kinds["add-place"][1], 2)                                             # in how many answers

    def test_a_rule_that_fired_is_in_the_count_and_one_that_did_not_is_not(self):
        _rows, _kinds, shapes, _errors = replay_answers.replay(Tree({}, []), self.items())
        overlap = [s for s in shapes if "overlaps the levels of the chain" in s]
        self.assertEqual(len(overlap), 1)
        self.assertEqual(shapes[overlap[0]][1], 1)                                             # only the second answer has an intercommunality
        self.assertFalse(any("has the same name as the place itself" in s for s in shapes))   # no level here has the name of the place

    def test_the_messages_that_never_fired_are_listed_and_the_ones_that_fired_are_not(self):
        _rows, _kinds, shapes, _errors = replay_answers.replay(Tree({}, []), self.items())
        never = [template for _file, template in replay_answers.unused(shapes)]
        self.assertTrue(never)                                                                  # a few answers cannot use every rule
        self.assertFalse(any("overlaps the levels of the chain" in t for t in never))           # this one fired (the intercommunality)
        self.assertTrue(any("matches the name of child place" in t for t in never))       # this one did not
        declared = [t for _f, t in replay_answers.declared_messages()]
        self.assertGreater(len(declared), 30)
        self.assertTrue(all(t in declared for t in never))

    def test_the_messages_that_fired_in_the_answers_of_the_user_are_not_listed_as_unused(self):
        fired = ["no source with a full link #: nothing in this answer can be checked", "These links already exist and require no changes: Provincia di Parma # -> Emilia-Romagna",
                 "the answer's own notes", "# places of the tree have this name: choose which one", "no period is given for the names Parma: when each was used is not known",
                 "CHOOSE: Erdelyi Fejedelemseg could be Magyarorszag #, which holds Hunyad # in the tree: the window asks which"]
        never = [template for _file, template in replay_answers.unused({s: (1, 1) for s in fired})]
        for part in ("nothing in this answer can be checked", "These links already exist", "the answer's own notes", "choose which one",
                     "no period is given for the names", "which holds %s in the tree"):
            self.assertFalse(any(part in t for t in never), part)

    def test_the_report_and_the_table_are_written(self):
        work = tempfile.mkdtemp(prefix="pc-replay-")
        try:
            answers = os.path.join(work, "answers")
            os.makedirs(answers)
            for label, _place, _date, text in self.items()[:2]:
                with open(os.path.join(answers, label), "w", encoding="utf-8") as fh:
                    fh.write(text)
            out = os.path.join(work, "report.tsv")
            import contextlib
            import io
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = replay_answers.main(["--answers", answers, "--out", out])
            self.assertEqual(code, 0)
            self.assertIn("answers read: 2   not read: 0", buffer.getvalue())
            with open(out, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
            self.assertEqual(lines[0].split("\t")[:3], ["file", "place", "date"])
            self.assertEqual(len(lines), 3)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_reports_that_the_tools_write_are_not_read_as_answers(self):
        work = tempfile.mkdtemp(prefix="pc-replay-")
        try:
            for name, text in (("Blagnac_2026.txt", same.answer()), ("ablate-table.txt", "rules switched off ..."), ("replay-old.txt", "answers read: 3"),
                               ("urls-status.txt", "200 https://example.org")):
                with open(os.path.join(work, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                replay_answers.main(["--answers", work, "--out", os.path.join(work, "r.tsv")])
            self.assertIn("answers read: 1   not read: 0", buffer.getvalue())
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_an_empty_folder_is_said(self):
        work = tempfile.mkdtemp(prefix="pc-replay-")
        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as buffer:
                code = replay_answers.main(["--answers", work])
            self.assertEqual(code, 2)
            self.assertIn("no answers", buffer.getvalue())
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
