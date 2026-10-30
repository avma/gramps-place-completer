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
"""The agent loop: build a request for the gaps, validate the answer, make a pack.

The engine never trusts the agent. A response is accepted item by item only if it
has the right shape, valid dates, and evidence (an https URL and a short quote)
for every statement. Accepted items become a regional pack (origin "agent"),
which goes through the same matching and simulation as every other pack.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import hashlib
import json
import re
import time

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import gaps, packs
from .wikidata import is_address
from .dates import describe, is_empty

REQUEST_SCHEMA = "placecompleter.request.v1"
RESPONSE_SCHEMA = "placecompleter.response.v1"
SOURCE_KINDS = ("primary", "scholarly", "gazetteer", "encyclopedia", "wikidata", "other")
LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
MAX_NAMES, MAX_LINKS, MAX_QUOTE_WORDS = 6, 4, 25


def _date_text(d):
    return describe(d) if d and not is_empty(d) else ""


def _place_summary(tree, handle):
    p = tree.places[handle]
    return {"gramps_id": p["id"], "type": p["type"].get("string") or p["type"].get("value"),
            "names": [{"name": n.get("value"), "language": n.get("lang") or "", "period": _date_text(n.get("date"))}
                      for n in tree.all_names(handle)],
            "parents": [{"name": tree.name_of(r.get("ref")), "gramps_id": tree.places[r["ref"]]["id"],
                         "period": _date_text(r.get("date"))} for r in p["refs"] if r.get("ref") in tree.places],
            "coordinates": {"lat": p["lat"], "lon": p["lon"]} if p["lat"] or p["lon"] else None,
            "urls": p["urls"][:6]}


ADMIN_TYPES = (1, 2, 3, 8, 9, 12, 14)      # Country, State, County, Province, Region, District, Municipality


def candidate_parents(tree, limit=120):
    """Places of the tree a link may point at: parents of something, administrative levels, custom types."""
    children = {}
    for p in tree.places.values():
        for r in p["refs"]:
            if r.get("ref") in tree.places:
                children[r["ref"]] = children.get(r["ref"], 0) + 1
    out = []
    for handle, place in tree.places.items():
        ptype = place["type"]
        custom = ptype.get("value") == 0 and bool(ptype.get("string"))
        if handle in children or ptype.get("value") in ADMIN_TYPES or custom:
            out.append({"gramps_id": place["id"], "name": tree.name_of(handle),
                        "type": ptype.get("string") or ptype.get("value"), "children": children.get(handle, 0),
                        "names": [{"name": n.get("value"), "language": n.get("lang") or "", "period": _date_text(n.get("date"))}
                                  for n in tree.all_names(handle)]})
    out.sort(key=lambda c: (-c["children"], c["name"] or ""))
    return out[:limit]


def build_request(tree, rows, attempt=1, max_tasks=12, previous_unresolved=(), skip_addresses=True):
    """One task per place that still has a gap in the given analysis rows."""
    tasks = {}
    for g in gaps.name_gaps(tree, rows):
        if g["cause"] == "undated event":
            continue
        t = tasks.setdefault(g["place"], {"place": g["place"], "gaps": [], "events": 0})
        t["gaps"].append({"kind": "name", "cause": g["cause"], "years": list(g["years"]) if g["years"] else None,
                          "events": g["events"]})
        if g["cause"] == "place ended":
            t["gaps"][-1]["question"] = ("do the names end because the place itself ceased to exist (then answer "
                                         "with `lifetime`), or did it go on under another name (then answer with `names`)?")
        t["events"] += g["events"]
    for g in gaps.link_gaps(rows):
        t = tasks.setdefault(g["place"], {"place": g["place"], "gaps": [], "events": 0})
        t["gaps"].append({"kind": "link", "years": list(g["years"]) if g["years"] else None, "events": g["events"]})
        t["events"] += g["events"]
    # the children of a place that ended need to know which place they belonged to afterwards
    successors = {}
    for r in rows:
        c = r["chain"]
        for position, handle in enumerate(c["handles"]):
            if (position and handle in r["unnamed"] and not r["undated"]
                    and gaps.name_gap_cause(tree, handle, r["sortval"], False) == "place ended"):
                successors.setdefault(c["via"][position - 1], []).append(r)
    for (child, _index), items in successors.items():
        parent_name = tree.name_of(tree.places[child]["refs"][_index]["ref"])
        years = sorted(r["year"] for r in items if r["year"])
        t = tasks.setdefault(child, {"place": child, "gaps": [], "events": 0})
        t["gaps"].append({"kind": "link", "cause": "parent ended", "parent": parent_name,
                          "_parent_handle": tree.places[child]["refs"][_index]["ref"],
                          "years": [years[0], years[-1]] if years else None, "events": len(items),
                          "question": "the link to %r ends with that place; which place (already in the tree) "
                                      "did this place belong to afterwards?" % parent_name})
        t["events"] += len(items)
    skipped = 0
    if skip_addresses:
        for handle in [h for h in tasks if is_address(tree, h)]:
            del tasks[handle]
            skipped += 1
    ordered = sorted(tasks.values(), key=lambda t: -t["events"])[:max_tasks]
    # a place that ended is useless without the place that took over: keep the pair together
    chosen = {t["place"] for t in ordered}
    for t in sorted(tasks.values(), key=lambda t: -t["events"]):
        if t["place"] not in chosen and any(g.get("_parent_handle") in chosen for g in t["gaps"]) and len(ordered) < max_tasks + 6:
            ordered.append(t)
            chosen.add(t["place"])
    out = []
    for i, t in enumerate(ordered, 1):
        sample = next((r["chain"]["names"] for r in rows
                       if t["place"] in r["chain"]["handles"] and not r["undated"]), [])
        info = _place_summary(tree, t["place"])
        for g in t["gaps"]:
            g.pop("_parent_handle", None)
        info.update(task_id="t%d" % i, gaps=t["gaps"], chain_now=sample)
        out.append(info)
    body = {"schema": REQUEST_SCHEMA, "attempt": attempt, "created": time.strftime("%Y-%m-%d"),
            "tasks": out, "skipped_addresses": skipped, "tree_places": candidate_parents(tree), "previous_unresolved": list(previous_unresolved),
            "date_format": "YYYY, YYYY-MM or YYYY-MM-DD"}
    body["request_id"] = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]
    return body


def _check_evidence(items):
    reasons = []
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        return ["evidence must be a list of 1 to 5 items"]
    for e in items:
        url, quote = (e or {}).get("url", ""), (e or {}).get("quote", "")
        if not re.match(r"^https?://[^\s]+\.[^\s]+$", url or ""):
            reasons.append("evidence url is not a web address: %r" % (url,))
        words = len((quote or "").split())
        if not quote or words > MAX_QUOTE_WORDS:
            reasons.append("evidence quote must be 1 to %d words (it has %d)" % (MAX_QUOTE_WORDS, words))
        if (e or {}).get("source_kind") not in SOURCE_KINDS:
            reasons.append("source_kind must be one of %s" % "/".join(SOURCE_KINDS))
    return reasons


def _years_in(text):
    return set(re.findall(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)", text or ""))


def unsupported_years(item):
    """Years the item claims (valid_from, valid_to) that no evidence quote contains."""
    claimed = {str(item[k])[:4] for k in ("valid_from", "valid_to") if item.get(k) and str(item[k])[:4].isdigit()}
    claimed.discard("2100")                                     # the stand-in for "until today"
    seen = set()
    for e in item.get("evidence") or []:
        seen |= _years_in((e or {}).get("quote", ""))
    return sorted(claimed - seen)


def _check_period(item):
    try:
        start = packs.parse_iso(item.get("valid_from"))
        stop = packs.parse_iso(item["valid_to"]) if item.get("valid_to") else None
    except packs.PackError as err:
        return [str(err)]
    if stop and (start[2], start[1], start[0]) > (stop[2], stop[1] or 12, stop[0] or 31):
        return ["valid_from is after valid_to"]
    return []


def validate_response(response, request, tree):
    """Return {"pack": pack dict or None, "accepted": [...], "rejected": [...], "notes": [...]}."""
    rejected, accepted, notes = [], [], []
    if response.get("schema") != RESPONSE_SCHEMA:
        return {"pack": None, "accepted": [], "notes": [],
                "rejected": [{"where": "response", "reasons": ["schema must be %s" % RESPONSE_SCHEMA]}]}
    if response.get("request_id") != request.get("request_id"):
        notes.append("request_id differs from the request (the answer may be for another request)")
    tasks = {t["task_id"]: t for t in request["tasks"]}
    pack_places, pack_edges = [], []
    for res in response.get("results") or []:
        task = tasks.get(res.get("task_id"))
        if task is None:
            rejected.append({"where": str(res.get("task_id")), "reasons": ["unknown task_id"]})
            continue
        base = {"key": task["task_id"], "gramps_id": task["gramps_id"],
                "names": [n["name"] for n in task["names"] if n["name"]], "origin": "agent"}
        known, new_names = set(), []
        for item in (res.get("names") or [])[:MAX_NAMES + 20]:
            label = "%s %r" % (task["task_id"], item.get("name"))
            reasons = []
            if len(new_names) >= MAX_NAMES:
                reasons.append("more than %d names for one place" % MAX_NAMES)
            if not item.get("name") or len(item["name"]) > 120:
                reasons.append("name is empty or too long")
            if item.get("language", "") != "" and not LANG.match(item.get("language") or ""):
                reasons.append("language must be a code such as hu or ro")
            reasons += _check_period(item) + _check_evidence(item.get("evidence"))
            key = (item.get("name"), item.get("language"), item.get("valid_from"), item.get("valid_to"))
            if key in known:
                reasons.append("duplicate")
            if reasons:
                rejected.append({"where": label, "reasons": reasons})
                continue
            known.add(key)
            gap = unsupported_years(item)
            new_names.append({"name": item["name"], "language": item.get("language") or "",
                              "valid_from": item["valid_from"], "valid_to": item.get("valid_to"),
                              "origin": "agent", "evidence": item["evidence"],
                              "basis": "assumption" if gap else "evidence"})
            accepted.append(label + (" [year %s is in no quote: kept as an assumption]" % ", ".join(gap) if gap else ""))
        life = res.get("lifetime")
        if life:
            label = "%s lifetime" % task["task_id"]
            reasons = _check_period(life)
            if life.get("valid_to") is None and not life.get("continues"):
                reasons.append("valid_to is required (or set continues: true)")
            reasons += _check_evidence(life.get("evidence"))
            if reasons:
                rejected.append({"where": label, "reasons": reasons})
            elif life.get("valid_to"):
                gap = unsupported_years(life)
                base["lifetime"] = {"valid_from": life["valid_from"], "valid_to": life["valid_to"], "origin": "agent",
                                    "evidence": life["evidence"], "basis": "assumption" if gap else "evidence"}
                accepted.append(label + (" [year %s is in no quote: kept as an assumption]" % ", ".join(gap) if gap else ""))
            else:
                notes.append("%s: the place continues to exist (no link is ended)" % task["task_id"])
        if new_names or base.get("lifetime"):
            pack_places.append(dict(base, names=base["names"] + new_names))
        links = 0
        for item in res.get("links") or []:
            label = "%s link to %r" % (task["task_id"], item.get("parent_name"))
            reasons = _check_period(item) + _check_evidence(item.get("evidence"))
            links += 1
            if links > MAX_LINKS:
                reasons.append("more than %d links for one place" % MAX_LINKS)
            parent = [h for h, p in tree.places.items() if any(
                packs.fold(n.get("value")) == packs.fold(item.get("parent_name")) for n in tree.all_names(h))]
            if len(parent) != 1:
                reasons.append("the parent must match exactly one place of the tree (%d match; creating places "
                               "is not supported yet)" % len(parent))
            if reasons:
                rejected.append({"where": label, "reasons": reasons})
                continue
            pk = "p-" + tree.places[parent[0]]["id"]
            if not any(p["key"] == pk for p in pack_places):
                pack_places.append({"key": pk, "gramps_id": tree.places[parent[0]]["id"],
                                    "names": [tree.name_of(parent[0])], "origin": "agent"})
            if not any(p["key"] == task["task_id"] for p in pack_places):
                pack_places.append(dict(base))
            gap = unsupported_years(item)
            pack_edges.append({"child": task["task_id"], "parent": pk, "valid_from": item["valid_from"],
                               "valid_to": item.get("valid_to") or "2100", "origin": "agent",
                               "evidence": item["evidence"], "basis": "assumption" if gap else "evidence"})
            accepted.append(label + (" [year %s is in no quote: kept as an assumption]" % ", ".join(gap) if gap else ""))
        for u in res.get("unresolved") or []:
            notes.append("%s unresolved: %s" % (task["task_id"], u))
    pack = None
    if pack_places:
        pack = {"schema": packs.SCHEMA, "pack": {"id": "agent-%s" % request.get("request_id"), "version": 1,
                                                 "origin": "agent", "created": time.strftime("%Y-%m-%d")},
                "places": pack_places, "edges": pack_edges}
        packs.validate(pack)
    return {"pack": pack, "accepted": accepted, "rejected": rejected, "notes": notes}
