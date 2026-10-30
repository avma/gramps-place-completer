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
"""The administrative levels that a place has in a country on a given year (data/hierarchies.json): they go into the question, so that the AI lists the
right levels in the right order, and they are used to say when an answer lacks a level that the country has on that date. Starter data: to be checked."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import data as datalib, packs
from .i18n import _ as tr


def _fold(text):
    return packs.fold(text or "")


def load(directory=""):
    """[{key, names, periods: [{from, to, state, levels}]}], leaving out what is damaged."""
    data = datalib.load("hierarchies.json", {}, directory)
    out = []
    for country in data.get("countries") if isinstance(data, dict) and isinstance(data.get("countries"), list) else []:
        if not (isinstance(country, dict) and isinstance(country.get("names"), list) and isinstance(country.get("periods"), list)):
            continue
        periods = [p for p in country["periods"] if isinstance(p, dict) and isinstance(p.get("from"), int) and isinstance(p.get("levels"), list)]
        if periods:
            out.append({"key": str(country.get("key") or ""), "names": [str(n) for n in country["names"] if n], "periods": periods})
    return out


COUNTRIES = load()


def find_country(text, countries=None):
    """The country whose name or alias is this text (or one of its comma-separated words), else None."""
    parts = [text or ""] + [p for p in re.split(r"[,;]", text or "") if p.strip()]
    for country in countries or COUNTRIES:
        names = {_fold(n) for n in country["names"]}
        if any(_fold(p).strip() in names for p in parts):
            return country
    return None


def year_of(date_text):
    found = re.search(r"\d{4}", str(date_text or ""))
    return int(found.group()) if found else None


def period_for(country, year):
    """The period of the country that holds this year, or None."""
    if not country or year is None:
        return None
    return next((p for p in country["periods"] if p["from"] <= year <= (p.get("to") if p.get("to") is not None else 9999)), None)


def levels(period):
    """[(type, local term, optional)] of a period."""
    out = []
    for text in period["levels"]:
        text = str(text)
        optional = text.startswith("?")
        kind, _sep, local = text.lstrip("?").partition("|")
        out.append((kind.strip(), local.strip(), optional))
    return out


def prompt_line(country, year):
    """The sentence of the question that lists the levels ('' when the country or the year is not known)."""
    period = period_for(country, year)
    if not period:
        return ""
    shown = ["%s (%s)%s" % (kind, local, tr(" [may not apply]") if optional else "") if local else kind for kind, local, optional in levels(period)]
    return tr("Administrative hierarchy for %s in %d (from local to national): %s. Select applicable types for this place; "
              "add intermediate levels only if historically accurate. ") % (country["names"][0], year, "; ".join(shown))


def missing(country, year, container_types):
    """[(type, local term)] of the levels that the country has on that year, that do not 'may not apply', and that no container of the answer has."""
    period = period_for(country, year)
    if not period:
        return []
    texts = [_fold(t) for t in container_types]
    found = []
    for kind, local, optional in levels(period):
        if optional:
            continue
        words = {_fold(kind)} | {_fold(w) for w in re.split(r"[,()/]", local) if w.strip()}
        if not any(w and w in text for w in words for text in texts):
            found.append((kind, local))
    return found
