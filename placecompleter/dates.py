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
"""Gramps date semantics needed for place hierarchies (Gramps 6.0/6.1).

Dates are the JSON dictionaries Gramps stores: modifier, quality, calendar,
dateval (day, month, year, slash[, day, month, year, slash]), sortval, text.
The matching rule of a place link or name against an event date is Gramps'
Date.match_exact(): it compares ONE point, the event date's sort value.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import datetime

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .i18n import _ as tr

M_NONE, M_BEFORE, M_AFTER, M_ABOUT, M_RANGE, M_SPAN, M_TEXT, M_FROM, M_TO = range(9)
INF = 10 ** 9
EPOCH = 1721425          # Julian day number = date.toordinal() + EPOCH (Gregorian)
ABOUT_RANGE = 50         # Gramps setting behavior.date-about-range (years)


def sdn(year, month, day):
    """Julian day number of a Gregorian date. The day may overflow the month."""
    return datetime.date(year, month, 1).toordinal() + EPOCH + (day - 1)


def ymd(sortval):
    d = datetime.date.fromordinal(int(sortval) - EPOCH)
    return d.year, d.month, d.day


def year_of(sortval):
    try:
        return ymd(sortval)[0]
    except (ValueError, OverflowError, TypeError):
        return None


def parts(d):
    dv = d.get("dateval") or [0, 0, 0, False]
    start = tuple(dv[0:3])
    stop = tuple(dv[4:7]) if len(dv) >= 8 else (0, 0, 0)
    return start, stop


def is_empty(d):
    """Gramps Date.is_empty(): no text and no date parts."""
    if not d:
        return True
    start, stop = parts(d)
    return not ((d.get("modifier") == M_TEXT and d.get("text"))
                or start != (0, 0, 0) or stop != (0, 0, 0))


def range_interval(d, about_range=None):
    """Inclusive sort-value interval of a range or span (Date.get_start_stop_range)."""
    about = ABOUT_RANGE if about_range is None else about_range
    (day1, month1, year1), (day2, month2, year2) = parts(d)
    if (day2, month2, year2) == (0, 0, 0):
        day2, month2, year2 = day1, month1, year1
    start = [year1, month1 or 1, day1 or 1]
    stop = [year2 or year1, month2 or 12, day2 or 31]
    if d.get("quality") == 1:       # estimated: widened by +-about_range years
        start[0] -= about
        stop[0] += about
    try:
        return sdn(*start), sdn(*stop)
    except (ValueError, OverflowError):
        sv = d.get("sortval") or 0
        return sv, sv


def interval(d, about_range=None):
    """Sort values an event date may have to match this link/name date, or None.

    Returns (low, high), inclusive. None means it never matches (about, text).
    """
    if is_empty(d):
        return (-INF, INF)
    mod, sv = d.get("modifier"), d.get("sortval") or 0
    if mod == M_NONE:
        return (sv, sv)
    if mod in (M_BEFORE, M_TO):
        return (-INF, sv - 1)
    if mod in (M_AFTER, M_FROM):
        return (sv + 1, INF)
    if mod in (M_RANGE, M_SPAN):
        return range_interval(d, about_range)
    return None


def match_exact(event_date, other, about_range=None):
    """Gramps Date.match_exact(event_date, other)."""
    iv = interval(other, about_range)
    if iv is None:
        return False
    return iv[0] <= (event_date.get("sortval") or 0) <= iv[1]


def merge(intervals):
    """Union of inclusive intervals as a sorted list of disjoint intervals."""
    out = []
    for lo, hi in sorted(i for i in intervals if i):
        if out and lo <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def make_span(start, stop):
    """A SPAN date dictionary from two (day, month, year) tuples (Gramps' dateval order)."""
    day1, month1, year1 = start
    day2, month2, year2 = stop
    return {"_class": "Date", "format": None, "calendar": 0, "modifier": M_SPAN,
            "quality": 0, "newyear": 0, "text": "",
            "dateval": [day1, month1, year1, False, day2, month2, year2, False],
            "sortval": sdn(year1, month1 or 1, day1 or 1)}


def make_from(start):
    """A FROM date dictionary from a (day, month, year) tuple.

    Gramps matches "from X" only for event dates strictly after X (an event dated
    exactly X does not match), which the engine's simulation reproduces.
    """
    day, month, year = start
    return {"_class": "Date", "format": None, "calendar": 0, "modifier": M_FROM, "quality": 0,
            "newyear": 0, "text": "", "dateval": [day, month, year, False],
            "sortval": sdn(year, month or 1, day or 1)}


def make_to(stop):
    """A TO date dictionary from a (day, month, year) tuple: matches event dates strictly before it."""
    day, month, year = stop
    return {"_class": "Date", "format": None, "calendar": 0, "modifier": M_TO, "quality": 0, "newyear": 0, "text": "",
            "dateval": [day, month, year, False], "sortval": sdn(year, month or 1, day or 1)}


def describe(d):
    """Short human text of a date dictionary, for reports."""
    if is_empty(d):
        return tr("(no date)")
    mod, (s, e) = d.get("modifier"), parts(d)

    def fmt(t):
        day, month, year = t
        return "-".join(str(x) for x in ((year,) + ((month,) if month else ()) + ((day,) if day and month else ())))
    names = {M_NONE: "", M_BEFORE: tr("before "), M_AFTER: tr("after "), M_ABOUT: tr("about "),
             M_FROM: tr("from "), M_TO: tr("to ")}
    if mod in (M_RANGE, M_SPAN):
        return "%s %s..%s" % ("range" if mod == M_RANGE else "span", fmt(s), fmt(e))
    if mod == M_TEXT:
        return "text:%r" % d.get("text")
    return names.get(mod, "") + fmt(s) + (tr(" (est.)") if d.get("quality") == 1 else "")
