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
"""The AI gave the question back (the template with its <fields> unfilled) instead of an answer: it is not an answer, and the next form of the question is tried."""
import glob
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest, prompts, session as sess                                   # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402

ECHO = os.path.join(HERE, "data", "answer_echo_trecasali.txt")


def echo():
    with open(ECHO, encoding="utf-8") as fh:
        return fh.read()


class EchoTests(unittest.TestCase):
    def test_the_question_given_back_is_recognised(self):
        self.assertTrue(prompts.looks_like_echo(echo()))
        for form in ("classic", "short", "dated", "long"):
            self.assertTrue(prompts.looks_like_echo(prompts.build_prompt("Trecasali, Italy", "1990", form)), form)      # the question of any form
        self.assertTrue(prompts.looks_like_echo("PLACE_NAME_ON_DATE: <name in the language of the state>\nLANGUAGE: <code>\n"))     # the template alone

    def test_a_real_answer_is_never_taken_for_the_question(self):
        files = glob.glob(os.path.join(HERE, "data", "answer_*.txt"))
        self.assertGreaterEqual(len(files), 8)
        for path in files:
            if path != ECHO:
                with open(path, encoding="utf-8") as fh:
                    self.assertFalse(prompts.looks_like_echo(fh.read()), os.path.basename(path))
        self.assertFalse(prompts.looks_like_echo(""))
        self.assertFalse(prompts.looks_like_echo(None))

    def test_the_fields_that_were_not_filled_in_are_unknown_and_there_is_no_place(self):
        rec = ingest.parse_structured(echo())
        self.assertFalse(rec["name"])
        self.assertEqual(rec["containers"], [])
        self.assertFalse(rec["ambiguous"])
        r = ingest.ingest(Tree({}, []), rec, "1990", aliases={})
        self.assertEqual(r["proposals"], [])                                                              # no place is made of a placeholder
        self.assertEqual(r["needs"], ["response lacks place name; no changes proposed"])

    def test_a_field_with_a_part_that_was_not_filled_in_keeps_the_rest(self):
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: Sissa\nLANGUAGE: <language code of that name>\nCOORDINATES: 44.9, 10.2\n")
        self.assertEqual(rec["name"], "Sissa")
        self.assertEqual(tuple(rec["coordinates"]), (44.9, 10.2))

    def make(self, form):
        s = sess.Session(Tree({}, []), tempfile.mkdtemp(), pack_files=[])
        s.begin("Trecasali", "1990", hint="Italy", engine="manual", form=form)
        return s

    def test_with_the_auto_form_the_next_form_is_prepared_and_the_reason_says_what_happened(self):
        s = self.make("auto")
        got = s.receive(echo())
        self.assertEqual(got["action"], "retry")
        self.assertIn("AI returned unfulfilled prompt", got["reason"])
        self.assertIn("province in Region hint", got["reason"])
        self.assertNotIn("Administrative levels of Italy", got["next"]["prompt"][:0])                    # (the next question is asked again)
        self.assertEqual(s.state, "asked")

    def test_with_one_form_only_it_fails_and_says_that_no_other_form_is_left(self):
        s = self.make("classic")
        got = s.receive(echo())
        self.assertEqual(got.get("action"), "error")
        self.assertIn("unfulfilled prompt", got["message"])
        self.assertIn("all prompt fallback formats exhausted", got["message"])
        self.assertIsNone(s.rec)

    def test_a_real_answer_is_still_read(self):
        s = self.make("classic")
        with open(os.path.join(HERE, "data", "answer_sissa_1990_v2.txt"), encoding="utf-8") as fh:
            got = s.receive(fh.read())
        self.assertNotEqual(got.get("action"), "retry")
        self.assertIsNotNone(s.rec)


if __name__ == "__main__":
    unittest.main(verbosity=2)
