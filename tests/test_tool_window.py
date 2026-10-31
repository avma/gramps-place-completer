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
"""The window file, run against stand-ins for GTK and the Gramps GUI: it cannot be drawn here, but every handler can be
called, so a wrong name, a wrong step or a forgotten update shows up here and not on the user's screen."""
import importlib.util
from inspect import isfunction
import os
import re
import sys
import tempfile
import time
import types
import unittest
import urllib.parse
from unittest import mock

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db.utils import make_database
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter.model import Tree                                                       # noqa: E402
from test_ai_mode import AMBIGUOUS, JOHNSTON, NO_ANSWER_TEXT, read                          # noqa: E402
from test_engines import claude_reply                                                       # noqa: E402
from test_ingest import SAMPLE, SAMPLE_CLAUDE, tree as bajmok_tree, typed                   # noqa: E402
from test_keystore import SECRET, MemoryStore                                               # noqa: E402
from placecompleter import geo as _geo_module                                                # noqa: E402
REAL_LOOKUP_MANY = _geo_module.lookup_many                                                   # the real one, before any test replaces it
from placecompleter import keystore                                                          # noqa: E402


class FakeRow(list):
    pass


class FakeNode(list):
    def __init__(self, row):
        super().__init__(row)
        self.children = []


class FakeTreeStore:
    """The TreeStore of GTK as far as the window uses it: top-level rows with children, indexed by a path like "0" or "0:2"."""
    def __init__(self, *types_):
        self.rows = []

    def append(self, parent, row):
        node = FakeNode(row)
        (self.rows if parent is None else parent.children).append(node)
        return node

    def clear(self):
        self.rows = []

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, path):
        parts = str(path).split(":")
        node = self.rows[int(parts[0])]
        for part in parts[1:]:
            node = node.children[int(part)]
        return node

    def __len__(self):
        return len(self.rows)


class FakeStore:
    def __init__(self, *types_):
        self.rows = []

    def append(self, row):
        self.rows.append(FakeRow(row))

    def clear(self):
        self.rows = []

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, path):
        return self.rows[int(path)]

    def __len__(self):
        return len(self.rows)


WIDGETS = ("Dialog", "Grid", "Entry", "ComboBoxText", "Button", "Label", "Frame", "TextView", "ScrolledWindow", "Box", "TreeView",
           "TreeViewColumn", "CellRendererToggle", "CellRendererText", "MessageDialog", "CheckButton")


def make_modules(log):
    gtk = mock.MagicMock(name="Gtk")
    for name in WIDGETS:
        getattr(gtk, name).side_effect = lambda *a, **k: mock.MagicMock()
    gtk.ListStore = FakeStore
    gtk.TreeStore = FakeTreeStore
    glib = mock.MagicMock(name="GLib")
    glib.idle_add = lambda fn, *a: fn(*a)                                   # no main loop: run at once
    repo = types.ModuleType("gi.repository")
    repo.Gtk, repo.GLib, repo.Gdk, repo.Pango = gtk, glib, mock.MagicMock(name="Gdk"), mock.MagicMock(name="Pango")
    gi = types.ModuleType("gi")
    gi.repository = repo

    class Tool:
        def __init__(self, dbstate, options_class, name):
            self.db = dbstate.db

    class ToolOptions:
        pass

    class ManagedWindow:
        def __init__(self, uistate, track, obj):
            self.uistate, self.closed = uistate, False

        def set_window(self, window, title, text, *a, **k):
            self.window = window

        def setup_configs(self, *a, **k):
            pass

        def show(self):
            log["shown"] = True

        def close(self, *a):
            self.closed = True

    class ErrorDialog:
        def __init__(self, msg1, msg2="", parent=None):
            log.setdefault("errors", []).append((msg1, msg2))

    plug = types.ModuleType("gramps.gui.plug")
    plug.tool = types.ModuleType("gramps.gui.plug.tool")
    plug.tool.Tool, plug.tool.ToolOptions = Tool, ToolOptions
    mw = types.ModuleType("gramps.gui.managedwindow")
    mw.ManagedWindow = ManagedWindow
    dlg = types.ModuleType("gramps.gui.dialog")
    dlg.ErrorDialog = ErrorDialog
    gui = types.ModuleType("gramps.gui")
    gui.plug, gui.managedwindow, gui.dialog = plug, mw, dlg
    return {"gi": gi, "gi.repository": repo, "gramps.gui": gui, "gramps.gui.plug": plug, "gramps.gui.plug.tool": plug.tool,
            "gramps.gui.managedwindow": mw, "gramps.gui.dialog": dlg}, gtk


class SyncThread:
    """A thread that runs at once, in the test's own thread."""
    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class Base(unittest.TestCase):
    def setUp(self):
        self.log = {}
        modules, self.gtk = make_modules(self.log)
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        spec = importlib.util.spec_from_file_location("placecompleter_tool_under_test", os.path.join(ROOT, "placecompleter_tool.py"))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.mod.WORK, self.mod.PREFS = tmp.name, os.path.join(tmp.name, "window.json")
        self.mod.WIKIDATA_CACHE = os.path.join(tmp.name, "wikidata.json")                # never the real cache ...
        self.asked_wikidata = []
        self.patch_lookup(lambda client, targets, articles=(): self.asked_wikidata.append(targets) or {})              # ... and never the network
        self.mod.threading.Thread = SyncThread
        self.opened = []
        self.mod.webbrowser = types.SimpleNamespace(open=lambda url: self.opened.append(url) or True)
        self.tree = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])
        test = self
        self.mod.Tree = type("TreeInTest", (Tree,), {"from_db": classmethod(lambda cls, db: test.tree)})      # the tree the test chose
        self.dbstate = types.SimpleNamespace(db=mock.MagicMock())
        self.tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter")
        self.clip = self.gtk.Clipboard.get.return_value
        self.tool.c_wikidata.get_active.return_value = False                              # off, but in the tests that are about it

    def patch_lookup(self, function):
        """Replace geo.lookup_many (a module the whole test run shares) for this test only."""
        patcher = mock.patch.object(_geo_module, "lookup_many", function)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fill(self, place="Johnston", date="1950", hint="", engine="manual", form="auto"):
        self.tool.e_place.get_text.return_value = place
        self.tool.e_date.get_text.return_value = date
        self.tool.e_hint.get_text.return_value = hint
        self.tool.c_engine.get_active_id.return_value = engine
        self.tool.c_form.get_active_id.return_value = form

    def answer(self, text):
        self.tool.tv_answer.get_buffer.return_value.get_text.return_value = text


class WindowTests(Base):
    def test_the_window_is_built_shown_and_lists_the_engines(self):
        self.assertTrue(self.log["shown"])
        ids = [c.args[0] for c in self.tool.c_engine.append.call_args_list]
        self.assertTrue({"google", "manual", "anthropic", "chatgpt"} <= set(ids))
        self.assertEqual([c.args[0] for c in self.tool.c_form.append.call_args_list], list(self.mod.FORMS))

    def test_the_engine_and_the_question_are_chosen_by_position_and_those_that_work_come_first(self):
        ids = [c.args[0] for c in self.tool.c_engine.append.call_args_list]
        labels = [c.args[1] for c in self.tool.c_engine.append.call_args_list]
        self.tool.c_engine.set_active.assert_called_with(ids.index("google"))                 # nothing remembered: Google AI mode
        self.tool.c_form.set_active.assert_called_with(0)                                     # "auto"
        self.assertTrue(labels[0].startswith("✓ Google AI mode"))
        self.assertTrue(any(label.startswith("✗ requires configuration:") for label in labels))

    def test_what_was_chosen_last_time_is_chosen_again(self):
        import json as _json
        with open(self.mod.PREFS, "w", encoding="utf-8") as fh:
            _json.dump({"engine": "manual", "form": "short", "hint": "Iowa"}, fh)
        self.tool._build()
        ids = [c.args[0] for c in self.tool.c_engine.append.call_args_list][-len(self.mod.pcsession.Session(Tree({}, []), self.mod.WORK).engine_options()):]
        self.tool.c_engine.set_active.assert_called_with(ids.index("manual"))
        self.tool.c_form.set_active.assert_called_with(list(self.mod.FORMS).index("short"))

    def test_the_hint_field_starts_empty_with_grey_placeholder_text_even_if_an_old_file_has_a_hint(self):
        import json as _json
        with open(self.mod.PREFS, "w", encoding="utf-8") as fh:
            _json.dump({"engine": "google", "form": "auto", "hint": "Iowa"}, fh)          # what an older version wrote
        self.tool.e_hint.set_text.reset_mock()
        self.tool._build()
        self.tool.e_hint.set_text.assert_not_called()                                    # nothing is put into the field
        self.tool.e_hint.set_placeholder_text.assert_called()

    def test_a_hint_typed_for_one_place_is_cleared_when_another_place_is_typed(self):
        self.tool.e_place.get_text.return_value = "Johnston"
        self.tool.e_hint.get_text.return_value = "Iowa"
        self.tool._on_hint_changed()
        self.tool.e_place.get_text.return_value = "Bajmok"
        self.tool._on_place_changed()
        self.tool.e_hint.set_text.assert_called_with("")

    def test_the_same_place_typed_slightly_differently_keeps_its_hint(self):
        self.tool.e_place.get_text.return_value = "Johnston"
        self.tool.e_hint.get_text.return_value = "Iowa"
        self.tool._on_hint_changed()
        self.tool.e_hint.set_text.reset_mock()
        for same in ("johnston ", "  JOHNSTON", "Johnston"):
            self.tool.e_place.get_text.return_value = same
            self.tool._on_place_changed()
        self.tool.e_hint.set_text.assert_not_called()

    def test_a_hint_typed_before_any_place_belongs_to_no_place_yet(self):
        self.tool.e_place.get_text.return_value = ""
        self.tool.e_hint.get_text.return_value = "Iowa"
        self.tool._on_hint_changed()
        self.tool.e_hint.set_text.reset_mock()
        self.tool.e_place.get_text.return_value = "Johnston"
        self.tool._on_place_changed()
        self.tool.e_hint.set_text.assert_not_called()

    def test_clearing_the_hint_forgets_which_place_it_was_for(self):
        self.tool.e_place.get_text.return_value = "Johnston"
        self.tool.e_hint.get_text.return_value = "Iowa"
        self.tool._on_hint_changed()
        self.tool.e_hint.get_text.return_value = ""
        self.tool._on_hint_changed()
        self.tool.e_hint.set_text.reset_mock()
        self.tool.e_place.get_text.return_value = "Bajmok"
        self.tool._on_place_changed()
        self.tool.e_hint.set_text.assert_not_called()

    def test_the_status_line_says_exactly_which_question_was_asked(self):
        self.fill(place="Johnston", date="1950", hint="Iowa", engine="manual")
        self.tool._on_ask()
        self.assertIn("«Johnston, Iowa» on 1950", self.tool.status.set_text.call_args.args[0])
        self.fill(place="Bajmok", date="1850", hint="", engine="google")
        self.tool._on_ask()
        self.assertIn("«Bajmok» on 1850", self.tool.status.set_text.call_args.args[0])

    def test_a_choice_that_no_longer_exists_falls_back_to_the_default(self):
        self.assertEqual(self.mod.PlaceCompleterTool._index(["a", "b"], "gone", "b"), 1)
        self.assertEqual(self.mod.PlaceCompleterTool._index(["a", "b"], "gone", "also gone"), 0)

    def test_an_engine_that_lacks_only_a_key_opens_the_key_window_before_anything_is_asked(self):
        self.fill(engine="openai")
        env = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.tool._on_ask()
        self.assertEqual(self.gtk.Dialog.call_args.kwargs["title"], "API key")      # the only thing missing is the key: its window opens by itself
        self.assertNotIn("no model name", "".join(c.args[0] for c in self.tool.status.set_text.call_args_list if c.args))
        self.assertEqual(self.opened, [])

    def test_the_help_button_opens_the_user_guide_and_the_window_stays(self):
        import placecompleter
        with mock.patch.object(self.mod.webbrowser, "open", return_value=True) as opened:
            self.tool._response(None, self.gtk.ResponseType.HELP)
        opened.assert_called_once_with(placecompleter.GUIDE_URL)
        self.assertFalse(self.tool.closed)

    def test_when_the_browser_does_not_open_the_help_says_the_address(self):
        import placecompleter
        with mock.patch.object(self.mod.webbrowser, "open", return_value=False):
            self.tool._response(None, self.gtk.ResponseType.HELP)
        said = "".join(c.args[0] for c in self.tool.status.set_text.call_args_list if c.args)
        self.assertIn(placecompleter.GUIDE_URL, said)

    def test_the_close_button_closes(self):
        self.tool._response(None, self.gtk.ResponseType.CLOSE)
        self.assertTrue(self.tool.closed)

    def test_a_missing_name_is_shown_in_an_error_dialog(self):
        self.fill(place="")
        self.tool._on_ask()
        self.assertIn("a place", self.log["errors"][0][1])

    def test_what_was_chosen_is_remembered_but_not_the_hint(self):
        self.fill(hint="Iowa", engine="google", form="classic")
        self.tool._on_ask()
        saved = self.tool._load_prefs()
        self.assertEqual((saved["engine"], saved["form"]), ("google", "classic"))
        self.assertNotIn("hint", saved)                                                  # a hint belongs to one question

    def test_the_manual_engine_copies_the_question_and_says_so(self):
        self.fill(engine="manual", form="classic")
        self.tool._on_ask()
        self.assertIn("Place: Johnston. Date: 1950.", self.clip.set_text.call_args.args[0])
        self.assertIn("Query for «Johnston» on 1950 copied", self.tool.status.set_text.call_args.args[0])

    def test_a_browser_engine_opens_the_link(self):
        self.fill(engine="google", hint="Iowa")
        self.tool._on_ask()
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlparse(self.opened[0]).query)["udm"], ["50"])

    def test_no_step_row_only_repeats_the_change_it_is_under(self):
        """A change of one step showed the same sentence twice (the change, and its step under it): the step is left out when it says nothing
        more. The steps of a change of several steps stay."""
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        for row in self.tool.rows:
            self.assertNotIn("• " + row[2], [child[2] for child in row.children])
        self.assertTrue(any(len([c for c in row.children if c[2].startswith("• ")]) > 1 for row in self.tool.rows))

    def test_analyze_shows_the_control_screen_with_nothing_checked(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.assertGreaterEqual(len(self.tool.rows), 1)
        self.assertGreater(sum(len(row.children) for row in self.tool.rows), 1)         # the steps are under their changes
        self.assertTrue(all(row[5] for row in self.tool.rows))                          # every top-level row is a change with a box
        self.assertFalse(any(row[0] for row in self.tool.rows))
        self.assertEqual(len(self.tool.levels), 3)
        self.assertTrue(self.tool.preview.set_text.called)
        self.assertFalse(self.tool.b_apply.set_sensitive.call_args_list[-1].args[0] is False and False)

    def test_checking_a_change_checks_all_its_steps_and_changes_the_preview(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(open(SAMPLE_CLAUDE, encoding="utf-8").read())
        self.tool._on_analyse()
        first = next(i for i, row in enumerate(self.tool.rows) if row[2].startswith("Create place «Johnston»"))
        self.tool._on_row_toggled(None, str(first))
        self.assertTrue(self.tool.rows[first][0])
        self.assertIn("Johnston, Webster Township, Polk County, Iowa, USA", self.tool.preview.set_text.call_args.args[0])
        self.tool._on_row_toggled(None, str(first))
        self.assertFalse(any(row[0] for row in self.tool.rows))

    def test_a_step_has_no_box_of_its_own(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(open(SAMPLE_CLAUDE, encoding="utf-8").read())
        self.tool._on_analyse()
        change = next(row for row in self.tool.rows if row[2].startswith("Create place «Johnston»"))
        self.assertGreater(len(change.children), 1)
        self.assertFalse(any(child[5] for child in change.children))                    # the box is shown only on a change
        before = self.tool.preview.set_text.call_count
        self.tool._on_row_toggled(None, "0:0")                                          # a click on a step does nothing
        self.assertEqual(self.tool.preview.set_text.call_count, before)
        self.assertFalse(any(row[0] for row in self.tool.rows))

    def test_the_user_case_is_one_change_in_plain_words(self):
        self.tree = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1), "city": typed("city", "City of Johnston", 4, lang="en")}, [])
        self.tree.places["iowa"]["refs"] = [{"ref": "usa", "date": {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False], "text": "", "sortval": 0}}]
        self.tree.places["city"]["refs"] = [{"ref": "iowa", "date": {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False], "text": "", "sortval": 0}}]
        self.fill(place="City of Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer("PLACE_NAME_ON_DATE: City of Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
                    "1 | Polk | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        self.tool._on_analyse()
        (change,) = [row for row in self.tool.rows if row[2].startswith("Insert")]
        self.assertEqual(change[2], "Insert «Polk County» (new) between «City of Johnston [CITY]» and «Iowa [IOWA]»")
        self.assertEqual(change[4], "inserts intermediate level")                                  # and not CONFLICT: nothing contradicts the tree
        texts = [child[2] for child in change.children]
        self.assertTrue(texts[0].startswith("ℹ These modification steps are interdependent"))
        self.assertEqual(len(texts), 4)                                                 # the reason and three steps: nothing is cut
        self.assertIn("• Enclose «City of Johnston [CITY]» inside «Polk County» (new): from 1846 (an intermediate level inserted before the direct link to "
                      "«Iowa [IOWA]», which applies to the other years)", texts)
        self.tool._on_row_toggled(None, str(list(self.tool.rows).index(change)))
        self.assertIn("City of Johnston, Polk County, Iowa, USA", self.tool.preview.set_text.call_args.args[0])

    def test_the_apply_button_follows_the_state(self):
        self.fill(engine="manual")
        self.tool._on_ask()
        self.assertIs(self.tool.b_apply.set_sensitive.call_args_list[-1].args[0], False)        # nothing analysed yet
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.assertIs(self.tool.b_apply.set_sensitive.call_args_list[-1].args[0], True)

    def test_a_text_that_is_not_an_answer_is_reported(self):
        self.fill(engine="google", form="classic")
        self.tool._on_ask()
        self.answer("something copied by mistake")
        self.tool._on_analyse()
        self.assertIn("to expected response template", self.log["errors"][-1][1])

    def test_no_answer_prepares_the_next_form_and_opens_it(self):
        self.fill(engine="google", hint="Iowa", form="auto")
        self.tool._on_ask()
        self.answer(NO_ANSWER_TEXT)
        self.tool._on_analyse()
        self.assertEqual(len(self.opened), 2)
        q = [urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["q"][0] for u in self.opened]
        self.assertNotEqual(q[0], q[1])

    def test_gemini_gets_the_question_by_the_clipboard_because_its_address_cannot_take_it(self):
        self.fill(engine="gemini", place="Galicia", date="1800")
        self.tool._on_ask()
        copied = self.clip.set_text.call_args.args[0]
        self.assertIn("Galicia", copied)
        self.assertEqual(self.opened, ["https://gemini.google.com/app"])
        self.assertIn("paste into the browser prompt)", self.tool.status.set_text.call_args.args[0])

    def test_google_and_chatgpt_do_not_touch_the_clipboard(self):
        self.fill(engine="google", place="Galicia", date="1800")
        self.clip.set_text.reset_mock()
        self.tool._on_ask()
        self.clip.set_text.assert_not_called()

    def test_the_clipboard_is_used_when_the_answer_box_is_empty(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer("")
        self.clip.wait_for_text.return_value = read(JOHNSTON)
        self.tool._on_analyse()
        self.assertGreaterEqual(len(self.tool.rows), 1)

    def test_paste_puts_the_clipboard_into_the_answer_box(self):
        self.clip.wait_for_text.return_value = "the copied answer"
        self.tool._on_paste()
        self.tool.tv_answer.get_buffer.return_value.set_text.assert_called_with("the copied answer")

    def test_analyze_before_asking_and_with_nothing_to_read_says_so(self):
        self.answer("")
        self.tool._on_analyse()
        self.assertIn("Ask first,", self.tool.status.set_text.call_args.args[0])

    def test_an_ambiguous_name_opens_the_choice_and_asks_again(self):
        self.fill(place="Johnston", date="1996", engine="google")
        self.tool._on_ask()
        radios = []

        def make_radio(group, text):
            r = mock.MagicMock()
            r.get_active.return_value = False
            radios.append(r)
            return r
        self.gtk.RadioButton.new_with_label_from_widget.side_effect = make_radio
        dialog = mock.MagicMock()
        dialog.run.side_effect = lambda: (setattr(radios[1].get_active, "return_value", True), setattr(radios[0].get_active, "return_value", False),
                                          self.gtk.ResponseType.OK)[-1]
        self.gtk.Dialog.side_effect = lambda *a, **k: dialog
        self.answer(read(AMBIGUOUS))
        self.tool._on_analyse()
        self.assertEqual(len(radios), 2)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.opened[-1]).query)["q"][0]
        self.assertIn("Johnston, Iowa, United States (coordinates 41.673, -93.6977)", q)

    def test_cancelling_the_choice_stops(self):
        self.fill(place="Johnston", date="1996", engine="google")
        self.tool._on_ask()
        self.gtk.RadioButton.new_with_label_from_widget.side_effect = lambda g, t: mock.MagicMock(**{"get_active.return_value": False})
        dialog = mock.MagicMock()
        dialog.run.return_value = self.gtk.ResponseType.CANCEL
        self.gtk.Dialog.side_effect = lambda *a, **k: dialog
        self.answer(read(AMBIGUOUS))
        self.tool._on_analyse()
        self.assertEqual(len(self.opened), 1)
        self.assertIn("no place selected", self.tool.status.set_text.call_args.args[0])

    def test_unchecking_a_level_analyses_again(self):
        self.tree = bajmok_tree()
        self.fill(place="Bajmok", date="1850", engine="manual")
        self.tool._on_ask()
        self.answer(open(SAMPLE, encoding="utf-8").read())
        self.tool._on_analyse()
        self.assertEqual([row[0] for row in self.tool.levels], [True, True, True])
        steps = lambda: sum(len(row.children) for row in self.tool.rows)
        before = steps()
        self.tool._on_level_toggled(None, "1")
        self.assertEqual([row[0] for row in self.tool.levels], [True, False, True])
        self.assertNotEqual(steps(), before)

    def analysed_window(self):
        self.tree = bajmok_tree()
        self.fill(place="Bajmok", date="1850", engine="manual")
        self.tool._on_ask()
        with open(SAMPLE, encoding="utf-8") as fh:
            self.answer(fh.read())
        self.tool._on_analyse()

    def test_one_button_chooses_everything_and_pressed_again_unchecks_everything(self):
        self.analysed_window()
        self.assertEqual(self.tool.session.selected, set())                               # nothing is chosen for the user
        self.tool._update_buttons()
        self.tool.b_toggle_all.set_label.assert_called_with("Select all")
        self.tool._on_toggle_all()
        self.assertTrue(self.tool.session.selected)
        self.assertRegex(self.tool.status.set_text.call_args.args[0], r"^\d+ change\(s\) selected")
        self.tool.b_toggle_all.set_label.assert_called_with("Clear all")                  # the same button now clears
        self.tool._on_toggle_all()
        self.assertEqual(self.tool.session.selected, set())
        self.assertIn("unchecked", self.tool.status.set_text.call_args.args[0])
        self.tool.b_toggle_all.set_label.assert_called_with("Select all")

    def test_the_button_says_what_it_left_for_the_user(self):
        self.analysed_window()
        self.tool.session.plan["proposals"].append({"id": 99, "kind": "add-url", "place": "baj", "path": "https://example.org/x", "optional": True,
                                                    "existing": False, "conflict": False, "basis": "assumption", "old": {}, "new": {}, "bundle": None,
                                                    "key": "", "requires_key": "", "label": "x"})
        self.tool._on_toggle_all()
        self.assertIn("of unknown type (check", self.tool.status.set_text.call_args.args[0])
        self.assertIn("site of unknown type", self.tool.status.set_text.call_args.args[0])
        self.assertNotIn(99, self.tool.session.selected)

    def test_the_button_is_greyed_when_there_is_nothing_to_choose_or_to_clear(self):
        self.analysed_window()
        self.tool.session.plan["proposals"] = []
        self.tool._update_buttons()
        self.tool.b_toggle_all.set_sensitive.assert_called_with(False)

    def test_an_api_engine_is_asked_in_a_thread_and_its_answer_is_shown(self):
        self.fill(engine="anthropic", hint="Iowa", date="1995")
        reply = claude_reply(read(JOHNSTON))
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["ANTHROPIC_API_KEY"] = "sk-ant-api03-x"
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(self.mod.pcsession.enginelib, "post_json", lambda *a, **k: reply):
            self.tool._on_ask()
        self.assertGreaterEqual(len(self.tool.rows), 1)
        self.assertEqual(self.tool.session.meta["engine"], "anthropic")
        self.assertFalse(self.tool._busy)

    def test_an_api_that_fails_is_reported_and_the_window_is_free_again(self):
        self.fill(engine="anthropic", date="1995")
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        env["ANTHROPIC_API_KEY"] = "sk-ant-api03-x"

        def overloaded(*a, **k):
            raise self.mod.pcsession.enginelib.EngineError("the service answered HTTP 529: overloaded")
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(self.mod.pcsession.enginelib, "post_json", overloaded):
            self.tool._on_ask()
        self.assertIn("HTTP 529", self.log["errors"][-1][1])
        self.assertFalse(self.tool._busy)

    def test_apply_with_nothing_checked_says_so_and_writes_nothing(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.dbstate.db.readonly = False
        self.tool._on_apply()
        self.assertIn("Select at least one proposed", self.tool.status.set_text.call_args.args[0])

    def test_a_read_only_tree_is_refused(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.dbstate.db.readonly = True
        self.tool._on_apply()
        self.assertIn("read-only", self.log["errors"][-1][1])


class OllamaSetupWindowTests(Base):
    """Ollama is set up for the user, step by step, and each step only after the user agreed to it."""
    def setUp(self):
        super().setUp()
        self.ollama = self.mod.ollama
        for name in ("open_installer_terminal", "start_server", "pull"):
            patcher = mock.patch.object(self.ollama, name, return_value=(True, ""))
            setattr(self, name, patcher.start())
            self.addCleanup(patcher.stop)

    def states(self, *sequence):
        patcher = mock.patch.object(self.ollama, "state", side_effect=list(sequence))
        patcher.start()
        self.addCleanup(patcher.stop)

    def answer_with(self, *responses):
        patcher = mock.patch.object(self.tool, "_ask_choice", side_effect=list(responses))
        self.asked = patcher.start()
        self.addCleanup(patcher.stop)

    def need_setup(self):
        with mock.patch.object(self.tool, "_on_ask") as again:
            self.tool._perform({"action": "error", "message": "Ollama cannot be asked yet", "needs_setup": "ollama"})
        return again

    def test_nothing_is_done_when_the_user_does_not_agree(self):
        for state in ("missing", "stopped"):
            self.states(state)
            self.answer_with(self.gtk.ResponseType.CANCEL)
            again = self.need_setup()
            again.assert_not_called()
        self.open_installer_terminal.assert_not_called()
        self.start_server.assert_not_called()
        self.pull.assert_not_called()

    def test_when_it_is_not_installed_the_command_is_shown_and_can_be_copied(self):
        self.states("missing")
        self.answer_with(self.mod.SETUP_COPY)
        again = self.need_setup()
        self.assertEqual(self.asked.call_args.args[0], "Ollama is not installed")
        self.assertEqual(self.asked.call_args.kwargs["command"], "curl -fsSL https://ollama.com/install.sh | sh")
        self.clip.set_text.assert_called_with("curl -fsSL https://ollama.com/install.sh | sh", -1)
        self.open_installer_terminal.assert_not_called()
        again.assert_not_called()

    def test_when_the_user_agrees_a_terminal_opens_for_the_installation_and_the_window_does_not_wait_for_it(self):
        self.states("missing")
        self.answer_with(self.mod.SETUP_DO)
        again = self.need_setup()
        self.open_installer_terminal.assert_called_once_with()
        again.assert_not_called()                                                    # the installation goes on there: ask again after it
        self.assertIn("administrator password there", self.tool.status.set_text.call_args.args[0])

    def test_no_terminal_is_said_and_the_command_stays_to_copy(self):
        self.open_installer_terminal.return_value = (False, "Terminal application not detected. Copy command and execute manually in system terminal.")
        self.states("missing")
        self.answer_with(self.mod.SETUP_DO)
        self.need_setup()
        self.assertIn("Terminal application not", self.log["errors"][-1][1])

    def test_a_server_that_is_not_running_is_started_after_the_agreement_and_the_question_is_asked_again(self):
        self.states("stopped", "ready")
        self.answer_with(self.mod.SETUP_DO)
        again = self.need_setup()
        self.assertIn("ollama serve", self.asked.call_args.args[1])                  # the command that will be run is said
        self.start_server.assert_called_once()
        self.assertEqual(self.start_server.call_args.kwargs["sleep"], self.mod.PlaceCompleterTool._pause_and_answer)      # the wait is not a plain sleep
        again.assert_called_once_with()

    def test_the_wait_for_the_server_lets_the_window_answer(self):
        """A plain sleep of up to 20 seconds in the thread of the window froze it: the pause handles the events that are waiting, and ends on time."""
        handled = []
        with mock.patch.object(self.mod.Gtk, "events_pending", side_effect=[True, True, False] * 1000), \
                mock.patch.object(self.mod.Gtk, "main_iteration", side_effect=lambda: handled.append(1)):
            started = time.monotonic()
            self.mod.PlaceCompleterTool._pause_and_answer(0.1)
            elapsed = time.monotonic() - started
        self.assertGreaterEqual(len(handled), 4)                                           # events were handled during the wait
        self.assertLess(elapsed, 1.0)                                                      # and the wait ended

    def test_a_server_that_does_not_start_gets_an_explanation_and_the_way_by_hand(self):
        self.start_server.return_value = (False, "Ollama was started but does not answer yet: see /x/log")
        self.states("stopped")
        self.answer_with(self.mod.SETUP_DO)
        again = self.need_setup()
        again.assert_not_called()
        self.assertIn("does not answer yet", self.log["errors"][-1][1])
        self.assertIn("sudo systemctl start ollama", self.log["errors"][-1][1])

    def test_a_model_is_downloaded_after_the_user_chose_it_and_the_question_is_asked_again(self):
        self.states("no-model", "ready")
        with mock.patch.object(self.tool, "_choose_model", return_value="gemma3:4b"), \
                mock.patch.object(self.tool, "_download_dialog", return_value=(True, "")) as download:
            again = self.need_setup()
        download.assert_called_once_with("gemma3:4b")
        again.assert_called_once_with()

    def test_no_model_is_downloaded_when_the_user_cancels_the_choice(self):
        self.states("no-model")
        with mock.patch.object(self.tool, "_choose_model", return_value=""), mock.patch.object(self.tool, "_download_dialog") as download:
            again = self.need_setup()
        download.assert_not_called()
        again.assert_not_called()

    def test_a_download_that_fails_is_said_and_nothing_is_asked_again(self):
        self.states("no-model")
        with mock.patch.object(self.tool, "_choose_model", return_value="llama3.2"), \
                mock.patch.object(self.tool, "_download_dialog", return_value=(False, "the download was interrupted: connection reset")):
            again = self.need_setup()
        again.assert_not_called()
        self.assertIn("connection reset", self.log["errors"][-1][1])

    def test_ollama_that_is_ready_needs_nothing(self):
        self.states("ready")
        again = self.need_setup()
        again.assert_called_once_with()

    def test_choosing_ollama_when_nothing_answers_opens_the_setup_and_not_only_an_error(self):
        self.fill(engine="ollama")
        self.states("missing")
        self.answer_with(self.gtk.ResponseType.CANCEL)
        with mock.patch.object(self.mod.pcsession.enginelib, "_listening", lambda host, port, timeout=0.5: False):
            self.tool._on_ask()
        self.assertEqual(self.asked.call_args.args[0], "Ollama is not installed")
        self.assertFalse(self.log.get("errors"))                                      # the questions replace the error window

    # the windows themselves (their buttons and fields), with the window toolkit replaced: every widget is a new stand-in, so the tests make them
    def widgets(self, run=None, active_id=None, typed=""):
        """Make Gtk.Dialog, Gtk.Entry and Gtk.ComboBoxText give stand-ins that answer as told; returns the lists of what was made."""
        made = {"Dialog": [], "Entry": [], "ComboBoxText": [], "Label": []}

        def dialog(*a, **k):
            d = mock.MagicMock()
            d.run.side_effect = lambda: run() if isfunction(run) else run
            made["Dialog"].append(d)
            return d

        def entry(*a, **k):
            e = mock.MagicMock()
            e.get_text.side_effect = lambda: typed() if isfunction(typed) else typed
            made["Entry"].append(e)
            return e

        def combo(*a, **k):
            c = mock.MagicMock()
            c.get_active_id.return_value = active_id
            made["ComboBoxText"].append(c)
            return c
        def label(*a, **k):
            w = mock.MagicMock()
            w.made_with = k
            made["Label"].append(w)
            return w
        self.gtk.Dialog.side_effect, self.gtk.Entry.side_effect, self.gtk.ComboBoxText.side_effect = dialog, entry, combo
        self.gtk.Label.side_effect = label
        return made

    def test_the_question_window_shows_the_command_in_a_box_that_can_be_selected_not_changed(self):
        made = self.widgets(run=77)
        self.assertEqual(self.tool._ask_choice("T", "text", [("_Cancel", 1), ("Go", 2)], command="curl x | sh"), 77)
        entry = made["Entry"][0]
        entry.set_text.assert_called_with("curl x | sh")
        entry.set_editable.assert_called_with(False)
        self.assertEqual([c.args for c in made["Dialog"][0].add_button.call_args_list], [("_Cancel", 1), ("Go", 2)])
        made["Dialog"][0].destroy.assert_called_once_with()

    def test_the_question_window_is_as_wide_as_the_command_and_its_text_wraps_at_sixty_characters(self):
        made = self.widgets(run=1)
        self.tool._ask_choice("T", "a text", [("_OK", 1)], command="curl -fsSL https://ollama.com/install.sh | sh")
        made["Entry"][0].set_width_chars.assert_called_with(len("curl -fsSL https://ollama.com/install.sh | sh") + 2)
        body = made["Label"][0]
        body.set_max_width_chars.assert_called_with(60)
        body.set_line_wrap.assert_called_with(True)

    def english_text(self, text):
        """A text of a small window: a few short lines, in English, saying one thing per line."""
        lines = text.split("\n")
        self.assertLessEqual(len(lines), 4, text)
        for line in lines:
            self.assertLessEqual(len(line), 115, line)                                           # two lines at 60 characters at the most
        self.assertFalse(re.search(r"[\u0590-\u05ff]", text), text)                                # the interface is English until the last stage

    def test_the_questions_about_ollama_are_a_few_short_lines_of_english(self):
        self.states("missing", "stopped", "no-model")
        self.answer_with(self.gtk.ResponseType.CANCEL, self.gtk.ResponseType.CANCEL)
        self.need_setup()                                                                       # not installed
        self.need_setup()                                                                       # not running
        texts = [(c.args[0], c.args[1]) for c in self.asked.call_args_list]
        self.assertEqual([t for t, _x in texts], ["Ollama is not installed", "Ollama service is not running"])
        for _title, text in texts:
            self.english_text(text)
        made = self.widgets(run=self.gtk.ResponseType.CANCEL)
        self.tool._choose_model()
        self.english_text(made["Label"][0].made_with["label"])

    def test_the_install_question_keeps_the_command_out_of_the_text_so_that_the_box_holds_only_the_command(self):
        self.states("missing")
        self.answer_with(self.gtk.ResponseType.CANCEL)
        self.need_setup()
        self.assertNotIn("curl", self.asked.call_args.args[1])
        self.assertEqual([b[0] for b in self.asked.call_args.args[2]], ["_Cancel", "Copy command", "Open terminal to run installer"])

    def test_the_question_window_without_a_command_has_no_box(self):
        made = self.widgets(run=5)
        self.tool._ask_choice("T", "text", [("_OK", 1)])
        self.assertEqual(made["Entry"], [])

    def test_the_model_window_offers_the_suggested_models_and_a_free_name(self):
        made = self.widgets(run=self.mod.SETUP_DO, active_id="gemma3:4b", typed="")
        self.assertEqual(self.tool._choose_model(), "gemma3:4b")
        self.assertEqual([c.args[0] for c in made["ComboBoxText"][0].append.call_args_list], [n for n, _ in self.ollama.SUGGESTED])
        self.widgets(run=self.mod.SETUP_DO, active_id="gemma3:4b", typed=" qwen2.5:7b ")
        self.assertEqual(self.tool._choose_model(), "qwen2.5:7b")                      # a name typed wins
        self.widgets(run=self.gtk.ResponseType.CANCEL, active_id="gemma3:4b")
        self.assertEqual(self.tool._choose_model(), "")

    def test_the_default_model_is_the_one_that_is_chosen_when_the_list_gives_nothing(self):
        self.widgets(run=self.mod.SETUP_DO, active_id=None, typed="")
        self.assertEqual(self.tool._choose_model(), "llama3.2")

    def test_the_download_window_runs_the_download_and_reports_its_progress(self):
        def fake_pull(model, progress, cancelled=lambda: False):
            progress("downloading", 500000000, 2000000000)
            return True, ""
        self.pull.side_effect = fake_pull
        made = self.widgets(run=self.gtk.ResponseType.OK)
        self.assertEqual(self.tool._download_dialog("llama3.2"), (True, ""))
        self.pull.assert_called_once()
        self.assertEqual(self.pull.call_args.args[0], "llama3.2")

    def test_the_download_can_be_cancelled(self):
        seen = {}

        def fake_pull(model, progress, cancelled=lambda: False):
            seen["cancelled_at_start"] = cancelled()
            return True, ""
        self.pull.side_effect = fake_pull
        self.widgets(run=self.gtk.ResponseType.CANCEL)
        ok, message = self.tool._download_dialog("llama3.2")
        self.assertEqual((ok, message), (False, "download cancelled"))


class ConfidenceColumnTests(Base):
    """The column that says how far a change can be relied on: titled Confidence, explained on hover on its title, and on hover on each change."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCOORDINATES: 41.673, -93.6977\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n"
              "SOURCES: https://en.wikipedia.org/wiki/Johnston,_Iowa | PLACE_NAME_ON_DATE, SETTLEMENT_TYPE_ON_DATE, COORDINATES\n"
              "https://en.wikipedia.org/wiki/Polk_County,_Iowa | CONTAINERS\nNOT_SURE: COORDINATES\n")

    def analysed(self):
        self.tree = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
                          "city": typed("city", "Johnston", 4, lang="en")}, [])
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(self.ANSWER)
        self.tool._on_analyse()
        return [row for row in self.tool.rows if row[5]]                                          # the changes (not their steps)

    def test_the_column_is_titled_confidence_and_has_an_explanation_on_its_title(self):
        labels = []

        def label(*a, **k):
            w = mock.MagicMock()
            w.made_with = k
            labels.append(w)
            return w
        self.gtk.Label.side_effect = label
        self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter")
        header = [w for w in labels if w.made_with.get("label") == "Confidence"]
        self.assertEqual(len(header), 1)
        header[0].set_tooltip_text.assert_called_once_with(self.mod.confidence.explanation())
        header[0].show.assert_called_once_with()
        self.assertEqual(self.tool._rows_view.set_tooltip_column.call_args.args, (6,))                # a tooltip on each row, from the sixth column

    def test_each_change_shows_its_level_and_says_why_on_hover(self):
        changes = self.analysed()
        by_level = {}
        for row in changes:
            by_level.setdefault(row[3], []).append(row)
        self.assertEqual(sorted(by_level), ["Inferred", "Reported", "Unsure"])
        unsure = by_level["Unsure"][0]
        self.assertIn("coordinates", unsure[2].lower())
        self.assertEqual(unsure[6], "Unsure: the response indicated uncertainty about COORDINATES")
        self.assertEqual(by_level["Reported"][0][6], "Reported: stated in the AI response with a supporting source citation")
        self.assertTrue(by_level["Inferred"][0][6].startswith("Inferred: "))

    def test_the_steps_and_the_notes_under_a_change_have_no_level_and_no_tooltip(self):
        self.analysed()
        below = [child for row in self.tool.rows for child in row.children]                      # the note and the steps under a change
        self.assertTrue(below)
        self.assertEqual({(child[3], child[6], child[5]) for child in below}, {("", "", False)})

    def test_a_tooltip_is_text_safe_for_the_markup_of_the_tooltips(self):
        from xml.sax.saxutils import escape
        self.assertEqual(escape("a < b & c"), "a &lt; b &amp; c")                                       # what the window uses for it
        self.assertIs(self.mod.escape, escape)


class UnitQuestionWindowTests(Base):
    """The window's question about a level of the answer: with a reason when the program has one."""
    def labels(self, run):
        made = []

        def label(*a, **k):
            w = mock.MagicMock()
            w.made_with = k
            made.append(w)
            return w
        self.gtk.Label.side_effect = label
        self.gtk.Dialog.side_effect = lambda *a, **k: mock.MagicMock(run=mock.MagicMock(return_value=run))
        return made

    def test_the_question_gives_the_reason_when_the_program_has_one(self):
        made = self.labels(self.gtk.ResponseType.CANCEL)
        unit = {"slot": "c1", "name": "Kauno apskritis", "type": "county", "candidates": [{"handle": "kc", "label": "Kaunas County [KC]", "score": 0}],
                "why": "«Kauno apskritis» is not in your tree under that name, but «Kaunas County [KC]» holds «Kaunas [K]» there. Is it the same place?"}
        self.assertIsNone(self.tool._choose_dialog(unit))
        self.assertEqual(made[0].made_with["label"], unit["why"])
        made[0].set_max_width_chars.assert_called_with(60)

    def test_without_a_reason_the_question_is_the_general_one(self):
        made = self.labels(self.gtk.ResponseType.CANCEL)
        unit = {"slot": "c1", "name": "Zombor", "type": "city", "candidates": [{"handle": "a", "label": "A", "score": 9}, {"handle": "b", "label": "B", "score": 9}]}
        self.tool._choose_dialog(unit)
        self.assertEqual(made[0].made_with["label"], "The response specifies «Zombor» (city), matching several existing places in your tree. No changes will be made until you choose one.")


class HintsAndOrderTests(Base):
    """The hints of the fields (they appear when the pointer rests on them) and the order of the fields: the question is chosen before the AI."""
    def build(self):
        made = {"Grid": [], "Label": [], "Frame": []}

        def factory(kind):
            def make(*a, **k):
                w = mock.MagicMock()
                w.made_with = k
                made[kind].append(w)
                return w
            return make
        for kind in made:
            getattr(self.gtk, kind).side_effect = factory(kind)
        tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter")
        return tool, made

    def rows_of(self, grid):
        return {id(c.args[0]): c.args[2] for c in grid.attach.call_args_list}

    def test_the_hints_are_short_english_texts_with_examples(self):
        for name, text in self.mod.hints.ALL.items():
            lines = text.split("\n")
            self.assertTrue(text.strip(), name)
            self.assertLessEqual(len(lines), 8, name)
            self.assertTrue(all(len(line) <= 120 for line in lines), name)
            self.assertFalse(re.search(r"[\u0590-\u05ff]", text), name)                         # the interface is English until the last stage
        hint = self.mod.hints.HINT
        for example in ("Parma", "Italy", "Johnston", "Iowa"):
            self.assertIn(example, hint)

    def test_the_hint_of_the_question_explains_every_form_that_can_be_chosen(self):
        for form in self.mod.FORMS:
            self.assertIn(form + ":", self.mod.hints.FORM, form)
        self.assertIn("prompt requesting", self.mod.hints.FORM)
        self.assertIn("browser", self.mod.hints.ENGINE)

    def test_the_question_is_chosen_before_the_ai_and_the_key_stays_beside_the_ai(self):
        tool, made = self.build()
        grid = made["Grid"][0]
        rows = self.rows_of(grid)
        self.assertLess(rows[id(tool.c_form)], rows[id(tool.c_engine)])
        self.assertEqual(rows[id(tool.c_engine)], rows[id(tool.c_form)] + 1)
        self.assertEqual(rows[id(tool.b_key)], rows[id(tool.c_engine)])
        labels = {rows[id(w)]: w.made_with.get("label") for w in made["Label"] if id(w) in rows}
        self.assertEqual([labels[r] for r in range(5)], ["Place", "Date", "Region hint", "Question", "AI"])

    def test_every_field_that_is_not_obvious_has_its_hint(self):
        tool, made = self.build()
        hints = self.mod.hints
        for widget, text in ((tool.e_place, hints.PLACE), (tool.e_date, hints.DATE), (tool.e_hint, hints.HINT), (tool.c_form, hints.FORM),
                             (tool.c_engine, hints.ENGINE), (tool.b_ask, hints.ASK), (tool.c_wikidata, hints.WIKIDATA), (tool.b_apply, hints.APPLY),
                             (tool.b_analyse, hints.ANALYSE), (tool._frame_levels, hints.LEVELS)):
            widget.set_tooltip_text.assert_any_call(text)
        by_label = {w.made_with.get("label"): w for w in made["Frame"]}
        by_label["Issues to review"].set_tooltip_text.assert_called_with(hints.NEEDS)
        answer = next(w for label, w in by_label.items() if label.startswith("Response (if copied"))
        answer.set_tooltip_text.assert_called_with(hints.ANSWER)

    def test_a_label_has_the_same_hint_as_its_field(self):
        tool, made = self.build()
        for label in made["Label"]:
            if label.made_with.get("label") == "Question":
                label.set_tooltip_text.assert_called_with(self.mod.hints.FORM)
            if label.made_with.get("label") == "Region hint":
                label.set_tooltip_text.assert_called_with(self.mod.hints.HINT)


class ResizablePanesTests(Base):
    """The sections of the window (answer, levels, changes, issues) can be made taller or shorter with a handle, and none can be made nothing."""
    def build(self):
        made = {"Paned": [], "Frame": [], "ScrolledWindow": [], "TreeViewColumn": []}

        def factory(kind):
            def make(*a, **k):
                w = mock.MagicMock()
                w.made_with = (a, k)
                made[kind].append(w)
                return w
            return make
        for kind in made:
            getattr(self.gtk, kind).side_effect = factory(kind)
        tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter")
        return tool, made

    def test_three_handles_separate_the_four_sections_and_each_section_keeps_its_own_minimum(self):
        tool, made = self.build()
        self.assertEqual(len(made["Paned"]), 3)
        for paned in made["Paned"]:
            paned.set_wide_handle.assert_called_with(True)
            for call in paned.pack1.call_args_list + paned.pack2.call_args_list:
                self.assertIs(call.args[2], False, "shrink must be off: a section cannot be made smaller than it needs")
        bottom, middle, top = made["Paned"]
        self.assertEqual(middle.pack1.call_args.args[0], tool._frame_levels)
        self.assertEqual(middle.pack2.call_args.args[0], bottom)
        self.assertEqual(top.pack2.call_args.args[0], middle)

    def test_the_changes_take_what_the_window_gives_and_the_others_keep_their_height(self):
        tool, made = self.build()
        bottom, middle, top = made["Paned"]
        self.assertIs(bottom.pack1.call_args.args[1], True)                                      # the changes grow
        self.assertIs(bottom.pack2.call_args.args[1], False)                                     # the issues keep their height
        self.assertIs(middle.pack1.call_args.args[1], False)                                     # the levels keep theirs
        self.assertIs(top.pack1.call_args.args[1], False)                                        # and the answer
        self.assertIs(middle.pack2.call_args.args[1], True)
        self.assertIs(top.pack2.call_args.args[1], True)

    def test_every_section_has_a_minimum_height_that_is_not_nothing(self):
        tool, made = self.build()
        heights = sorted(c.args[0] for w in made["ScrolledWindow"] for c in w.set_min_content_height.call_args_list)
        self.assertEqual(heights, [60, 70, 90, 150])
        self.assertTrue(all(h >= 60 for h in heights))

    def test_the_results_are_hidden_with_their_handle_until_there_is_an_answer(self):
        tool, made = self.build()
        self.assertIn(tool._results_pane, tool._result_widgets)
        tool._results_pane.hide.assert_called()
        tool._results_pane.set_no_show_all.assert_called_with(True)

    def test_the_titles_of_the_sections_and_of_the_columns(self):
        tool, made = self.build()
        titles = [w.made_with[1].get("label") for w in made["Frame"]]
        self.assertIn("Other changes (each box is a grouped change applied as a set)", titles)
        self.assertIn("Retrieved administrative levels (uncheck uncertain levels)", titles)
        columns = [w.made_with[0][0] for w in made["TreeViewColumn"] if w.made_with[0]]
        self.assertEqual(columns.count("Select"), 2)                                              # the levels and the changes
        self.assertIn("Proposed changes", columns)                                                # the column of the texts of the changes
        for old in ("Use", "Apply", "Change"):
            self.assertNotIn(old, columns)

    def test_the_preview_says_how_gramps_will_display_an_event_on_the_date(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        shown = self.tool.preview.set_text.call_args.args[0]
        self.assertTrue(shown.startswith("Gramps display format for an event on this date: "), shown)
        self.assertNotIn("would display", shown)


class PrefillHintTests(Base):
    """The window opened from a place or an event gets the highest place above it as the Region hint."""
    def test_the_hint_is_filled_with_the_place_and_the_date(self):
        tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter",
                                           prefill={"place": "Trecasali", "date": "1990", "hint": "Italy"})
        tool.e_place.set_text.assert_called_with("Trecasali")
        tool.e_date.set_text.assert_called_with("1990")
        tool.e_hint.set_text.assert_called_with("Italy")

    def test_without_a_hint_the_field_is_emptied_and_not_left_with_an_old_one(self):
        tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter",
                                           prefill={"place": "Bajmok", "date": "1850"})
        tool.e_hint.set_text.assert_called_with("")

    def test_a_window_opened_from_the_menu_has_nothing_prefilled(self):
        tool = self.mod.PlaceCompleterTool(self.dbstate, types.SimpleNamespace(uistate=object()), self.mod.PlaceCompleterOptions, "placecompleter")
        for field in (tool.e_place, tool.e_date):
            for call in field.set_text.call_args_list:
                self.assertNotIn(call.args[0], ("Trecasali", "1990"))


class PastedAnswerTests(Base):
    """An answer of an earlier question can be pasted and analysed without asking again: the button is ready when there is an answer in the box."""
    def test_the_button_is_not_ready_with_no_question_and_no_answer(self):
        self.answer("")
        self.tool._update_buttons()
        self.tool.b_analyse.set_sensitive.assert_called_with(False)

    def test_the_button_is_ready_when_there_is_an_answer_in_the_box_even_with_no_question(self):
        self.assertIsNone(self.tool.session)
        self.answer(read(JOHNSTON))
        self.tool._update_buttons()
        self.tool.b_analyse.set_sensitive.assert_called_with(True)

    def test_the_button_follows_the_box_while_something_is_busy(self):
        self.answer(read(JOHNSTON))
        self.tool._busy = True
        self.tool._update_buttons()
        self.tool.b_analyse.set_sensitive.assert_called_with(False)

    def test_the_box_tells_the_window_when_it_changes(self):
        calls = [c for c in self.tool.tv_answer.get_buffer.return_value.connect.call_args_list if c.args[0] == "changed"]
        self.assertEqual(len(calls), 1)
        self.answer(read(JOHNSTON))
        calls[0].args[1]()                                                                         # the signal: the buttons are updated
        self.tool.b_analyse.set_sensitive.assert_called_with(True)

    def test_an_answer_pasted_with_no_question_is_analysed_with_the_place_and_the_date_of_the_fields(self):
        self.fill(engine="google", date="1995")
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.assertIsNotNone(self.tool.session)
        self.assertEqual((self.tool.session.place, self.tool.session.date), ("Johnston", "1995"))
        self.assertEqual(self.tool.session.state, "ready")                                         # the answer was read and analysed
        self.assertTrue(self.tool.session.rec)
        self.assertFalse(self.log.get("opened"))                                                    # no browser, no question

    def test_nothing_is_asked_or_copied_by_it(self):
        self.fill(engine="google", date="1995")
        self.answer(read(JOHNSTON))
        with mock.patch.object(self.mod, "webbrowser") as browser:
            self.tool._on_analyse()
        browser.open.assert_not_called()
        self.assertFalse(self.gtk.Clipboard.get.return_value.set_text.called)

    def test_without_the_place_or_the_date_it_says_what_is_missing(self):
        for place, date in (("", "1995"), ("Johnston", "")):
            self.fill(place=place, date=date)
            self.answer(read(JOHNSTON))
            self.tool.session = None
            self.tool._on_analyse()
            self.assertIsNone(self.tool.session)
            self.assertEqual(self.tool.status.set_text.call_args.args[0], "Specify the place name and date for the query.")

    def test_with_no_answer_and_no_question_it_says_so(self):
        self.answer("")
        self.tool.session = None
        self.tool._on_analyse()
        self.assertEqual(self.tool.status.set_text.call_args.args[0], "Click Ask first, or paste a response into the text box.")

    def test_after_a_question_it_works_as_before(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.assertEqual(self.tool.session.state, "ready")


class KeyWindowTests(Base):
    """The small window for the key: a hidden field, Test, Save, Remove; opened by itself when only a key is missing."""
    def setUp(self):
        super().setUp()
        self.store = MemoryStore()
        keystore.reset_store(self.store)
        self.addCleanup(keystore.reset_store, None)
        env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.labels, self.entries = [], []

    def dialog(self, responses, typed=SECRET):
        def make_label(*a, **k):
            m = mock.MagicMock()
            self.labels.append(m)
            return m

        def make_entry(*a, **k):
            m = mock.MagicMock()
            m.get_text.return_value = typed
            self.entries.append(m)
            return m
        self.gtk.Label.side_effect, self.gtk.Entry.side_effect = make_label, make_entry
        d = mock.MagicMock()
        d.run.side_effect = list(responses)
        self.gtk.Dialog.side_effect = lambda *a, **k: d
        return d

    def texts(self):
        return [c.args[0] for m in self.labels for c in m.set_text.call_args_list if c.args] + \
               [c.args[0] for c in self.tool.status.set_text.call_args_list]

    def test_the_key_button_opens_a_small_window_with_a_password_field(self):
        d = self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertEqual(self.gtk.Dialog.call_args.kwargs["title"], "API key")
        self.entries[-1].set_visibility.assert_called_with(False)
        self.gtk.InputPurpose.PASSWORD                                                  # asked for: no suggestions, no history
        self.entries[-1].set_input_purpose.assert_called_with(self.gtk.InputPurpose.PASSWORD)
        d.destroy.assert_called()
        self.assertEqual(self.store.items, {})

    def test_the_window_says_where_the_key_will_be_kept(self):
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertTrue(any("encrypted via system keyring" in t for t in self.texts()))
        keystore.reset_store(keystore.FileStore(tempfile.mkdtemp()))
        self.labels.clear()
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool._on_key()
        self.assertTrue(any("unencrypted" in t for t in self.texts()))

    def test_test_then_save_keeps_the_key_and_clears_the_field(self):
        self.dialog([self.mod.KEY_TEST, self.mod.KEY_SAVE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", lambda url, headers, timeout=20: {"id": "m", "display_name": "Claude X"}):
            self.tool._on_key()
        self.assertEqual(self.store.items, {"anthropic": SECRET})
        self.assertTrue(any("✓ API key validated successfully; model Claude X is active." in t for t in self.texts()))
        self.entries[-1].set_text.assert_called_with("")                                # the key does not stay in the window
        self.assertTrue(any(t.startswith("Key saved (sk-ant-") for t in self.texts()))

    def models_file(self):
        patcher = mock.patch.dict(os.environ, {"PLACECOMPLETER_MODELS": os.path.join(tempfile.mkdtemp(), "models.json")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_saved_openai_key_finds_its_model_by_itself_and_the_window_stays_on_that_ai(self):
        """No model is written by hand: right after the key is saved the service is asked which models it has, one is chosen and kept, and
        the window stays on this AI (it used to jump back to Google AI mode and show 'needs setup': a saved key looked lost)."""
        self.models_file()
        self.dialog([self.mod.KEY_SAVE], typed="sk-proj-" + "Q" * 40)
        self.tool.c_engine.get_active_id.return_value = "openai"
        listing = {"data": [{"id": "gpt-5", "created": 300}, {"id": "gpt-5-mini", "created": 400}, {"id": "whisper-1", "created": 1}]}
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", lambda url, headers, timeout=20: listing):
            self.tool._on_key()
        self.assertEqual(self.store.items, {"openai": "sk-proj-" + "Q" * 40})                  # it WAS saved
        ids = [c.args[0] for c in self.tool.c_engine.append.call_args_list][-len(self.mod.pcsession.Session(Tree({}, []), self.mod.WORK).engine_options()):]
        self.tool.c_engine.set_active.assert_called_with(ids.index("openai"))                  # and the window stays on this AI
        labels = [c.args[1] for c in self.tool.c_engine.append.call_args_list][-12:]
        self.assertTrue(any(l.startswith("✓ OpenAI-compatible") for l in labels))              # ready: nothing more to set up
        self.assertTrue(any(t == "Key saved; model gpt-5 was automatically selected." for t in self.texts()))
        self.assertEqual(self.mod.pcsession.enginelib.remembered_model("openai"), "gpt-5")

    def test_when_no_model_can_be_chosen_the_window_says_so_and_still_keeps_the_key(self):
        self.models_file()
        self.dialog([self.mod.KEY_SAVE], typed="sk-proj-" + "Q" * 40)
        self.tool.c_engine.get_active_id.return_value = "openai"
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", lambda url, headers, timeout=20: {"data": [{"id": "whisper-1"}]}):
            self.tool._on_key()
        self.assertEqual(self.store.items, {"openai": "sk-proj-" + "Q" * 40})
        self.assertTrue(any(t.startswith("Key saved, but could not select a model: could not select a model from api.openai.com")
                            for t in self.texts()))

    def test_a_key_that_the_service_refuses_is_still_kept_and_the_refusal_is_said(self):
        self.models_file()
        self.dialog([self.mod.KEY_SAVE], typed="sk-proj-" + "Q" * 40)
        self.tool.c_engine.get_active_id.return_value = "openai"

        def refuse(url, headers, timeout=20):
            raise self.mod.pcsession.enginelib.EngineError("the service answered HTTP 401: Incorrect API key provided")
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", refuse):
            self.tool._on_key()
        self.assertEqual(self.store.items, {"openai": "sk-proj-" + "Q" * 40})
        self.assertTrue(any("Key saved, but could not select a model: the service answered HTTP 401" in t for t in self.texts()))

    def test_the_key_never_appears_in_any_text_of_the_window(self):
        self.dialog([self.mod.KEY_TEST, self.mod.KEY_SAVE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", lambda url, headers, timeout=20: {"id": "m"}):
            self.tool._on_key()
        self.assertFalse([t for t in self.texts() if SECRET in t or "QQQQ" in t])

    def test_a_refused_key_is_said_and_nothing_is_saved_by_a_test(self):
        self.dialog([self.mod.KEY_TEST, self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"

        def refuse(url, headers, timeout=20):
            raise self.mod.pcsession.enginelib.EngineError("the service answered HTTP 401: invalid x-api-key")
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", refuse):
            self.tool._on_key()
        refusal = next(t for t in self.texts() if t.startswith("✗ Service api.anthropic.com rejected the API key (HTTP 401)"))
        self.assertIn("Sent key suffix: sk-ant-…wXyZ", refusal)               # to compare with the key in the console
        self.assertNotIn("QQQQ", refusal)
        self.assertEqual(self.store.items, {})

    def test_an_empty_field_is_not_saved_and_the_window_stays_open(self):
        d = self.dialog([self.mod.KEY_SAVE, self.gtk.ResponseType.CLOSE], typed="  ")
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertTrue(any("Please enter an API key first." in t for t in self.texts()))
        self.assertEqual((self.store.items, d.run.call_count), ({}, 2))

    def test_a_place_that_cannot_keep_it_says_so_and_stays_open(self):
        keystore.reset_store(keystore.NullStore())
        d = self.dialog([self.mod.KEY_SAVE, self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertTrue(any("key persistence disabled" in t for t in self.texts()))
        self.assertEqual(d.run.call_count, 2)

    def test_remove_takes_the_saved_key_out(self):
        self.store.set("anthropic", SECRET)
        self.dialog([self.mod.KEY_REMOVE, self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertEqual(self.store.items, {})
        self.assertTrue(any("The saved key has been removed." in t for t in self.texts()))

    def test_a_saved_key_is_shown_by_its_hint_only(self):
        self.store.set("anthropic", SECRET)
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertTrue(any(t.startswith("Key already saved: sk-ant-…wXyZ") for t in self.texts()))
        self.assertFalse([t for t in self.texts() if SECRET in t])

    def test_the_window_says_which_server_the_key_goes_to(self):
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        self.tool._on_key()
        self.assertTrue(any(t.endswith("Sent only to api.anthropic.com.") for t in self.texts()))
        self.labels.clear()
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "openai"
        self.tool._on_key()
        self.assertTrue(any(t.endswith("Sent only to api.openai.com.") for t in self.texts()))

    def test_a_claude_key_given_to_the_openai_engine_is_caught_before_anything_is_sent(self):
        self.dialog([self.mod.KEY_TEST, self.mod.KEY_SAVE, self.gtk.ResponseType.CLOSE])
        self.tool.c_engine.get_active_id.return_value = "openai"
        sent = []
        with mock.patch.object(self.mod.pcsession.enginelib, "get_json", lambda *a, **k: sent.append(a) or {}):
            self.tool._on_key()
        warnings = [t for t in self.texts() if "This is an Anthropic Claude key, but the engine sends requests to api.openai.com" in t]
        self.assertEqual(len(warnings), 2)                                            # at Test and at Save
        self.assertIn("select 'Claude API with web search'", warnings[0])
        self.assertEqual((sent, self.store.items), ([], {}))                          # nothing was asked, nothing was kept

    def test_an_ai_that_cannot_work_yet_is_not_remembered_as_the_one_to_open_with(self):
        import json as _json
        with open(self.mod.PREFS, "w", encoding="utf-8") as fh:
            _json.dump({"engine": "manual", "form": "auto", "hint": ""}, fh)
        self.fill(engine="openai")
        self.tool._on_ask()
        with open(self.mod.PREFS, encoding="utf-8") as fh:
            self.assertEqual(_json.load(fh)["engine"], "manual")

    def test_the_window_does_not_open_on_an_ai_that_cannot_work(self):
        import json as _json
        with open(self.mod.PREFS, "w", encoding="utf-8") as fh:
            _json.dump({"engine": "openai", "form": "auto", "hint": ""}, fh)
        self.tool._build()
        ids = [c.args[0] for c in self.tool.c_engine.append.call_args_list][-len(self.tool._keys.engine_options()):]
        self.tool.c_engine.set_active.assert_called_with(ids.index("google"))

    def test_the_list_of_engines_is_refilled_after_a_key_is_saved(self):
        self.dialog([self.mod.KEY_SAVE])
        self.tool.c_engine.get_active_id.return_value = "anthropic"
        before = self.tool.c_engine.remove_all.call_count
        self.tool._on_key()
        self.assertEqual(self.tool.c_engine.remove_all.call_count, before + 1)
        labels = [c.args[1] for c in self.tool.c_engine.append.call_args_list][-8:]
        self.assertTrue(any(l.startswith("✓ Claude API with web search") for l in labels))

    def test_an_engine_that_needs_no_key_has_no_key_window(self):
        self.tool.c_engine.get_active_id.return_value = "google"
        self.tool._on_key()
        self.assertIn("an API key", self.tool.status.set_text.call_args.args[0])
        self.assertFalse(self.gtk.Dialog.call_args and self.gtk.Dialog.call_args.kwargs.get("title") == "API key")

    def test_when_only_a_key_is_missing_the_window_asks_for_it_and_goes_on(self):
        self.dialog([self.mod.KEY_SAVE])
        self.fill(engine="anthropic", hint="Iowa", date="1995")
        reply = claude_reply(read(JOHNSTON))
        with mock.patch.object(self.mod.pcsession.enginelib, "post_json", lambda *a, **k: reply):
            self.tool._on_ask()
        self.assertEqual(self.store.items, {"anthropic": SECRET})
        self.assertGreaterEqual(len(self.tool.rows), 1)                                    # the question was asked with the new key
        self.assertNotIn("errors", self.log)                                               # and nobody was told off
        self.assertEqual(self.tool.session.meta["engine"], "anthropic")

    def test_if_the_key_window_is_closed_the_reason_stays_in_the_status_line(self):
        self.dialog([self.gtk.ResponseType.CLOSE])
        self.fill(engine="anthropic", date="1995")
        self.tool._on_ask()
        self.assertIn("no key", self.tool.status.set_text.call_args_list[-1].args[0])
        self.assertNotIn("errors", self.log)
        self.assertEqual(self.store.items, {})

    def test_a_key_the_service_refuses_opens_the_key_window_again(self):
        self.store.set("anthropic", SECRET)
        d = self.dialog([self.gtk.ResponseType.CLOSE])
        self.fill(engine="anthropic", date="1995")

        def refuse(*a, **k):
            raise self.mod.pcsession.enginelib.EngineError("the service answered HTTP 401: invalid x-api-key")
        with mock.patch.object(self.mod.pcsession.enginelib, "post_json", refuse):
            self.tool._on_ask()
        d.run.assert_called()
        self.assertFalse([t for t in self.texts() if SECRET in t])


class FitTests(Base):
    """The window must fit the screen: its content scrolls, the buttons are always in sight, nothing empty takes room."""
    def screen(self, width, height, x=0, y=0):
        self.mod.Gdk.Display.get_default.return_value.get_primary_monitor.return_value.get_workarea.return_value = \
            types.SimpleNamespace(x=x, y=y, width=width, height=height)

    def build(self):
        user = types.SimpleNamespace(uistate=object())
        with mock.patch.object(self.mod.PlaceCompleterTool, "setup_configs") as configs:
            tool = self.mod.PlaceCompleterTool(self.dbstate, user, self.mod.PlaceCompleterOptions, "placecompleter")
        return tool, configs.call_args.args

    def test_the_starting_size_follows_the_screen(self):
        self.screen(1920, 1080)
        self.assertEqual(self.build()[1], ("interface.placecompleter", 940, 780))
        self.screen(1366, 768)
        self.assertEqual(self.build()[1], ("interface.placecompleter", 940, 648))
        self.screen(1024, 600)
        self.assertEqual(self.build()[1], ("interface.placecompleter", 940, 480))
        self.screen(800, 480)
        self.assertEqual(self.build()[1], ("interface.placecompleter", 740, 480))

    def test_a_size_remembered_from_a_bigger_screen_is_brought_back_inside(self):
        self.screen(1366, 768)
        win = self.tool.window
        win.get_size.return_value, win.get_position.return_value = (1800, 1300), (-50, -40)
        self.tool._keep_on_screen()
        win.resize.assert_called_with(1326, 688)
        win.move.assert_called_with(0, 0)

    def test_a_window_that_sticks_out_at_the_side_or_the_bottom_is_moved_in(self):
        self.screen(1366, 768)
        win = self.tool.window
        win.get_size.return_value, win.get_position.return_value = (900, 600), (1300, 700)
        self.tool._keep_on_screen()
        win.resize.assert_not_called()
        win.move.assert_called_with(466, 168)

    def test_a_window_that_fits_is_left_alone(self):
        self.screen(1366, 768)
        win = self.tool.window
        win.get_size.return_value, win.get_position.return_value = (900, 600), (100, 50)
        self.tool._keep_on_screen()
        win.resize.assert_not_called()
        win.move.assert_not_called()

    def test_a_second_monitor_is_respected(self):
        self.screen(1280, 720, x=1920, y=0)
        win = self.tool.window
        win.get_size.return_value, win.get_position.return_value = (900, 600), (100, 50)        # left of the monitor: brought onto it
        self.tool._keep_on_screen()
        win.move.assert_called_with(1920, 50)

    def test_the_content_scrolls_and_the_write_button_is_in_the_row_of_buttons_below_it(self):
        scrollers = []
        self.gtk.ScrolledWindow.side_effect = lambda *a, **k: scrollers.append(mock.MagicMock()) or scrollers[-1]
        dialogs = []
        self.gtk.Dialog.side_effect = lambda *a, **k: dialogs.append(mock.MagicMock()) or dialogs[-1]
        tool, _ = self.build()
        main = scrollers[0]
        main.set_policy.assert_called_with(self.gtk.PolicyType.AUTOMATIC, self.gtk.PolicyType.AUTOMATIC)     # nothing is cut off: it scrolls
        self.assertIs(dialogs[0].get_content_area.return_value.pack_start.call_args.args[0], main)
        responses = [c.args[1] for c in dialogs[0].add_button.call_args_list]
        self.assertEqual(responses, [self.gtk.ResponseType.HELP, self.gtk.ResponseType.CLOSE, self.mod.RESPONSE_WRITE])
        self.assertEqual(dialogs[0].add_button.call_args_list[0].args[0], "_Help")                  # the label of Gramps' own catalog: nothing new to translate
        self.assertIs(tool.b_apply, dialogs[0].add_button.return_value)

    def test_every_scrolled_window_has_a_classic_slim_bar_that_does_not_float_over_the_text(self):
        scrollers = []
        self.gtk.ScrolledWindow.side_effect = lambda *a, **k: scrollers.append(mock.MagicMock()) or scrollers[-1]
        self.build()
        self.assertGreaterEqual(len(scrollers), 5)                                          # the whole, the answer, the notes, the two tables
        for s in scrollers:
            s.set_overlay_scrolling.assert_called_with(False)
            s.get_style_context.return_value.add_class.assert_called_with(self.mod.SCROLL_CLASS)

    def test_the_css_is_installed_once_for_the_screen_but_only_matches_scrolled_windows_of_this_addon(self):
        self.gtk.StyleContext.add_provider_for_screen.reset_mock()
        self.mod._css_installed.clear()
        self.build()
        self.build()
        self.assertEqual(self.gtk.StyleContext.add_provider_for_screen.call_count, 1)
        for line in self.mod.SLIM_CSS.decode().strip().splitlines():
            self.assertTrue(line.startswith("scrolledwindow.placecompleter-scroll "), line)         # nothing else in Gramps is styled
        self.assertIn("scrollbar button { min-width: 0; min-height: 0;", self.mod.SLIM_CSS.decode())     # no arrow buttons at the ends

    def test_a_theme_that_refuses_the_css_does_not_break_the_window(self):
        self.gtk.CssProvider.side_effect = RuntimeError("bad css")
        self.mod._css_installed.clear()
        scroller = mock.MagicMock()
        self.assertIs(self.mod.tidy_scroller(scroller), scroller)
        scroller.set_overlay_scrolling.assert_called_with(False)

    def test_long_words_break_instead_of_making_the_window_wider(self):
        tool, _ = self.build()
        for view in (tool.tv_answer, tool.tv_needs):
            view.set_wrap_mode.assert_called_with(self.gtk.WrapMode.WORD_CHAR)
        for label in (tool.status, tool.preview):
            label.set_line_wrap_mode.assert_called_with(self.mod.Pango.WrapMode.WORD_CHAR)

    def test_the_minimum_heights_cannot_add_up_to_a_screen(self):
        scrollers = []
        self.gtk.ScrolledWindow.side_effect = lambda *a, **k: scrollers.append(mock.MagicMock()) or scrollers[-1]
        self.build()
        total = sum(c.args[0] for s in scrollers for c in s.set_min_content_height.call_args_list)
        self.assertLessEqual(total, 400)

    def test_nothing_empty_is_shown_before_there_is_an_answer(self):
        self.assertEqual(len(self.tool._result_widgets), 6)                                       # the four sections, the button and the pane that holds them
        for widget in self.tool._result_widgets:
            widget.set_no_show_all.assert_called_with(True)
            widget.hide.assert_called()
            widget.show_all.assert_not_called()

    def test_the_parts_of_the_answer_appear_with_the_answer_and_go_with_a_new_question(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        for widget in self.tool._result_widgets:
            widget.show_all.assert_called()
            widget.set_no_show_all.assert_called_with(False)
            widget.hide.reset_mock()
        self.fill(engine="manual", date="1996")
        self.tool._on_ask()
        for widget in self.tool._result_widgets:
            widget.hide.assert_called()

    def test_the_button_row_writes(self):
        self.fill(engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(read(JOHNSTON))
        self.tool._on_analyse()
        self.dbstate.db.readonly = False
        self.tool._response(None, self.mod.RESPONSE_WRITE)
        self.assertIn("Select at least one proposed change first", self.tool.status.set_text.call_args.args[0])


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class ApplyTests(Base):
    """The last step, with a real Gramps database: confirm, write in one step, read the tree again."""
    def test_apply_writes_after_the_confirmation_and_the_tree_is_read_again(self):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(bajmok_tree(), path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        self.dbstate.db = db
        self.mod.Tree = Tree                                                    # the real one: read the open database
        self.fill(place="Bajmok", date="1850", engine="manual")
        if True:
            self.tool._on_ask()
            self.answer(open(SAMPLE, encoding="utf-8").read())
            self.tool._on_analyse()
            self.tool._on_level_toggled(None, "1")
            self.tool.session.select_all(include_conflicts=True)
            self.tool._refresh_checks()
            confirm = mock.MagicMock()
            confirm.run.return_value = self.gtk.ResponseType.OK
            self.gtk.MessageDialog.side_effect = lambda *a, **k: confirm
            before = len(Tree.from_db(db).places)
            self.tool._on_apply()
        self.assertEqual(self.tool.session.state, "applied")
        self.assertIn("Edit > Undo", self.tool.status.set_text.call_args.args[0])
        confirm.format_secondary_text.assert_called()
        self.assertEqual(len(self.tool.rows), 0)
        self.assertGreaterEqual(len(Tree.from_db(db).places), before)


class RegistrationTests(unittest.TestCase):
    def register(self, major=None):
        """Run the gpr file as Gramps does; `major` stands in for the version of Gramps that reads it."""
        calls = []
        names = {"register": lambda *a, **k: calls.append((a, k)), "TOOL": "TOOL", "GRAMPLET": "GRAMPLET", "TOOL_DBPROC": "DBPROC",
                 "TOOL_MODE_GUI": "GUI", "EXPERIMENTAL": "EXPERIMENTAL", "QUICKREPORT": "QUICKREPORT", "CATEGORY_QR_PLACE": 4}
        stub = {}
        if major is not None:
            stub = {"gramps.version": types.SimpleNamespace(major_version=major)}
        with mock.patch.dict(sys.modules, stub):
            with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
                exec(compile(fh.read(), "PlaceCompleter.gpr.py", "exec"), names)
        self.calls = calls
        tool = [c for c in calls if c[0][0] == "TOOL"]
        (args, kw), = tool
        return args, kw

    def test_the_gpr_registers_the_tool_with_names_that_exist(self):
        args, kw = self.register()
        self.assertEqual((args, kw["id"], kw["fname"], kw["toolclass"], kw["optionclass"]),
                         (("TOOL",), "placecompleter", "placecompleter_tool.py", "PlaceCompleterTool", "PlaceCompleterOptions"))
        self.assertEqual((kw["category"], kw["tool_modes"]), ("DBPROC", ["GUI"]))
        self.assertTrue(os.path.exists(os.path.join(ROOT, kw["fname"])))
        source = open(os.path.join(ROOT, kw["fname"]), encoding="utf-8").read()
        self.assertIn("class %s(" % kw["toolclass"], source)
        self.assertIn("class %s(" % kw["optionclass"], source)

    def test_it_names_the_running_version_when_that_one_was_tested(self):
        for major in ("6.0", "6.1"):
            self.assertEqual(self.register(major)[1]["gramps_target_version"], major)
            self.assertEqual({k["gramps_target_version"] for _a, k in self.calls}, {major})            # the gramplet too

    def test_the_names_are_given_through_the_underscore_that_gramps_provides(self):
        """Gramps runs the file with its own _ (Gramps first, then the locale folder of the addon): the file must not replace it, or the names stay English."""
        import placecompleter
        calls = []
        names = {"register": lambda *a, **k: calls.append((a, k)), "TOOL": "TOOL", "GRAMPLET": "GRAMPLET", "TOOL_DBPROC": "DBPROC", "TOOL_MODE_GUI": "GUI",
                 "EXPERIMENTAL": "EXPERIMENTAL", "QUICKREPORT": "QUICKREPORT", "CATEGORY_QR_PLACE": 4, "_": lambda text: "T<" + text + ">"}
        with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
            exec(compile(fh.read(), "PlaceCompleter.gpr.py", "exec"), names)
        self.assertTrue(calls)
        for _args, kw in calls:
            self.assertTrue(kw["name"].startswith("T<Place Completer"), kw["name"])
            self.assertTrue(kw["description"].startswith("T<"), kw["description"])
            self.assertEqual(kw["status"], "EXPERIMENTAL", kw["name"])                              # (it is experimental: the addon manager says so)
            self.assertEqual(kw["help_url"], placecompleter.GUIDE_URL, kw["name"])                   # (the Help of a gramplet opens the user guide)
        self.assertEqual(names["_"]("x"), "T<x>")                                                   # the file kept the _ that Gramps gave

    def registered(self, kind, id_):
        self.register()
        (args, kw), = [c for c in self.calls if c[0][0] == kind and c[1]["id"] == id_]
        return kw

    def test_the_gpr_also_registers_the_gramplet_for_the_events_view(self):
        kw = self.registered("GRAMPLET", "placecompleter-gramplet")
        self.assertEqual((kw["fname"], kw["gramplet"], kw["navtypes"]), ("placecompleter_gramplet.py", "PlaceCompleterGramplet", ["Event"]))
        source = open(os.path.join(ROOT, kw["fname"]), encoding="utf-8").read()
        self.assertTrue(os.path.exists(os.path.join(ROOT, kw["fname"])))
        self.assertIn("class %s(Gramplet)" % kw["gramplet"], source)

    def test_the_gpr_registers_a_gramplet_for_the_places_view_too(self):
        kw = self.registered("GRAMPLET", "placecompleter-place-gramplet")
        self.assertEqual((kw["fname"], kw["gramplet"], kw["navtypes"]), ("placecompleter_gramplet.py", "PlaceCompleterPlaceGramplet", ["Place"]))
        self.assertIn("class %s(" % kw["gramplet"], open(os.path.join(ROOT, kw["fname"]), encoding="utf-8").read())

    def test_the_gpr_puts_an_entry_in_the_right_click_menu_of_places_without_touching_gramps(self):
        kw = self.registered("QUICKREPORT", "placecompleter-quickview")
        self.assertEqual((kw["fname"], kw["runfunc"], kw["category"]), ("placecompleter_quickview.py", "run", 4))       # CATEGORY_QR_PLACE
        source = open(os.path.join(ROOT, kw["fname"]), encoding="utf-8").read()
        self.assertIn("def %s(database, document, place)" % kw["runfunc"], source)

    def test_every_registration_has_its_own_id_and_the_version_of_the_running_gramps(self):
        self.register("6.1")
        ids = [k["id"] for _a, k in self.calls]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 4)
        self.assertEqual({k["gramps_target_version"] for _a, k in self.calls}, {"6.1"})

    def test_any_other_version_declines_it_on_purpose(self):
        for major in ("6.2", "7.0", "5.1"):
            self.assertEqual(self.register(major)[1]["gramps_target_version"], "6.0" if major != "6.0" else "6.0")
        # "6.0" is not the running version there, so Gramps' own rule rejects it:
        self.assertNotEqual(self.register("6.2")[1]["gramps_target_version"], "6.2")

    def test_gramps_itself_accepts_what_the_gpr_names_for_the_gramps_that_runs_the_tests(self):
        try:
            from gramps.gen.plug._pluginreg import valid_plugin_version
        except Exception:                                                     # pragma: no cover
            self.skipTest("the plugin registry of Gramps cannot be imported here")
        self.assertTrue(valid_plugin_version(self.register()[1]["gramps_target_version"]))

    def test_the_rule_of_gramps_rejects_6_0_in_6_1_which_is_why_the_gpr_follows_the_version(self):
        try:
            from gramps.gen.plug import _pluginreg
        except Exception:                                                     # pragma: no cover
            self.skipTest("the plugin registry of Gramps cannot be imported here")
        with mock.patch.object(_pluginreg, "VERSION_TUPLE", (6, 1, 0)):
            self.assertFalse(_pluginreg.valid_plugin_version("6.0"))
            self.assertTrue(_pluginreg.valid_plugin_version("6.1"))
        with mock.patch.object(_pluginreg, "VERSION_TUPLE", (6, 0, 8)):
            self.assertTrue(_pluginreg.valid_plugin_version("6.0"))
            self.assertFalse(_pluginreg.valid_plugin_version("6.1"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class WikidataWindowTests(Base):
    """Coordinates from Wikidata, in the background: the screen appears at once and is updated when Wikidata has answered."""
    JOHNSTON = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCOORDINATES: 41.673, -93.6977\nCONTAINERS:\n"
                "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")

    def setUp(self):
        super().setUp()
        from test_geo import ENTITIES, SEARCH, FakeClient
        self.tree = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1), "city": typed("city", "Johnston", 4, lang="en")}, [])
        self.patch_lookup(lambda client, targets, articles=(): self.asked_wikidata.append(targets) or REAL_LOOKUP_MANY(FakeClient(SEARCH, ENTITIES), targets))
        self.saved, self.client_args = [], []
        patcher = mock.patch.object(self.mod.wikidata, "Client",
                                    lambda **kw: self.client_args.append(kw) or types.SimpleNamespace(save=lambda: self.saved.append(True)))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tool.c_wikidata.get_active.return_value = True

    def analyse(self):
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(self.JOHNSTON)
        self.tool._on_analyse()

    def texts(self):
        return [step.__getitem__(2) for row in self.tool.rows for step in row.children]

    def test_the_checkbox_is_there_on_by_default_and_remembered(self):
        self.assertEqual(self.gtk.CheckButton.call_args.kwargs["label"], "Look up coordinates on Wikidata (only place names are sent)")
        self.fill(engine="google")
        self.tool.c_wikidata.get_active.return_value = False
        self.tool._on_ask()
        self.assertFalse(self.tool._load_prefs()["wikidata"])

    def test_after_the_answer_wikidata_is_asked_and_the_screen_shows_what_it_said(self):
        self.analyse()
        (targets,) = self.asked_wikidata
        self.assertEqual(sorted(t["name"] for t in targets), ["Iowa", "Johnston", "Polk County"])
        self.assertTrue(any("coordinates 41.6849, -93.5738 from Wikidata Q2" in x for x in self.texts()))
        self.assertTrue(any("Set missing coordinates for «Johnston [CITY]»: 41.6856, -93.7172 (from Wikidata Q1 «Johnston»)" in r[2] for r in self.tool.rows))
        self.assertIn("Wikidata queried: 3 place(s) populated with coordinates.", self.tool.status.set_text.call_args.args[0])

    def test_the_cache_is_the_users_and_is_saved(self):
        self.analyse()
        self.assertEqual(self.client_args[0]["cache_path"], self.mod.WIKIDATA_CACHE)
        self.assertEqual(self.saved, [True])

    def test_with_the_box_off_nothing_is_sent(self):
        self.tool.c_wikidata.get_active.return_value = False
        self.analyse()
        self.assertEqual((self.asked_wikidata, self.client_args), ([], []))

    def test_what_was_checked_stays_checked(self):
        self.tool.c_wikidata.get_active.return_value = False
        self.analyse()
        self.tool._on_row_toggled(None, "0")
        checked = [row[1] for row in self.tool.rows if row[0]]
        self.assertTrue(checked)
        self.tool.c_wikidata.get_active.return_value = True
        self.tool._start_wikidata()
        self.assertEqual([row[1] for row in self.tool.rows if row[0]], checked)

    def test_a_failure_of_wikidata_is_said_and_nothing_is_lost(self):
        self.patch_lookup(lambda client, targets, articles=(): (_ for _ in ()).throw(OSError("no network")))
        self.analyse()
        self.assertIn("Could not query Wikidata: no network", self.tool.status.set_text.call_args.args[0])
        self.assertGreaterEqual(len(self.tool.rows), 1)

    def test_an_answer_for_an_old_question_is_ignored(self):
        self.analyse()
        old_session, old_token = self.tool.session, self.tool._wiki_token
        self.fill(place="Bajmok", engine="manual", date="1850")
        self.tool._on_ask()                                                        # a new question: a new session
        applied = []
        self.tool.session.apply_coordinates = lambda f: applied.append(f) or 0
        self.tool._after_wikidata(old_session, {"x": {"found": False}}, old_token)
        self.assertEqual(applied, [])
        self.tool._after_wikidata(self.tool.session, {"x": {"found": False}}, old_token)       # the same session but an older step
        self.assertEqual(applied, [])

    def test_when_every_place_has_its_coordinates_nothing_is_asked(self):
        for key in ("iowa", "city"):
            self.tree.places[key]["lat"], self.tree.places[key]["lon"] = "41.67", "-93.7"                          # (near the place of the answer: ID1)
        text = self.JOHNSTON.replace("Polk County", "Johnston County")
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(text)
        self.tool._on_analyse()
        names = [t["name"] for targets in self.asked_wikidata for t in targets]
        self.assertEqual(names, ["Johnston County"])                                  # only the one place that will be created


class AmbiguityWindowTests(Base):
    """A level that could be several places of the tree: the window asks, and nothing is created before the user has chosen."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | United States of America | country | 1776-present | United States\n")

    def setUp(self):
        super().setUp()
        self.tree = Tree({"usa": typed("usa", "USA", 1, lang="en"), "usa2": typed("usa2", "United States of America", 1, lang="en"),
                          "city": typed("city", "Johnston", 4, lang="en")}, [])
        self.asked = []

    def analyse(self, chooser):
        def choose(unit):
            self.asked.append(unit)
            return chooser(unit)
        self.tool._choose_dialog = choose
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(self.ANSWER)
        self.tool._on_analyse()

    def test_the_window_asks_and_uses_the_choice(self):
        self.analyse(lambda unit: "usa2")
        (unit,) = self.asked
        self.assertEqual((unit["slot"], unit["name"]), ("c2", "United States of America"))
        self.assertEqual(self.tool.session.choices, {"c2": "usa2"})
        self.assertEqual(self.tool.session.ambiguous_units(), [])
        self.assertTrue(any("United States of America [USA2]" in step[2] for row in self.tool.rows for step in row.children))

    def test_cancelling_leaves_the_level_out_and_says_so(self):
        self.analyse(lambda unit: None)
        self.assertEqual(len(self.asked), 1)                                            # not asked again and again
        self.assertTrue(self.tool.session.ambiguous_units())
        self.assertGreaterEqual(len(self.tool.rows), 1)
        self.assertFalse([p for p in self.tool.session.result["proposals"] if p["kind"] == "add-place" and "United States" in p["names"][0]["value"]])

    def test_several_levels_are_asked_one_after_the_other(self):
        self.tree.places["iowa"] = typed("iowa", "Iowa", 2, lang="en")
        self.tree.places["iowa2"] = typed("iowa2", "Iowa", 2, lang="en")                 # two places called Iowa: the first level is ambiguous too
        text = self.ANSWER.replace("Polk County | county | 1846-present | Iowa", "Iowa | state | 1846-present | United States")
        self.tool._choose_dialog = lambda unit: self.asked.append(unit) or unit["candidates"][0]["handle"]
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer(text)
        self.tool._on_analyse()
        self.assertEqual([u["slot"] for u in self.asked], ["c1", "c2"])
        self.assertEqual(self.tool.session.ambiguous_units(), [])

    def test_the_dialog_offers_the_candidates_a_new_place_and_leaving_it_out(self):
        radios = []
        self.gtk.RadioButton.new_with_label_from_widget.side_effect = lambda first, label: radios.append(types.SimpleNamespace(
            label=label, first=first, get_active=lambda: False)) or radios[-1]
        dialog = mock.MagicMock()
        dialog.run.return_value = self.gtk.ResponseType.CANCEL
        self.gtk.Dialog.side_effect = lambda *a, **k: dialog
        unit = {"slot": "c2", "name": "United States of America", "type": "country",
                "candidates": [{"handle": "usa", "label": "USA [P0122]", "score": 12}, {"handle": "usa2", "label": "United States of America [P0256]", "score": 12}]}
        self.assertIsNone(self.tool._choose_dialog(unit))
        self.assertEqual([r.label for r in radios], ["USA [P0122]", "United States of America [P0256]", "New place «United States of America»", "Exclude this level"])
        self.assertIsNone(radios[0].first)                                               # one group
        self.assertTrue(all(r.first is radios[0] for r in radios[1:]))

    def test_the_dialog_returns_what_was_chosen(self):
        for index, expected in ((1, "usa2"), (2, "new"), (3, "skip")):
            radios = []
            self.gtk.RadioButton.new_with_label_from_widget.side_effect = lambda first, label, n=index: radios.append(types.SimpleNamespace(
                first=first, get_active=lambda i=len(radios): i == n)) or radios[-1]
            dialog = mock.MagicMock()
            dialog.run.return_value = self.gtk.ResponseType.OK
            self.gtk.Dialog.side_effect = lambda *a, **k: dialog
            unit = {"slot": "c2", "name": "X", "type": "country", "candidates": [{"handle": "usa", "label": "A", "score": 12}, {"handle": "usa2", "label": "B", "score": 12}]}
            self.assertEqual(self.tool._choose_dialog(unit), expected)
            dialog.destroy.assert_called()

    def test_no_wikidata_question_while_a_choice_is_pending_and_one_after(self):
        self.tool.c_wikidata.get_active.return_value = True
        self.analyse(lambda unit: "usa2")
        self.assertTrue(self.asked_wikidata)                                             # asked once the answer is complete


class HebrewWindowTests(Base):
    """With the Hebrew installed the flags of the table are the words of the catalogue, not the English ones."""
    def setUp(self):
        super().setUp()
        import gettext
        import io
        from placecompleter import msgfmt
        catalog = msgfmt.parse_po(open(os.path.join(ROOT, "po", "he-local.po"), encoding="utf-8").read())
        self.hebrew = gettext.GNUTranslations(io.BytesIO(msgfmt.compile_mo(catalog)))
        self.mod._ = self.hebrew.gettext
        from placecompleter import i18n
        i18n.set_translator(self.hebrew.gettext)
        self.addCleanup(lambda: i18n.set_translator(None))

    def test_the_basis_and_the_flag_of_a_change_are_in_hebrew(self):
        self.tree = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
                          "city": typed("city", "Johnston", 4, lang="en")}, [])
        self.fill(place="Johnston", engine="manual", date="1995")
        self.tool._on_ask()
        self.answer("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk County | county | 1846-present | Iowa\n"
                    "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n")
        self.tool._on_analyse()
        levels = {row[3] for row in self.tool.rows if row[3]}
        flags = {row[4] for row in self.tool.rows}
        words = {self.hebrew.gettext(w) for w in ("Confirmed", "Reported", "Inferred", "Unsure")}
        self.assertEqual(len(words), 4)                                                                       # four different words, all translated
        self.assertFalse(words & {"Confirmed", "Reported", "Inferred", "Unsure"})
        self.assertTrue(levels and levels <= words, levels)
        self.assertIn(self.hebrew.gettext("populates unassigned field"), flags)

    def test_the_conflict_flag_is_a_word_in_hebrew(self):
        self.assertNotEqual(self.hebrew.gettext("CONFLICT"), "CONFLICT")                      # it is translated
