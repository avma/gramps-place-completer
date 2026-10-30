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
"""The confidence of a change: Confirmed, Reported, Inferred, Unsure, and why. Only what the program really knows."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placecompleter import confidence as cf                                                  # noqa: E402


def ai(kind="set-type", url="https://en.wikipedia.org/wiki/X", claim="SETTLEMENT_TYPE_ON_DATE", **extra):
    evidence = [{"source": "ai-answer", "url": url, "claim": claim}] if url else []
    return {"kind": kind, "origin": "ai-answer", "basis": "assumption", "evidence": evidence, **extra}


class LevelTests(unittest.TestCase):
    def test_independent_data_is_confirmed(self):
        for p in ({"kind": "set-coordinates", "origin": "wikidata", "basis": "evidence"}, {"kind": "add-link", "basis": "evidence"},
                  {"kind": "end-link", "basis": "tree"}, {"kind": "add-place", "origin": "agent", "basis": "evidence"}):
            self.assertEqual(cf.level_of(p)[0], cf.CONFIRMED, p)

    def test_what_the_program_works_out_from_other_data_is_inferred(self):
        for p in ({"kind": "set-name-date", "origin": "wikidata", "basis": "lifetime"}, {"kind": "add-link", "basis": "assumption"},
                  {"kind": "end-link", "origin": "agent", "basis": "assumption"}):
            self.assertEqual(cf.level_of(p)[0], cf.INFERRED, p)

    def test_what_the_answer_states_and_cites_is_reported(self):
        level, why = cf.level_of(ai())
        self.assertEqual((level, why), (cf.REPORTED, "stated in the AI response with a supporting source citation"))

    def test_what_the_program_works_out_from_the_answer_is_inferred(self):
        for p in (ai("set-name-date"), ai("set-name-language"), ai("rename-place"), ai("add-link", refines=True)):
            self.assertEqual(cf.level_of(p)[0], cf.INFERRED, p)

    def test_a_field_the_answer_is_not_sure_about_is_unsure(self):
        level, why = cf.level_of(ai("set-coordinates", claim="COORDINATES"), unsure={"COORDINATES"})
        self.assertEqual((level, why), (cf.UNSURE, "the response indicated uncertainty about COORDINATES"))
        self.assertEqual(cf.level_of(ai("set-type"), unsure={"COORDINATES"})[0], cf.REPORTED)             # another field: no doubt about this one

    def test_when_the_evidence_names_no_field_the_kind_decides(self):
        p = ai("set-coordinates", claim="")
        self.assertEqual(cf.fields_of(p), {"COORDINATES"})
        self.assertEqual(cf.level_of(p, unsure={"COORDINATES"})[0], cf.UNSURE)
        self.assertEqual(cf.fields_of(ai("add-link", claim="")), {"CONTAINERS"})

    def test_an_answer_that_contradicts_itself_or_disagrees_with_a_saved_one_makes_everything_in_it_unsure(self):
        for p in (ai(), ai("set-name-date"), ai("add-place")):
            level, why = cf.level_of(p, doubtful=True)
            self.assertEqual((level, why), (cf.UNSURE, "the response contains internal contradictions or conflicts with saved historical data"))

    def test_a_statement_with_no_page_is_unsure(self):
        level, why = cf.level_of(ai(url=""))
        self.assertEqual((level, why), (cf.UNSURE, "stated in the AI response without supporting web citations"))
        self.assertEqual(cf.level_of(ai(url="   "))[0], cf.UNSURE)

    def test_doubt_comes_before_the_rule(self):
        self.assertEqual(cf.level_of(ai("set-name-date", claim="PLACE_NAME_ON_DATE"), unsure={"PLACE_NAME_ON_DATE"})[0], cf.UNSURE)
        self.assertEqual(cf.level_of(ai("set-name-date", claim="PLACE_NAME_ON_DATE"))[0], cf.INFERRED)

    def test_a_change_of_several_steps_has_the_level_of_its_least_sure_step(self):
        steps = [ai("add-place"), ai("add-link"), ai("set-coordinates", claim="COORDINATES")]
        self.assertEqual(cf.of_steps(steps, unsure={"COORDINATES"})[0], cf.UNSURE)
        self.assertEqual(cf.of_steps([ai("add-place"), ai("set-name-date")])[0], cf.INFERRED)
        self.assertEqual(cf.of_steps([ai("add-place"), ai("add-link")])[0], cf.REPORTED)
        self.assertEqual(cf.of_steps([{"kind": "x", "basis": "evidence"}, ai()])[0], cf.REPORTED)
        self.assertEqual(cf.of_steps([])[0], cf.CONFIRMED)

    def test_the_levels_are_ordered_from_the_surest(self):
        self.assertEqual(cf.ORDER, (cf.CONFIRMED, cf.REPORTED, cf.INFERRED, cf.UNSURE))
        self.assertEqual([cf.label(x) for x in cf.ORDER], ["Confirmed", "Reported", "Inferred", "Unsure"])

    def test_the_explanation_names_every_level_in_a_few_short_lines(self):
        text = cf.explanation()
        for word in ("Confirmed:", "Reported:", "Inferred:", "Unsure:"):
            self.assertIn(word, text)
        self.assertLessEqual(len(text.split("\n")), 6)
        self.assertTrue(all(len(line) <= 100 for line in text.split("\n")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
