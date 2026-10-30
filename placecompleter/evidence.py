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
"""The evidence of a proposal: the sources of an answer, the fields that each source supports, and the proposal to add a web link.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re


def url_proposal(place, offered, evidence, origin="ai-answer", basis="assumption"):
    """The proposal to add one web link to a place of the tree (offered: an item of links.select_links)."""
    return {"kind": "add-url", "confidence": "assumption" if basis == "assumption" else "evidence", "basis": basis, "place": place, "path": offered["path"],
            "url_kind": offered["kind"], "optional": not offered["chosen"], "note": offered["reason"], "old": {}, "new": {}, "conflict": False,
            "origin": origin, "evidence": evidence, "events": 0, "worse": 0, "bundle": None}


MAIN_FIELDS = ("PLACE_NAME_ON_DATE", "SETTLEMENT_TYPE_ON_DATE", "COORDINATES", "OTHER_NAMES", "LANGUAGE", "CONTAINERS")


UNIT_FIELDS = ("CONTAINERS", "STATE_ON_DATE")


_ALL_LABELS = {"PLACE_NAME_ON_DATE", "LANGUAGE", "OTHER_NAMES", "SETTLEMENT_TYPE_ON_DATE", "COORDINATES", "CONTAINERS", "STATE_ON_DATE"}


# What a page is said to support, in the words of the AI (it writes "supports name, coordinates and administrative history", not the labels)
_FIELD_WORDS = {
    "PLACE_NAME_ON_DATE": {"name", "names", "spelling", "called", "dialect", "alias", "naming"},
    "OTHER_NAMES": {"name", "names", "spelling", "called", "dialect", "alias", "naming"},
    "LANGUAGE": {"language", "dialect"},
    "COORDINATES": {"coordinates", "coordinate", "latitude", "longitude", "location", "geographic"},
    "SETTLEMENT_TYPE_ON_DATE": {"type", "status", "settlement", "comune", "commune", "municipality"},               # (not city, town, village: part of names)
    "CONTAINERS": {"administrative", "administration", "hierarchy", "containers", "province", "region", "county", "district", "canton", "parent", "merger",
                   "merged", "boundaries", "history", "belongs", "within"},
    "STATE_ON_DATE": {"state", "country", "sovereign", "empire", "kingdom", "republic"},
}


def _supported_fields(text):
    """The fields of the answer that a page is said to support: the labels as written, and the fields that its words are about. Empty when the text
    is about none of them (then the page is a general one)."""
    tokens = {t for t in re.split(r"\W+", (text or "").lower()) if t}
    found = {t.upper() for t in tokens} & _ALL_LABELS
    found |= {label for label, words in _FIELD_WORDS.items() if tokens & words}
    return found


def _sources(rec, fields=None):
    """The pages the answer lists, as evidence. With `fields`: only those that the answer cites for one of these fields (a page that says
    nothing about them is no evidence for them), each with only the fields that matter here."""
    out = []
    for s in rec["sources"]:
        supported = _supported_fields(s["supports"])
        if fields and supported and not supported & set(fields):
            continue
        claim = ", ".join(f for f in fields if f in supported) if fields and supported else (s["supports"] or "")
        out.append({"source": "ai-answer", "url": s["url"], "claim": claim})
    return out
