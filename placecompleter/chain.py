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
"""The place chain Gramps displays for an event date (Gramps 6.0/6.1 rules).

For each place: the first parent link whose date is empty or matches the event
date; the first name that matches (a name in the requested language wins).
This module reproduces Gramps' get_location_list(); it was checked against
Gramps' own display on tens of thousands of random events.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .dates import INF, interval, is_empty, match_exact

COUNTRY = 1   # Gramps PlaceType.COUNTRY


def pick_name(place, event_date, about=None, lang=""):
    endonym = None
    for name in [place["name"]] + list(place["alt_names"]):
        nd = name.get("date")
        if is_empty(nd) or match_exact(event_date, nd, about):
            if (name.get("lang") or "") == lang:
                return name.get("value") or ""
            if endonym is None:
                endonym = name.get("value") or ""
    return endonym if endonym is not None else "?"


def _after_all_links(place, sortval, about):
    """True if every parent link of the place is bounded and ended before sortval."""
    for ref in place["refs"]:
        iv = interval(ref.get("date"), about)
        if iv is None or iv[1] >= INF or iv[1] >= sortval:
            return False
    return bool(place["refs"])


def chain(places, handle, event_date, about=None):
    """Return a dict describing the chain for one place and one event date.

    end: "top" (no parents at all), "truncated" (parents exist but no link
    covers the date), "after-links" (a country whose links all ended before the
    date: normal top-level), "cycle", "missing-parent".
    via: for every step above the first place, (child handle, link index).
    """
    place = places[handle]
    names = [pick_name(place, event_date, about)]
    handles, via, visited = [handle], [], [handle]
    sortval = event_date.get("sortval") or 0
    while True:
        chosen = None
        for index, ref in enumerate(place["refs"]):
            rd = ref.get("date")
            if is_empty(rd) or match_exact(event_date, rd, about):
                chosen = (index, ref.get("ref"))
                break
        if chosen is None:
            if not place["refs"]:
                end = "top"
            elif (place["type"].get("value") == COUNTRY and sortval
                  and _after_all_links(place, sortval, about)):
                end = "after-links"
            else:
                end = "truncated"
            return {"names": names, "handles": handles, "via": via, "end": end,
                    "last": handles[-1]}
        index, nxt = chosen
        if nxt in visited:
            return {"names": names, "handles": handles, "via": via, "end": "cycle", "last": handles[-1]}
        if nxt not in places:
            return {"names": names, "handles": handles, "via": via, "end": "missing-parent", "last": handles[-1]}
        via.append((handles[-1], index))
        place = places[nxt]
        visited.append(nxt)
        handles.append(nxt)
        names.append(pick_name(place, event_date, about))
