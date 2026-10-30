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
"""The model of the window, headless: asking, reading the answer, choosing, previewing, writing with one Undo."""
import os
import sys
import tempfile
import unittest
import urllib.parse

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"      # never the user's own file
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db.utils import make_database
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import Date, Event, EventType
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import prompts, session as sess                                       # noqa: E402
from placecompleter.model import Tree                                                      # noqa: E402
from test_ai_mode import AMBIGUOUS, JOHNSTON, NO_ANSWER_TEXT, read                         # noqa: E402
from test_engines import Recorder, claude_reply                                            # noqa: E402
from test_ingest import PACK, SAMPLE, SAMPLE_CLAUDE, WORLD, tree as bajmok_tree, typed     # noqa: E402

PACKS = [PACK, WORLD]


def iowa_tree():
    return Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])


class Base(unittest.TestCase):
    def make(self, tree=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return sess.Session(tree or iowa_tree(), tmp.name, pack_files=PACKS)


class AskingTests(Base):
    def test_a_missing_name_a_bad_date_and_an_unknown_engine_are_explained(self):
        s = self.make()
        self.assertEqual(s.begin("", "1950")["action"], "error")
        self.assertIn("place name", s.message)
        self.assertEqual(s.begin("Johnston", "last year")["action"], "error")
        self.assertIn("YYYY", s.message)
        self.assertEqual(s.begin("Johnston", "1950", engine="nobody")["action"], "error")
        self.assertIn("no engine called 'nobody'", s.message)

    def test_a_browser_engine_gives_the_link_with_the_whole_question(self):
        s = self.make()
        a = s.begin("Johnston", "1950", hint="Iowa", engine="google", form="classic")
        self.assertEqual((a["action"], s.state), ("open-url", "asked"))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(a["url"]).query)
        self.assertEqual(q["udm"], ["50"])
        self.assertIn("Place: Johnston, Iowa. Date: 1950.", q["q"][0])
        self.assertEqual(a["form"], "classic")                                  # the form Google answers

    def test_the_manual_and_the_api_engines_give_their_actions(self):
        from unittest import mock
        s = self.make()
        self.assertEqual(s.begin("Johnston", "1950", engine="manual")["action"], "copy-prompt")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-x"}):
            self.assertEqual(s.begin("Johnston", "1950", engine="anthropic")["action"], "call-api")

    def test_an_engine_that_cannot_work_yet_says_what_is_missing_and_how_to_fix_it(self):
        from unittest import mock
        s = self.make()
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            a = s.begin("Johnston", "1950", engine="openai")
            self.assertEqual(a["action"], "error")
            self.assertNotIn("no model name", s.message)                           # the model is found by itself once there is a key
            self.assertIn("no key", s.message)
            self.assertIn("ANTHROPIC_API_KEY", (s.begin("Johnston", "1950", engine="anthropic"), s.message)[1])

    def test_asking_ollama_when_it_is_not_running_says_what_to_do_in_steps(self):
        from unittest import mock
        from placecompleter import engines as enginelib
        s = self.make()
        with mock.patch.object(enginelib, "_listening", lambda host, port, timeout=0.5: False):
            a = s.begin("Johnston", "1950", engine="ollama")
        self.assertEqual(a["action"], "error")
        self.assertIn("no response from host localhost:11434", s.message)
        self.assertIn("1) Install from ollama.com", s.message)
        self.assertIn("ollama pull llama3.2", s.message)
        self.assertEqual(a.get("needs_setup"), "ollama")                                        # the window offers to set it up
        self.assertNotIn("engines.json", s.message)

    def test_ollama_that_answers_but_has_no_model_asks_the_window_to_offer_the_download(self):
        from unittest import mock
        from placecompleter import engines as enginelib
        s = self.make()
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")}), \
                mock.patch.object(enginelib, "_listening", lambda host, port, timeout=0.5: True):
            self.assertEqual(s.begin("Johnston", "1950", engine="ollama")["action"], "call-api")
            result = s.run_api(http=lambda *a, **k: {}, http_get=lambda url, headers, timeout=20: {"data": []})
        self.assertEqual(result["action"], "error")
        self.assertEqual(result.get("needs_setup"), "ollama")
        self.assertIn("no models installed", result["message"])

    def test_an_engine_that_is_not_ollama_never_asks_for_this(self):
        from unittest import mock
        from placecompleter import engines as enginelib
        s = self.make()
        with mock.patch.object(enginelib, "_listening", lambda host, port, timeout=0.5: False):
            a = s.begin("Johnston", "1950", engine="openai")
        self.assertNotIn("needs_setup", a)

    def test_a_level_that_the_tree_holds_under_another_name_is_asked_about_and_then_used(self):
        from test_engine import EMPTY
        t = Tree({"lt": typed("lt", "Lithuania", 1, lang="en"), "kc": typed("kc", "Kaunas County", 3, lang="en"), "k": typed("k", "Kaunas", 4, lang="en")}, [])
        t.places["kc"]["refs"] = [{"ref": "lt", "date": EMPTY}]
        t.places["k"]["refs"] = [{"ref": "kc", "date": EMPTY}]
        s = self.make(t)
        s.begin("Kaunas", "1995", engine="manual")
        s.receive("PLACE_NAME_ON_DATE: Kaunas\nLANGUAGE: lt\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Kauno apskritis | county | 1950-present | Lietuvos Respublika\n"
                  "2 | Lietuvos Respublika | state | 1990-present |\nSTATE_ON_DATE: Lietuvos Respublika | 1990-present\n"
                  "SOURCES: https://lt.wikipedia.org/wiki/Kaunas | PLACE_NAME_ON_DATE\n")
        first = s.ambiguous_units()
        self.assertEqual([(u["slot"], u["name"]) for u in first], [("c1", "Kauno apskritis")])
        self.assertIn("Is it the same place?", first[0]["why"])
        s.choose_unit("c1", "kc")
        self.assertEqual([(u["slot"], u["name"]) for u in s.ambiguous_units()], [("c2", "Lietuvos Respublika")])
        s.choose_unit("c2", "lt")
        self.assertEqual(s.ambiguous_units(), [])
        kinds = sorted(p["kind"] for p in s.plan["proposals"])
        self.assertNotIn("add-place", kinds)
        self.assertEqual(kinds.count("add-name"), 2)                                              # the two names are offered as names of the places
        titles = [c["title"] for c in s.changes()]
        self.assertTrue(any("Lietuvos Respublika" in t_ and "Lithuania" in t_ for t_ in titles), titles)

    def test_gemini_asks_the_window_to_copy_the_question_and_says_to_paste_it(self):
        s = self.make()
        a = s.begin("Johnston", "1950", engine="gemini")
        self.assertEqual((a["action"], a["url"], a["copy"]), ("open-url", "https://gemini.google.com/app", True))
        self.assertIn("Johnston", a["prompt"])
        self.assertIn("copied and Gemini", s.message)
        self.assertIn("Paste query (Ctrl+V)", s.message)

    def test_the_other_browser_engines_carry_the_question_in_the_address_and_do_not_copy(self):
        s = self.make()
        for engine in ("google", "chatgpt"):
            a = s.begin("Johnston", "1950", engine=engine)
            self.assertEqual(a["action"], "open-url")
            self.assertNotIn("copy", a)
            self.assertIn("q=", a["url"])

    def test_the_list_for_the_window_puts_the_engines_that_can_work_first_and_marks_the_rest(self):
        from unittest import mock
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        with mock.patch.dict(os.environ, env, clear=True):
            options = self.make().engine_options()
        ids = [o["id"] for o in options]
        self.assertEqual(ids[:4], ["google", "manual", "chatgpt", "gemini"])                   # they need nothing
        ready = [o["ready"] for o in options]
        self.assertEqual(ready, sorted(ready, reverse=True))                                   # all those that can work come before the others
        self.assertFalse(next(o for o in options if o["id"] == "openai")["ready"])
        openai = next(o for o in options if o["id"] == "openai")
        self.assertIn("use the Key button", openai["fix"])
        self.assertEqual(openai["lacks"], [])                                                  # the model is not one of the things to do by hand

    def test_the_engine_list_has_a_label_a_kind_and_the_key_state(self):
        rows = {r[0]: r for r in self.make().engine_choices()}
        self.assertEqual(rows["google"][2], "browser")
        self.assertEqual(rows["manual"][3], "no key required")
        self.assertIn("key in $ANTHROPIC_API_KEY", rows["anthropic"][3])


class ReadingTests(Base):
    def ready(self, text, place="Johnston", date="1950", **kw):
        s = self.make(kw.pop("tree", None))
        s.begin(place, date, engine="manual")
        self.assertEqual(s.receive(text)["action"], "ready")
        return s

    def test_an_answer_becomes_the_control_screen_with_nothing_checked(self):
        s = self.ready(read(JOHNSTON), date="1995")
        self.assertEqual(s.state, "ready")
        rows = s.rows()
        self.assertTrue(rows)
        self.assertFalse([r for r in rows if r["selected"]])                    # every proposal is an assumption: you decide
        self.assertTrue(all(r["basis"] == "assumption" for r in rows))
        self.assertEqual(s.selected_proposals(), [])

    def test_the_answer_is_kept_with_who_answered(self):
        s = self.ready(read(JOHNSTON), date="1995")
        self.assertTrue(os.path.exists(s.saved_path))
        self.assertTrue(os.path.exists(s.saved_path[:-4] + ".meta.json"))
        self.assertEqual((s.meta["engine"], s.meta["kind"], s.meta["form"]), ("manual", "manual", prompts.AUTO_ORDER[0]))

    def test_no_answer_moves_to_the_next_form_and_in_the_end_fails(self):
        s = self.make()
        s.begin("Johnston", "1950", engine="google")
        a = s.receive(NO_ANSWER_TEXT)
        self.assertEqual(a["action"], "retry")
        self.assertEqual(a["next"]["form"], prompts.AUTO_ORDER[1])
        self.assertIn("no search results for this query", a["reason"])
        for _ in range(len(prompts.AUTO_ORDER) - 2):
            a = s.receive(NO_ANSWER_TEXT)
            self.assertEqual(a["action"], "retry")
        self.assertEqual(s.receive(NO_ANSWER_TEXT)["action"], "error")
        self.assertIn("all prompt fallback formats exhausted", s.message)

    def test_a_text_that_is_not_an_answer_is_explained(self):
        s = self.make()
        s.begin("Johnston", "1950", engine="google", form="classic")
        self.assertEqual(s.receive("something copied by mistake")["action"], "error")
        self.assertIn("does not conform to expected response template", s.message)
        self.assertEqual(s.receive("   ")["action"], "error")

    def test_an_ambiguous_name_is_chosen_here_and_asked_again_with_the_place_described_exactly(self):
        s = self.make()
        s.begin("Johnston", "1996", engine="google", form="classic")
        a = s.receive(read(AMBIGUOUS))
        self.assertEqual((a["action"], s.state), ("ambiguous", "ambiguous"))
        self.assertEqual(a["best"], 1)                                          # the one whose state the tree has: Iowa
        self.assertIn("your tree has: Iowa", a["candidates"][1]["notes"][0])
        again = s.choose_candidate(1)
        self.assertEqual(again["action"], "open-url")
        self.assertIn("Place: Johnston, Iowa, United States (coordinates 41.673, -93.6977). Date: 1996.",
                      urllib.parse.parse_qs(urllib.parse.urlparse(again["url"]).query)["q"][0])

    def test_the_api_engine_asks_by_itself_and_the_model_is_written_down(self):
        s = self.make()
        import os as _os
        from unittest import mock
        with mock.patch.dict(_os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-x"}):
            self.assertEqual(s.begin("Johnston", "1995", hint="Iowa", engine="anthropic")["action"], "call-api")
            self.assertEqual(s.run_api(http=Recorder(claude_reply(read(JOHNSTON), model="claude-sonnet-5-5-20261001")))["action"], "ready")
        self.assertEqual(s.meta["model"], "claude-sonnet-5-5-20261001")

    def test_an_api_that_fails_ends_with_its_message(self):
        from unittest import mock
        from placecompleter import engines as enginelib

        def refuse(url, headers, body, timeout=120):
            raise enginelib.EngineError("the service answered HTTP 529: overloaded")
        s = self.make()
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-api03-x"}):
            s.begin("Johnston", "1995", engine="anthropic")
            a = s.run_api(http=refuse)
        self.assertEqual(a["action"], "error")
        self.assertIn("HTTP 529", s.message)

    def test_the_same_text_for_another_date_is_a_warning(self):
        s = self.make()
        s.begin("Johnston", "1950", engine="manual")
        s.receive(read(JOHNSTON))
        s.begin("Johnston", "1995", engine="manual")
        s.receive(read(JOHNSTON))
        texts = [t for t, level in s.needs() if "IDENTICAL" in t]
        self.assertEqual(len(texts), 1)
        self.assertIn("1950", texts[0])

class ChoosingTests(Base):
    def johnston(self, date="1950"):
        s = self.make()
        s.begin("Johnston", date, engine="manual")
        s.receive(open(SAMPLE_CLAUDE, encoding="utf-8").read())
        return s

    def test_a_new_place_and_its_links_are_one_choice(self):
        s = self.johnston()
        place = next(r for r in s.rows() if r["kind"] == "add-place" and "Johnston" in r["text"])
        s.toggle(place["id"])
        checked = [r for r in s.rows() if r["selected"]]
        self.assertGreater(len(checked), 1)
        self.assertEqual({r["bundle"] for r in checked}, {place["bundle"]})
        s.toggle(place["id"])
        self.assertEqual([r for r in s.rows() if r["selected"]], [])

    def test_the_preview_follows_what_is_checked(self):
        s = self.johnston("1950")
        before, _ = s.preview()
        s.select_all()
        after, end = s.preview()
        self.assertNotEqual(before, after)
        self.assertEqual(after, "Johnston, Webster Township, Polk County, Iowa, USA")
        self.assertEqual(end, "top")
        s.clear_selection()
        self.assertEqual(s.preview()[0], before)

    def test_the_same_answer_gives_the_other_name_in_another_year(self):
        s = self.johnston("1995")
        s.select_all()
        self.assertEqual(s.preview()[0], "Johnston, Webster Township, Polk County, Iowa, USA")

    def test_the_descriptions_are_plain_words(self):
        s = self.johnston()
        text = "\n".join(r["text"] for r in s.rows())
        self.assertIn("Create place «Johnston» (Locality, coordinates 41.69111, -93.72361)", text)
        self.assertIn("Create place «Webster Township»", text)
        self.assertIn("Enclose «Webster Township» (new) inside «Polk County» (new)", text)
        self.assertIn("Enclose «Polk County» (new) inside «Iowa [IOWA]»", text)

    def test_a_level_can_be_left_out_and_the_chain_follows(self):
        s = self.make(bajmok_tree())
        s.begin("Bajmok", "1850", engine="manual")
        s.receive(open(SAMPLE, encoding="utf-8").read())
        self.assertEqual([lv["used"] for lv in s.levels], [True, True, True])
        s.set_level_used(2, False)                                              # the doubtful Batsch-Bodrog
        s.select_all(include_conflicts=True)
        self.assertEqual(s.preview()[0], "Bajmok, Zombori kerület, Szerb Vajdaság és Temesi Bánság, Kaisertum Österreich")

    def test_changes_to_existing_data_are_not_checked_by_select_all(self):
        s = self.make(bajmok_tree())
        s.begin("Bajmok", "1850", engine="manual")
        s.receive(open(SAMPLE, encoding="utf-8").read())
        s.set_level_used(2, False)
        s.select_all()
        self.assertFalse([p for p in s.plan["proposals"] if p.get("existing") and p["id"] in s.selected])
        self.assertTrue(s.rows() and any(r["selected"] for r in s.rows()))

    def test_applying_with_nothing_checked_is_refused(self):
        s = self.johnston()
        with self.assertRaises(ValueError):
            s.apply(None)


class ChoiceTests(Base):
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | United States of America | country | 1776-present | United States\n")

    def two_usa(self):
        from test_engine import EMPTY
        t = Tree({"usa": typed("usa", "USA", 1, lang="en"), "usa2": typed("usa2", "United States of America", 1, lang="en"),
                  "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["city"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        return self.make(t)

    def test_the_session_reports_the_units_that_need_a_choice(self):
        s = self.two_usa()
        s.begin("Johnston", "1995", engine="manual")
        s.receive(self.ANSWER)
        (amb,) = s.ambiguous_units()
        self.assertEqual((amb["slot"], {c["handle"] for c in amb["candidates"]}), ("c2", {"usa", "usa2"}))

    def test_choosing_analyses_again_with_the_choice_and_it_is_remembered(self):
        s = self.two_usa()
        s.begin("Johnston", "1995", engine="manual")
        s.receive(self.ANSWER)
        action = s.choose_unit("c2", "usa2")
        self.assertEqual(action, {"action": "ready"})
        self.assertEqual(s.ambiguous_units(), [])
        s.set_level_used(0, False)                                                      # a later analysis keeps the choice
        self.assertEqual(s.choices, {"c2": "usa2"})
        self.assertEqual(s.ambiguous_units(), [])

    def test_a_new_session_starts_without_choices(self):
        self.assertEqual(self.two_usa().choices, {})


class ChangesTests(Base):
    """The proposals as the CHOICES they are: what goes together has one box, what stands alone has its own."""
    def iowa_city_tree(self):
        from test_engine import EMPTY
        t = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1), "city": typed("city", "City of Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        return t

    def inserted(self):
        s = self.make(self.iowa_city_tree())
        s.begin("City of Johnston", "1995", engine="manual")
        s.receive("PLACE_NAME_ON_DATE: City of Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk | county | 1846-present | Iowa\n"
                  "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        return s

    def test_a_level_put_in_between_is_one_change_with_four_steps_and_the_reason(self):
        s = self.inserted()
        (change,) = [c for c in s.changes() if c["title"].startswith("Insert")]
        self.assertEqual(change["title"], "Insert «Polk County» (new) between «City of Johnston [CITY]» and «Iowa [IOWA]»")
        self.assertEqual([st["text"] for st in change["steps"]][0], "Create place «Polk County» (County); primary name: from 1846")
        self.assertEqual(len(change["steps"]), 3)                                       # the place and its two links; nothing of the old link is cut
        self.assertIn("new link placed before the existing link", change["why"])
        self.assertIn("the existing link is retained for the remaining years", change["why"])
        self.assertIn("target place entity must exist prior to hierarchy linking", change["why"])
        self.assertEqual((change["flag"], change["selected"]), ("inserts intermediate level", False))

    def test_the_steps_of_such_a_change_are_not_worth_anything_alone_so_there_is_one_box(self):
        s = self.inserted()
        change = next(c for c in s.changes() if c["title"].startswith("Insert"))
        s.toggle(change["steps"][0]["id"])                                            # any step of the change ...
        self.assertEqual(len(s.selected), 3)                                           # ... checks all three
        self.assertEqual(s.preview()[0], "City of Johnston, Polk County, Iowa, USA")
        s.toggle_change(change["id"])
        self.assertEqual(s.selected, set())
        self.assertEqual(s.preview()[0], "City of Johnston, Iowa, USA")                # unchanged: nothing was written

    def test_things_that_stand_alone_are_separate_choices(self):
        s = self.make()
        s.begin("Johnston", "1995", engine="manual")
        s.receive(open(SAMPLE_CLAUDE, encoding="utf-8").read())
        changes = s.changes()
        names = [c for c in changes if c["title"].startswith(("Set language tag for name", "Assign date period to name"))]
        self.assertGreaterEqual(len(names), 4)                                         # each name of a level that is given a language or a period is its own choice
        self.assertTrue(all(len(c["steps"]) == 1 and c["why"] == "" for c in names))
        made = next(c for c in changes if c["title"].startswith("Create place «Johnston»"))
        self.assertGreater(len(made["steps"]), 3)
        self.assertEqual(made["title"], "Create place «Johnston» and place it in the hierarchy")
        self.assertIn("target place entity must exist prior to hierarchy linking", made["why"])
        s.toggle_change(names[0]["id"])                                                # one name is chosen without the rest
        self.assertEqual([c["selected"] for c in s.changes() if c["id"] == names[0]["id"]], [True])
        self.assertEqual(sum(c["selected"] for c in s.changes()), 1)

    def iowa_twice(self):
        from test_engine import EMPTY
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en", alts=[("Iowa", "en", EMPTY), ("Hawkeye State", "en", EMPTY), ("IA", "en", EMPTY)]),
                  "usa": typed("usa", "USA", 1, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        s = self.make(t)
        s.begin("Johnston", "1995", engine="manual")
        s.receive("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk County | county | 1846-present | Iowa\n"
                  "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        return s

    def periods_of_iowa(self, s):
        return [c for c in s.changes() if "Assign date period to name «Iowa»" in c["title"]]

    def test_the_same_name_twice_in_a_place_is_one_choice_not_one_per_copy(self):
        s = self.iowa_twice()
        (change,) = self.periods_of_iowa(s)                                            # not three: Hawkeye State and IA are not Iowa
        self.assertEqual(len(change["steps"]), 2)
        self.assertIn("«Iowa» (primary name, language: en) of «Iowa [IOWA]»: from 1846", change["title"])
        self.assertIn("name occurs 2 times in this place; period assigned to all occurrences", change["title"])
        self.assertEqual((change["why"], change["show_steps"]), ("", False))           # the two steps would only repeat the title

    def iowa_in_languages(self):
        """The state has the same name in many languages (as the user's Iowa has): one name each, none with a period."""
        from test_engine import EMPTY
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="", alts=[("Iowa", l, EMPTY) for l in ("en", "de", "fr", "hu", "es")]),
                  "usa": typed("usa", "USA", 1, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        s = self.make(t)
        s.begin("Johnston", "1995", engine="manual")
        s.receive("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk County | county | 1846-present | Iowa\n"
                  "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        return s

    def test_the_same_name_in_several_languages_is_dated_only_in_the_language_of_the_answer(self):
        """It showed six rows with the same sentence (the name in six languages): the answer is in English, so only the English name and the
        name that has no language get its period."""
        s = self.iowa_in_languages()
        rows = self.periods_of_iowa(s)
        self.assertEqual(len(rows), 2)

    def test_every_row_says_which_name_it_is_about(self):
        rows = self.periods_of_iowa(self.iowa_in_languages())
        self.assertEqual(len({r["title"] for r in rows}), len(rows))                              # no two rows read the same
        titles = " | ".join(r["title"] for r in rows)
        self.assertIn("(primary name, unspecified language)", titles)
        self.assertIn("(alternative name #1, language: en)", titles)

    def test_the_rows_that_set_a_language_say_which_name_too(self):
        from test_engine import EMPTY
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="", alts=[("Iowa", "", EMPTY), ("Iowa", "", EMPTY)]),
                  "usa": typed("usa", "USA", 1, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        s = self.make(t)
        s.begin("Johnston", "1995", engine="manual")
        s.receive("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk County | county | 1846-present | Iowa\n"
                  "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        languages = [c["title"] for c in s.changes() if c["title"].startswith("Set language tag for name «Iowa»")]
        self.assertEqual(len(languages), 3)
        self.assertEqual(len(set(languages)), 3)                                                   # primary, no. 1 and no. 2: all different
        self.assertTrue(any("(primary name)" in t for t in languages))
        self.assertTrue(any("(alternative name #2)" in t for t in languages))

    def test_one_box_checks_and_unchecks_all_the_copies_of_the_name(self):
        s = self.iowa_twice()
        (change,) = self.periods_of_iowa(s)
        ids = {st["id"] for st in change["steps"]}
        s.clear_selection()
        s.toggle_change(change["id"])
        self.assertTrue(ids <= s.selected)
        self.assertEqual([p["index"] for p in s.selected_proposals() if p["kind"] == "set-name-date" and p["place"] == "iowa"], [0, 1])
        s.toggle_change(change["id"])
        self.assertFalse(ids & s.selected)

    def test_a_change_of_a_single_step_shows_it_as_it_is(self):
        s = self.make()
        s.begin("Johnston", "1995", engine="manual")
        s.receive(open(SAMPLE_CLAUDE, encoding="utf-8").read())
        single = [c for c in s.changes() if len(c["steps"]) == 1]
        self.assertTrue(single)
        self.assertTrue(all(c["show_steps"] for c in single))                          # (the window leaves out one that repeats its title)

    def test_a_different_parent_is_added_and_nothing_that_exists_is_changed(self):
        s = self.make(bajmok_tree())
        s.begin("Bajmok", "1850", engine="manual")
        s.receive(open(SAMPLE, encoding="utf-8").read())                                 # all three levels, the doubtful one included
        flags = {c["flag"] for c in s.changes()}
        self.assertNotIn("CONFLICT", flags)
        s.select_all()
        self.assertFalse([c for c in s.changes() if c["existing"] and c["selected"]])                    # a change to what exists is never chosen by itself
        self.assertTrue(all(c["selected"] for c in s.changes() if not c["existing"]))                    # every addition is chosen by itself

    def test_every_proposal_belongs_to_exactly_one_change(self):
        s = self.inserted()
        ids = [st["id"] for c in s.changes() for st in c["steps"]]
        self.assertEqual(sorted(ids), sorted(p["id"] for p in s.plan["proposals"]))
        self.assertEqual(len(ids), len(set(ids)))

    def test_with_no_answer_there_are_no_changes_and_an_unknown_change_is_ignored(self):
        s = self.make()
        self.assertEqual(s.changes(), [])
        s2 = self.inserted()
        s2.toggle_change(99)
        self.assertEqual(s2.selected, set())


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class GrampsTests(Base):
    """The window's tree comes from the open database, and what it writes is one Undo."""
    def build(self, tree):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(tree, path)
        return path

    def test_the_tree_read_from_the_database_is_the_tree_read_from_the_file(self):
        path = self.build(bajmok_tree())
        from_file = Tree.from_sqlite(os.path.join(path, "sqlite.db"))
        db = make_database("sqlite")
        db.load(path)
        try:
            from_db = Tree.from_db(db)
        finally:
            db.close()
        self.assertEqual(from_db.places, from_file.places)
        self.assertEqual(from_db.events, from_file.events)

    def test_the_whole_way_from_the_answer_to_one_undo(self):
        path = self.build(bajmok_tree())
        db = make_database("sqlite")
        db.load(path)
        try:
            before = Tree.from_db(db)
            s = sess.Session(before, tempfile.mkdtemp(), pack_files=PACKS)
            s.begin("Bajmok", "1850", engine="manual")
            s.receive(open(SAMPLE, encoding="utf-8").read())
            s.set_level_used(2, False)
            s.select_all(include_conflicts=True)
            dry = s.check(db)
            self.assertEqual({r["status"] for r in dry}, {"dry-run"})
            results = s.apply(db)
            self.assertEqual({r["status"] for r in results}, {"applied"})
            self.assertEqual(s.state, "applied")
            self.assertIn("Edit > Undo", s.message)
            # Gramps itself shows what the preview promised
            baj = next(h for h, p in before.places.items() if p["name"]["value"] == "Bajmok")
            with __import__("gramps.gen.db", fromlist=["DbTxn"]).DbTxn("probe", db) as txn:
                ev = Event()
                ev.set_type(EventType.RESIDENCE)
                ev.set_place_handle(baj)
                d = Date()
                d.set_yr_mon_day(1850, 5, 1)
                ev.set_date_object(d)
                db.add_event(ev, txn)
            self.assertEqual(place_displayer.display_event(db, ev), "Bajmok, Zombori kerület, Szerb Vajdaság és Temesi Bánság, Kaisertum Österreich")
            db.undo()                                                           # the probe event
            after = Tree.from_db(db)
            self.assertNotEqual(after.places, before.places)
            s.refresh(after)
            db.undo()                                                           # the PlaceCompleter transaction: all of it
            self.assertEqual(Tree.from_db(db).places, before.places)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
