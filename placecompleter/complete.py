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
"""Complete one place for one date: identity, coordinates, names, type and the dated hierarchy.

Input: a place name and the date of an event (and optionally a region hint). The result is
a "control screen" (rows with a source and a basis, a duplicate check, the chain Gramps
would display) and a list of proposals in the same form the rest of the engine uses, so
that they can be simulated, reviewed and written in one transaction.

Wikidata gives identity, coordinates and, where it has dated statements, the hierarchy.
What it lacks for the date is reported under "needs" with a ready question for an agent.
Names follow the language of the state the place belonged to on that date.
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
from . import gaps, packs
from .dates import INF, make_from, make_span, sdn, ymd
from .wikidata import (PLACE_TYPE_NAMES, claims, coordinates, entity_id, km, labels, lifetime, official_names,
                       place_like, tree_coordinates, type_from_classes)

# The language of a place's name follows the state it belonged to on the date (user's rule).
# None means "undecided": the screen asks instead of guessing.
STATE_LANG = {
    "Q171150": "hu", "Q696970": "hu", "Q28": "hu",                                  # Hungary
    "Q218": "ro", "Q203493": "ro",                                                   # Romania
    "Q403": "sr", "Q191077": "sr", "Q1277557": "sr", "Q83286": "sr", "Q838261": "sr",
    "Q37024": "sr", "Q934644": "sr",                                                 # Serbia, Yugoslavia
    "Q212": "uk", "Q214": "sk", "Q33946": "cs", "Q40": "de", "Q183": "de",
    "Q36": "pl", "Q224": "hr", "Q215": "sl", "Q801": "he",
    "Q131964": None, "Q28513": None,                                                 # Austrian Empire, Austria-Hungary
}
SEARCH_LANGUAGES = ("en", "hu", "de", "ro", "sr")


def parse_date(text):
    """'1850', '1850-05' or '1850-05-14' -> (dict like Gramps' date, first-day sort value)."""
    m = re.match(r"^(\d{1,4})(?:-(\d{2})(?:-(\d{2}))?)?$", str(text).strip())
    if not m:
        raise ValueError("date must be YYYY, YYYY-MM or YYYY-MM-DD: %r" % (text,))
    year, month, day = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
    sv = sdn(year, month or 1, day or 1)
    return ({"modifier": 0, "quality": 0, "calendar": 0, "dateval": [day, month, year, False], "text": "",
             "sortval": sv}, sv)


def _bound(iso, end):
    if not iso:
        return INF if end else -INF
    parts = [int(x) for x in iso.split("-")]
    year, month, day = parts[0], parts[1] if len(parts) > 1 else (12 if end else 1), parts[2] if len(parts) > 2 else (31 if end else 1)
    return sdn(year, month, day)


def valid_at(claim, sv):
    return _bound(claim["start"], False) <= sv <= _bound(claim["end"], True)


def _iso(sv):
    if sv in (INF, -INF):
        return None
    y, m, d = ymd(sv)
    return "%d-%02d-%02d" % (y, m, d)


def candidates(client, name, region=None, languages=None):
    """Place-like Wikidata entities for a name, best first. `languages`: those to search in (default SEARCH_LANGUAGES)."""
    qids = []
    for language in (languages or SEARCH_LANGUAGES):
        for hit in client.search(name, language):
            if hit.get("id") not in qids:
                qids.append(hit["id"])
    ents = client.entities(qids)
    wanted = packs.fold(name)
    out = []
    for qid in qids:
        e = ents.get(qid)
        if not e or not place_like(e):
            continue
        known = {packs.fold(v) for v in labels(e).values()} | {packs.fold(o["name"]) for o in official_names(e)}
        score = 3 if wanted in known else 0
        if not score:
            continue
        countries = [entity_id(c["value"]) for c in claims(e, "P17")]
        parents = [entity_id(c["value"]) for c in claims(e, "P131")]
        around = client.entities([x for x in countries + parents if x])
        around_text = " ".join(packs.fold(v) for x in countries + parents for v in labels(around.get(x, {})).values())
        if region and packs.fold(region) in around_text:
            score += 3
        if coordinates(e):
            score += 1
        classes = client.entities([entity_id(c["value"]) for c in claims(e, "P31") if entity_id(c["value"])])
        out.append({"qid": qid, "score": score, "label": labels(e).get("en") or next(iter(labels(e).values()), qid),
                    "country": next((labels(around[x]).get("en") for x in countries if x in around), None),
                    "coordinates": coordinates(e),
                    "classes": [labels(c).get("en") for c in classes.values() if labels(c).get("en")]})
    return sorted(out, key=lambda c: -c["score"])


def historical_chain(client, qid, sv, stop_at=lambda q: False, max_depth=6):
    """Parents of an entity on a date: dated P131 first, then dated P17, then an undated P131 (an assumption)."""
    steps, current, seen = [], qid, {qid}
    for _ in range(max_depth):
        entity = client.entities([current]).get(current)
        if not entity:
            break
        dated = [c for c in claims(entity, "P131") if (c["start"] or c["end"]) and valid_at(c, sv)]
        via = "P131"
        if not dated:
            dated = [c for c in claims(entity, "P17") if (c["start"] or c["end"]) and valid_at(c, sv)]
            via = "P17"
        basis = "evidence"
        if not dated:
            born, died = lifetime(entity)
            undated = [c for c in claims(entity, "P131") if not (c["start"] or c["end"])]
            if undated and _bound(born, False) <= sv <= _bound(died, True):
                dated, via, basis = undated, "P131", "assumption"
        if not dated:
            break
        best = sorted(dated, key=lambda c: (c["rank"] != "preferred", -(_bound(c["start"], False) if c["start"] else -INF)))[0]
        target = entity_id(best["value"])
        if not target or target in seen:
            break
        seen.add(target)
        client.entities([target])
        steps.append({"child": current, "parent": target, "via": via, "start": best["start"], "end": best["end"],
                      "basis": basis, "rank": best["rank"], "stop": stop_at(target)})
        if steps[-1]["stop"]:
            break
        current = target
    return steps


def match_tree(tree, client, qid):
    """Tree places that carry the entity's Wikidata link or one of its names (and are not far away)."""
    entity = client.entities([qid]).get(qid) or {}
    url = "https://www.wikidata.org/wiki/%s" % qid
    known = {packs.fold(v) for v in labels(entity).values()} | {packs.fold(o["name"]) for o in official_names(entity)}
    there, found = coordinates(entity), []
    for handle, place in tree.places.items():
        if url in place.get("urls", []):
            found.append(handle)
            continue
        names = {packs.fold(n.get("value")) for n in tree.all_names(handle)}
        if names & known:
            here = tree_coordinates(place)
            if here and there and km(here, there) > 150:
                continue
            found.append(handle)
    return found


def similar_places(tree, client, qid, name):
    """Places already in the tree that could be the same place (name, coordinates, Wikidata link)."""
    entity = client.entities([qid]).get(qid) or {}
    known = {packs.fold(name)} | {packs.fold(v) for v in labels(entity).values()}
    there, out = coordinates(entity), []
    for handle, place in tree.places.items():
        reasons = []
        if "https://www.wikidata.org/wiki/%s" % qid in place.get("urls", []):
            reasons.append("same Wikidata link")
        if {packs.fold(n.get("value")) for n in tree.all_names(handle)} & known:
            reasons.append("same name")
        here = tree_coordinates(place)
        if here and there and km(here, there) <= 10:
            reasons.append("%.0f km away" % km(here, there))
        if reasons:
            out.append({"handle": handle, "label": tree.label(handle), "reasons": reasons})
    return out


def _name_in(entity, language):
    return labels(entity).get(language)


def complete_place(tree, name, date_text, client, region=None, pick=None, language=None, about=None):
    """Return the control screen for one place on one date."""
    date, sv = parse_date(date_text)
    result = {"name": name, "date": date_text, "rows": [], "needs": [], "similar": [], "proposals": [],
              "chain": [], "preview": [], "candidates": [], "selected": None, "mode": "new"}
    cands = candidates(client, name, region)
    result["candidates"] = cands
    if pick:
        chosen = next((c for c in cands if c["qid"] == pick), None) or {"qid": pick, "label": pick, "score": 0,
                                                                         "coordinates": None, "classes": [], "country": None}
    elif cands and (len(cands) == 1 or cands[0]["score"] - cands[1]["score"] >= 3):
        chosen = cands[0]
    else:
        chosen = None
    if not chosen:
        result["needs"].append("choose one of %d Wikidata candidates (--pick Qxxx), or give a region hint" % len(cands)
                               if cands else "no place named %r was found in Wikidata" % name)
        return result
    qid = chosen["qid"]
    entity = client.entities([qid]).get(qid)
    result["selected"] = chosen
    result["similar"] = similar_places(tree, client, qid, name)
    existing = match_tree(tree, client, qid)
    result["mode"] = "existing" if len(existing) == 1 else "new"
    child = existing[0] if len(existing) == 1 else "new:wd-%s" % qid

    # hierarchy on the date, up to the first place the tree already has
    def stop(q):
        return bool(match_tree(tree, client, q))
    steps = historical_chain(client, qid, sv, stop_at=stop)
    result["chain"] = steps
    ents = client.entities([qid] + [s["parent"] for s in steps])
    for s in steps:
        s["child_label"] = labels(ents.get(s["child"], {})).get("en") or s["child"]
        s["parent_label"] = labels(ents.get(s["parent"], {})).get("en") or s["parent"]

    # language of the names: the first state on the way up that has a rule
    lang, lang_note = language, ""
    if not lang:
        for s in steps:
            if s["parent"] in STATE_LANG:
                lang = STATE_LANG[s["parent"]]
                lang_note = "state on the date: %s" % (labels(ents.get(s["parent"], {})).get("en") or s["parent"])
                if lang is None:
                    lang_note += " (undecided: the English label is used; choose with --lang)"
                break
    chain_lo = max([_bound(s["start"], False) for s in steps] + [-INF])
    chain_hi = min([_bound(s["end"], True) for s in steps] + [INF])
    if not steps:
        result["needs"].append("Wikidata has no dated hierarchy for %s on %s: ask an agent or enter it yourself" % (name, date_text))

    def best_name(ent, fallback, typed=False):
        """Label in the state's language; without a rule, the name as typed (or the English label)."""
        if lang:
            return _name_in(ent, lang) or _name_in(ent, "en") or fallback
        return fallback if typed else (_name_in(ent, "en") or fallback)

    # ---- rows of the control screen
    rows = result["rows"]
    rows.append({"field": "identity", "value": "%s (%s) %s" % (chosen["label"], qid, chosen.get("country") or ""),
                 "source": "https://www.wikidata.org/wiki/%s" % qid, "basis": "evidence" if chosen["score"] >= 3 else "assumption"})
    if coordinates(entity):
        rows.append({"field": "coordinates", "value": "%s, %s" % coordinates(entity), "source": "Wikidata P625", "basis": "evidence"})
    else:
        result["needs"].append("no coordinates in Wikidata")
    guessed = type_from_classes(chosen.get("classes", []))
    rows.append({"field": "type", "value": "%s (as Wikidata calls it today; the type on %s needs a source)" % (
        PLACE_TYPE_NAMES.get(guessed, "Unknown"), date_text), "source": ", ".join(chosen.get("classes", [])[:3]),
        "basis": "assumption"})
    primary = best_name(entity, name, typed=True)
    rows.append({"field": "name", "value": "%s (%s)" % (primary, lang or "as typed"), "source": lang_note or "no state rule for this date: the name as you typed it",
                 "basis": "evidence" if lang else "assumption"})

    # ---- proposals
    proposals = []
    period = ({"valid_from": _iso(chain_lo), "valid_to": _iso(chain_hi)} if steps and _iso(chain_lo) and _iso(chain_hi) else {})

    def date_dict(first, last):
        if first and last:
            return make_span(packs.parse_iso(first), packs.parse_iso(last))
        if first:
            return make_from(packs.parse_iso(first))
        return {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False], "text": "", "sortval": 0}

    if child.startswith("new:"):
        coords = coordinates(entity)
        proposals.append({
            "kind": "add-place", "confidence": "evidence", "basis": "evidence", "handle": child, "gramps_id": "NEW-%s" % qid,
            "names": [{"value": primary, "lang": lang or "", "date": date_dict(period.get("valid_from"), period.get("valid_to"))}],
            "type_value": guessed if guessed is not None else -1,
            "lat": str(coords[0]) if coords else "", "lon": str(coords[1]) if coords else "",
            "urls": [{"path": "https://www.wikidata.org/wiki/%s" % qid, "type": "Wikidata"}], "origin": "wikidata",
            "evidence": [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/%s" % qid, "claim": "item %s" % qid}],
            "events": 1, "worse": 0, "conflict": False, "old": {}, "new": {}, "bundle": "complete-%s" % qid})
    handles = {qid: child}
    for s in steps:
        parent_handle = None
        if s["stop"]:
            found = match_tree(tree, client, s["parent"])
            parent_handle = found[0] if len(found) == 1 else None
        if parent_handle is None:
            parent_handle = "new:wd-%s" % s["parent"]
            pent = ents.get(s["parent"]) or {}
            pcoords = coordinates(pent)
            born, died = lifetime(pent)
            proposals.append({
                "kind": "add-place", "confidence": "evidence", "basis": "evidence", "handle": parent_handle,
                "gramps_id": "NEW-%s" % s["parent"],
                "names": [{"value": best_name(pent, s["parent"]), "lang": lang or "en", "date": date_dict(born, died)}],
                "type_value": type_from_classes([labels(c).get("en") for c in client.entities(
                    [entity_id(x["value"]) for x in claims(pent, "P31") if entity_id(x["value"])]).values()]) or -1,
                "lat": str(pcoords[0]) if pcoords else "", "lon": str(pcoords[1]) if pcoords else "",
                "urls": [{"path": "https://www.wikidata.org/wiki/%s" % s["parent"], "type": "Wikidata"}], "origin": "wikidata",
                "evidence": [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/%s" % s["parent"], "claim": "item %s" % s["parent"]}],
                "events": 0, "worse": 0, "conflict": False, "old": {}, "new": {}, "bundle": "complete-%s" % qid})
        handles[s["parent"]] = parent_handle
        link_from = handles[s["child"]]
        existing_refs = tree.places[link_from]["refs"] if link_from in tree.places else []
        already = any(r.get("ref") == parent_handle for r in existing_refs)
        if not already:
            proposals.append({
                "kind": "add-link", "confidence": "evidence", "basis": s["basis"], "child": link_from, "parent": parent_handle,
                "index": len(existing_refs), "old": {}, "new": date_dict(s["start"], s["end"]), "conflict": False,
                "origin": "wikidata", "events": 1, "worse": 0, "bundle": "complete-%s" % qid,
                "evidence": [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/%s" % s["child"],
                              "claim": "%s %s, start %s, end %s, rank %s" % (s["via"], s["parent"], s["start"], s["end"], s["rank"])}]})
    result["proposals"] = proposals

    # ---- what Gramps would display for an event on that date
    synthetic = {"handle": "synthetic", "id": "NEW", "type": {}, "date": date, "place": child}
    trial = gaps.apply(tree, proposals)
    trial.events = list(tree.events) + [synthetic]
    rows_after = [r for r in gaps.analyse(trial, about) if r["event"]["handle"] == "synthetic"]
    if rows_after:
        result["preview"] = rows_after[0]["chain"]["names"]
        result["preview_end"] = rows_after[0]["chain"]["end"]
    result["covered"] = (_iso(chain_lo), _iso(chain_hi)) if steps else None
    return result


def render(result):
    """The control screen as text."""
    out = ["PLACE %r on %s" % (result["name"], result["date"])]
    sel = result.get("selected")
    if len(result["candidates"]) > 1 or not sel:
        out.append("candidates in Wikidata:")
        for c in result["candidates"][:5]:
            out.append("  %s %-34s %-18s score %d  %s" % (
                "*" if sel and sel["qid"] == c["qid"] else " ", c["label"][:34], (c.get("country") or "")[:18], c["score"], c["qid"]))
    if not sel:
        out += ["NEEDS: " + n for n in result["needs"]]
        return "\n".join(out)
    out.append("mode: %s" % ("the place is already in the tree" if result["mode"] == "existing" else "a new place"))
    if result["similar"]:
        out.append("SIMILAR PLACES ALREADY IN THE TREE (check before creating):")
        for s in result["similar"][:6]:
            out.append("  %s  (%s)" % (s["label"], ", ".join(s["reasons"])))
    out.append("")
    out.append("%-12s %-62s %-10s %s" % ("field", "value", "basis", "source"))
    for r in result["rows"]:
        out.append("%-12s %-62s %-10s %s" % (r["field"], r["value"][:62], r["basis"], r["source"][:60]))
    out.append("")
    out.append("HIERARCHY ON %s" % result["date"])
    for s in result["chain"]:
        out.append("  %s -> %s   [%s .. %s] %s%s" % (s.get("child_label") or s.get("child", "?"), s.get("parent_label") or s.get("parent", "?"),
                                                     s["start"] or "?", s["end"] or "?", s["basis"],
                                                     "  (%s)" % s["where"] if s.get("where") else ("  (already in the tree)" if s["stop"] else "")))
    if result.get("covered"):
        out.append("this chain is valid %s .. %s" % result["covered"])
    out.append("")
    if result["preview"]:
        out.append("GRAMPS WOULD DISPLAY: " + ", ".join(result["preview"]))
    for n in result["needs"]:
        out.append("NEEDS: " + n)
    out.append("")
    out.append("PROPOSALS (%d): %s" % (len(result["proposals"]), ", ".join(
        "%s%s" % (p["kind"], " '%s'" % p["names"][0]["value"] if p["kind"] == "add-place" else "") for p in result["proposals"])))
    return "\n".join(out)
