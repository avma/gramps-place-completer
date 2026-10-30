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
"""What the gramplets need from an event or a place of the open Gramps database: its date as text, its place, and what Gramps shows for it.

The only module besides model.py and writer.py that talks to Gramps objects (Date, Event, the place displayer).
"""


def date_text(date):
    """('YYYY[-MM[-DD]]', note) for a Gramps Date: in the Gregorian calendar, the first date of a range or a span.
    ('', reason) when there is no usable year (no date, only text, no year)."""
    from gramps.gen.lib import Date
    if date is None or date.is_empty():
        return "", "the event has no date"
    if date.get_modifier() == Date.MOD_TEXTONLY:
        return "", "the date is only text: type the year in the window"
    notes = []
    if date.get_calendar() != Date.CAL_GREGORIAN:
        date = date.to_calendar("gregorian")
        notes.append("converted to the Gregorian calendar")
    if date.get_modifier() in (Date.MOD_RANGE, Date.MOD_SPAN):
        notes.append("the first date of the range is used")
    day, month, year, _slash = date.get_start_date()
    if not year:
        return "", "the date has no year"
    text = "%d" % year + ("-%02d" % month if month else "") + ("-%02d" % day if month and day else "")
    return text, "; ".join(notes)


def top_name(db, place, date=None):
    """The name of the highest place above this one for the date (the country, or the empire), '' when it has no parent. It goes into the Region hint
    of the window: it tells the place from others of its name, and it is the country that the question lists the levels of."""
    from gramps.gen.utils.location import get_location_list
    chain = get_location_list(db, place, None if date is None or date.is_empty() else date)
    return chain[-1][0] if len(chain) > 1 and chain[-1][0] and chain[-1][0] != "?" else ""


def event_summary(db, event):
    """What the gramplet shows about an event: {type, date_text, date_note, place_handle, place_name, shown, incomplete}."""
    from gramps.gen.display.place import displayer as place_displayer
    text, note = date_text(event.get_date_object())
    handle = event.get_place_handle()
    name, top = "", ""
    if handle:
        place = db.get_place_from_handle(handle)
        if place:
            name = place.get_name().get_value() or ""
            top = top_name(db, place, event.get_date_object())
    shown = place_displayer.display_event(db, event) if handle else ""
    return {"type": str(event.get_type()), "date_text": text, "date_note": note, "place_handle": handle or "", "place_name": name,
            "top_name": top, "shown": shown, "incomplete": "?" in shown}


def place_summary(db, place):
    """What the gramplet of the Places view shows: same keys as event_summary, plus 'missing' (what the place lacks that this addon can
    fill or document) and 'gramps_id'."""
    from gramps.gen.display.place import displayer as place_displayer
    from gramps.gen.lib import PlaceType
    from .i18n import _
    name = place.get_name()
    shown = place_displayer.display(db, place)
    missing = []
    if not ((place.get_latitude() or "").strip() and (place.get_longitude() or "").strip()):
        missing.append(_("coordinates"))
    if place.get_type().value == PlaceType.UNKNOWN or (place.get_type().value == PlaceType.CUSTOM and not (place.get_type().string or "").strip()):
        missing.append(_("type"))                                                       # (a type of the user's own with no text shows blank, as Unknown does)
    if not name.get_language():
        missing.append(_("name language"))
    if not place.get_citation_list():
        missing.append(_("cited source"))
    return {"type": _("Place"), "date_text": "", "date_note": "", "place_handle": place.get_handle(), "place_name": name.get_value() or "",
            "top_name": top_name(db, place), "shown": shown, "incomplete": "?" in shown, "missing": missing, "gramps_id": place.get_gramps_id()}
