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
"""The level that a type of place has in a hierarchy, and what may be inside what. Rules of the analysis (docs/ANALYZER_RULES.md, table 2):
T1 a place is not inside itself (no loop); T2 the parent is on a higher level than the place (a country may be inside a country: federations);
T3 a place is not inside a place of its own type; T4 settlements are on one level and are not inside one another; T5 a type with no level has no rule."""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .i18n import _ as tr
from .typelearn import type_key

COUNTRY, AREA, MUNICIPALITY, SETTLEMENT, SUB_SETTLEMENT, STREET, BUILDING = 1, 2, 3, 4, 5, 6, 7

# the types of Gramps: Country 1, State 2, County 3, City 4, Parish 5 (no level), Locality 6 (no level), Street 7, Province 8, Region 9, Department 10,
# Neighborhood 11, District 12, Borough 13, Municipality 14, Town 15, Village 16, Hamlet 17, Farm 18, Building 19, Number 20
_BY_VALUE = {1: COUNTRY, 2: AREA, 3: AREA, 8: AREA, 9: AREA, 10: AREA, 12: AREA, 14: MUNICIPALITY, 4: SETTLEMENT, 15: SETTLEMENT, 16: SETTLEMENT,
             17: SETTLEMENT, 11: SUB_SETTLEMENT, 13: SUB_SETTLEMENT, 7: STREET, 18: BUILDING, 19: BUILDING, 20: BUILDING}


def _same(a, b):
    return a.get("value", -1) == b.get("value", -1) and type_key(a.get("string")) == type_key(b.get("string"))


def level(ptype, conventions):
    """The level (1..7) of a type ({"value", "string"}), or None when it has none (T5: no rule applies to it)."""
    if not ptype:
        return None
    value = ptype.get("value", -1)
    if value in _BY_VALUE:
        return _BY_VALUE[value]
    text = type_key(ptype.get("string"))
    if value != 0 or not text:
        return None
    custom = {"empire": COUNTRY, "monarchy": COUNTRY, "province": AREA}
    for key, found in custom.items():
        if conventions.get(key) and text == type_key(conventions[key]):
            return found
    if text in {type_key(s) for s in conventions.get("district", [])}:
        return AREA
    if text in {type_key(r["string"]) for r in conventions.get("rules", []) if r.get("string")}:
        return AREA                                                          # canton, járás ...: the types that the rules of the tree name
    if text in {type_key(s) for s in conventions.get("settlements", [])}:
        return SETTLEMENT
    return None


def violation(parent, child, conventions):
    """Why a place of the type `child` cannot be inside a place of the type `parent` ('' when it can, or when a type has no level)."""
    lp, lc = level(parent, conventions), level(child, conventions)
    if lp is None or lc is None:
        return ""
    if lp == COUNTRY and lc == COUNTRY:
        return ""                                                            # federations, countries inside countries
    if _same(parent, child):
        return tr("a place cannot contain another place of identical administrative type")
    if lp == SETTLEMENT and lc == SETTLEMENT:
        return tr("settlement places belong to a single tier; nesting settlements is invalid")
    if lp == AREA and lc == AREA:
        return ""                                                            # a county in a state, a district in a province
    if lp >= lc:
        return tr("parent place administrative level rank is lower than child place")
    return ""
