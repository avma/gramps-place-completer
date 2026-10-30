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
"""The places that the answer makes, and what it says about the places that exist: the new place of the question with its names, type and coordinates, and the plain
name, the language and the type of the levels.
"""

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
from . import names as namelib
from . import rules
from .evidence import MAIN_FIELDS, UNIT_FIELDS, _sources
from .kinds import has_no_type, _container_type, _same_kind, _state_type
from .matching import _alternatives, _is_unit_name
from .periods import _date, _name_really_ended
from .screen import _need
from .words import fold


def new_place(a):
    """The proposals; the new place of the question with its name, type and coordinates when the tree does not have it."""
    child, link_offer, name = a.child, a.link_offer, a.name
    name_plain, out, rec = a.name_plain, a.out, a.rec
    ruling, skip, state_began = a.ruling, a.skip, a.state_began
    unit_lang = a.unit_lang
    # ------------- proposals
    proposals = []
    props_new = {}

    def place_for(u):
        if u["handle"]:
            return u["handle"]
        c = u["mention"]
        shown = namelib.plain_name(c["name"], None, c["type"])
        if (not c.get("is_state") and "county" in c["type"].lower() and "county" not in shown.lower()
                and (rec["language"] in (None, "en"))):
            shown += " County"
        ptype = _state_type(c["name"]) if c.get("is_state") else _container_type(c["type"])
        base = key = "new:ai-%s" % re.sub(r"\W+", "", fold(shown))
        word = (re.findall(r"[a-z]+", fold(c["type"])) or ["level"])[0]
        kind_of = ((ptype or {}).get("value", -1), (ptype or {}).get("string", ""))
        while rules.on("LV2") and (key == child or key in props_new and (props_new[key]["type_value"], props_new[key]["type_string"]) != kind_of):
            key = "%s-%s" % (base, word) if key == base else key + "x"           # one name, two different places (a canton and the commune that is its seat)
        if key != base:
            _need(out, "level «%s» (%s) matches the name of child place or parent tier; created as distinct place «%s»",
                  c["name"], c["type"], shown)
        if key not in props_new:
            p = {"kind": "add-place", "confidence": "assumption", "basis": "assumption", "handle": key,
                 "gramps_id": "NEW-" + key[7:], "names": [{"value": shown, "lang": unit_lang(c), "date": _date(c["from"], c["to"])}],
                 "type_value": (ptype or {}).get("value", -1), "type_string": (ptype or {}).get("string", ""),
                 "lat": "", "lon": "", "urls": [], "origin": "ai-answer", "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0,
                 "conflict": False, "old": {}, "new": {}, "bundle": "ingest-%s" % re.sub(r"\W+", "", fold(name)),
                 "note": "the name is as the answer wrote it (English): rename it if needed"}
            props_new[key] = p
            proposals.append(p)
        return key

    if child.startswith("new:"):
        lat, lon = rec["coordinates"] or ("", "")
        first = dict(next((c for n, c in enumerate(rec["containers"], 1) if n not in skip), {}))
        if first and fold(first.get("name")) not in {fold(name), fold(name_plain)}:
            first = {}                                                       # the first level is the parent (Sissa Trecasali 2014-): its years are not those of the name
        if rules.on("NP1") and first.get("to") and not _name_really_ended(rec, first["to"]):
            _need(out, "response defines period %s-%s for place; as no subsequent name is specified, name «%s» period end date "
                       "remains open", first.get("from") or "?", first["to"], name_plain)
            first["to"] = None
        if rules.on("NP3") and not first.get("from") and not first.get("to") and state_began:
            first["from"] = state_began
            _need(out, "name «%s» applies from %s (establishment of ruling state %s); provided in state official language (inferred)", name, state_began, ruling)
        proposals.append({
            "kind": "add-place", "confidence": "assumption", "basis": "assumption", "handle": child, "gramps_id": "NEW-%s" % child[7:],
            "names": [{"value": name_plain, "lang": rec["language"] or "", "date": _date(first.get("from"), first.get("to"))}],
            "type_value": rec["type_value"] if rec["type_value"] is not None else (0 if rec["type_string"] else -1), "type_string": rec["type_string"],
            "lat": str(lat), "lon": str(lon), "urls": [{"path": o["path"], "type": "Web Home"} for o in link_offer if o["chosen"]],
            "origin": "ai-answer", "evidence": _sources(rec, MAIN_FIELDS), "events": 1, "worse": 0, "conflict": False, "old": {}, "new": {},
            "bundle": "ingest-%s" % re.sub(r"\W+", "", fold(name))})
    a.keep(locals(), "place_for", "proposals")


def fix_levels(a):
    """What the answer says about the levels that exist: the plain name, the language, the type."""
    aliases, child, proposals = a.aliases, a.child, a.proposals
    rec, tree, typed_changed = a.rec, a.tree, a.typed_changed
    unit_lang, unit_names, units = a.unit_lang, a.unit_names, a.units
    for u in units:
        if u.get("handle") and u["handle"] != child:
            held = tree.places[u["handle"]]
            kind = held["type"] or {}
            primary = held["name"].get("value") or ""
            simple = namelib.plain_name(primary, kind.get("value"), kind.get("string", ""))
            if simple and simple != primary:
                proposals.append({"confidence": "assumption", "basis": "assumption", "conflict": False, "origin": "ai-answer",
                                  "evidence": [], "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {}, "kind": "rename-place",
                                  "place": u["handle"], "index": 0, "value": primary, "new_value": simple,
                                  "lang": held["name"].get("lang") or "", "keep_old": True})
    done_language = set()
    for u in units:
        lang = unit_lang(u["mention"]) if rules.on("NL") and u.get("handle") and u["handle"] != child else ""
        if lang:
            wanted = unit_names(u["mention"])
            kind = tree.places[u["handle"]]["type"] or {}
            for position, n in enumerate(tree.all_names(u["handle"])):
                if (u["handle"], position) in done_language or (n.get("lang") or ""):
                    continue
                if _is_unit_name(n.get("value"), kind, wanted, _alternatives(u["mention"]["name"], aliases)):
                    done_language.add((u["handle"], position))
                    proposals.append({"confidence": "assumption", "basis": "assumption", "conflict": False, "origin": "ai-answer",
                                      "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {},
                                      "kind": "set-name-language", "place": u["handle"], "index": position, "value": n["value"],
                                      "lang": lang})
        # a unit that is in the tree with no type gets the type the answer gives it (an empty field is filled, a filled one is never touched)
        if u.get("handle") and u["handle"] != child:
            held = tree.places[u["handle"]]["type"] or {}
            ptype = _state_type(u["mention"]["name"]) if u["mention"].get("is_state") else _container_type(u["mention"]["type"])
            if ptype and has_no_type(held):
                proposals.append({"confidence": "assumption", "basis": "assumption", "conflict": False, "origin": "ai-answer",
                                  "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {},
                                  "kind": "set-type", "place": u["handle"], "index": None, "type_value": ptype["value"],
                                  "type_string": ptype["string"]})
            elif (ptype and held.get("value", -1) > 0 and (ptype["value"], ptype["string"]) != (held["value"], held.get("string") or "")
                  and u["handle"] not in typed_changed
                  and not _same_kind(tree, u["handle"], ("empire" if _state_type(u["mention"]["name"])["value"] == 0 else "state")
                                     if u["mention"].get("is_state") else u["mention"]["type"])):
                # a type of Gramps that is not the kind of unit that the answer names (a region typed State): a change to data that exists
                typed_changed.add(u["handle"])
                proposals.append({"confidence": "assumption", "basis": "assumption", "conflict": False, "origin": "ai-answer", "inferred": True,
                                  "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {},
                                  "kind": "change-type", "place": u["handle"], "index": None, "type_value": ptype["value"], "type_string": ptype["string"],
                                  "old_type_value": held["value"], "old_type_string": held.get("string") or ""})
