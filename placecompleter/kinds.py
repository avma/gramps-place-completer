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
"""The types of places: the size classes of a settlement, the custom types of the user's tree, the type of a level from the word of the answer, and
whether two types are the same kind.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os
import re

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import data as datalib
from .words import fold


OVERLAY_WORDS = ("intercommunal", "intercommunity", "intermunicipal")    # a structure that overlaps the levels without being inside one (a French intercommunality)


SETTLEMENT_CLASSES = {"metropolis": 4, "city": 4, "town": 15, "village": 16, "hamlet": 17, "neighborhood": 11, "locality": 6}


SETTLEMENT_TYPES = (("unincorporated", 6), ("hamlet", 17), ("market town", 15), ("town", 15), ("village", 16), ("city", 4),
                    ("borough", 13), ("municipality", 14), ("locality", 6), ("neighborhood", 11), ("neighbourhood", 11))


def conventions_file(directory=""):
    """The file that describes the custom place types of the user's own tree: the file that PLACECOMPLETER_CONVENTIONS names, else
    ~/.config/placecompleter/type-conventions.json (an update of the addon does not touch it), else the one that comes with the addon
    (data/type-conventions.json: empty). With `directory` (the tests): data/type-conventions.json of that folder."""
    if directory:
        return os.path.join(directory, "type-conventions.json")
    for candidate in (os.environ.get("PLACECOMPLETER_CONVENTIONS", ""), os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "type-conventions.json")):
        if candidate and os.path.isfile(candidate):
            return candidate
    return os.path.join(datalib.DATA_DIR, "type-conventions.json")


def load_tree_types(directory=""):
    """The custom place types of the user's own tree (see conventions_file): the type of a province, of an empire, of a monarchy, and the
    types that are districts. A missing or empty entry means the type of Gramps itself."""
    data = datalib.load_path(conventions_file(directory), {})
    data = data if isinstance(data, dict) else {}
    districts = data.get("district")
    rules = []
    for rule in data.get("rules") if isinstance(data.get("rules"), list) else []:
        if isinstance(rule, dict) and isinstance(rule.get("words"), list) and any(rule["words"]):
            value = rule.get("value", 0)
            rules.append({"words": [fold(str(w)) for w in rule["words"] if w], "value": value if isinstance(value, int) else 0,
                          "string": str(rule.get("string") or "")})
    return {"province": str(data.get("province") or ""), "empire": str(data.get("empire") or ""), "monarchy": str(data.get("monarchy") or ""),
            "district": [str(x) for x in districts if x] if isinstance(districts, list) else [], "rules": rules,
            "settlements": [str(x) for x in data.get("settlements") if x] if isinstance(data.get("settlements"), list) else []}


TREE_TYPES = load_tree_types()


def _custom(role, builtin):
    """The type of a unit that Gramps has no type for: the custom type of the tree, else the type of Gramps."""
    text = TREE_TYPES[role]
    return {"value": 0, "string": text} if text else {"value": builtin, "string": ""}


# the user's own convention for administrative units (learned from the tree); None = ask
CONTAINER_TYPES = (
    (("voivodeship", "crownland", "kronland", "vajdasag"), _custom("province", 8)),
    (("empire", "kaisertum", "kaiserreich"), _custom("empire", 1)),
    (("county", "komitat", "varmegye"), {"value": 3, "string": ""}),
    (("district", "bezirk", "kreis", "jaras", "kerulet"), {"value": 12, "string": ""}),
    (("township",), {"value": 0, "string": "Township"}),   # before "town": a township is not a town
    (("city",), {"value": 4, "string": ""}), (("town",), {"value": 15, "string": ""}), (("village",), {"value": 16, "string": ""}),
    (("hamlet",), {"value": 17, "string": ""}), (("borough",), {"value": 13, "string": ""}),
    (("municipal",), {"value": 14, "string": ""}), (("parish",), {"value": 5, "string": ""}),
    (("province",), {"value": 8, "string": ""}), (("region",), {"value": 9, "string": ""}), (("department",), {"value": 10, "string": ""}),
    (("neighborhood", "neighbourhood"), {"value": 11, "string": ""}), (("locality",), {"value": 6, "string": ""}),
    (("country", "republic", "kingdom", "commonwealth"), {"value": 1, "string": ""}), (("state",), {"value": 2, "string": ""}),
)


def _type_matches(tree, handle, wanted_text):
    ptype = tree.places[handle]["type"]
    low = (wanted_text or "").lower()
    if any(w in low for w in ("voivodeship", "crownland", "kronland")):
        return (bool(TREE_TYPES["province"]) and ptype.get("string") == TREE_TYPES["province"]) or ptype.get("value") in (8, 9)
    if re.search(r"\bstate\b", low):                      # "state", "State of New York", "federal state"
        return ptype.get("value") in (1, 2)
    if any(w in low for w in ("empire", "kaisertum")):
        return (bool(TREE_TYPES["empire"]) and ptype.get("string") == TREE_TYPES["empire"]) or ptype.get("value") == 1
    if any(w in low for w in ("county", "komitat")):
        return ptype.get("value") == 3
    if any(w in low for w in ("district", "bezirk", "kreis")):
        return (bool(ptype.get("string")) and ptype.get("string") in TREE_TYPES["district"]) or ptype.get("value") == 12
    expected = _container_type(wanted_text)                                   # a type of the rules of the tree, or the answer's own word
    if expected and expected["value"] == 0 and expected["string"]:
        return (ptype.get("string") or "").casefold() == expected["string"].casefold()
    return False


_SUBDIVISIONS = {3, 8, 9, 10, 12}                          # county, province, region, department, district: the tree may use any of them for one


TYPE_NAMES = {1: "Country", 2: "State", 3: "County", 4: "City", 5: "Parish", 6: "Locality", 7: "Street", 8: "Province", 9: "Region", 10: "Department",
              11: "Neighborhood", 12: "District", 13: "Borough", 14: "Municipality", 15: "Town", 16: "Village", 17: "Hamlet", 18: "Farm", 19: "Building", 20: "Number"}
def type_name(value):
    """The name of a type of place for the user: the word that Gramps itself shows in the Type column (its own translation: it differs between the versions
    of Gramps, for example State and Province in Hebrew), and the English word when Gramps cannot be asked."""
    english = TYPE_NAMES.get(value)
    if english is None:
        return str(value)
    try:
        from gramps.gen.lib import PlaceType
        return str(PlaceType(value))
    except Exception:                                                      # (the engine runs without Gramps too: the tests of the engine, the command line)
        return english


def has_no_type(kind):
    """Does a place have no type? In Gramps two types show as an empty field: Unknown (value -1) and a type of the user's own (value 0, CUSTOM) with
    an empty text: the Type column is blank for both, and a place with either is a place that is given the type that the answer gives."""
    kind = kind or {}
    value = kind.get("value", -1)
    return value in (None, -1) or (value == 0 and not (kind.get("string") or "").strip())


_AREA_TYPES = {1, 2} | _SUBDIVISIONS                      # country, state, county, province, region, department, district


_SETTLEMENT_TYPES = {4, 6, 13, 14, 15, 16, 17}             # city, locality, borough, municipality, town, village, hamlet


def _type_conflict(tree, handle, type_text):
    """The answer names an area (province, county, region, state, canton ...) and the place of the tree is a settlement (city, town, village ...): they
    share a name (Parma the province, Parma the city) and are not the same place."""
    expected = _container_type(type_text)
    if not expected:
        return False
    area = expected["value"] in _AREA_TYPES or (expected["value"] == 0 and bool(expected["string"]))
    return area and (tree.places[handle].get("type") or {}).get("value") in _SETTLEMENT_TYPES


def _same_kind(tree, handle, type_text):
    """The place of the tree is of the kind that the answer gives the unit: the same type, or both subdivisions of a state (county, province, district ...:
    the tree may call one by another of these names), or both a country or a state."""
    if _type_matches(tree, handle, type_text):
        return True
    expected = _container_type(type_text)
    if not expected or expected["value"] <= 0:
        return False
    value = (tree.places[handle].get("type") or {}).get("value")
    return value == expected["value"] or {value, expected["value"]} <= _SUBDIVISIONS or {value, expected["value"]} <= {1, 2}


def _state_type(name):
    low = fold(name or "")
    if any(w in low for w in ("empire", "kaisertum", "kaiserreich")):
        return _custom("empire", 1)
    if any(w in low for w in ("monarchy", "monarchie", "monarchia")):
        return _custom("monarchy", 1)
    return {"value": 1, "string": ""}


_TYPE_WORDS = {"country", "state", "province", "region", "county", "district", "municipality", "canton", "borough", "parish", "department", "prefecture",
               "governorate", "oblast", "commune", "township", "ward", "principality", "duchy", "kingdom", "empire", "republic", "federation",
               "confederation", "territory", "colony", "dominion", "archduchy", "margraviate", "hundred", "shire", "riding", "voivodeship", "crownland"}


def _own_type(text):
    """The type of a unit that no rule of the tree and no type of Gramps fits: the answer's own word, as a custom type (a canton is a canton: no
    artificial type is forced on it). The English generic word of the answer is preferred; else its first words. None when the answer says nothing."""
    parts = [p.strip() for p in re.split(r"[,;/()]", text or "") if p.strip()]
    for part in parts:
        if any(w in _TYPE_WORDS for w in re.split(r"[^a-z]+", fold(part))):
            return {"value": 0, "string": part[:1].upper() + part[1:]}
    return {"value": 0, "string": parts[0][:1].upper() + parts[0][1:40]} if parts else None


def _container_type(text):
    low = fold(text or "")
    for rule in TREE_TYPES["rules"]:                                          # the conventions of the tree come first
        if any(re.search(r"\b%s\b" % re.escape(w), low) for w in rule["words"]):
            return {"value": rule["value"], "string": rule["string"]}
    for words, ptype in CONTAINER_TYPES:
        if any(w in low for w in words):
            return ptype
    return _own_type(text)
