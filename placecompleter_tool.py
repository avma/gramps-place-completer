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
"""The window of Place Completer (Tools > Family Tree Processing > Place Completer).

A thin layer: every decision is made by placecompleter.session.Session (tested without a screen); this file only draws it,
passes the clicks, and runs the one slow thing (an API call) in a thread.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import json
import os
import sys
import threading
import time
from xml.sax.saxutils import escape
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)                    # the package placecompleter sits next to this file

# -------------------------------------------------------------------------
#
# GTK/Gnome modules
#
# -------------------------------------------------------------------------
from gi.repository import Gdk, GLib, Gtk, Pango

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gui.dialog import ErrorDialog
from gramps.gui.managedwindow import ManagedWindow
from gramps.gui.plug import tool

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from placecompleter import i18n                                             # first: the engine's texts are made when it is imported
_ = i18n.install_from_gramps(__file__)

from placecompleter import confidence, engines, geo, hints, keystore, ollama, settings, wikidata   # noqa: E402
from placecompleter import session as pcsession                             # noqa: E402
from placecompleter.model import Tree                                       # noqa: E402


WORK = engines.work_dir()                                                   # $PLACECOMPLETER_WORK, or ~/gramps-place-work
PACKS = os.path.join(HERE, "packs")
PREFS = os.path.join(WORK, "window.json")
WIKIDATA_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "placecompleter_wikidata.json")
FORMS = ("auto", "table", "classic", "short", "dated", "long")
KEY_TEST, KEY_SAVE, KEY_REMOVE = 1, 2, 3          # the responses of the key window
SETUP_DO, SETUP_COPY = 11, 12                      # the responses of the window that sets Ollama up
RESPONSE_WRITE = 4                                # the button that writes, in the row of buttons at the bottom of the window


SCROLL_CLASS = "placecompleter-scroll"
SLIM_CSS = b"""
scrolledwindow.placecompleter-scroll scrollbar.vertical { min-width: 8px; }
scrolledwindow.placecompleter-scroll scrollbar.vertical slider { min-width: 5px; }
scrolledwindow.placecompleter-scroll scrollbar.horizontal { min-height: 8px; }
scrolledwindow.placecompleter-scroll scrollbar.horizontal slider { min-height: 5px; }
scrolledwindow.placecompleter-scroll scrollbar button { min-width: 0; min-height: 0; padding: 0; margin: 0; border: none; background: none; -gtk-icon-source: none; }
"""
_css_installed = []


def install_scrollbar_css():
    """The slim-bar rules, once, for the screen but only for scrolled windows that carry the class of this addon: the rest of Gramps is
    not touched. A theme that refuses them simply keeps its own bars."""
    if _css_installed:
        return
    _css_installed.append(True)
    try:
        provider = Gtk.CssProvider()
        provider.load_from_data(SLIM_CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    except Exception:
        pass


def tidy_scroller(scroller, horizontal=Gtk.PolicyType.AUTOMATIC):
    """A scrolled window whose bar takes its own room (an overlay bar floats over the text at its edge) and is slim, without the arrow
    buttons at its ends."""
    scroller.set_policy(horizontal, Gtk.PolicyType.AUTOMATIC)
    scroller.set_overlay_scrolling(False)
    install_scrollbar_css()
    try:
        scroller.get_style_context().add_class(SCROLL_CLASS)
    except Exception:
        pass
    return scroller


class PlaceCompleterOptions(tool.ToolOptions):
    """The tool has no options of its own: what it remembers is kept in ~/gramps-place-work/window.json."""


class PlaceCompleterTool(tool.Tool, ManagedWindow):
    def __init__(self, dbstate, user, options_class, name, callback=None, prefill=None):
        uistate = user.uistate
        self.label = _("Place Completer")
        tool.Tool.__init__(self, dbstate, options_class, name)
        ManagedWindow.__init__(self, uistate, [], self.__class__)
        self.dbstate = dbstate
        self.session = None
        self._keys = pcsession.Session(Tree({}, []), WORK)               # only for the key window: no tree is needed
        self._busy = False
        self._wiki_token = 0
        self._build()
        _x, _y, screen_w, screen_h = self._screen_area()
        self.setup_configs("interface.placecompleter", min(940, max(screen_w - 60, 640)), min(780, max(screen_h - 120, 480)))
        self.show()
        self._keep_on_screen()                                        # a size or a place remembered from a bigger screen must not trap it
        if prefill:                                                   # from the gramplet: the place and the date of the active event
            self.e_place.set_text(prefill.get("place", ""))
            self.e_date.set_text(prefill.get("date", ""))
            self.e_hint.set_text(prefill.get("hint", ""))                 # the country (or the highest place above): it tells the place from others

    # ------------------------------------------------------------------ the window
    def _screen_area(self):
        """(x, y, width, height) of the usable area of the main monitor (without the panels)."""
        try:
            display = Gdk.Display.get_default()
            area = (display.get_primary_monitor() or display.get_monitor(0)).get_workarea()
            return int(area.x), int(area.y), int(area.width), int(area.height)
        except Exception:
            return 0, 0, 1024, 700

    def _keep_on_screen(self):
        """Shrink the window to the screen and bring it back inside it: the buttons must always be reachable."""
        try:
            x0, y0, screen_w, screen_h = self._screen_area()
            width, height = self.window.get_size()
            x, y = self.window.get_position()
            new_w, new_h = min(width, max(screen_w - 40, 640)), min(height, max(screen_h - 80, 480))
            if (new_w, new_h) != (width, height):
                self.window.resize(new_w, new_h)
            new_x, new_y = min(max(x, x0), x0 + screen_w - new_w), min(max(y, y0), y0 + screen_h - new_h)
            if (new_x, new_y) != (x, y):
                self.window.move(new_x, new_y)
        except Exception:
            pass

    def _build(self):
        prefs = self._load_prefs()
        dialog = Gtk.Dialog()
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        self.b_apply = dialog.add_button(_("Apply checked changes"), RESPONSE_WRITE)      # always in sight, below the scrolling part
        self.b_apply.set_tooltip_text(hints.APPLY)
        dialog.connect("response", self._response)
        scroller = tidy_scroller(Gtk.ScrolledWindow())                    # the content scrolls, so that no screen is too small
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)
        scroller.add(box)
        dialog.get_content_area().pack_start(scroller, True, True, 0)

        grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        self.e_place, self.e_date, self.e_hint = Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
        self.e_place.set_hexpand(True)
        self.e_hint.set_placeholder_text(_("optional: a word that distinguishes places, e.g., Iowa or the country, e.g., Italy"))      # grey, and never real text
        self._hint_for = None                                             # the place the hint was typed for (a hint belongs to one place)
        self.e_place.connect("changed", self._on_place_changed)
        self.e_hint.connect("changed", self._on_hint_changed)
        self.e_date.set_placeholder_text("YYYY")
        self.c_engine, self.c_form = Gtk.ComboBoxText(), Gtk.ComboBoxText()
        self._fill_engines(prefs.get("engine"))
        for form in FORMS:
            self.c_form.append(form, form)
        self.c_form.set_active(self._index(list(FORMS), prefs.get("form"), "auto"))
        self.b_ask = Gtk.Button(label=_("Ask"))
        self.b_ask.connect("clicked", self._on_ask)
        self.b_key = Gtk.Button(label=_("Key…"))
        self.b_key.set_tooltip_text(_("Enter the API key for the selected AI once: it will be saved securely"))
        self.b_key.connect("clicked", self._on_key)
        for row, (text, widget, hint) in enumerate([(_("Place"), self.e_place, hints.PLACE), (_("Date"), self.e_date, hints.DATE),
                                                    (_("Region hint"), self.e_hint, hints.HINT), (_("Question"), self.c_form, hints.FORM),
                                                    (_("AI"), self.c_engine, hints.ENGINE)]):
            label = Gtk.Label(label=text)
            label.set_xalign(0)
            for part in (label, widget):                                   # the hint appears over the label and over the field
                part.set_tooltip_text(hint)
            grid.attach(label, 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        self.e_languages = Gtk.Entry()
        self.e_languages.set_text(", ".join(settings.wikipedia_languages()))
        self.e_languages.connect("focus-out-event", self._on_languages_left)
        label = Gtk.Label(label=_("Wikipedia languages"))
        label.set_xalign(0)
        for part in (label, self.e_languages):
            part.set_tooltip_text(hints.LANGUAGES)
        grid.attach(label, 0, 5, 1, 1)
        grid.attach(self.e_languages, 1, 5, 1, 1)
        self.c_wikidata = Gtk.CheckButton(label=_("Look up coordinates on Wikidata (only place names are sent)"))
        self.c_wikidata.set_active(prefs.get("wikidata", True))
        self.c_wikidata.set_tooltip_text(hints.WIKIDATA)
        self.b_ask.set_tooltip_text(hints.ASK)
        grid.attach(self.c_wikidata, 1, 6, 1, 1)
        grid.attach(self.b_ask, 2, 0, 1, 2)
        grid.attach(self.b_key, 2, 4, 1, 1)                                  # beside the AI
        box.pack_start(grid, False, False, 0)

        self.status = Gtk.Label()
        self.status.set_xalign(0)
        self.status.set_line_wrap(True)
        self.status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        box.pack_start(self.status, False, False, 0)

        frame = Gtk.Frame(label=_("Response (if copied from a browser, paste it here)"))
        self.tv_answer = Gtk.TextView()
        self.tv_answer.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.tv_answer.get_buffer().connect("changed", lambda *args: self._update_buttons())     # the button is ready when there is an answer to read
        frame.set_tooltip_text(hints.ANSWER)
        scroll = tidy_scroller(Gtk.ScrolledWindow())
        scroll.set_min_content_height(70)
        scroll.add(self.tv_answer)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        inner.pack_start(scroll, True, True, 0)
        buttons = Gtk.Box(spacing=6)
        b_paste, self.b_analyse = Gtk.Button(label=_("Paste from clipboard")), Gtk.Button(label=_("Analyze"))
        b_paste.connect("clicked", self._on_paste)
        b_paste.set_tooltip_text(hints.PASTE)
        self.b_analyse.set_tooltip_text(hints.ANALYSE)
        self.b_analyse.connect("clicked", self._on_analyse)
        buttons.pack_start(b_paste, False, False, 0)
        buttons.pack_start(self.b_analyse, False, False, 0)
        inner.pack_start(buttons, False, False, 0)
        frame.add(inner)

        self.levels = Gtk.ListStore(bool, int, str)
        self._frame_levels = self._table(_("Retrieved administrative levels (uncheck uncertain levels)"), self.levels,
                                         [(_("Select"), self._on_level_toggled)], [(_("Level"), 2)], 60)
        self._frame_levels.set_tooltip_text(hints.LEVELS)

        self.rows = Gtk.TreeStore(bool, int, str, str, str, bool, str)    # apply?, change number, text, confidence, flag, has a box, tooltip
        self._frame_rows = self._changes_table(_("Other changes (each box is a grouped change applied as a set)"),
                                               self.rows, 150)
        changes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        changes_box.pack_start(self._frame_rows, True, True, 0)

        self.preview = Gtk.Label()
        self.preview.set_xalign(0)
        self.preview.set_line_wrap(True)
        self.preview.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.preview.set_selectable(True)
        changes_box.pack_start(self.preview, False, False, 0)
        self.b_toggle_all = Gtk.Button(label=_("Select all"))
        self.b_toggle_all.set_tooltip_text(hints.TOGGLE_ALL)
        self.b_toggle_all.connect("clicked", self._on_toggle_all)
        changes_box.pack_start(self.b_toggle_all, False, False, 0)

        self.tv_needs = Gtk.TextView()
        self.tv_needs.set_editable(False)
        self.tv_needs.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.tag_warn = self.tv_needs.get_buffer().create_tag("warn", foreground="#b00020", weight=Pango.Weight.BOLD)
        scroll2 = tidy_scroller(Gtk.ScrolledWindow())
        scroll2.set_min_content_height(90)
        scroll2.add(self.tv_needs)
        frame2 = Gtk.Frame(label=_("Issues to review"))
        frame2.set_tooltip_text(hints.NEEDS)
        frame2.add(scroll2)

        # The sections are one under the other with a handle between each two: the user drags it to make a section taller or shorter. None can be
        # made smaller than the height it needs (shrink is off), so none can be made nothing; the changes take what the window gives.
        bottom = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        bottom.pack1(changes_box, True, False)
        bottom.pack2(frame2, False, False)
        middle = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        middle.pack1(self._frame_levels, False, False)
        middle.pack2(bottom, True, False)
        self._results_pane = middle
        top = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        top.pack1(frame, False, False)
        top.pack2(middle, True, False)
        for paned in (bottom, middle, top):
            paned.set_wide_handle(True)
        box.pack_start(top, True, True, 0)

        self._result_widgets = [self._frame_levels, self._frame_rows, self.preview, self.b_toggle_all, frame2, self._results_pane]
        for widget in self._result_widgets:                               # nothing to show before there is an answer
            widget.set_no_show_all(True)
            widget.hide()
        self.set_window(dialog, None, self.label)
        self._update_buttons()

    @staticmethod
    def _same(text):
        return " ".join((text or "").split()).casefold()

    def _on_hint_changed(self, *args):
        place, hint = self._same(self.e_place.get_text()), self.e_hint.get_text().strip()
        self._hint_for = place if hint and place else None                # a hint typed before any place belongs to no place yet

    def _on_place_changed(self, *args):
        """A hint tells THIS place from others of the same name: when another place is typed, the old hint must not stay in the field."""
        if self._hint_for is not None and self._same(self.e_place.get_text()) != self._hint_for:
            self._hint_for = None
            self.e_hint.set_text("")

    def _fill_engines(self, wanted, keep=False):
        """(Re)fill the list of AIs: those that can work first, each marked, with what it still lacks; keep the one chosen, if it can work
        (or whatever the state of it, with keep: right after a key was saved for it, it must not jump to another one)."""
        self.c_engine.remove_all()
        ids, ready = [], {}
        for option in self._keys.engine_options():
            state = "; ".join([option["status"]] + ([] if option["ready"] else list(option["lacks"])))
            self.c_engine.append(option["id"], "%s %s  (%s)" % ("✓" if option["ready"] else "✗ " + _("requires configuration:"), option["label"], state))
            ids.append(option["id"])
            ready[option["id"]] = option["ready"]
        wanted = wanted if (wanted in ready if keep else ready.get(wanted)) else None       # one that cannot work is not where the window opens
        self.c_engine.set_active(self._index(ids, wanted, "google"))     # by position: always something is chosen

    @staticmethod
    def _index(ids, wanted, default):
        """Position of what was chosen last time; else of the default; else the first."""
        for candidate in (wanted, default):
            if candidate in ids:
                return ids.index(candidate)
        return 0

    def _changes_table(self, title, store, height):
        """The changes, each with a check box, and under each one the steps it is made of (without a box: they cannot be chosen apart)."""
        view = Gtk.TreeView(model=store)
        toggle = Gtk.CellRendererToggle()
        toggle.connect("toggled", self._on_row_toggled)
        view.append_column(Gtk.TreeViewColumn(_("Select"), toggle, active=0, visible=5))        # only a change has a box
        text = Gtk.CellRendererText()
        text.set_property("wrap-mode", Pango.WrapMode.WORD)
        text.set_property("wrap-width", 560)
        column = Gtk.TreeViewColumn(_("Proposed changes"), text, text=2)
        view.append_column(column)
        view.set_expander_column(column)
        confidence_column = Gtk.TreeViewColumn(_("Confidence"), Gtk.CellRendererText(), text=3)
        header = Gtk.Label(label=_("Confidence"))                                # a title of its own, to say what the column means on hover
        header.set_tooltip_text(confidence.explanation())
        header.show()
        confidence_column.set_widget(header)
        view.append_column(confidence_column)
        view.append_column(Gtk.TreeViewColumn("!", Gtk.CellRendererText(), text=4))
        view.set_tooltip_column(6)                                              # on a change: why it has its level
        self._rows_view = view
        scroll = tidy_scroller(Gtk.ScrolledWindow())
        scroll.set_min_content_height(height)
        scroll.add(view)
        frame = Gtk.Frame(label=title)
        frame.add(scroll)
        return frame

    def _table(self, title, store, toggles, columns, height):
        view = Gtk.TreeView(model=store)
        for title_, handler in toggles:
            renderer = Gtk.CellRendererToggle()
            renderer.connect("toggled", handler)
            view.append_column(Gtk.TreeViewColumn(title_, renderer, active=0))
        for title_, index in columns:
            renderer = Gtk.CellRendererText()
            renderer.set_property("wrap-mode", Pango.WrapMode.WORD)
            renderer.set_property("wrap-width", 620 if index == 2 else -1)
            view.append_column(Gtk.TreeViewColumn(title_, renderer, text=index))
        scroll = tidy_scroller(Gtk.ScrolledWindow())
        scroll.set_min_content_height(height)
        scroll.add(view)
        frame = Gtk.Frame(label=title)
        frame.add(scroll)
        return frame

    def _response(self, obj, response_id):
        if response_id == Gtk.ResponseType.CLOSE:
            self.close()
        elif response_id == RESPONSE_WRITE:
            self._on_apply()

    # ------------------------------------------------------------------ what is remembered
    def _load_prefs(self):
        try:
            with open(PREFS, encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return {}

    def _save_prefs(self):
        engine = self.c_engine.get_active_id()
        ready = {o["id"]: o["ready"] for o in self._keys.engine_options()}
        if not ready.get(engine):                                         # an AI that cannot work yet is not remembered
            engine = self._load_prefs().get("engine", "google")
        try:
            os.makedirs(WORK, exist_ok=True)
            with open(PREFS, "w", encoding="utf-8") as fh:
                json.dump({"engine": engine, "form": self.c_form.get_active_id(), "wikidata": bool(self.c_wikidata.get_active())}, fh)   # not the hint
        except OSError:
            pass

    # ------------------------------------------------------------------ the steps
    def _say(self, text):
        self.status.set_text(text)

    def _update_buttons(self):
        ready = bool(self.session and self.session.state == "ready")
        self.b_ask.set_sensitive(not self._busy)
        self.b_analyse.set_sensitive((bool(self.session) or bool(self._answer_text().strip())) and not self._busy)     # an answer pasted without a question counts
        self.b_apply.set_sensitive(ready and not self._busy)
        if ready:
            self.b_toggle_all.set_label(_("Clear all") if self.session.all_selected() else _("Select all"))
        self.b_toggle_all.set_sensitive(ready and not self._busy and (bool(self.session.selectable_by_all()[0]) or bool(self.session.selected)))

    def _on_toggle_all(self, *args):
        done = self.session.toggle_all()
        self._refresh_checks()
        self._refresh_preview()
        self._update_buttons()
        if done["action"] == "cleared":
            self._say(_("All items are unchecked."))
            return
        left = []                                                       # what is left for the user is said
        if done["conflicts"]:
            left.append(_("%d change(s) in CONFLICT with existing tree data (replacing a different date)") % done["conflicts"])
        if done["optional"]:
            left.append(_("%d web link(s) to a site of unknown type (check if official)") % done["optional"])
        if done["exclusive"]:
            left.append(_("%d conflicting change(s) (select one option)") % done["exclusive"])
        if done["needs"]:
            left.append(_("%d change(s) depending on these options") % done["needs"])
        self._say(_("%d change(s) selected. Remaining to review: %s.") % (done["chosen"], "; ".join(left)) if left else _("%d change(s) selected.") % done["chosen"])

    def _new_session(self):
        self._wiki_token += 1                                         # whatever Wikidata is still answering belongs to the old question
        self._save_prefs()
        tree = Tree.from_db(self.dbstate.db)                              # the tree as it is now
        self.session = pcsession.Session(tree, WORK, pack_files=sorted(os.path.join(PACKS, f) for f in os.listdir(PACKS)
                                                                        if f.endswith(".json")) if os.path.isdir(PACKS) else ())
        self._clear_result()

    def _on_languages_left(self, *args):
        """Keep the languages typed (the words that are not language codes are reported and left out). Returns False so that Gtk goes on."""
        languages, bad = settings.set_wikipedia_languages(self.e_languages.get_text())
        if bad:
            self._say(_("Invalid language codes ignored: %s. Please use standard 2-letter codes (e.g., en, he, fr).") % ", ".join(bad))
        self.e_languages.set_text(", ".join(languages or settings.wikipedia_languages()))
        return False

    def _on_ask(self, *args):
        self._on_languages_left()
        self._new_session()
        action = self.session.begin(self.e_place.get_text(), self.e_date.get_text(), self.e_hint.get_text(),
                                    self.c_engine.get_active_id() or "google", self.c_form.get_active_id() or "auto")
        self._perform(action)

    def _perform(self, action):
        kind = action["action"]
        if kind == "error":
            self._say(action["message"])
            if action.get("needs_key"):
                if self._key_dialog(action["needs_key"]):                 # a key is all that was missing: ask again
                    self._after_key_saved(action["needs_key"])
                    self._on_ask()
                    return
            elif action.get("needs_setup") == "ollama":
                if self._ollama_setup():                                  # it is ready now: ask again
                    self._on_ask()
                    return
            else:
                ErrorDialog(self.label, action["message"], parent=self.window)
        elif kind == "open-url":
            if action.get("copy"):                                        # the page cannot take the question in its address: it is pasted there
                Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(action["prompt"], -1)
            if not webbrowser.open(action["url"]):
                self._say(_("Could not launch web browser. Please open this URL manually:\n%s") % action["url"])
            else:
                self._say(self.session.message)
        elif kind == "copy-prompt":
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(action["prompt"], -1)
            self._say(self.session.message)
        elif kind == "call-api":
            self._busy = True
            self._say(self.session.message)
            threading.Thread(target=self._api_worker, daemon=True).start()
        elif kind == "retry":
            self._say(self.session.message)
            self._perform(action["next"])
        elif kind == "ambiguous":
            self._choose_place(action)
        elif kind == "ready":
            self._show_result()
            if not self._ask_ambiguous():                             # (a choice analyses again, and comes back here)
                self._start_wikidata()
        self._update_buttons()

    def _api_worker(self):
        action = self.session.run_api()                                   # blocking: this is why it runs in a thread
        GLib.idle_add(self._after_api, action)

    def _after_api(self, action):
        self._busy = False
        self._perform(action)
        return False

    # ------------------------------------------------------------------ a level that could be several places of the tree
    def _ask_ambiguous(self):
        """Ask which place a level of the answer is when several of the tree could be it: a new place is never made while one that exists
        may be the same. Returns True when the answer was analysed again with the choice."""
        pending = self.session.ambiguous_units() if self.session else []
        if not pending:
            return False
        unit = pending[0]
        choice = self._choose_dialog(unit)
        if choice is None:                                            # cancelled: the level stays out, and the screen says CHOOSE
            return False
        self._perform(self.session.choose_unit(unit["slot"], choice))
        return True

    def _choose_dialog(self, unit):
        dialog = Gtk.Dialog(title=_("Which place is this?"), transient_for=self.window, modal=True)
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_OK"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_border_width(10)
        text = Gtk.Label(label=unit.get("why") or _("The response specifies «%(name)s» (%(type)s), matching several existing places in your tree. No changes will "
                                                    "be made until you choose one.") % {"name": unit["name"], "type": unit["type"]})
        self._wrap(text)
        box.pack_start(text, False, False, 0)
        options = [(c["handle"], c["label"]) for c in unit["candidates"]] + [
            ("new", _("New place «%s»") % unit["name"]), ("skip", _("Exclude this level"))]
        radios, first = [], None
        for value, label in options:
            radio = Gtk.RadioButton.new_with_label_from_widget(first, label)
            first = first or radio                                    # the first (the best match) is the one chosen to start with
            box.pack_start(radio, False, False, 0)
            radios.append((value, radio))
        dialog.show_all()
        response = dialog.run()
        chosen = next((value for value, radio in radios if radio.get_active()), None) if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        return chosen

    # ------------------------------------------------------------------ coordinates from Wikidata, in the background
    def _start_wikidata(self):
        if not self.session or not self.c_wikidata.get_active():
            return
        targets = self.session.coordinate_targets()
        if not targets:
            return
        self._wiki_token += 1
        self._say(_("The response is ready. Looking up coordinates on Wikidata…"))
        threading.Thread(target=self._wikidata_worker, args=(self.session, targets, self._wiki_token), daemon=True).start()

    def _wikidata_worker(self, session, targets, token):
        try:
            client = wikidata.Client(cache_path=WIKIDATA_CACHE, fetch=wikidata.urllib_fetch, pause=1.0)
            findings = geo.lookup_many(client, targets, articles=settings.wikipedia_languages())                   # the network: slow, so not in the window's own thread
            try:
                client.save()
            except OSError:
                pass
        except Exception as exc:
            findings = {"error": str(exc)}
        GLib.idle_add(self._after_wikidata, session, findings, token)

    def _after_wikidata(self, session, findings, token):
        if session is not self.session or token != self._wiki_token or not session.result:     # a newer question was asked meanwhile
            return False
        if "error" in findings:
            self._say(_("Could not query Wikidata: %s") % findings["error"])
            return False
        session.apply_coordinates(findings)
        self._show_result()                                               # the same screen, with what Wikidata said
        return False

    def _on_paste(self, *args):
        text = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
        self.tv_answer.get_buffer().set_text(text or "")

    def _answer_text(self):
        buf = self.tv_answer.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)

    def _on_analyse(self, *args):
        if not self.session:                                          # an answer of an earlier question, pasted: no new question is needed
            if not self._answer_text().strip():
                self._say(_("Click Ask first, or paste a response into the text box."))
                return
            if not (self.e_place.get_text().strip() and self.e_date.get_text().strip()):
                self._say(_("Specify the place name and date for the query."))
                return
            self._new_session()
            self.session.begin(self.e_place.get_text(), self.e_date.get_text(), self.e_hint.get_text(), "manual", "classic")      # (nothing is copied or opened)
        text = self._answer_text() or (Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() or "")
        self._perform(self.session.receive(text))

    def _choose_place(self, action):
        dialog = Gtk.Dialog(title=_("Which place is this?"), transient_for=self.window, modal=True)
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("_OK"), Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(10)
        box.pack_start(Gtk.Label(label=_("This name matches multiple places. Which one did you mean?")), False, False, 4)
        group, radios = None, []
        for i, hint in enumerate(action["candidates"]):
            c = hint["candidate"]
            text = "%s, %s%s  (%s, %s)%s" % (c["name"], c["country"], " (%s)" % c["region"] if c["region"] else "",
                                             c["coordinates"][0], c["coordinates"][1], "\n    " + "; ".join(hint["notes"]) if hint["notes"] else "")
            radio = Gtk.RadioButton.new_with_label_from_widget(group, text)
            group = group or radio
            radio.set_active(i == action["best"])
            radios.append(radio)
            box.pack_start(radio, False, False, 2)
        box.show_all()
        response = dialog.run()
        chosen = next((i for i, r in enumerate(radios) if r.get_active()), None)
        dialog.destroy()
        if response == Gtk.ResponseType.OK and chosen is not None:
            self._perform(self.session.choose_candidate(chosen))
        else:
            self._say(_("Cancelled: no place selected."))

    # ------------------------------------------------------------------ the key window
    @staticmethod
    def _pause_and_answer(seconds):
        """Wait `seconds` while the window keeps answering (it redraws, it can be moved): a plain sleep in the thread of the window freezes it."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            for _i in range(50):                                          # (bounded: a flood of events cannot keep the wait from ending)
                if not Gtk.events_pending():
                    break
                Gtk.main_iteration()
            time.sleep(0.02)

    def _flush(self):
        for _i in range(50):                                              # let the window redraw before a slow step (bounded)
            if not Gtk.events_pending():
                break
            Gtk.main_iteration()

    # ------------------------------------------------------------------ Ollama: set it up for the user, step by step, each after an approval
    def _ollama_setup(self):
        """Look at what Ollama lacks on this computer and offer the step that fixes it, once the user agrees: open a terminal that installs it,
        start it, or download a model. Returns True when it is ready to be asked."""
        for _round in range(4):
            now = ollama.state()
            if now == "ready":
                return True
            if now == "missing":
                self._offer_install()
                return False                                              # the installation goes on in its terminal: ask again after it
            if now == "stopped":
                if self._ask_choice(_("Ollama service is not running"),
                                    _("Ollama is installed locally but is not currently active.\nStart it now? It will run in the background (ollama "
                                      "serve) until stopped or the computer shuts down."),
                                    [(_("_Cancel"), Gtk.ResponseType.CANCEL), (_("Start service"), SETUP_DO)]) != SETUP_DO:
                    return False
                self._say(_("Starting Ollama…"))
                self._flush()
                ok, message = ollama.start_server(sleep=self._pause_and_answer)      # (up to 20 seconds of waiting: the window keeps answering)
                if not ok:
                    self._say(message)
                    ErrorDialog(self.label, message + "\n\n" + _("To start manually via terminal run:  ollama serve   (or:  sudo systemctl start ollama )"),
                                parent=self.window)
                    return False
                continue
            if now == "no-model":
                model = self._choose_model()
                if not model:
                    return False
                self._say(_("Downloading model %s…") % model)
                ok, message = self._download_dialog(model)
                if not ok:
                    self._say(message)
                    ErrorDialog(self.label, message, parent=self.window)
                    return False
                self._say(_("Model %s successfully installed.") % model)
        return ollama.state() == "ready"

    def _offer_install(self):
        """Ollama is not installed: say what the installation is, show the command (it can be copied), and open a terminal that runs it."""
        response = self._ask_choice(
            _("Ollama is not installed"),
            _("Ollama runs a local AI model: free, no API key required.\nIt lacks web access and may be less reliable than "
              "Google AI mode or Claude.\nThe installer will ask for administrator permissions in the terminal window that "
              "opens. The command:"),
            [(_("_Cancel"), Gtk.ResponseType.CANCEL), (_("Copy command"), SETUP_COPY), (_("Open terminal to run installer"), SETUP_DO)],
            command=ollama.INSTALL_COMMAND)
        if response == SETUP_COPY:
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(ollama.INSTALL_COMMAND, -1)
            self._say(_("Command copied: open a terminal and paste it (Ctrl+Shift+V)."))
        elif response == SETUP_DO:
            ok, message = ollama.open_installer_terminal()
            self._say(_("A terminal window is open: enter your administrator password there. Once installation finishes, click Ask "
                        "again.")
                      if ok else message)
            if not ok:
                ErrorDialog(self.label, message, parent=self.window)

    def _choose_model(self):
        """Ask which model to download (or none). Returns its name, or '' when the user cancelled."""
        dialog = Gtk.Dialog(title=_("Download a model"), transient_for=self.window, modal=True)
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        dialog.add_button(_("Download"), SETUP_DO)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        text = Gtk.Label(label=_("Ollama is running but no model is installed.\nDownloading a model (a few GB) takes a few minutes and stays "
                                 "stored locally on this computer.\nSelect a model below or enter a model name from ollama.com/library:"))
        self._wrap(text)
        box.pack_start(text, False, False, 0)
        combo = Gtk.ComboBoxText()
        for name, note in ollama.SUGGESTED:
            combo.append(name, "%s: %s" % (name, note))
        combo.set_active_id(ollama.DEFAULT_MODEL)
        box.pack_start(combo, False, False, 0)
        other = Gtk.Entry()
        other.set_placeholder_text(_("another model name (optional)"))
        box.pack_start(other, False, False, 0)
        box.show_all()
        response = dialog.run()
        model = (other.get_text() or "").strip() or (combo.get_active_id() or ollama.DEFAULT_MODEL)
        dialog.destroy()
        return model if response == SETUP_DO else ""

    def _download_dialog(self, model):
        """Download a model with a progress bar; the window stays alive and the download can be cancelled. Returns (ok, message)."""
        dialog = Gtk.Dialog(title=_("Downloading %s") % model, transient_for=self.window, modal=True)
        dialog.add_button(_("_Cancel"), Gtk.ResponseType.CANCEL)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        label = Gtk.Label(label=_("Starting download…"))
        self._wrap(label)
        bar = Gtk.ProgressBar()
        box.pack_start(label, False, False, 0)
        box.pack_start(bar, False, False, 0)
        box.show_all()
        state = {"cancel": False, "result": (False, "")}

        def update(status, done, total):
            share = ollama.percent(done, total)
            if share is None:
                label.set_text(status or _("Downloading…"))
                bar.pulse()
            else:
                label.set_text("%s: %d%% (%s / %s)" % (status, share, ollama.human_size(done), ollama.human_size(total)))
                bar.set_fraction(share / 100.0)
            return False

        def worker():
            state["result"] = ollama.pull(model, lambda st, d, t: GLib.idle_add(update, st, d, t), cancelled=lambda: state["cancel"])
            GLib.idle_add(dialog.response, Gtk.ResponseType.OK)

        threading.Thread(target=worker, daemon=True).start()
        if dialog.run() == Gtk.ResponseType.CANCEL:
            state["cancel"] = True                                        # the worker stops at its next line
            dialog.destroy()
            return False, _("download cancelled")
        dialog.destroy()
        return state["result"]

    @staticmethod
    def _wrap(label):
        """A text of a small window: it wraps at about 60 characters (without this the window grows as wide as the longest line) and is read from
        the left edge. Lines are made by the line breaks of the text itself."""
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(60)
        label.set_xalign(0)

    def _ask_choice(self, title, text, buttons, command=""):
        """A question with buttons [(label, response)]; the command, when there is one, is shown in a selectable box. Returns the response."""
        dialog = Gtk.Dialog(title=title, transient_for=self.window, modal=True)
        for label, response in buttons:
            dialog.add_button(label, response)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        body = Gtk.Label(label=text)
        self._wrap(body)
        box.pack_start(body, False, False, 0)
        if command:
            shown = Gtk.Entry()
            shown.set_text(command)
            shown.set_editable(False)                                     # it can be selected and copied, not changed
            shown.set_width_chars(len(command) + 2)                       # as wide as the command: nothing more
            box.pack_start(shown, False, False, 0)
        box.show_all()
        response = dialog.run()
        dialog.destroy()
        return response

    def _on_key(self, *args):
        engine = self.c_engine.get_active_id()
        if engine and self._key_dialog(engine):
            self._after_key_saved(engine)

    def _after_key_saved(self, engine):
        """The key is kept: the model is found by itself (an OpenAI-compatible service says which models it has), the list is filled again
        with this AI still chosen, and whatever is still missing is said, so that a key that WAS saved never looks lost."""
        self._say(_("Key saved. Finding an available model…"))
        self._flush()
        found = self._keys.settle_model(engine)
        self._fill_engines(engine, keep=True)
        option = next((o for o in self._keys.engine_options() if o["id"] == engine), None)
        if not found["ok"]:
            self._say(_("Key saved, but could not select a model: %s") % found["message"])
        elif option and not option["ready"]:
            self._say(_("API key saved, but service is unavailable: %s") % option["fix"])
        elif found["how"] == "chosen":
            self._say(_("Key saved; model %s was automatically selected.") % found["model"])
        else:
            self._say(_("Key saved (%s).") % self._keys.key_info(engine)["hint"])

    def _key_dialog(self, engine_id):
        """A small window to enter the key of an engine once. Returns True if a key was saved."""
        keys = self._keys
        info = keys.key_info(engine_id)
        if not info["needed"]:
            self._say(_("%s does not require an API key.") % info["label"])
            return False
        dialog = Gtk.Dialog(title=_("API key"), transient_for=self.window, modal=True)
        dialog.add_button(_("_Close"), Gtk.ResponseType.CLOSE)
        dialog.add_button(_("Remove"), KEY_REMOVE)
        dialog.add_button(_("Test"), KEY_TEST)
        dialog.add_button(_("Save"), KEY_SAVE)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_border_width(14)
        title = Gtk.Label()
        title.set_markup("<b>%s</b>" % GLib.markup_escape_text(info["label"]))
        state, where, result = Gtk.Label(), Gtk.Label(), Gtk.Label()
        entry = Gtk.Entry()
        entry.set_visibility(False)                                       # a password field: nothing typed is shown
        entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        entry.set_placeholder_text(_("paste the key here"))
        entry.set_width_chars(48)
        for label in (title, state, where, result):
            label.set_xalign(0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            box.pack_start(label, False, False, 0)
        box.pack_start(entry, False, False, 0)
        sent = _("Sent only to %s.") % info["host"]
        where.set_text((_("Key saved in %s (encrypted via system keyring).") % info["store"] if info["secure"] else
                        _("No system keyring detected; key saved unencrypted in %s. Do not copy or sync this folder.")
                        % info["store"]) + " " + sent)

        def show(info):
            state.set_text(_("Key already saved: %(hint)s (in %(where)s). Entering a new key will overwrite it.") % {"hint": info["hint"], "where": info["where"]}
                           if info["set"] else _("No API key saved for this AI engine yet."))
        show(info)
        box.show_all()
        saved = False
        while True:
            response = dialog.run()
            typed = entry.get_text()
            if response == KEY_TEST:
                result.set_text(_("Testing API key connection…"))
                self._flush()
                res = keys.test_key(engine_id, key=typed or None)
                result.set_text(("✓ " if res["ok"] else "✗ ") + res["message"])
            elif response == KEY_SAVE:
                try:
                    info = keys.save_key(engine_id, typed)
                except (ValueError, keystore.StoreError) as exc:
                    result.set_text(str(exc))
                    continue
                entry.set_text("")                                        # the key does not stay in the window
                saved = True
                break
            elif response == KEY_REMOVE:
                try:
                    show(keys.remove_key(engine_id))
                    result.set_text(_("The saved key has been removed."))
                except keystore.StoreError as exc:
                    result.set_text(str(exc))
                entry.set_text("")
            else:
                break
        entry.set_text("")
        dialog.destroy()
        if saved:
            self._say(_("Key saved (%s).") % info["hint"])
        return saved

    # ------------------------------------------------------------------ the control screen
    def _clear_result(self):
        self.levels.clear()
        self.rows.clear()
        self.preview.set_text("")
        self.tv_needs.get_buffer().set_text("")
        for widget in self._result_widgets:
            widget.hide()

    def _reveal_result(self):
        for widget in self._result_widgets:
            widget.set_no_show_all(False)
            widget.show_all()

    def _show_result(self):
        s = self.session
        self._reveal_result()
        self.levels.clear()
        for level in s.levels:
            self.levels.append([level["used"], level["index"], level["text"]])
        self.rows.clear()
        for change in s.changes():
            parent = self.rows.append(None, [change["selected"], change["id"], change["title"], change["confidence"], _(change["flag"]), True,
                                             escape("%s: %s" % (change["confidence"], change["confidence_why"]))])
            if change["why"]:
                self.rows.append(parent, [False, 0, "ℹ " + change["why"], "", "", False, ""])
            for step in change["steps"]:
                if not change.get("show_steps", True) or (len(change["steps"]) == 1 and step["text"] == change["title"]):
                    continue                                                  # a step that only says again what its change says is not shown
                self.rows.append(parent, [False, 0, "• " + step["text"], "", "", False, ""])
        self._rows_view.expand_all()
        self._refresh_needs()
        self._refresh_preview()
        self._say(s.message)

    def _refresh_needs(self):
        buf = self.tv_needs.get_buffer()
        buf.set_text("")
        for text, level in self.session.needs():
            buf.insert_with_tags(buf.get_end_iter(), "• " + text + "\n", *([self.tag_warn] if level == "warning" else []))

    def _refresh_preview(self):
        text, end = self.session.preview()
        self.preview.set_text(_("Gramps display format for an event on this date: %s") % text +
                              ("" if end in ("top", "after-links", None) else "   (%s)" % end))

    def _on_row_toggled(self, renderer, path):
        row = self.rows[path]
        if not row[5]:                                                    # a step: it is not chosen apart from its change
            return
        self.session.toggle_change(row[1])
        self._refresh_checks()
        self._refresh_preview()
        self._update_buttons()

    def _refresh_checks(self):
        checked = {c["id"]: c["selected"] for c in self.session.changes()}
        for row in self.rows:                                             # the changes (the steps below them have no box)
            row[0] = checked.get(row[1], False)

    def _on_level_toggled(self, renderer, path):
        row = self.levels[path]
        self._perform(self.session.set_level_used(row[1], not row[0]))

    # ------------------------------------------------------------------ writing
    def _on_apply(self, *args):
        s, db = self.session, self.dbstate.db
        if db.readonly:
            ErrorDialog(self.label, _("This family tree is opened as read-only."), parent=self.window)
            return
        proposals = s.selected_proposals()
        if not proposals:
            self._say(_("Select at least one proposed change first."))
            return
        skipped = [r for r in s.check(db) if r["status"] == "skipped"]
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True, message_type=Gtk.MessageType.QUESTION,
                                   buttons=Gtk.ButtonsType.OK_CANCEL, text=_("Apply %d change(s) to the family tree?") % len(proposals))
        dialog.format_secondary_text(
            _("Changes are applied together in one step; Edit > Undo will revert all of them.") +
            ("\n\n" + _("%d change(s) will be skipped: %s") % (len(skipped), "; ".join(r["reason"] for r in skipped)) if skipped else ""))
        response = dialog.run()
        dialog.destroy()
        if response != Gtk.ResponseType.OK:
            return
        try:
            s.apply(db)
        except Exception as exc:                                          # shown, not hidden
            ErrorDialog(self.label, str(exc), parent=self.window)
            return
        s.refresh(Tree.from_db(db))
        self._say(s.message)
        self.rows.clear()
        self._update_buttons()
