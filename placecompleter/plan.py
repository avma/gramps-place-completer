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
"""A plan: the proposals of one analysis, in a file, so that they can be reviewed and applied later.

The plan is plain JSON. Every proposal gets a stable number, the data needed to
write it (handles, the old and the new date) and the texts a person needs to judge
it (labels, evidence, effect). Applying never recomputes anything: it checks that the
tree still looks the way it did and writes what was selected.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import json
import time

PLAN_SCHEMA = "placecompleter.plan.v1"
FILL_KINDS = ("set-coordinates", "set-name-language", "set-type")      # fields that are empty and the answer can fill
EDIT_KINDS = FILL_KINDS + ("rename-place", "change-type")                             # proposals about a place that exists, each standing alone


def make_plan(tree, proposals, source_note=""):
    items = []
    for i, p in enumerate(proposals, 1):
        item = {k: p[k] for k in ("kind", "basis", "old", "new", "events", "evidence", "origin", "bundle") if k in p}
        item.update(id=i, worse=p.get("worse", 0), conflict=bool(p.get("conflict")), refines=bool(p.get("refines")), inferred=bool(p.get("inferred")),
                    existing=bool(p.get("existing")), key=p.get("key", ""), requires_key=p.get("requires_key", ""))
        if p["kind"] == "add-place":
            item.update(handle=p["handle"], names=p["names"], type_value=p["type_value"], type_string=p.get("type_string", ""),
                        note=p.get("note", ""), source_note=p.get("source_note", ""), lat=p.get("lat", ""),
                        lon=p.get("lon", ""), urls=p.get("urls", []), gramps_id=p.get("gramps_id", ""),
                        label="NEW PLACE %s" % p["names"][0]["value"])
        elif p["kind"] == "add-url":
            item.update(place=p["place"], path=p["path"], url_kind=p.get("url_kind", ""), optional=bool(p.get("optional")), note=p.get("note", ""),
                        label=tree.label(p["place"]))
        elif p["kind"] in ("add-name", "set-name-date"):
            item.update(place=p["place"], value=p["value"], lang=p["lang"], index=p["index"],
                        label=tree.label(p["place"]))
        elif p["kind"] in EDIT_KINDS:                    # an empty field of a place that exists, or its name
            item.update(place=p["place"], index=p.get("index"), value=p.get("value", ""), lang=p.get("lang", ""), lat=p.get("lat", ""),
                        lon=p.get("lon", ""), type_value=p.get("type_value"), type_string=p.get("type_string", ""),
                        new_value=p.get("new_value", ""), keep_old=bool(p.get("keep_old")), source_note=p.get("source_note", ""),
                        old_type_value=p.get("old_type_value"), old_type_string=p.get("old_type_string", ""),
                        label=tree.label(p["place"]))
        else:
            def name(h):
                return tree.label(h) if h in tree.places else h
            item.update(child=p["child"], parent=p["parent"], index=p["index"], position=p.get("position"), above=p.get("above"),
                        label="%s -> %s" % (name(p["child"]), name(p["parent"])))
        items.append(item)
    return {"schema": PLAN_SCHEMA, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source_note,
            "proposals": items}


def save_plan(plan, path):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1)


def load_plan(path):
    with open(path, encoding="utf-8") as fh:
        plan = json.load(fh)
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("not a PlaceCompleter plan: %s" % path)
    return plan


def _target(p):
    """(what is decided, the value proposed) for a proposal that decides one field of one place, else None."""
    kind = p["kind"]
    new = lambda: json.dumps(p.get("new"), sort_keys=True, default=str)
    if kind == "set-coordinates":
        return ("coordinates", p["place"]), (p.get("lat"), p.get("lon"))
    if kind in ("set-type", "change-type"):
        return ("type", p["place"]), (p.get("type_value"), p.get("type_string") or "")
    if kind == "rename-place":
        return ("name", p["place"]), (p.get("new_value"),)
    if kind == "set-name-language":
        return ("language of a name", p["place"], p.get("index")), (p.get("lang"),)
    if kind == "set-name-date":
        return ("period of a name", p["place"], p.get("index"), p.get("value"), p.get("lang")), (new(),)
    if kind in ("set-link", "end-link"):
        return ("period of a link", p["child"], p["parent"], p.get("index")), (new(),)
    return None


def rivals(proposals):
    """{id: the ids of the proposals that cannot be chosen together with it}: two proposals that decide the same field of the same place
    in different ways are alternatives (the same decision twice is not). Only proposals that have a rival are in the result."""
    decided = {}
    for p in proposals:
        target = _target(p)
        if target:
            decided.setdefault(target[0], []).append((p["id"], target[1]))
    out = {}
    for items in decided.values():
        for pid, value in items:
            against = {other for other, v in items if v != value}
            if against:
                out[pid] = against
    return out


def select(plan, ids=None, bases=None):
    """Proposals picked by number and/or by basis (tree, evidence, assumption)."""
    picked = []
    in_conflict = {p["bundle"] for p in plan["proposals"] if p.get("bundle") and p.get("conflict")}
    for p in plan["proposals"]:
        if ids is not None and p["id"] in ids:
            picked.append(p)
        elif (bases is not None and p["basis"] in bases and not p.get("conflict") and not p.get("optional")
              and p.get("bundle") not in in_conflict):       # a bundle with a conflict is never picked by basis
            picked.append(p)
    # a bundle (a new place and its links) is applied whole or not at all
    bundles = {p["bundle"] for p in picked if p.get("bundle")}
    chosen = [p for p in plan["proposals"] if p in picked or (p.get("bundle") in bundles)]
    return chosen
