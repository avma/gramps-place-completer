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
"""tools/collect_answers.py: the table question asked of an AI by itself, for a list of places, and the answers kept."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import engines, prompts                                                   # noqa: E402
import test_table as tab                                                                      # noqa: E402

spec = importlib.util.spec_from_file_location("collect_answers", os.path.join(ROOT, "tools", "collect_answers.py"))
collect_answers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect_answers)

GOOD = tab.tsv(tab.ROWS)
CFG = engines.pick("anthropic")


def asking(replies):
    """A fake AI: replies is {place: [reply, ...]} (an Exception is raised, a string is the text); it counts its calls."""
    calls = []

    def ask(cfg, prompt):
        place = next(p for p in replies if "settlement %s in" % p in prompt or "Place: %s." % p in prompt)
        calls.append(place)
        queue = replies[place]
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return {"text": reply, "model": "fake-model"}
    ask.calls = calls
    return ask


class SmallTests(unittest.TestCase):
    def test_a_file_of_places_is_read_with_remarks_and_blank_lines(self):
        work = tempfile.mkdtemp()
        try:
            path = os.path.join(work, "places.txt")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("# a remark\n\nBlagnac | 2026\nSissa Trecasali | 1990\n")
            self.assertEqual(collect_answers.read_places(path), [("Blagnac", "2026"), ("Sissa Trecasali", "1990")])
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("no year here\n")
            with self.assertRaises(ValueError):
                collect_answers.read_places(path)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_what_is_a_usable_answer(self):
        self.assertTrue(collect_answers.usable(GOOD))
        self.assertFalse(collect_answers.usable(prompts.build_prompt("Aussonne", "1997", "table")))        # the question given back
        self.assertFalse(collect_answers.usable("I could not find anything about this place."))
        self.assertFalse(collect_answers.usable(""))
        self.assertFalse(collect_answers.usable(None))
        self.assertFalse(collect_answers.usable("Category\tValue/Name\tYear Range\tLevel Type\tExplanation\tSource\n"))      # a header and no rows

    def test_the_older_forms_are_judged_by_the_labelled_lines_and_not_by_a_table(self):
        import test_same_names as same
        self.assertTrue(collect_answers.usable(same.answer(), "classic"))
        self.assertFalse(collect_answers.usable(same.answer(), "table"))
        self.assertFalse(collect_answers.usable(GOOD, "classic"))
        self.assertFalse(collect_answers.usable("No idea.", "classic"))

    def test_the_list_of_places_is_twenty_places_with_years_and_every_question_can_be_made(self):
        places = collect_answers.DEFAULT_PLACES
        self.assertEqual(len(places), 20)
        self.assertEqual(len(set(places)), 20)
        for place, year in places:
            self.assertRegex(year, r"^\d{4}$")
            self.assertNotRegex(prompts.build_prompt(place, year, "table", language="he"), r"\{[a-z_]+\}")


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="pc-collect-")
        self.said = []

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def run_collect(self, places, replies, **kw):
        ask = asking(replies)
        results = collect_answers.collect(places, CFG, self.folder, ask=ask, say=self.said.append, **kw)
        return results, ask

    def test_a_table_is_kept_with_who_answered(self):
        results, _ask = self.run_collect([("Aussonne", "1997")], {"Aussonne": [GOOD]})
        self.assertEqual([r[2] for r in results], ["saved"])
        path = os.path.join(self.folder, "Aussonne_1997.txt")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), GOOD)
        with open(path[:-4] + ".meta.json", encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual((meta["engine"], meta["form"], meta["model"], meta["place"], meta["date"]), ("anthropic", "table", "fake-model", "Aussonne", "1997"))

    def test_the_time_and_the_length_of_each_answer_are_kept_and_averaged(self):
        ticks = iter([0.0, 4.0, 10.0, 16.0])
        results, _ask = self.run_collect([("Aussonne", "1997"), ("Blagnac", "2026")], {"Aussonne": [GOOD], "Blagnac": [GOOD]}, clock=lambda: next(ticks))
        self.assertEqual([r[4]["seconds"] for r in results], [4.0, 6.0])
        with open(os.path.join(self.folder, "Aussonne_1997.meta.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        self.assertEqual((meta["seconds"], meta["chars"]), (4.0, len(GOOD)))
        self.assertIn("an answer took 5 seconds and %d characters on average" % len(GOOD), collect_answers.summary(results))

    def test_an_older_form_can_be_collected_for_the_comparison(self):
        import test_same_names as same
        results, _ask = self.run_collect([("Blagnac", "2026")], {"Blagnac": [same.answer()]}, form="classic")
        self.assertEqual(results[0][2], "saved")
        with open(os.path.join(self.folder, "Blagnac_2026.meta.json"), encoding="utf-8") as fh:
            self.assertEqual(json.load(fh)["form"], "classic")

    def test_the_question_that_is_asked_is_the_table_question_with_the_language(self):
        seen = []

        def ask(cfg, prompt):
            seen.append(prompt)
            return {"text": GOOD, "model": "m"}
        collect_answers.collect([("Aussonne", "1997")], CFG, self.folder, language="he", ask=ask, say=lambda s: None)
        self.assertEqual(seen, [prompts.build_prompt("Aussonne", "1997", "table", language="he")])

    def test_an_answer_that_is_not_a_table_is_asked_once_more_and_then_rejected_with_its_text_kept_apart(self):
        results, ask = self.run_collect([("Blagnac", "2026")], {"Blagnac": ["No idea."]})
        self.assertEqual(results[0][2], "rejected")
        self.assertEqual(len(ask.calls), 2)                                                          # the question and one more
        self.assertIn("no table in the answer", results[0][3])
        self.assertFalse(os.path.exists(os.path.join(self.folder, "Blagnac_2026.txt")))
        self.assertTrue(os.path.exists(os.path.join(self.folder, "rejected", "Blagnac_2026.txt")))

    def test_the_second_try_can_be_the_good_one(self):
        results, ask = self.run_collect([("Blagnac", "2026")], {"Blagnac": ["No idea.", GOOD]})
        self.assertEqual((results[0][2], len(ask.calls)), ("saved", 2))
        self.assertFalse(os.path.exists(os.path.join(self.folder, "rejected")))

    def test_a_failure_of_the_engine_is_said_and_the_others_go_on(self):
        failing = engines.EngineError("HTTP 529: overloaded\nsecond line")
        results, _ask = self.run_collect([("Blagnac", "2026"), ("Aussonne", "1997")], {"Blagnac": [failing], "Aussonne": [GOOD]})
        self.assertEqual([r[2] for r in results], ["rejected", "saved"])
        self.assertEqual(results[0][3], "HTTP 529: overloaded")
        self.assertFalse(os.path.exists(os.path.join(self.folder, "rejected")))                       # no text to keep

    def test_an_answer_that_is_already_kept_is_not_asked_again(self):
        self.run_collect([("Aussonne", "1997")], {"Aussonne": [GOOD]})
        results, ask = self.run_collect([("Aussonne", "1997")], {"Aussonne": [GOOD]}, skip_existing=True)
        self.assertEqual(([r[2] for r in results], ask.calls), (["kept"], []))

    def test_there_is_a_pause_between_the_questions_and_not_after_the_last(self):
        pauses = []
        self.run_collect([("Blagnac", "2026"), ("Aussonne", "1997"), ("Paris", "2026")], {"Blagnac": [GOOD], "Aussonne": [GOOD], "Paris": [GOOD]},
                         pause=2.5, sleep=pauses.append)
        self.assertEqual(pauses, [2.5, 2.5])

    def test_the_summary_counts_and_names_what_was_rejected(self):
        results, _ask = self.run_collect([("Blagnac", "2026"), ("Aussonne", "1997")], {"Blagnac": ["No."], "Aussonne": [GOOD]})
        text = collect_answers.summary(results)
        self.assertIn("saved: 1   already kept: 0   rejected: 1", text)
        self.assertIn("rejected: Blagnac 2026", text)


class MainTests(unittest.TestCase):
    def run_main(self, argv, ask=None):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = collect_answers.main(argv, ask=ask or engines.ask)
        return code, buffer.getvalue()

    def test_an_engine_that_is_not_ready_is_said_with_the_way_to_fix_it(self):
        with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (False, ["no key"], "press the Key button")):
            code, out = self.run_main(["--check"])
            self.assertEqual(code, 2)
            self.assertIn("NOT ready: no key", out)
            self.assertIn("press the Key button", out)
            code, out = self.run_main(["--pause", "0"])                                              # a run does not start either
            self.assertEqual(code, 2)

    def test_check_says_ready_and_asks_nothing(self):
        def never(cfg, prompt):
            raise AssertionError("asked")
        with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (True, [], "")):
            code, out = self.run_main(["--check"], ask=never)
        self.assertEqual(code, 0)
        self.assertIn("ready", out)

    def test_an_engine_that_does_not_answer_by_itself_and_an_unknown_one_are_refused(self):
        self.assertEqual(self.run_main(["--engine", "manual", "--check"])[0], 2)
        self.assertEqual(self.run_main(["--engine", "nosuch", "--check"])[0], 2)

    def test_a_dry_run_prints_the_questions_and_asks_nothing(self):
        work = tempfile.mkdtemp()
        try:
            places = os.path.join(work, "p.txt")
            with open(places, "w", encoding="utf-8") as fh:
                fh.write("Blagnac | 2026\nAussonne | 1997\n")

            def never(cfg, prompt):
                raise AssertionError("asked")
            with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (False, ["no key"], "enter it")):         # no key is needed for it
                code, out = self.run_main(["--dry-run", "--places", places, "--language", "he"], ask=never)
            self.assertEqual(code, 0)
            self.assertIn("settlement Blagnac in 2026", out)
            self.assertIn("ISO code he", out)
            self.assertIn("2 questions would be asked", out)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_a_run_keeps_the_answers_and_the_code_says_whether_all_were_good(self):
        work = tempfile.mkdtemp()
        try:
            places = os.path.join(work, "p.txt")
            with open(places, "w", encoding="utf-8") as fh:
                fh.write("Blagnac | 2026\nAussonne | 1997\n")
            out_dir = os.path.join(work, "answers-table")
            ask = asking({"Blagnac": [GOOD], "Aussonne": [GOOD]})
            with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (True, [], "")):
                code, out = self.run_main(["--places", places, "--out", out_dir, "--pause", "0"], ask=ask)
            self.assertEqual(code, 0)
            self.assertEqual(sorted(f for f in os.listdir(out_dir) if f.endswith(".txt")), ["Aussonne_1997.txt", "Blagnac_2026.txt"])
            self.assertIn("saved: 2", out)
            ask = asking({"Blagnac": ["No."], "Aussonne": [GOOD]})
            with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (True, [], "")):
                code, _out = self.run_main(["--places", places, "--out", os.path.join(work, "second"), "--pause", "0"], ask=ask)
            self.assertEqual(code, 1)                                                                # one place was rejected
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_report_runs_the_replay_and_the_ablation_for_each_folder(self):
        work = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(work, "answers-old"))
            os.makedirs(os.path.join(work, "new"))
            runs = []
            with mock.patch.object(collect_answers, "WORK", work), mock.patch.object(collect_answers.subprocess, "run", lambda cmd, **kw: runs.append(cmd)):
                written = collect_answers.report(os.path.join(work, "new"), "snapshot.db")
            names = sorted(os.path.basename(w) for w in written)
            self.assertEqual(names, ["ablate-old.txt", "ablate-table.txt", "replay-old.txt", "replay-table.txt"])
            self.assertTrue(all(os.path.dirname(w) == os.path.join(work, "new", "reports") for w in written))            # not among the answers
            self.assertEqual(len(runs), 4)
            self.assertEqual(sum("--ablate" in cmd for cmd in runs), 2)                                # one ablation and one plain replay for each folder
            self.assertTrue(all("--db" in cmd and "snapshot.db" in cmd for cmd in runs))
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_a_report_needs_the_snapshot(self):
        work = tempfile.mkdtemp()
        try:
            places = os.path.join(work, "p.txt")
            with open(places, "w", encoding="utf-8") as fh:
                fh.write("Aussonne | 1997\n")
            with mock.patch.object(collect_answers.engines, "readiness", lambda cfg: (True, [], "")):
                code, out = self.run_main(["--places", places, "--out", os.path.join(work, "a"), "--pause", "0", "--report"], ask=asking({"Aussonne": [GOOD]}))
            self.assertEqual(code, 0)
            self.assertIn("--report needs --db", out)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
