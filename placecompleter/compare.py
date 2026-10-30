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
"""Comparing answers: two answers for the same place, and an answer with the answers that were saved before.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import glob
import os
import re

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .wikidata import km
from .reader import parse_structured
from .words import _tokens, fold


def _key(name):
    return " ".join(sorted(_tokens(name or "")))


def _answer_year(path):
    m = re.search(r"_(\d{4})(?:_|\.|$)", os.path.basename(path))
    return m.group(1) if m else None


def _same_place(a, b):
    if a["coordinates"] and b["coordinates"]:
        return km(a["coordinates"], b["coordinates"]) <= 3
    return bool(set(_tokens(a["name"] or "")) & set(_tokens(b["name"] or "")))


def compare_answers(rec, other, label, same_date):
    """Where two answers about the same place disagree (facts that do not depend on the date always; name and type only for the same date)."""
    msgs = []
    if rec["coordinates"] and other["coordinates"]:
        d = km(rec["coordinates"], other["coordinates"])
        if d > 1:
            msgs.append("coordinates are %.1f km apart (%s, %s in this answer; %s, %s in %s)" % (d, *rec["coordinates"], *other["coordinates"], label))
    if same_date:
        if rec["name"] and other["name"] and fold(rec["name"]) != fold(other["name"]):
            msgs.append("it names the place %r on this date; %s says %r" % (rec["name"], label, other["name"]))
        if rec["type_value"] is not None and other["type_value"] is not None and rec["type_value"] != other["type_value"]:
            msgs.append("type on this date: %r here, %r in %s" % (rec["type_text"], other["type_text"], label))
    mine = {_key(c["name"]): c for c in rec["containers"]}
    for c in other["containers"]:
        m = mine.get(_key(c["name"]))
        if m and (m["from"] != c["from"] or m["to"] != c["to"]):
            msgs.append("%s: valid %s-%s here, %s-%s in %s" % (m["name"], m["from"], m["to"] or "present", c["from"], c["to"] or "present", label))
    own = {fold(o["name"]): o for o in rec["other_names"]}
    for o in other["other_names"]:
        m = own.get(fold(o["name"]))
        if m and (m["from"] != o["from"] or m["to"] != o["to"]):
            msgs.append("name %r: %s-%s here, %s-%s in %s" % (o["name"], m["from"], m["to"] or "present", o["from"], o["to"] or "present", label))
    return msgs


def compare_with_saved(rec, folder, date, skip_path=None):
    """Compare the answer with every saved answer about the same place (same coordinates within 3 km, or a shared name)."""
    out = []
    for path in sorted(glob.glob(os.path.join(folder, "*.txt"))):
        if skip_path and os.path.abspath(path) == os.path.abspath(skip_path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                other = parse_structured(fh.read())
        except OSError:
            continue
        if not other["name"] or not _same_place(rec, other):
            continue
        year = _answer_year(path)
        out += compare_answers(rec, other, os.path.basename(path), year is not None and str(date)[:4] == year)
    return list(dict.fromkeys(out))[:12]
