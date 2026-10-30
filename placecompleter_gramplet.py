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
"""Place Completer as a gramplet of the Events view and of the Places view (sidebar or bottombar).

It is a small front for the full window. In the Events view it shows the active event (its date, its place, what Gramps displays for it)
and a button, "Complete the place...", that opens the Place Completer window with that place and that date already filled in. In the Places
view it shows the active place and what it lacks, and the same button opens the window with the place's name. Nothing is asked and
nothing is written from here.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)                    # the package placecompleter and placecompleter_tool sit next to this file

# -------------------------------------------------------------------------
#
# GTK/Gnome modules
#
# -------------------------------------------------------------------------
from gi.repository import Gtk, Pango

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.plug import Gramplet

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from placecompleter import i18n                                             # first: the engine's texts are made when it is imported
_ = i18n.install_from_gramps(__file__)

from placecompleter import grampslink                                       # noqa: E402
from placecompleter_open import open_window                                 # noqa: E402


class PlaceCompleterGramplet(Gramplet):
    def init(self):
        self.summary = None
        self.gui.WIDGET = self._build()
        self.gui.get_container_widget().remove(self.gui.textview)
        self.gui.get_container_widget().add(self.gui.WIDGET)
        self.gui.WIDGET.show_all()

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(6)
        self.l_event, self.l_shown, self.l_note = Gtk.Label(), Gtk.Label(), Gtk.Label()
        for label in (self.l_event, self.l_shown, self.l_note):
            label.set_xalign(0)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_selectable(True)
            box.pack_start(label, False, False, 0)
        self.b_open = Gtk.Button(label=_("Complete place data…"))
        self.b_open.set_tooltip_text(_("Open Place Completer with this event's place and date"))
        self.b_open.connect("clicked", self._on_open)
        box.pack_start(self.b_open, False, False, 0)
        return box

    def db_changed(self):
        self.connect(self.dbstate.db, "event-update", self.update)
        self.connect(self.dbstate.db, "place-update", self.update)
        self.connect_signal("Event", self.update)             # the active event changed

    def active_changed(self, handle):
        self.update()

    def main(self):
        self._refresh()
        yield False

    def _read(self):
        """The summary of what is active, or None."""
        event = self.get_active_object("Event") if self.dbstate.is_open() else None
        return grampslink.event_summary(self.dbstate.db, event) if event is not None else None

    def _refresh(self):
        self.summary = None
        try:
            self.summary = self._read()
        except Exception:                                      # a handle that no longer exists: nothing is selected
            self.summary = None
        s = self.summary
        if s is None:
            self.l_event.set_text(self.NOTHING)
            self.l_shown.set_text("")
            self.l_note.set_text("")
        else:
            self._show(s)
        self.b_open.set_sensitive(s is not None)

    NOTHING = _("Select an event.")

    def _show(self, s):
        self.l_event.set_text(_("%(type)s, %(date)s") % {"type": s["type"], "date": s["date_text"] or _("no valid date")})
        self.l_shown.set_text(_("Gramps currently displays: %s") % s["shown"] if s["shown"] else _("This event has no place assigned."))
        self.l_note.set_text(_("Names are missing for this date (place displayed with «?»)") if s["incomplete"] else s["date_note"])

    def _on_open(self, *args):
        if not self.summary:
            return
        if not open_window(self.dbstate, self.uistate, self.summary["place_name"], self.summary["date_text"], self.summary.get("top_name", "")):
            self.l_note.set_text(_("Place Completer window is already open."))


class PlaceCompleterPlaceGramplet(PlaceCompleterGramplet):
    """The same for the Places view: the active place, what it lacks, and the button that opens the window with its name (the date is
    asked in the window: a place has none)."""
    NOTHING = _("Select a place.")

    def db_changed(self):
        self.connect(self.dbstate.db, "place-update", self.update)
        self.connect(self.dbstate.db, "event-update", self.update)
        self.connect_signal("Place", self.update)

    def _read(self):
        place = self.get_active_object("Place") if self.dbstate.is_open() else None
        return grampslink.place_summary(self.dbstate.db, place) if place is not None else None

    def _show(self, s):
        self.l_event.set_text("%s [%s]" % (s["place_name"] or _("(no name)"), s["gramps_id"]))
        self.l_shown.set_text(_("Gramps currently displays: %s") % s["shown"])
        self.l_note.set_text(_("Missing data: %s") % ", ".join(s["missing"]) if s["missing"] else _("Analyze the response, then choose which changes to apply."))
