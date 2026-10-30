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
"""Opening Google in AI mode with the question, and reading the copied answer."""
import argparse
import contextlib
import io
import os
import sys
import tempfile
import unittest
import urllib.parse

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"      # never the user's own file
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import cli, ingest, prompts                                           # noqa: E402
from test_ingest import SAMPLE, tree                                                      # noqa: E402


def answer_text():
    with open(SAMPLE, encoding="utf-8") as fh:
        return fh.read()


class PromptTests(unittest.TestCase):
    def test_the_two_variables_are_filled_everywhere(self):
        p = prompts.build_prompt("Bajmok", "1850")
        self.assertIn("Place: Bajmok. Date: 1850.", p)
        self.assertIn("Every container must be valid on 1850", p)
        self.assertNotIn("{place}", p + prompts.build_prompt("Bajmok", 1850, "short"))

    def test_the_link_opens_ai_mode_and_carries_the_whole_question(self):
        p = prompts.build_prompt("Bács-Bodrog", "1850")
        url = prompts.ai_mode_url(p)
        self.assertTrue(url.startswith("https://www.google.com/search?udm=50&q="))
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        self.assertEqual(query["udm"], ["50"])
        self.assertEqual(query["q"], [p])                          # nothing is lost in the encoding, not even the pipes and Hebrew-safe letters
        self.assertNotIn(" ", url)
        self.assertNotIn("\n", url)

    def test_the_template_insists_on_the_date_and_asks_whether_it_differs_from_today(self):
        p = prompts.build_prompt("Johnston, Iowa", "1995", "long")
        self.assertIn("must be those valid on 1995, not today's", p)
        self.assertIn("DIFFERS_FROM_TODAY:", p)

    def test_the_short_form_is_much_shorter(self):
        self.assertLess(len(prompts.build_prompt("Bajmok", "1850", "short")), len(prompts.build_prompt("Bajmok", "1850")) / 2)


class FlatteningTests(unittest.TestCase):
    def test_an_answer_whose_line_breaks_were_lost_is_read_the_same(self):
        original = ingest.parse_structured(answer_text())
        flat = ingest.parse_structured(" ".join(answer_text().split("\n")))
        for key in ("name", "language", "type_value", "coordinates", "containers", "state", "other_names", "sources", "not_sure"):
            self.assertEqual(flat[key], original[key], key)


class FlowTests(unittest.TestCase):
    def args(self, tmp, **kw):
        from test_agent_loop import write_db
        db = os.path.join(tmp, "t.db")
        write_db(tree(), db)
        base = dict(place="Bajmok", date="1850", db=db, short=False, skip="2", out=os.path.join(tmp, "plan.json"),
                    save_dir=os.path.join(tmp, "answers"), about_range=50)
        base.update(kw)
        return argparse.Namespace(**base)

    def run_flow(self, args, clipboard_text):
        opened = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.ai_complete(args, opener=lambda u: opened.append(u) or True, wait=lambda: None, read=lambda: clipboard_text)
        return code, buf.getvalue(), opened

    def test_the_browser_is_opened_in_ai_mode_and_the_copied_answer_becomes_the_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, opened = self.run_flow(self.args(tmp), answer_text())
            self.assertEqual(code, 0)
            self.assertEqual(len(opened), 1)
            self.assertIn("udm=50", opened[0])
            self.assertIn("GRAMPS WOULD DISPLAY: Bajmok, Zombori kerület", out)
            self.assertTrue(os.path.exists(os.path.join(tmp, "answers", "Bajmok_1850.txt")))      # the answer is kept
            self.assertTrue(os.path.exists(os.path.join(tmp, "plan.json")))

    def test_a_clipboard_without_an_answer_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_flow(self.args(tmp), "Bajmok is a village in Serbia with a long and interesting history.")
            self.assertEqual(code, 2)
            self.assertIn("does not hold an answer in the template", out)
            self.assertFalse(os.path.exists(os.path.join(tmp, "plan.json")))

    def test_an_empty_clipboard_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = self.run_flow(self.args(tmp), None)
            self.assertEqual(code, 2)
            self.assertIn("xclip, xsel or wl-paste", out)

    def test_search_ai_only_opens_the_link(self):
        opened = []
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.search_ai(argparse.Namespace(place="Hadad", date="1900", short=False, show=False, no_open=False),
                          opener=lambda u: opened.append(u) or True)
        self.assertEqual(len(opened), 1)
        self.assertIn("Place: Hadad. Date: 1900.", urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)["q"][0])


AMBIGUOUS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_ambiguous.txt")
JOHNSTON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_1950.txt")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class AmbiguityTests(unittest.TestCase):
    """Google loses the question when a candidate is clicked there, so the choice is made in the tool."""

    def args(self, tmp, **kw):
        from placecompleter.model import Tree
        from test_agent_loop import write_db
        from test_ingest import typed
        db = os.path.join(tmp, "t.db")
        write_db(Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, []), db)
        base = dict(place="Johnston", date="1996", db=db, short=False, skip="", hint="", out=os.path.join(tmp, "plan.json"),
                    save_dir=os.path.join(tmp, "answers"), about_range=50, no_packs=True)
        base.update(kw)
        return argparse.Namespace(**base)

    def run_flow(self, args, texts, choose):
        opened, queue, buf = [], iter(texts), io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.ai_complete(args, opener=lambda u: opened.append(u) or True, wait=lambda: None,
                                   read=lambda: next(queue), choose=choose)
        return code, buf.getvalue(), opened

    def query(self, url):
        return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]

    def test_the_candidates_of_an_ambiguous_answer_are_read(self):
        rec = ingest.parse_structured(read(AMBIGUOUS))
        self.assertEqual([(c["region"], c["coordinates"]) for c in rec["candidates"]],
                         [("Rhode Island", (41.8218, -71.5034)), ("Iowa", (41.673, -93.6977))])
        self.assertEqual(rec["candidates"][0]["name"], "Johnston")

    def test_the_tree_helps_to_choose(self):
        from placecompleter.model import Tree
        from test_ingest import typed
        hints = ingest.candidate_hints(Tree({"iowa": typed("iowa", "Iowa", 2)}, []), ingest.parse_structured(read(AMBIGUOUS))["candidates"])
        self.assertEqual([h["score"] for h in hints], [0, 2])
        self.assertIn("your tree has: Iowa", hints[1]["notes"][0])

    def test_the_choice_is_made_here_and_the_question_is_asked_again_with_the_place_described_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, opened = self.run_flow(self.args(tmp), [read(AMBIGUOUS), read(JOHNSTON)], lambda n: 2)
            self.assertEqual(code, 0)
            self.assertEqual(len(opened), 2)
            self.assertIn("Place: Johnston. Date: 1996.", self.query(opened[0]))
            self.assertIn("Place: Johnston, Iowa, United States (coordinates 41.673, -93.6977). Date: 1996.", self.query(opened[1]))
            self.assertIn("Which one do you mean?", out)
            self.assertIn("your tree has: Iowa", out)
            self.assertIn("PLACE 'Johnston' on 1996", out)
            self.assertTrue(os.path.exists(os.path.join(tmp, "answers", "Johnston_1996.txt")))

    def test_stopping_at_the_choice_asks_nothing_more(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, opened = self.run_flow(self.args(tmp), [read(AMBIGUOUS)], lambda n: 0)
            self.assertEqual((code, len(opened)), (0, 1))

    def test_a_hint_up_front_avoids_the_question(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, opened = self.run_flow(self.args(tmp, hint="Iowa"), [read(JOHNSTON)], lambda n: 1)
            self.assertEqual(len(opened), 1)
            self.assertIn("Place: Johnston, Iowa. Date: 1996.", self.query(opened[0]))

    def test_the_text_command_lists_the_candidates_numbered_for_a_second_try(self):
        from placecompleter.model import Tree
        from test_ingest import typed
        r = ingest.ingest(Tree({"iowa": typed("iowa", "Iowa", 2)}, []), ingest.parse_structured(read(AMBIGUOUS)), "1996")
        text = " | ".join(r["needs"])
        self.assertIn("1. Johnston, United States (Rhode Island)", text)
        self.assertIn("2. Johnston, United States (Iowa)", text)
        self.assertIn("<- your tree has: Iowa", text)


class SameAnswerTests(unittest.TestCase):
    def test_the_same_text_saved_for_another_date_is_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "Johnston_1950.txt"), "w", encoding="utf-8") as fh:
                fh.write(read(JOHNSTON))
            self.assertEqual(cli.same_answer_elsewhere(tmp, "Johnston", "1995", read(JOHNSTON)), ["1950"])
            self.assertEqual(cli.same_answer_elsewhere(tmp, "Johnston", "1995", read(JOHNSTON) + "\nsomething else"), [])
            self.assertEqual(cli.same_answer_elsewhere(tmp, "Johnston", "1950", read(JOHNSTON)), [])      # not itself

    def test_the_flow_warns_when_the_ai_gave_the_same_text_for_another_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = AmbiguityTests().args(tmp, date="1995", hint="Iowa")
            os.makedirs(args.save_dir)
            with open(os.path.join(args.save_dir, "Johnston_1950.txt"), "w", encoding="utf-8") as fh:
                fh.write(read(JOHNSTON))
            code, out, _ = AmbiguityTests().run_flow(args, [read(JOHNSTON)], lambda n: 1)
            self.assertIn("WARNING: this answer is IDENTICAL to the one saved for 1950", out)
            self.assertIn("GRAMPS WOULD DISPLAY: Johnston, Polk County", out.replace("Johnston, Polk County, Iowa, United States of America", "Johnston, Polk County"))


class FormsTests(unittest.TestCase):
    def test_the_first_template_is_kept_so_that_two_forms_can_be_compared(self):
        classic = prompts.build_prompt("Johnston, Iowa", "1995", "classic")
        newer = prompts.build_prompt("Johnston, Iowa", "1995", "long")
        self.assertNotIn("DIFFERS_FROM_TODAY", classic)
        self.assertNotIn("not today's", classic)
        self.assertIn("DIFFERS_FROM_TODAY", newer)
        self.assertEqual(prompts.build_prompt("X", "1900", "classic").splitlines()[0], "Administrative history lookup. Place: X. Date: 1900.")
        self.assertEqual(prompts.build_prompt("X", "1900"), prompts.build_prompt("X", "1900", "classic"))      # the default

    def test_the_dated_form_is_the_classic_one_plus_one_sentence(self):
        classic, dated = prompts.build_prompt("X", "1900", "classic"), prompts.build_prompt("X", "1900", "dated")
        self.assertIn("must be those valid on 1900, not today's", dated)
        self.assertNotIn("DIFFERS_FROM_TODAY", dated)
        self.assertEqual(dated.replace(" Name, type and containers must be those valid on 1900, not today's.", ""), classic)

    def test_a_classic_answer_is_read_like_any_other(self):
        rec = ingest.parse_structured(read(JOHNSTON))              # this answer has no DIFFERS_FROM_TODAY line
        self.assertIsNone(rec["differs_from_today"])
        self.assertEqual(rec["name"], "Johnston")

    def test_search_ai_takes_a_form_and_a_hint(self):
        opened, buf = [], io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.search_ai(argparse.Namespace(place="Johnston", date="1950", short=False, form="classic", hint="Iowa", show=False, no_open=False),
                          opener=lambda u: opened.append(u) or True)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)["q"][0]
        self.assertIn("Place: Johnston, Iowa. Date: 1950.", q)
        self.assertNotIn("DIFFERS_FROM_TODAY", q)
        self.assertIn("form classic", buf.getvalue())


NO_ANSWER_TEXT = "It seems: %s. Maybe: %s." % tuple(p for p in prompts.NO_ANSWER if not p.isascii())          # a service page in another language


class NoAnswerTests(unittest.TestCase):
    def run_flow(self, texts, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            args = AmbiguityTests().args(tmp, hint="Iowa", **kw)
            return AmbiguityTests().run_flow(args, texts, lambda n: 1)

    def test_the_message_is_recognised_in_hebrew_and_in_english(self):
        self.assertTrue(prompts.looks_like_no_answer(NO_ANSWER_TEXT))
        self.assertTrue(prompts.looks_like_no_answer("It seems there's no answer for this search. You can try asking something else."))
        self.assertFalse(prompts.looks_like_no_answer(read(JOHNSTON)))

    def test_the_next_form_of_the_question_is_tried_automatically(self):
        code, out, opened = self.run_flow([NO_ANSWER_TEXT, read(JOHNSTON)], form="auto")
        self.assertEqual(code, 0)
        self.assertEqual(len(opened), 2)
        first = urllib.parse.parse_qs(urllib.parse.urlparse(opened[0]).query)["q"][0]
        second = urllib.parse.parse_qs(urllib.parse.urlparse(opened[1]).query)["q"][0]
        self.assertEqual(first, prompts.build_prompt("Johnston, Iowa", "1996", prompts.AUTO_ORDER[0]))      # the first of the order: the table
        self.assertEqual(second, prompts.build_prompt("Johnston, Iowa", "1996", prompts.AUTO_ORDER[1]))
        self.assertIn("Google returned no search results for this query", out)
        self.assertIn("Trying the next form of the question (%s)" % prompts.AUTO_ORDER[1], out)

    def test_all_the_forms_failing_ends_with_advice_and_not_a_loop(self):
        code, out, opened = self.run_flow([NO_ANSWER_TEXT] * len(prompts.AUTO_ORDER), form="auto")
        self.assertEqual((code, len(opened)), (2, len(prompts.AUTO_ORDER)))
        self.assertIn("no other form is left", out)
        self.assertIn("--engine chatgpt", out)

    def test_a_single_form_asked_for_is_not_replaced(self):
        code, out, opened = self.run_flow([NO_ANSWER_TEXT], form="classic")
        self.assertEqual((code, len(opened)), (2, 1))

    def test_a_clipboard_that_is_not_an_answer_also_moves_on(self):
        code, out, opened = self.run_flow(["something copied by mistake", read(JOHNSTON)], form="auto")
        self.assertEqual((code, len(opened)), (0, 2))
        self.assertIn("does not hold an answer in the template", out)


class EngineTests(unittest.TestCase):
    def test_the_three_links(self):
        p = prompts.build_prompt("Johnston, Iowa", "1950")
        google, gpt, gem = (prompts.engine_url(e, p) for e in prompts.ENGINES)
        self.assertTrue(google.startswith("https://www.google.com/search?udm=50&q="))
        self.assertTrue(gpt.startswith("https://chatgpt.com/?hints=search&q="))
        self.assertTrue(gem.startswith("https://gemini.google.com/app?q="))
        for url in (google, gpt, gem):
            self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"], [p])

    def test_the_command_can_open_chatgpt_instead(self):
        opened = []
        with contextlib.redirect_stdout(io.StringIO()):
            cli.search_ai(argparse.Namespace(place="Johnston", date="1950", short=False, form="long", hint="Iowa", engine="chatgpt",
                                             show=False, no_open=False), opener=lambda u: opened.append(u) or True)
        self.assertTrue(opened[0].startswith("https://chatgpt.com/?hints=search&q="))


if __name__ == "__main__":
    unittest.main(verbosity=2)
