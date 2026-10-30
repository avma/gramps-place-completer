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
"""The administrative levels of a country on a year (data/hierarchies.json): what the data holds, the question that lists them and the note when an
answer lacks a level."""
import os
import sys
import tempfile
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from placecompleter import hierarchy as hi, ingest, prompts, session as sess               # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_real_answers import answer                                                          # noqa: E402


def country(name):
    return hi.find_country(name)


class DataTests(unittest.TestCase):
    def test_the_data_is_well_formed(self):
        self.assertGreaterEqual(len(hi.COUNTRIES), 12)
        keys = [c["key"] for c in hi.COUNTRIES]
        self.assertEqual(len(keys), len(set(keys)))
        for c in hi.COUNTRIES:
            self.assertTrue(c["names"], c["key"])
            ordered = sorted(c["periods"], key=lambda p: p["from"])
            for earlier, later in zip(ordered, ordered[1:]):
                self.assertIsNotNone(earlier.get("to"), "%s: only the last period is open" % c["key"])
                self.assertLess(earlier["to"], later["from"], "%s: periods must not overlap" % c["key"])
            for p in c["periods"]:
                self.assertTrue(hi.levels(p), c["key"])
                for kind, local, optional in hi.levels(p):
                    self.assertTrue(kind, c["key"])

    def test_every_country_has_a_required_level_so_that_a_missing_one_can_be_said(self):
        for c in hi.COUNTRIES:
            for p in c["periods"]:
                self.assertTrue([1 for _k, _l, optional in hi.levels(p) if not optional], "%s %s" % (c["key"], p["from"]))

    def test_the_shipped_file_says_it_is_to_be_checked(self):
        from placecompleter import data
        self.assertIn("to be checked", data.load("hierarchies.json", {})["description"])

    def test_a_damaged_file_gives_no_countries(self):
        folder = tempfile.mkdtemp()
        with open(os.path.join(folder, "hierarchies.json"), "w", encoding="utf-8") as fh:
            fh.write('{"countries": [{"key": "x", "names": ["X"], "periods": [{"from": "y", "levels": []}]}, "text", {"names": 1}]}')
        self.assertEqual(hi.load(folder), [])
        self.assertEqual(hi.load(tempfile.mkdtemp()), [])


class FindTests(unittest.TestCase):
    def test_a_country_is_found_by_its_name_or_an_alias_in_any_case_and_with_accents(self):
        for text in ("Italy", "italia", "Repubblica Italiana", "Parma, Italia", "Österreich", "osterreich", "  Hungary "):
            self.assertIsNotNone(hi.find_country(text), text)
        self.assertEqual(hi.find_country("Österreich")["key"], "austria")

    def test_a_word_that_is_not_a_country_is_not_found(self):
        for text in ("Iowa", "polk", "", None, "Emilia-Romagna"):
            self.assertIsNone(hi.find_country(text), text)

    def test_the_year_is_the_first_four_digits(self):
        self.assertEqual((hi.year_of("1990"), hi.year_of("1990-05-17"), hi.year_of("about 1850"), hi.year_of("")), (1990, 1990, 1850, None))

    def test_the_period_of_a_year(self):
        hungary = country("Hungary")
        self.assertEqual(hi.period_for(hungary, 1900)["levels"][-1], "county|vármegye")
        self.assertEqual(hi.period_for(hungary, 1990)["levels"][-1], "county|megye")
        self.assertNotIn("?district|járás", hi.period_for(hungary, 1990)["levels"])                  # no járás from 1984 to 2012
        self.assertIn("?district|járás", hi.period_for(hungary, 2015)["levels"])
        self.assertIsNone(hi.period_for(hungary, 1700))
        self.assertIsNone(hi.period_for(hungary, None))
        self.assertIsNone(hi.period_for(None, 1990))


class QuestionTests(unittest.TestCase):
    def test_the_sentence_lists_the_levels_from_the_smallest_and_says_which_may_not_apply(self):
        line = hi.prompt_line(country("Italy"), 1990)
        self.assertIn("Administrative hierarchy for Italy in 1990", line)
        self.assertLess(line.index("municipality (comune) [may not apply]"), line.index("province (provincia)"))
        self.assertLess(line.index("province (provincia)"), line.index("region (regione)"))
        self.assertTrue(line.endswith(" "))

    def test_the_levels_depend_on_the_year(self):
        self.assertNotIn("region (regione)", hi.prompt_line(country("Italy"), 1950))
        self.assertIn("region (regione)", hi.prompt_line(country("Italy"), 1990))

    def test_nothing_is_added_when_the_country_or_the_year_is_not_known(self):
        self.assertEqual(hi.prompt_line(None, 1990), "")
        self.assertEqual(hi.prompt_line(country("Italy"), 1700), "")
        self.assertEqual(hi.prompt_line(country("Italy"), None), "")

    def test_the_levels_go_into_the_forms_before_the_closing_rule_and_nowhere_when_empty(self):
        line = hi.prompt_line(country("Italy"), 1990)
        for form in ("classic", "dated", "long"):
            text = prompts.build_prompt("Parma", "1990", form, line)
            self.assertLess(text.index("Administrative hierarchy for Italy"), text.index("Every container must be valid on 1990"), form)
        self.assertIn("Administrative hierarchy for Italy", prompts.build_prompt("Parma", "1990", "short", line))
        for form in prompts.FORMS:
            plain = prompts.build_prompt("Parma", "1990", form)
            self.assertNotIn("Administrative levels", plain)
            self.assertEqual(plain, plain.rstrip())
            self.assertEqual(plain, prompts.build_prompt("Parma", "1990", form, ""))


class SessionTests(unittest.TestCase):
    def make(self):
        return sess.Session(Tree({}, []), tempfile.mkdtemp(), pack_files=[])

    def test_a_country_typed_in_the_hint_puts_its_levels_into_the_question(self):
        s = self.make()
        a = s.begin("Parma", "1990", hint="Italy", engine="manual")
        self.assertIn("Administrative hierarchy for Italy in 1990", a["prompt"])
        self.assertIn("Parma, Italy", a["prompt"])                                               # (the hint also tells it from the other Parmas)

    def test_a_country_in_the_place_text_counts_too(self):
        a = self.make().begin("Parma, Italia", "1990", engine="manual")
        self.assertIn("Administrative hierarchy for Italy in 1990", a["prompt"])

    def test_a_hint_that_is_not_a_country_adds_no_levels(self):
        a = self.make().begin("Johnston", "1990", hint="Iowa", engine="manual")
        self.assertNotIn("Administrative levels", a["prompt"])

    def test_a_year_outside_the_data_adds_no_levels(self):
        a = self.make().begin("Parma", "1700", hint="Italy", engine="manual")
        self.assertNotIn("Administrative levels", a["prompt"])


class AnswerTests(unittest.TestCase):
    PARMA = ("PLACE_NAME_ON_DATE: Parma\nLANGUAGE: it\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Emilia-Romagna | region | 1970-present | Repubblica Italiana\n"
             "STATE_ON_DATE: Repubblica Italiana | 1946-present\nSOURCES: https://it.wikipedia.org/wiki/Parma | PLACE_NAME_ON_DATE\n")

    def notes(self, text, **kw):
        r = ingest.ingest(Tree({}, []), ingest.parse_structured(text), "1990", aliases={}, **kw)
        return [n for n in r["needs"] if n.startswith("response omits administrative tier ")]

    def test_a_level_that_the_answer_lacks_is_said_with_the_country_found_from_the_state_of_the_answer(self):
        self.assertEqual(self.notes(self.PARMA), ["response omits administrative tier province (provincia) present for Italy on date 1990"])

    def test_the_country_typed_by_the_user_is_used_when_given(self):
        self.assertEqual(len(self.notes(self.PARMA, country=country("Italy"))), 1)

    def test_nothing_is_said_when_the_answer_has_the_level(self):
        text = self.PARMA.replace("1 | Emilia-Romagna | region", "1 | Provincia di Parma | province | 1861-present | Repubblica Italiana\n2 | Emilia-Romagna | region")
        self.assertEqual(self.notes(text), [])

    def test_the_real_answers_of_new_york_and_zurich_lack_no_required_level(self):
        for name in ("answer_nyc_1990.txt", "answer_zurich_1990.txt"):
            r = ingest.ingest(Tree({}, []), ingest.parse_structured(answer(name)), "1990", aliases={})
            self.assertEqual([n for n in r["needs"] if n.startswith("response omits administrative tier ")], [], name)

    def test_a_country_that_is_not_in_the_data_says_nothing(self):
        text = self.PARMA.replace("Repubblica Italiana", "Atlantis")
        self.assertEqual(self.notes(text), [])

    def test_the_note_is_information_and_not_a_warning(self):
        from placecompleter.session import WARNING_STARTS
        self.assertFalse("response omits administrative tier province (provincia) present for Italy on date 1990".startswith(tuple(WARNING_STARTS)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
