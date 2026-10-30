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
"""Periods: the date of a period, and the arithmetic on the periods that two answers, or an answer and the tree, give.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import packs
from .complete import _bound
from .dates import INF, interval, make_from, make_span, make_to, ymd



def _date(first, last):
    if first and last:
        return make_span(packs.parse_iso(first), packs.parse_iso(last))
    if first:
        return make_from(packs.parse_iso(first))
    if last:
        y = packs.parse_iso(last)
        return make_to((0, 0, y[2] + 1)) if len(str(last)) == 4 else make_to(y)
    return {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False], "text": "", "sortval": 0}


def _covers_text(c, sv):
    first, last = c.get("from"), c.get("to")
    return _bound(first, False) <= sv <= _bound(last, True)


def _intersect(first, last, other):
    lo = max(first or "", other.get("from") or "") or None
    hi_candidates = [x for x in (last, other.get("to")) if x]
    return lo, (min(hi_candidates) if hi_candidates else None)


def _overlaps(date, period):
    iv = interval(date or {})
    if iv is None:
        return False
    lo, hi = _bound(period[0], False), _bound(period[1], True)
    return iv[0] <= hi and lo <= iv[1]


def _tuple(sv, start):
    y, m, d = ymd(sv)
    if start and (m, d) == (1, 1):
        return (0, 0, y)
    if not start and (m, d) == (12, 31):
        return (0, 0, y)
    return (d, m, y)


def _piece(lo, hi):
    """A date dictionary for the sort-value interval lo..hi (either side may be open)."""
    if lo <= -INF and hi >= INF:
        return None
    if lo > hi:
        return None                                                          # a period that ends before it starts is no period
    if lo <= -INF:
        return make_to(_tuple(hi + 1, True))
    year, month, day = ymd(lo)
    starts_a_year = (month, day) in ((1, 1), (1, 2))                        # the engine counts "from YEAR" from the day after its first day
    if hi >= INF:
        return make_from((0, 0, year) if starts_a_year else _tuple(lo - 1, False))      # "from" excludes its own day, so it starts one day earlier
    return make_span((0, 0, year) if starts_a_year else _tuple(lo, True), _tuple(hi, False))


def _split(ref, period):
    """The old link without the years of the new one: (left piece, right piece), either may be None."""
    iv = interval(ref.get("date") or {})
    if iv is None:
        return None, None
    lo, hi = _bound(period[0], False), _bound(period[1], True)
    left, right = (iv[0], min(iv[1], lo - 1)), (max(iv[0], hi + 1), iv[1])
    return (_piece(*left) if left[0] <= left[1] else None), (_piece(*right) if right[0] <= right[1] else None)


def _name_really_ended(rec, end_text):
    """Does the answer say that the name of the place ended: a later name of the place starts in the year of that end or the next one? The period that the
    answer gives to the place itself (a municipality 1806-2013) is not the period of its name: the village goes on being called Sissa."""
    try:
        end_year = ymd(_bound(end_text, True))[0]
    except Exception:                                                        # a date that is not understood: nothing says that the name ended
        return False
    return any(o["from"] and ymd(_bound(o["from"], False))[0] in (end_year, end_year + 1) for o in rec["other_names"])
