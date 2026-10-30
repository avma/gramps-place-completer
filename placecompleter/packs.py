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
"""Regional packs: place links and names with dates and evidence (JSON).

A pack lists places (by name) and dated parent links between them. It is matched
to the places of a tree by name; proposals are made only when both ends match
exactly one place, and only when the link would fix events (checked by
simulation). Every non-user edge must carry evidence.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import functools
import json
import re
import unicodedata

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .dates import INF, interval, is_empty, make_from, make_span, sdn

SCHEMA = "placecompleter.pack.v1"
ISO = re.compile(r"^(\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?$")
ORIGINS = ("user", "agent", "wikidata", "table")


class PackError(ValueError):
    pass


@functools.lru_cache(maxsize=262144)                    # the same names are folded again and again (every level of an answer meets every place of the tree)
def fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def parse_iso(text):
    """'1804', '1804-05' or '1804-05-17' -> (day, month, year) like Gramps' dateval."""
    m = ISO.match(str(text or ""))
    if not m:
        raise PackError("bad date %r (use YYYY, YYYY-MM or YYYY-MM-DD)" % (text,))
    year, month, day = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    if not (0 <= month <= 12 and 0 <= day <= 31 and year >= 1):
        raise PackError("date out of range: %r" % (text,))
    return (day, month, year)


def _names(place):
    out = []
    for n in place.get("names") or []:
        out.append(n if isinstance(n, str) else n.get("name", ""))
    return [n for n in out if n]


def _dated_names(place):
    """Pack names that carry a period, as the dictionaries of the pack."""
    return [n for n in place.get("names") or [] if isinstance(n, dict) and n.get("valid_from")]


def validate(data):
    errors = []
    if data.get("schema") != SCHEMA:
        errors.append("schema must be %s" % SCHEMA)
    keys = set()
    for p in data.get("places") or []:
        if not p.get("key") or p["key"] in keys:
            errors.append("place without a unique key: %r" % (p.get("key"),))
        keys.add(p.get("key"))
        if not _names(p):
            errors.append("place %r has no names" % (p.get("key"),))
        for n in p.get("names") or []:
            if isinstance(n, dict) and (n.get("valid_from") or n.get("valid_to")):
                try:
                    start = parse_iso(n.get("valid_from"))
                    stop = parse_iso(n["valid_to"]) if n.get("valid_to") else None
                    if stop and (start[2], start[1], start[0]) > (stop[2], stop[1] or 12, stop[0] or 31):
                        errors.append("name %r: valid_from is after valid_to" % n.get("name"))
                except PackError as err:
                    errors.append("name %r: %s" % (n.get("name"), err))
                if n.get("origin", p.get("origin")) not in (None, "user") and not (n.get("evidence") or p.get("evidence")):
                    errors.append("name %r: evidence is required" % n.get("name"))
    for p in data.get("places") or []:
        life = p.get("lifetime")
        if life:
            try:
                if life.get("valid_from"):
                    parse_iso(life["valid_from"])
                end = parse_iso(life.get("valid_to"))
                if life.get("valid_from"):
                    start = parse_iso(life["valid_from"])
                    if (start[2], start[1], start[0]) > (end[2], end[1] or 12, end[0] or 31):
                        errors.append("lifetime of %r: valid_from is after valid_to" % p.get("key"))
            except PackError as err:
                errors.append("lifetime of %r: %s" % (p.get("key"), err))
            if life.get("origin", p.get("origin")) not in (None, "user") and not life.get("evidence"):
                errors.append("lifetime of %r: evidence is required" % p.get("key"))
    for e in data.get("edges") or []:
        label = "%s -> %s" % (e.get("child"), e.get("parent"))
        if e.get("child") not in keys or e.get("parent") not in keys:
            errors.append("edge %s uses an unknown place key" % label)
        if e.get("child") == e.get("parent"):
            errors.append("edge %s is a loop" % label)
        try:
            start, stop = parse_iso(e.get("valid_from")), parse_iso(e.get("valid_to"))
            if (start[2], start[1], start[0]) > (stop[2], stop[1] or 12, stop[0] or 31):
                errors.append("edge %s: valid_from is after valid_to" % label)
        except PackError as err:
            errors.append("edge %s: %s" % (label, err))
        if e.get("origin") not in ORIGINS:
            errors.append("edge %s: origin must be one of %s" % (label, "/".join(ORIGINS)))
        elif e["origin"] != "user" and not e.get("evidence"):
            errors.append("edge %s: evidence is required for origin %s" % (label, e["origin"]))
    if errors:
        raise PackError("; ".join(errors))
    return data


def load_pack(path):
    with open(path, encoding="utf-8") as fh:
        return validate(json.load(fh))


def match_place(tree, pack_place):
    if pack_place.get("gramps_id"):
        return [h for h, p in tree.places.items() if p["id"] == pack_place["gramps_id"]]
    wanted = {fold(n) for n in _names(pack_place)}
    found = []
    for handle, place in tree.places.items():
        have = {fold(n.get("value")) for n in tree.all_names(handle)}
        if wanted & have and (pack_place.get("type_value") in (None, place["type"].get("value"))):
            found.append(handle)
    return found


def propose_from_pack(tree, pack, about=None):
    """Return (proposals, notes).

    Candidates come from the pack's links, dated names and place lifetimes. A candidate
    is judged by what it adds TOGETHER with the others (leave one out), because some
    fixes only work as a pair: ending a link to a place that is gone, and adding the
    link to its successor. It is kept only if it fixes more events than it worsens.
    """
    from . import gaps
    places = {p["key"]: p for p in pack["places"]}
    cands, notes = [], []

    def note(text):
        notes.append(text)

    created = {}                      # pack key -> symbolic handle of a place that would be created
    for key, pp in places.items():
        if not pp.get("create"):
            continue
        found = match_place(tree, pp)
        if found:
            if len(found) > 1:
                note("%s: not created, %d places of the tree match it" % (key, len(found)))
            continue
        created[key] = "new:" + key
        names = []
        for n in pp.get("names") or []:
            entry = n if isinstance(n, dict) else {"name": n}
            if entry.get("valid_from"):
                date = (make_span(parse_iso(entry["valid_from"]), parse_iso(entry["valid_to"])) if entry.get("valid_to")
                        else make_from(parse_iso(entry["valid_from"])))
            else:
                date = {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False], "text": "", "sortval": 0}
            names.append({"value": entry["name"], "lang": entry.get("language") or "", "date": date})
        coords = pp.get("coordinates") or {}
        cands.append({"kind": "add-place", "confidence": "evidence", "basis": "evidence", "handle": created[key],
                      "gramps_id": "NEW-" + key, "names": names, "type_value": pp.get("type_value", -1),
                      "lat": str(coords.get("lat", "")), "lon": str(coords.get("lon", "")),
                      "urls": [{"path": "https://www.wikidata.org/wiki/%s" % pp["wikidata_qid"], "type": "Wikidata"}]
                      if pp.get("wikidata_qid") else [],
                      "origin": pp.get("origin") or pack["pack"].get("origin", "user"),
                      "pack": pack["pack"]["id"], "evidence": pp.get("evidence") or [], "label": "new place %s" % key,
                      "group": "new:" + key, "old": {}, "new": {}, "conflict": False, "key": key})

    def end_of(key):
        if key in created:
            return [created[key]]
        return match_place(tree, places[key])

    for e in pack["edges"]:
        mc, mp = end_of(e["child"]), end_of(e["parent"])
        label = "%s -> %s" % (e["child"], e["parent"])
        if len(mc) != 1 or len(mp) != 1:
            note("%s: not applied, %d place(s) match the child and %d the parent" % (label, len(mc), len(mp)))
            continue
        ch, ph = mc[0], mp[0]
        new = make_span(parse_iso(e["valid_from"]), parse_iso(e["valid_to"]))
        refs = tree.places[ch]["refs"] if ch in tree.places else []
        same = [i for i, r in enumerate(refs) if r.get("ref") == ph]
        niv = interval(new, about)
        if same:
            index = same[0]
            old = refs[index].get("date") or {}
            oiv = interval(old, about)
            if oiv == niv:
                note("%s: the tree already has this link" % label)
                continue
            kind = "set-link"
            conflict = (not is_empty(old)) and not (oiv is not None and niv[0] <= oiv[0] and niv[1] >= oiv[1])
        else:
            kind, index, old, conflict = "add-link", len(refs), {}, False
        group = next((created[k] for k in (e["child"], e["parent"]) if k in created), None)
        cands.append({"kind": kind, "confidence": "evidence",
                      "basis": "assumption" if e.get("basis") == "assumption" else "evidence", "child": ch, "parent": ph,
                      "index": index, "old": old, "new": new, "conflict": conflict, "origin": e["origin"],
                      "pack": pack["pack"]["id"], "evidence": e.get("evidence") or [], "label": label,
                      "group": group})
    for key, pack_place in places.items():
        matched = match_place(tree, pack_place)
        for entry in _dated_names(pack_place):
            value, lang = entry["name"], entry.get("language") or ""
            first, last = entry["valid_from"], entry.get("valid_to")
            label = "name %r of %s" % (value, key)
            if len(matched) != 1:
                if len(matched) > 1:
                    note("%s: not applied, %d places match" % (label, len(matched)))
                continue
            handle = matched[0]
            new = make_span(parse_iso(first), parse_iso(last)) if last else make_from(parse_iso(first))
            niv = interval(new, about)
            slot = None
            for i, nm in enumerate(tree.all_names(handle)):
                if fold(nm.get("value")) == fold(value) and (nm.get("lang") or "") == lang:
                    slot = (i, nm)
                    break
            if slot is None:
                prop = {"kind": "add-name", "place": handle, "value": value, "lang": lang, "index": None,
                        "old": {}, "new": new, "conflict": False}
            else:
                oiv = interval(slot[1].get("date"), about)
                if oiv == niv:
                    continue
                prop = {"kind": "set-name-date", "place": handle, "value": value, "lang": lang, "index": slot[0],
                        "old": slot[1].get("date") or {}, "new": new,
                        "conflict": (not is_empty(slot[1].get("date"))) and not (oiv is not None and niv[0] <= oiv[0] and niv[1] >= oiv[1])}
            prop.update(confidence="evidence", basis="assumption" if entry.get("basis") in ("lifetime", "assumption") else "evidence",
                        origin=entry.get("origin") or pack_place.get("origin") or pack["pack"].get("origin", "user"),
                        pack=pack["pack"]["id"], evidence=entry.get("evidence") or pack_place.get("evidence") or [],
                        label=label)
            cands.append(prop)
        life = pack_place.get("lifetime")
        if not life or not life.get("valid_to") or len(matched) != 1:
            continue
        parent = matched[0]
        end = parse_iso(life["valid_to"])
        end_sv = sdn(end[2], end[1] or 12, end[0] or 31)
        for child, place in tree.places.items():
            for index, ref in enumerate(place["refs"]):
                if ref.get("ref") != parent:
                    continue
                old = ref.get("date") or {}
                oiv = interval(old, about)
                if oiv is None or oiv[1] <= end_sv:
                    continue
                if oiv[0] > -INF and not is_empty(old):
                    day, month, year = old["dateval"][0:3]
                    start = (day, month, year)
                elif life.get("valid_from"):
                    start = parse_iso(life["valid_from"])
                else:
                    note("%s: the link of %s would end in %s, but its start is unknown" % (key, tree.label(child), life["valid_to"]))
                    continue
                cands.append({"kind": "end-link", "confidence": "evidence",
                              "basis": "assumption" if life.get("basis") == "assumption" else "evidence", "child": child,
                              "parent": parent, "index": index, "old": old, "new": make_span(start, end),
                              "conflict": False,
                              "origin": life.get("origin") or pack_place.get("origin") or pack["pack"].get("origin", "user"),
                              "pack": pack["pack"]["id"], "evidence": life.get("evidence") or [],
                              "label": "%s ended %s: link of %s" % (key, life["valid_to"], tree.label(child))})
    if not cands:
        return [], notes
    for i, prop in enumerate(cands):
        if not prop.get("group"):
            prop["group"] = "single:%d" % i
    full = gaps.analyse(gaps.apply(tree, cands), about)
    proposals, bundle_no = [], 0
    for group in dict.fromkeys(c["group"] for c in cands):
        members = [c for c in cands if c["group"] == group]
        without = gaps.analyse(gaps.apply(tree, [c for c in cands if c["group"] != group]), about)
        effect = gaps.compare(without, full)
        fixed = effect.get("truncated chains fixed", 0) + effect.get("? names removed (events)", 0)
        worse = effect.get("? names introduced (events)", 0) + effect.get("chains newly truncated", 0)
        label = "; ".join(m.pop("label") for m in members)
        if fixed <= 0:
            note("%s: valid, but it fixes none of the events in this tree" % label)
            continue
        if worse >= fixed:
            if members[0]["kind"] == "end-link" and worse == fixed:
                note("%s: ends the link, but %d event(s) would then have no parent at all instead of a '?' "
                     "(a new parent for that period is needed first)" % (label, worse))
            else:
                note("%s: not proposed, it would make %d event(s) worse and fix %d" % (label, worse, fixed))
            continue
        bundle = None
        if len(members) > 1:
            bundle_no += 1
            bundle = "b%d-%s" % (bundle_no, pack["pack"]["id"])
        for m in members:
            m["events"] = 0 if m["kind"] == "add-place" else fixed
            m["worse"], m["effect"], m["bundle"], m["_order"] = worse, dict(effect), bundle, (-fixed, group)
            proposals.append(m)
    proposals.sort(key=lambda p: (p["_order"], p["kind"] != "add-place"))
    for p in proposals:
        p.pop("_order")
    return proposals, notes
