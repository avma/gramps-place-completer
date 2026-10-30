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
"""The gramplet of the Events view: what it reads from an event (tested with a real Gramps database) and how it opens the window."""
import importlib.util
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.lib import Date, Event, EventType
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import grampslink                                                       # noqa: E402
from test_tool_window import make_modules                                                   # noqa: E402


def gramps_date(**kw):
    d = Date()
    d.set(**kw)
    return d


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class DateTextTests(unittest.TestCase):
    def check(self, date, text, note=""):
        self.assertEqual(grampslink.date_text(date), (text, note))

    def test_a_year_a_month_and_a_day(self):
        self.check(gramps_date(modifier=Date.MOD_NONE, value=(0, 0, 1850, False)), "1850")
        self.check(gramps_date(modifier=Date.MOD_NONE, value=(0, 5, 1850, False)), "1850-05")
        self.check(gramps_date(modifier=Date.MOD_NONE, value=(14, 5, 1850, False)), "1850-05-14")

    def test_a_year_of_one_to_three_digits_is_not_padded(self):
        self.check(gramps_date(modifier=Date.MOD_NONE, value=(0, 0, 900, False)), "900")

    def test_about_before_after_and_estimated_use_the_year_they_name(self):
        for modifier in (Date.MOD_ABOUT, Date.MOD_BEFORE, Date.MOD_AFTER):
            self.check(gramps_date(modifier=modifier, value=(0, 0, 1850, False)), "1850")
        self.check(gramps_date(quality=Date.QUAL_ESTIMATED, modifier=Date.MOD_NONE, value=(0, 0, 1850, False)), "1850")

    def test_a_range_or_a_span_uses_its_first_date_and_says_so(self):
        for modifier in (Date.MOD_RANGE, Date.MOD_SPAN):
            text, note = grampslink.date_text(gramps_date(modifier=modifier, value=(1, 1, 1850, False, 31, 12, 1860, False)))
            self.assertEqual((text, note), ("1850-01-01", "the first date of the range is used"))

    def test_a_julian_date_is_converted_to_the_gregorian_calendar(self):
        text, note = grampslink.date_text(gramps_date(calendar=Date.CAL_JULIAN, modifier=Date.MOD_NONE, value=(1, 1, 1850, False)))
        self.assertEqual((text, note), ("1850-01-13", "converted to the Gregorian calendar"))

    def test_no_date_only_text_and_no_year_give_nothing_and_say_why(self):
        self.check(Date(), "", "the event has no date")
        self.check(gramps_date(modifier=Date.MOD_TEXTONLY, text="in the time of the flood"), "", "the date is only text: type the year in the window")
        self.assertEqual(grampslink.date_text(None), ("", "the event has no date"))

    def test_the_text_is_one_the_engine_accepts(self):
        from placecompleter.complete import parse_date
        for text in ("1850", "1850-05", "1850-05-14", "900"):
            parse_date(text)


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class EventSummaryTests(unittest.TestCase):
    def setUp(self):
        from test_ingest import tree
        from test_writer import IngestWriterTests
        self.path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(self.path), ignore_errors=True))
        IngestWriterTests().build_from(tree(), self.path)
        self.db = make_database("sqlite")
        self.db.load(self.path)
        self.addCleanup(self.db.close)

    def event(self, place, **date):
        ev = Event()
        ev.set_type(EventType.RESIDENCE)
        if place:
            ev.set_place_handle(place)
        ev.set_date_object(gramps_date(**date) if date else Date())
        with DbTxn("event", self.db) as txn:
            self.db.add_event(ev, txn)
        return ev

    def test_an_event_with_a_complete_chain(self):
        s = grampslink.event_summary(self.db, self.event("baj", modifier=Date.MOD_NONE, value=(0, 0, 1900, False)))
        self.assertEqual((s["type"], s["date_text"], s["place_name"], s["place_handle"]), ("Residence", "1900", "Bajmok", "baj"))
        self.assertEqual(s["shown"], "Bajmok, Bácsalmási járás, Bács-Bodrog vármegye, Magyarország")
        self.assertFalse(s["incomplete"])

    def test_missing_names_are_flagged_by_the_question_mark_gramps_shows(self):
        s = grampslink.event_summary(self.db, self.event("zk", modifier=Date.MOD_NONE, value=(0, 0, 1840, False)))      # the name starts in 1849
        self.assertIn("?", s["shown"])
        self.assertTrue(s["incomplete"])

    def test_an_event_without_a_place_or_a_date(self):
        s = grampslink.event_summary(self.db, self.event(None))
        self.assertEqual((s["place_name"], s["shown"], s["incomplete"], s["date_text"], s["date_note"]),
                         ("", "", False, "", "the event has no date"))

    def test_the_date_note_is_carried(self):
        s = grampslink.event_summary(self.db, self.event("baj", modifier=Date.MOD_SPAN, value=(1, 1, 1850, False, 31, 12, 1860, False)))
        self.assertEqual((s["date_text"], s["date_note"]), ("1850-01-01", "the first date of the range is used"))


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class PlaceSummaryTests(unittest.TestCase):
    def open(self):
        from placecompleter.model import Tree
        from test_engine import EMPTY
        from test_ingest import typed
        from test_writer import IngestWriterTests
        tree = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "city": typed("city", "Johnston", -1)}, [])
        tree.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(tree, path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        return db

    def test_a_place_that_lacks_everything_says_so(self):
        db = self.open()
        s = grampslink.place_summary(db, db.get_place_from_handle("city"))
        self.assertEqual(s["missing"], ["coordinates", "type", "name language", "cited source"])
        self.assertEqual((s["place_name"], s["shown"], s["gramps_id"], s["place_handle"]), ("Johnston", "Johnston, Iowa", s["gramps_id"], "city"))
        self.assertFalse(s["incomplete"])

    def test_a_place_that_has_it_all_lacks_nothing(self):
        from gramps.gen.db import DbTxn
        from gramps.gen.lib import Citation, Source
        db = self.open()
        place = db.get_place_from_handle("city")
        place.set_latitude("41.68")
        place.set_longitude("-93.71")
        place.set_type(4)
        place.get_name().set_language("en")
        with DbTxn("fill", db) as txn:
            source = Source()
            source.set_title("s")
            citation = Citation()
            citation.set_reference_handle(db.add_source(source, txn))
            place.add_citation(db.add_citation(citation, txn))
            db.commit_place(place, txn)
        self.assertEqual(grampslink.place_summary(db, db.get_place_from_handle("city"))["missing"], [])

    def test_only_one_coordinate_is_still_missing_coordinates(self):
        db = self.open()
        place = db.get_place_from_handle("city")
        place.set_latitude("41.68")
        self.assertIn("coordinates", grampslink.place_summary(db, place)["missing"])


class GrampletTests(unittest.TestCase):
    """The gramplet file, with stand-ins for GTK and the Gramps GUI: its handlers are called and what they do is checked."""
    def setUp(self):
        self.log = {}
        modules, self.gtk = make_modules(self.log)
        user_module = types.ModuleType("gramps.gui.user")
        self.users = []
        user_module.User = lambda **kw: self.users.append(kw) or types.SimpleNamespace(uistate=kw.get("uistate"))
        modules["gramps.gui.user"] = user_module
        modules["gramps.gui"].user = user_module
        patcher = mock.patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)

        class StubGramplet:
            def __init__(self, gui, nav_group=0):
                self.gui, self.dbstate, self.uistate = gui, gui.dbstate, gui.uistate
                self.connected, self.signals, self.updates = [], [], 0
                self.active = None
                self.init()

            def connect(self, obj, signal, method):
                self.connected.append(signal)

            def connect_signal(self, nav_type, method):
                self.signals.append(nav_type)

            def update(self, *a):
                self.updates += 1
                for _ in self.main():
                    pass

            def get_active_object(self, nav_type):
                if isinstance(self.active, Exception):
                    raise self.active
                return self.active

        import gramps.gen.plug as plug
        patch2 = mock.patch.object(plug, "Gramplet", StubGramplet, create=True)
        patch2.start()
        self.addCleanup(patch2.stop)
        spec = importlib.util.spec_from_file_location("placecompleter_gramplet_under_test", os.path.join(ROOT, "placecompleter_gramplet.py"))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.opened = []

        class FakeTool:
            def __init__(inner, dbstate, user, options, name, prefill=None):
                self.opened.append({"user": user, "options": options, "name": name, "prefill": prefill})
                if getattr(self, "already_open", False):
                    from gramps.gen.errors import WindowActiveError
                    raise WindowActiveError("already")
        fake = types.ModuleType("placecompleter_tool")
        fake.PlaceCompleterTool, fake.PlaceCompleterOptions = FakeTool, type("Options", (), {})
        patch3 = mock.patch.dict(sys.modules, {"placecompleter_tool": fake})
        patch3.start()
        self.addCleanup(patch3.stop)
        gui = types.SimpleNamespace(dbstate=mock.MagicMock(), uistate=mock.MagicMock(), textview=mock.MagicMock(), get_container_widget=mock.MagicMock())
        gui.dbstate.is_open.return_value = True
        self.gui = gui
        self.g = self.mod.PlaceCompleterGramplet(gui)
        self.pg = self.mod.PlaceCompleterPlaceGramplet(gui)

    def place_summary(self, **kw):
        s = {"type": "Place", "date_text": "", "date_note": "", "place_handle": "h", "place_name": "Johnston", "shown": "Johnston, Polk County, Iowa, USA",
             "incomplete": False, "missing": ["coordinates", "type"], "gramps_id": "P0087"}
        s.update(kw)
        return s

    def show_place(self, summary):
        with mock.patch.object(self.mod.grampslink, "place_summary", lambda db, place: summary):
            self.pg.active = object()
            self.pg.update()

    def summary(self, **kw):
        s = {"type": "Residence", "date_text": "1850", "date_note": "", "place_handle": "h", "place_name": "Bajmok",
             "shown": "Bajmok, Bácsalmási járás", "incomplete": False}
        s.update(kw)
        return s

    def show(self, summary):
        with mock.patch.object(self.mod.grampslink, "event_summary", lambda db, ev: summary):
            self.g.active = object()
            self.g.update()

    def test_the_places_gramplet_follows_the_active_place_and_the_database(self):
        self.pg.db_changed()
        self.assertEqual(self.pg.connected, ["place-update", "event-update"])
        self.assertEqual(self.pg.signals, ["Place"])

    def test_the_places_gramplet_shows_the_place_what_gramps_shows_and_what_it_lacks(self):
        self.show_place(self.place_summary())
        self.assertEqual(self.pg.l_event.set_text.call_args.args[0], "Johnston [P0087]")
        self.assertEqual(self.pg.l_shown.set_text.call_args.args[0], "Gramps currently displays: Johnston, Polk County, Iowa, USA")
        self.assertEqual(self.pg.l_note.set_text.call_args.args[0], "Missing data: coordinates, type")
        self.pg.b_open.set_sensitive.assert_called_with(True)

    def test_a_place_that_lacks_nothing_says_so(self):
        self.show_place(self.place_summary(missing=[]))
        self.assertEqual(self.pg.l_note.set_text.call_args.args[0], "Analyze the response, then choose which changes to apply.")

    def test_a_place_without_a_name_is_still_shown(self):
        self.show_place(self.place_summary(place_name=""))
        self.assertEqual(self.pg.l_event.set_text.call_args.args[0], "(no name) [P0087]")

    def test_with_no_place_selected_the_button_is_off(self):
        self.pg.active = None
        self.pg.update()
        self.assertEqual(self.pg.l_event.set_text.call_args.args[0], "Select a place.")
        self.pg.b_open.set_sensitive.assert_called_with(False)

    def test_the_button_opens_the_window_with_the_name_of_the_place_and_no_date(self):
        self.show_place(self.place_summary())
        self.pg._on_open()
        (call,) = self.opened
        self.assertEqual(call["prefill"], {"place": "Johnston", "date": "", "hint": ""})

    def test_the_places_gramplet_says_when_the_window_is_already_open(self):
        self.already_open = True
        self.show_place(self.place_summary())
        self.pg._on_open()
        self.assertIn("already open", self.pg.l_note.set_text.call_args.args[0])

    def test_the_two_gramplets_do_not_share_what_they_show(self):
        self.show(self.summary())
        self.show_place(self.place_summary())
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Residence, 1850")
        self.assertEqual(self.pg.l_event.set_text.call_args.args[0], "Johnston [P0087]")

    def test_the_widget_replaces_the_text_view_of_the_gramplet(self):
        self.gui.get_container_widget.return_value.remove.assert_called_with(self.gui.textview)
        self.gui.get_container_widget.return_value.add.assert_called_with(self.gui.WIDGET)

    def test_it_follows_the_active_event_and_the_database(self):
        self.g.db_changed()
        self.assertEqual(self.g.connected, ["event-update", "place-update"])
        self.assertEqual(self.g.signals, ["Event"])
        before = self.g.updates
        self.g.active_changed("handle")
        self.assertEqual(self.g.updates, before + 1)

    def test_it_shows_the_event_its_place_and_what_gramps_shows(self):
        self.show(self.summary())
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Residence, 1850")
        self.assertEqual(self.g.l_shown.set_text.call_args.args[0], "Gramps currently displays: Bajmok, Bácsalmási járás")
        self.g.b_open.set_sensitive.assert_called_with(True)

    def test_missing_names_are_pointed_out(self):
        self.show(self.summary(shown="?, Zombori kerület", incomplete=True))
        self.assertIn("Names are missing for this date", self.g.l_note.set_text.call_args.args[0])

    def test_the_note_about_the_date_is_shown_when_nothing_is_missing(self):
        self.show(self.summary(date_note="the first date of the range is used"))
        self.assertEqual(self.g.l_note.set_text.call_args.args[0], "the first date of the range is used")

    def test_an_event_without_a_date_or_a_place_is_described(self):
        self.show(self.summary(date_text="", shown="", place_name="", place_handle=""))
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Residence, no valid date")
        self.assertEqual(self.g.l_shown.set_text.call_args.args[0], "This event has no place assigned.")

    def test_with_no_event_selected_the_button_is_off(self):
        self.g.active = None
        self.g.update()
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Select an event.")
        self.g.b_open.set_sensitive.assert_called_with(False)

    def test_an_event_that_no_longer_exists_is_not_an_error(self):
        self.g.active = KeyError("gone")
        self.g.update()
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Select an event.")

    def test_with_no_database_open_nothing_is_read(self):
        self.gui.dbstate.is_open.return_value = False
        self.g.active = object()
        self.g.update()
        self.assertEqual(self.g.l_event.set_text.call_args.args[0], "Select an event.")

    def test_the_button_opens_the_window_with_the_place_and_the_date_of_the_event(self):
        self.show(self.summary())
        self.g._on_open()
        (call,) = self.opened
        self.assertEqual((call["prefill"], call["name"]), ({"place": "Bajmok", "date": "1850", "hint": ""}, "placecompleter"))
        self.assertEqual(self.users[0]["uistate"], self.gui.uistate)

    def test_the_button_passes_the_highest_place_above_as_the_hint(self):
        self.show(self.summary(place_name="Trecasali", date_text="1990", top_name="Italy"))
        self.g._on_open()
        (call,) = self.opened
        self.assertEqual(call["prefill"], {"place": "Trecasali", "date": "1990", "hint": "Italy"})

    def test_an_event_without_a_place_opens_it_with_only_the_date(self):
        self.show(self.summary(place_name="", place_handle="", shown=""))
        self.g._on_open()
        self.assertEqual(self.opened[0]["prefill"], {"place": "", "date": "1850", "hint": ""})

    def test_a_window_that_is_already_open_is_said_not_raised(self):
        self.already_open = True
        self.show(self.summary())
        self.g._on_open()
        self.assertIn("already open", self.g.l_note.set_text.call_args.args[0])

    def test_the_button_does_nothing_without_an_event(self):
        self.g.active = None
        self.g.update()
        self.g._on_open()
        self.assertEqual(self.opened, [])


class QuickViewTests(unittest.TestCase):
    """The entry in the right-click menu of the Places view: it opens the window and tells a few lines about the place."""
    def setUp(self):
        spec = importlib.util.spec_from_file_location("placecompleter_quickview_under_test", os.path.join(ROOT, "placecompleter_quickview.py"))
        self.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.mod)
        self.opened = []
        self.mod.open_window = lambda dbstate, uistate, place, date, hint="": self.opened.append((dbstate, uistate, place, date, hint)) or self.result
        self.result = True
        self.doc = mock.MagicMock()
        self.doc.dbstate, self.doc.uistate = object(), object()
        self.summary = {"place_name": "Johnston", "gramps_id": "P0087", "shown": "Johnston, Iowa", "missing": ["coordinates"]}
        patcher = mock.patch.object(self.mod.grampslink, "place_summary", lambda db, place: self.summary)
        patcher.start()
        self.addCleanup(patcher.stop)

    def written(self):
        return " | ".join(c.args[0] for c in self.doc.write_text.call_args_list)

    def test_it_opens_the_window_with_the_place_and_no_date(self):
        self.mod.run(object(), self.doc, object())
        ((dbstate, uistate, place, date, hint),) = self.opened
        self.assertEqual((dbstate, uistate, place, date, hint), (self.doc.dbstate, self.doc.uistate, "Johnston", "", ""))

    def test_it_tells_about_the_place_in_the_small_window_that_gramps_shows(self):
        self.mod.run(object(), self.doc, object())
        text = self.written()
        self.assertIn("Johnston [P0087]", text)
        self.assertIn("Gramps currently displays: Johnston, Iowa", text)
        self.assertIn("Missing data: coordinates", text)
        self.assertIn("Place Completer opened for this place", text)

    def test_when_the_window_is_already_open_it_says_so(self):
        self.result = False
        self.mod.run(object(), self.doc, object())
        self.assertIn("already open", self.written())

    def test_a_place_that_lacks_nothing(self):
        self.summary["missing"] = []
        self.mod.run(object(), self.doc, object())
        self.assertIn("Analyze the response, then choose which changes to apply.", self.written())


class OpenWindowTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.fail = False
        users = types.ModuleType("gramps.gui.user")
        users.User = lambda **kw: self.calls.append(("user", kw)) or types.SimpleNamespace(uistate=kw.get("uistate"))
        gui = types.ModuleType("gramps.gui")
        gui.user = users

        class FakeTool:
            def __init__(inner, dbstate, user, options, name, prefill=None):
                self.calls.append(("tool", prefill))
                if self.fail:
                    from gramps.gen.errors import WindowActiveError
                    raise WindowActiveError("already")
        fake = types.ModuleType("placecompleter_tool")
        fake.PlaceCompleterTool, fake.PlaceCompleterOptions = FakeTool, type("Options", (), {})
        patcher = mock.patch.dict(sys.modules, {"gramps.gui": gui, "gramps.gui.user": users, "placecompleter_tool": fake})
        patcher.start()
        self.addCleanup(patcher.stop)
        import placecompleter_open
        self.open = placecompleter_open.open_window

    def test_the_window_is_opened_with_the_place_and_the_date(self):
        self.assertTrue(self.open("db", "ui", "Bajmok", "1850"))
        self.assertEqual(self.calls, [("user", {"uistate": "ui", "dbstate": "db"}), ("tool", {"place": "Bajmok", "date": "1850", "hint": ""})])

    def test_the_highest_place_goes_as_the_hint(self):
        self.assertTrue(self.open("db", "ui", "Trecasali", "1990", "Italy"))
        self.assertEqual(self.calls[1], ("tool", {"place": "Trecasali", "date": "1990", "hint": "Italy"}))

    def test_a_window_that_is_already_open_is_not_an_error(self):
        self.fail = True
        self.assertFalse(self.open("db", "ui", "Bajmok", "1850"))


class OpenWindowAfterGrampsLoadTests(unittest.TestCase):
    """Gramps puts the folder of a plugin on sys.path only while it imports the plugin, then takes it off again (import_plugin in
    gramps/gen/plug/_manager.py does sys.path.pop(0)). A click comes long after that, so the opener must not rely on the path: this
    runs the real opener in a clean interpreter that does what Gramps does, with the tool module not yet imported (as when the Tools
    menu was never used), and no stand-in for placecompleter_tool in sys.modules."""

    SCRIPT = """
import os, sys, types
folder = sys.argv[1]
sys.path.insert(0, folder)
import placecompleter_open                       # Gramps loading a gramplet that imports it
sys.path.pop(0)                                  # what Gramps does right after the import
assert folder not in sys.path
users = types.ModuleType("gramps.gui.user")
users.User = lambda **kw: types.SimpleNamespace(**kw)
gui = types.ModuleType("gramps.gui")
gui.user = users
sys.modules.update({"gramps.gui": gui, "gramps.gui.user": users})
print("opened" if placecompleter_open.open_window("db", "ui", "Bajmok", "1850") else "already")
print("path-clean" if folder not in sys.path else "path-left-changed")
"""

    TOOL = """
calls = []
class PlaceCompleterOptions: pass
class PlaceCompleterTool:
    def __init__(self, dbstate, user, options, name, prefill=None):
        print("tool", dbstate, name, prefill)
"""

    def run_opener(self):
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(ROOT, "placecompleter_open.py"), encoding="utf-8") as src:
                with open(os.path.join(folder, "placecompleter_open.py"), "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            with open(os.path.join(folder, "placecompleter_tool.py"), "w", encoding="utf-8") as dst:
                dst.write(self.TOOL)
            with tempfile.TemporaryDirectory() as elsewhere:                # not the plugin folder: "" on sys.path would find the module
                return subprocess.run([sys.executable, "-c", self.SCRIPT, folder], capture_output=True, text=True, env=dict(os.environ),
                                      cwd=elsewhere)

    def test_the_tool_module_is_found_after_gramps_took_the_folder_off_the_path(self):
        done = self.run_opener()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("tool db placecompleter {'place': 'Bajmok', 'date': '1850', 'hint': ''}", done.stdout)
        self.assertIn("opened", done.stdout)

    def test_the_path_is_left_as_it_was(self):
        done = self.run_opener()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("path-clean", done.stdout)


class ToolPrefillTests(unittest.TestCase):
    def test_the_window_starts_with_the_place_and_the_date_it_is_given(self):
        from test_tool_window import Base

        class Case(Base):
            def runTest(inner):
                pass
        case = Case()
        case.setUp()
        try:
            user = types.SimpleNamespace(uistate=object())
            tool = case.mod.PlaceCompleterTool(case.dbstate, user, case.mod.PlaceCompleterOptions, "placecompleter",
                                               prefill={"place": "Bajmok", "date": "1850"})
            tool.e_place.set_text.assert_called_with("Bajmok")
            tool.e_date.set_text.assert_called_with("1850")
            plain = case.mod.PlaceCompleterTool(case.dbstate, user, case.mod.PlaceCompleterOptions, "placecompleter")
            plain.e_place.set_text.assert_not_called()                              # opened from the menu: nothing is filled in
        finally:
            case.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
