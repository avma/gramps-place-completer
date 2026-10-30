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
"""Find where place chains break, propose safe fixes, and simulate them.

Two kinds of defects exist for an event at a place:
  - LINK gap: the chain stops although the last place still has parent links,
    because no link covers the event date ("truncated").
  - NAME gap: a place in the chain shows as "?" because no name covers the date.
Some name gaps come from a link that continues after its parent place stopped
existing. That is only safe to conclude for TOP-LEVEL parents (no parents of their
own: an empire, a monarchy), whose existence is defined by their own names. For
any other place (a county, a district, a village) the dated names are usually
just incomplete, and the right fix is an extra or longer name from an outside
source, never removing the link (propose_end_clips does not touch those).
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import collections

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .chain import chain
from .dates import (INF, M_NONE, M_RANGE, M_SPAN, interval, is_empty, make_span,
                    merge, parts, year_of, ymd)


def analyse(tree, about=None):
    rows = []
    for ev in tree.events:
        if ev["place"] not in tree.places:
            continue
        date = ev["date"] or {}
        if not date:
            date = {"modifier": 0, "sortval": 0, "dateval": [0, 0, 0, False]}
        sortval = date.get("sortval") or 0
        undated = is_empty(date) or sortval == 0
        result = chain(tree.places, ev["place"], date, about)
        unnamed = [h for h, n in zip(result["handles"], result["names"]) if n == "?"]
        rows.append({"event": ev, "undated": undated, "sortval": sortval,
                     "year": None if undated else year_of(sortval),
                     "chain": result, "unnamed": unnamed})
    return rows


def summarize(rows):
    c = collections.Counter()
    for r in rows:
        c["events"] += 1
        c["undated" if r["undated"] else "dated"] += 1
        end = r["chain"]["end"]
        if end in ("top", "after-links"):
            c["complete"] += 1
        if end == "truncated":
            c["truncated, undated" if r["undated"] else "truncated, dated"] += 1
        if r["unnamed"]:
            c["with a ? name"] += 1
        if end in ("cycle", "missing-parent"):
            c["cycle or missing parent"] += 1
    return c


def _years(items):
    years = [r["year"] for r in items if r["year"]]
    return (min(years), max(years)) if years else None


def link_gaps(rows):
    """Dated truncated chains, grouped by the place whose links do not cover the date."""
    groups = collections.defaultdict(list)
    for r in rows:
        if r["chain"]["end"] == "truncated" and not r["undated"]:
            groups[r["chain"]["last"]].append(r)
    return sorted(({"place": h, "events": len(v), "years": _years(v), "ids": [x["event"]["id"] for x in v[:5]]}
                   for h, v in groups.items()), key=lambda g: -g["events"])


def coverage(tree, handle, about=None):
    return merge(interval(n.get("date"), about) for n in tree.all_names(handle))


def name_gap_cause(tree, handle, sortval, undated, about=None):
    cov = coverage(tree, handle, about)
    if undated:
        return "undated event"
    if not cov:
        return "no usable name"
    if sortval > cov[-1][1]:
        return "place ended"
    if sortval < cov[0][0]:
        return "place not yet named"
    return "hole between names"


def name_gaps(tree, rows, about=None):
    groups = collections.defaultdict(list)
    for r in rows:
        for h in set(r["unnamed"]):
            groups[(h, name_gap_cause(tree, h, r["sortval"], r["undated"], about))].append(r)
    return sorted(({"place": h, "cause": cause, "events": len(v), "years": _years(v),
                    "top_level": not tree.places[h]["refs"],
                    "likely_fix": likely_fix(cause, not tree.places[h]["refs"])}
                   for (h, cause), v in groups.items()), key=lambda g: -g["events"])


def likely_fix(cause, top_level):
    if cause == "place ended":
        return "end the link (proposed)" if top_level else "extend the name (outside source)"
    return {"place not yet named": "add an earlier name (outside source)",
            "hole between names": "add a name for the hole (outside source)",
            "undated event": "date the event, or add a 'to' link",
            "no usable name": "add a name (outside source)"}.get(cause, "")


def _end_tuple(tree, handle, hi, about=None):
    """The stop of the last interval of a place's names, as (day, month, year)."""
    for name in tree.all_names(handle):
        nd = name.get("date")
        iv = interval(nd, about)
        if iv and iv[1] == hi and nd.get("quality") != 1:
            if nd.get("modifier") in (M_RANGE, M_SPAN):
                s, e = parts(nd)
                day, month, year = e if e != (0, 0, 0) else s
                return (day, month, year)
            if nd.get("modifier") == M_NONE:
                return tuple(parts(nd)[0])
    year, month, day = ymd(hi)
    return (day, month, year)


def _start_tuple(tree, handle, lo, about=None):
    """The start of the first interval of a place's names, as (day, month, year)."""
    for name in tree.all_names(handle):
        nd = name.get("date")
        iv = interval(nd, about)
        if iv and iv[0] == lo and nd.get("quality") != 1 and nd.get("modifier") in (M_NONE, M_RANGE, M_SPAN):
            return tuple(parts(nd)[0])
    year, month, day = ymd(lo)
    return (day, month, year)


def propose_end_clips(tree, rows, about=None):
    """Links that continue after a TOP-LEVEL parent stopped existing (by its own names).

    Evidence is the tree itself: the parent has no parents, and every name of it ends
    before the link does, so events after that end show "?" for the parent. The fix
    shortens the link to the parent's last day. Nothing is proposed for a parent
    that has parents of its own (its names are probably just incomplete), when a
    link start cannot be determined, or when the parent's names have holes.
    """
    found = collections.defaultdict(list)
    for r in rows:
        c = r["chain"]
        for position, handle in enumerate(c["handles"]):
            if position == 0 or handle not in r["unnamed"]:
                continue
            if name_gap_cause(tree, handle, r["sortval"], r["undated"], about) == "place ended":
                found[c["via"][position - 1]].append(r)
    proposals = []
    for (child, index), items in found.items():
        ref = tree.places[child]["refs"][index]
        parent = ref.get("ref")
        if tree.places[parent]["refs"]:
            continue
        cov = coverage(tree, parent, about)
        if not cov or cov[-1][1] >= INF:
            continue
        lo_n, hi_n = cov[-1]
        old = ref.get("date") or {}
        liv = interval(old, about)
        if liv is None or liv[1] <= hi_n:
            continue
        if liv[0] > -INF and not is_empty(old):
            day, month, year = parts(old)[0]
            start = (day, month, year)
        elif lo_n > -INF:
            start = _start_tuple(tree, parent, lo_n, about)
        else:
            continue
        end = _end_tuple(tree, parent, hi_n, about)
        new = make_span(start, end)
        if new["sortval"] > hi_n:
            continue
        proposals.append({
            "kind": "end-link", "confidence": "high", "basis": "tree", "child": child, "index": index, "parent": parent,
            "old": old, "new": new, "events": len(items), "years": _years(items),
            "evidence": "all names of %s end by %d-%02d-%02d, but the link from %s goes on" % (
                tree.label(parent), *ymd(hi_n), tree.label(child))})
    return sorted(proposals, key=lambda p: -p["events"])


def apply(tree, proposals):
    """A copy of the tree with the proposals applied (the tree itself is not changed)."""
    out = tree.clone()
    ordered = [p for p in proposals if p["kind"] == "add-place"] + [p for p in proposals if p["kind"] != "add-place"]
    ordered.sort(key=lambda p: (0 if p["kind"] not in ("add-link", "remove-link", "move-link") else 1 if p["kind"] == "remove-link" else 2,
                                -(p.get("index") or 0) if p["kind"] == "remove-link" else 0))       # edits, then removals from the end, then insertions
    removed = {}
    for p in ordered:
        if p["kind"] == "add-place":
            names = p["names"]
            out.places[p["handle"]] = {
                "handle": p["handle"], "id": p.get("gramps_id", "NEW"), "type": {"value": p["type_value"], "string": p.get("type_string", "")},
                "name": names[0], "alt_names": names[1:], "refs": [], "urls": p.get("urls", []),
                "lat": p.get("lat", ""), "lon": p.get("lon", "")}
            continue
        if p["kind"] == "add-url":
            out.places[p["place"]]["urls"] = list(out.places[p["place"]].get("urls") or []) + [p["path"]]
            continue
        if p["kind"] == "set-coordinates":
            out.places[p["place"]]["lat"], out.places[p["place"]]["lon"] = p["lat"], p["lon"]
            continue
        if p["kind"] == "set-name-language":
            place = out.places[p["place"]]
            (place["name"] if p["index"] == 0 else place["alt_names"][p["index"] - 1])["lang"] = p["lang"]
            continue
        if p["kind"] in ("set-type", "change-type"):
            out.places[p["place"]]["type"] = {"value": p["type_value"], "string": p.get("type_string", "")}
            continue
        if p["kind"] == "rename-place":
            place = out.places[p["place"]]
            if p.get("keep_old") and not any(n.get("value") == p["value"] for n in place["alt_names"]):
                place["alt_names"].append({"_class": "PlaceName", "value": p["value"], "lang": p.get("lang", ""), "date": place["name"].get("date") or {}})
            place["name"]["value"] = p["new_value"]
            continue
        if p["kind"] in ("add-name", "set-name-date"):
            place = out.places[p["place"]]
            if p["kind"] == "add-name":
                place["alt_names"].append({"_class": "PlaceName", "value": p["value"],
                                           "lang": p["lang"], "date": p["new"]})
            elif p["index"] == 0:
                place["name"]["date"] = p["new"]
            else:
                place["alt_names"][p["index"] - 1]["date"] = p["new"]
            continue
        refs = out.places[p["child"]]["refs"]
        if p["kind"] in ("end-link", "set-link"):
            refs[p["index"]]["date"] = p["new"]
        elif p["kind"] == "remove-link":
            refs.pop(p["index"])
            removed.setdefault(p["child"], []).append(p["index"])
        elif p["kind"] == "move-link":
            refs.insert(min(p["position"], len(refs) - 1), refs.pop(p["index"]))
        elif p["kind"] == "add-link":
            ref = {"_class": "PlaceRef", "ref": p["parent"], "date": p["new"]}
            if p.get("position") is None:
                refs.append(ref)
            else:
                where = p["position"] - sum(1 for i in removed.get(p["child"], []) if i < p["position"])
                refs.insert(min(where, len(refs)), ref)                       # before the direct link, which Gramps would otherwise find first
    return out


def compare(before_rows, after_rows):
    old = {r["event"]["handle"]: r for r in before_rows}
    out = collections.Counter()
    for r in after_rows:
        o = old[r["event"]["handle"]]
        oc, nc = o["chain"], r["chain"]
        if oc["names"] != nc["names"] or oc["end"] != nc["end"]:
            out["events whose displayed place changes"] += 1
        if o["unnamed"] and not r["unnamed"]:
            out["? names removed (events)"] += 1
        if not o["unnamed"] and r["unnamed"]:
            out["? names introduced (events)"] += 1
        if oc["end"] == "truncated" and nc["end"] != "truncated" and not r["undated"]:
            out["truncated chains fixed"] += 1
        if oc["end"] != "truncated" and nc["end"] == "truncated" and not r["undated"]:
            out["chains newly truncated"] += 1
        if len(nc["names"]) < len(oc["names"]):
            out["chains that get shorter"] += 1
    return out
