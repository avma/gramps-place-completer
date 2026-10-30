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
"""The links of the chain: for the place and for each level, the link to the level above it is added, changed, cut or left alone (rules C1-C8, T1, T2).
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
from . import levels
from . import names as namelib
from . import rules
from .i18n import _ as tr
from .complete import _bound, _iso
from .dates import describe, interval, is_empty
from .evidence import UNIT_FIELDS, _sources
from .kinds import TREE_TYPES, _SETTLEMENT_TYPES, has_no_type, type_name, _container_type, _same_kind, _state_type
from .matching import _alternatives, _ancestors, _homonym_settlement
from .periods import _date, _intersect, _overlaps, _piece, _split
from .screen import _lbl, _need
from .words import _tokens, fold


def existing_place(a):
    """The place of the question that the tree has: what the answer adds to it; and the checks of a link (type_of, cannot)."""
    child, name, proposals = a.child, a.name, a.proposals
    out, rec, tree = a.out, a.rec, a.tree
    # what the place that exists still lacks, and the answer can give (an empty field is filled, a filled one is never touched)
    if child in tree.places:
        place = tree.places[child]
        stand_alone = {"confidence": "assumption", "basis": "assumption", "conflict": False, "origin": "ai-answer", "evidence": [],
                       "events": 0, "worse": 0, "bundle": None, "old": {}, "new": {}, "index": None}
        if rec["coordinates"] and not (str(place["lat"]).strip() or str(place["lon"]).strip()):
            proposals.append({**stand_alone, "kind": "set-coordinates", "place": child, "lat": str(rec["coordinates"][0]),
                              "lon": str(rec["coordinates"][1]), "evidence": _sources(rec, ("COORDINATES",))})
        if rec["language"]:
            for position, n in enumerate(tree.all_names(child)):
                if fold(n.get("value")) == fold(name) and not (n.get("lang") or ""):
                    proposals.append({**stand_alone, "kind": "set-name-language", "place": child, "index": position,
                                      "value": n["value"], "lang": rec["language"], "evidence": _sources(rec, ("PLACE_NAME_ON_DATE", "LANGUAGE"))})
        kind = place["type"] or {}
        primary = place["name"].get("value") or ""
        simple = namelib.plain_name(primary, kind.get("value"), kind.get("string", ""))
        if simple and simple != primary:
            proposals.append({**stand_alone, "kind": "rename-place", "place": child, "index": 0, "value": primary, "new_value": simple,
                              "lang": place["name"].get("lang") or "", "keep_old": True})
        if (rec["type_value"] is not None or rec["type_string"]) and has_no_type(kind):
            proposals.append({**stand_alone, "kind": "set-type", "place": child, "type_value": rec["type_value"] if rec["type_value"] is not None else 0, "type_string": rec["type_string"],
                              "evidence": _sources(rec, ("SETTLEMENT_TYPE_ON_DATE",))})
        elif (rules.on("ST6") and rec.get("type_closed") and kind.get("value", -1) in _SETTLEMENT_TYPES and not kind.get("string")
              and (rec["type_value"] in _SETTLEMENT_TYPES or (rec["type_value"] == 0 and rec["type_string"]))
              and (rec["type_value"], rec["type_string"]) != (kind["value"], "")):
            # ST6: a type of Gramps that is a settlement, and the answer (one word of the closed list) gives another size class: a change to data that exists.
            # Never a type of the user's own, never a place that is not a settlement, never an answer of the old kind (its words may be a legal status).
            proposals.append({**stand_alone, "kind": "change-type", "place": child, "type_value": rec["type_value"], "type_string": rec["type_string"],
                              "old_type_value": kind["value"], "old_type_string": "", "fields": ["SETTLEMENT_TYPE_ON_DATE"],
                              "evidence": _sources(rec, ("SETTLEMENT_TYPE_ON_DATE",))})
        elif (rec.get("type_closed") and rec["type_value"] in _SETTLEMENT_TYPES and not has_no_type(kind)
              and (kind.get("value", -1) not in _SETTLEMENT_TYPES or kind.get("string"))
              and kind.get("string") not in TREE_TYPES.get("settlements", [])):
            # the place of the tree is not a settlement (an area, a canton, a type of the user's own): its type is not changed, and the screen says why (it may be
            # the canton or the province of the same name, which is another place, or the town itself that was typed wrongly)
            _need(out, "the type of %s in the tree is «%s» but the response specifies %s: non-settlement types are not modified "
                       "automatically here. Adjust the place type in Gramps if needed",
                  tree.label(child), kind.get("string") or type_name(kind.get("value")), rec["type_text"] or rec["type_string"] or "?")
    # links: place -> unit 1 -> unit 2 -> ... -> state
    chain_from = child
    already = []                                                             # links that exist and need no change

    def type_of(handle):
        if handle in tree.places:
            return tree.places[handle].get("type") or {}
        for q in proposals:
            if q["kind"] == "add-place" and q["handle"] == handle:
                return {"value": q["type_value"], "string": q.get("type_string", "")}
        return {}

    def cannot(parent_handle, parent_type, child_handle):
        """Why a place cannot be inside another (T1 loop, T2-T5 levels), '' when it can."""
        if rules.on("T1") and parent_handle == child_handle:
            return tr("a place cannot contain itself")
        if rules.on("T1") and parent_handle in tree.places and child_handle in tree.places and child_handle in _ancestors(tree, parent_handle):
            return tr("this would create a circular hierarchy loop")
        return levels.violation(parent_type, type_of(child_handle), TREE_TYPES) if rules.on("T2") else ""
    a.keep(locals(), "already", "cannot", "chain_from", "type_of")


def link_chain(a):
    """The links of the chain, level by level (C1-C8, T1, T2): added, changed, cut or left alone."""
    already, cannot, chain_from = a.already, a.cannot, a.chain_from
    name, out, place_for = a.name, a.out, a.place_for
    proposals, rec, tree = a.proposals, a.rec, a.tree
    type_of, units, untouched = a.type_of, a.units, a.untouched

    for i, u in enumerate(units):
        c = u["mention"]
        mention_type = (tree.places[u["handle"]].get("type") or {}) if u.get("handle") else (_state_type(c["name"]) if c.get("is_state") else _container_type(c["type"]) or {})
        if u.get("handle") != chain_from:
            refused = cannot(u.get("handle") or "", mention_type, chain_from) if rules.on("C8") else ""
            if refused:                                                      # C8: the level is left out, the next one is linked to the same place
                _need(out, "%s -> %s excluded from hierarchy chain: %s. Next level linked directly to %s instead", _lbl(tree, chain_from), c["name"], refused,
                      _lbl(tree, chain_from))
                u["refused"] = True
                continue
        parent = place_for(u)
        u["key"] = parent
        if parent == chain_from:
            continue
        period = _intersect(c["from"], c["to"], units[i - 1]["mention"] if i else {"from": None, "to": None})
        refs = tree.places[chain_from]["refs"] if chain_from in tree.places else []
        same = [r for r in refs if r.get("ref") == parent]
        later = {u2["handle"] for u2 in units[i + 1:] if u2.get("handle")}
        link_key = "link:%s:%s" % (chain_from, parent)
        fix_key = "fix:%s:%s" % (chain_from, parent)
        wrong_links = []                                                     # links that break the rules at any time (C5): the answer names another parent
        for r in (refs if rules.on("C5") else []):
            rp = r.get("ref")
            if rp == parent or rp in later or rp in untouched or rp not in tree.places:
                continue
            reason = cannot(rp, type_of(rp), chain_from)
            if not reason and _homonym_settlement(tree, rp, c):
                reason = tr("it is a settlement sharing its name with the area specified in the answer")
            if reason:
                wrong_links.append((r, reason))
        wrong_ids = {id(r) for r, _reason in wrong_links}

        def disconnect_notes(requires):
            for r, reason in wrong_links:
                _need(out, "CONFLICT: in the tree, %s is linked to %s, but the response places it under %s (from %s), and the existing "
                           "link is incorrect: %s. Result if you disconnect: %s will no longer be inside %s. Not selected automatically: "
                           "changes to existing data must be approved one by one.", _lbl(tree, chain_from), _lbl(tree, r.get("ref")), c["name"], c["from"] or "?", reason, _lbl(tree, chain_from),
                      _lbl(tree, r.get("ref")))
                proposals.append(piece_proposal("remove-link", r, {}, refs.index(r), requires_key=requires))

        def piece_proposal(kind, r2, new, index, **extra):
            return dict({"kind": kind, "confidence": "assumption", "basis": "assumption", "child": chain_from, "parent": r2.get("ref"), "index": index,
                         "old": r2.get("date") or {}, "new": new, "conflict": False, "inferred": True, "existing": True, "refines": False,
                         "origin": "ai-answer", "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None}, **extra)

        def duplicate_notes():
            """Another parent of the place with the same name and kind as this level: two places that are one (Regione Emilia-Romagna beside Emilia-Romagna)."""
            if parent not in tree.places:
                return
            wanted = set(_tokens(c["name"]))
            for r2 in refs:
                other_place = r2.get("ref")
                if (other_place != parent and other_place in tree.places and wanted and _same_kind(tree, other_place, c["type"])
                        and any(set(_tokens(n.get("value") or "")) == wanted for n in tree.all_names(other_place))):
                    _need(out, "%s is also linked to %s, which appears identical to %s (same name and type). Merge them in Gramps (Edit > "
                               "Merge Places) to consolidate this hierarchy level", _lbl(tree, chain_from), _lbl(tree, other_place), _lbl(tree, parent))

        def offer_shortcuts(shortcuts, correct_index, requires):
            """The direct links to a higher place of the chain that the link of the answer makes redundant: a disconnect when all their years are covered, a
            cut to the years before otherwise; each needs `requires` (the link of the answer, or its widening). correct_index: where that link stands."""
            if not rules.on("C6"):
                return
            for r2 in shortcuts:
                first = correct_index is not None and refs.index(r2) < correct_index
                left, right = _split(r2, period)
                pieces = [x for x in (left, right) if x]
                if not pieces:
                    if first:
                        _need(out, "%s is also linked directly to %s (prior to link %s) covering the same date range. Disconnecting will lose no "
                                   "data: %s is accessible via %s", _lbl(tree, chain_from), _lbl(tree, r2.get("ref")), c["name"], _lbl(tree, chain_from), c["name"])
                    else:
                        _need(out, "%s is also linked directly to %s (after link %s) covering the same date range. Disconnecting will lose no "
                                   "data: %s is accessible via %s", _lbl(tree, chain_from), _lbl(tree, r2.get("ref")), c["name"], _lbl(tree, chain_from), c["name"])
                    proposals.append(piece_proposal("remove-link", r2, {}, refs.index(r2), requires_key=requires))
                    continue
                if first:
                    _need(out, "%s is also linked directly to %s (listed before the link to %s): it applies only to the years before this link takes effect", _lbl(tree, chain_from),
                          _lbl(tree, r2.get("ref")), c["name"])
                else:
                    _need(out, "%s is also linked directly to %s (listed after the link to %s): it applies only to the years before this link takes effect", _lbl(tree, chain_from),
                          _lbl(tree, r2.get("ref")), c["name"])
                cut_key = "cut:%s:%s" % (chain_from, r2.get("ref"))
                proposals.append(piece_proposal("set-link", r2, pieces[0], refs.index(r2), key=cut_key, requires_key=requires))
                if len(pieces) == 2:
                    proposals.append(piece_proposal("add-link", r2, pieces[1], len(refs), requires_key=cut_key))

        duplicate_notes()
        if same:                                                             # the link exists
            r = same[0]
            iv = interval(r.get("date") or {})
            lo, hi = _bound(period[0], False), _bound(period[1], True)
            if rules.on("C3") and iv is not None and iv[0] > iv[1]:          # C3: a period that ends before it starts
                _need(out, "%s -> %s: existing tree link has an invalid date range (%s). The response period (%s-%s) will replace it if "
                           "selected", _lbl(tree, chain_from), c["name"], describe(r.get("date") or {}), c["from"] or "?", c["to"] or "present")
                proposals.append(piece_proposal("set-link", r, _date(*period) or {}, refs.index(r), key=fix_key))
            elif iv is None or (iv[0] <= lo + 1 and hi <= iv[1]):            # C2: as the answer says
                already.append("%s -> %s" % (_lbl(tree, chain_from), c["name"]))
            elif not rules.on("C3"):
                pass
            else:
                outside = [x for x in ((lo, min(hi, iv[0] - 1)), (max(lo, iv[1] + 1), hi)) if x[0] <= x[1]]
                clash = [r2 for r2 in refs if r2 is not r and r2.get("ref") not in later and any(_overlaps(r2.get("date"), (_iso(x[0]), _iso(x[1]))) for x in outside)]
                if clash:
                    _need(out, "%s -> %s: the response specifies %s-%s, but the tree contains %s, and %s covers the intervening years; date "
                               "period left unchanged for verification", _lbl(tree, chain_from), c["name"], c["from"], c["to"] or "present",
                          describe(r.get("date") or {}), ", ".join(_lbl(tree, r2.get("ref")) for r2 in clash))
                elif lo > iv[1] + 1 or hi < iv[0] - 1:
                    _need(out, "%s -> %s: the response specifies %s-%s and the tree contains %s, with gaps not covered by the link; date "
                               "period was left unchanged for review", _lbl(tree, chain_from), c["name"], c["from"], c["to"] or "present", describe(r.get("date") or {}))
                else:                                                        # the answer is wider and nothing else claims the years
                    proposals.append(piece_proposal("set-link", r, _piece(min(iv[0], lo), max(iv[1], hi)), refs.index(r), inferred=False, key=fix_key))
            # C6/C7: a direct link to a higher place of the chain is redundant when the link of the answer covers its years; it needs that link to cover them
            offer_shortcuts([x for x in refs if x is not r and x.get("ref") in later and _overlaps(x.get("date"), period)], refs.index(r),
                            fix_key if any(q.get("key") == fix_key for q in proposals) else "")
            disconnect_notes("")                                             # the correct link is there: the wrong ones can go without anything else
        else:                                                                # the link does not exist: it is added (C1, C4, C5)
            other = [r for r in refs if r.get("ref") != parent and r.get("ref") not in untouched and _overlaps(r.get("date"), period)]
            inserted = [r for r in other if r.get("ref") in later]           # a direct link to a higher place of the same chain: a level is put in between
            rest = [r for r in other if r.get("ref") not in later]
            different = [(r, "") for r in rest if id(r) not in wrong_ids]
            bundle = "ingest-%s" % re.sub(r"\W+", "", fold(name))
            link = {"kind": "add-link", "confidence": "assumption", "basis": "assumption", "child": chain_from, "parent": parent, "key": link_key,
                    "index": len(refs), "old": {}, "new": _date(*period), "conflict": False, "inferred": False, "refines": bool(inserted) and not rest,
                    "origin": "ai-answer", "evidence": _sources(rec, UNIT_FIELDS), "events": 1, "worse": 0, "bundle": bundle}
            if rules.on("C4") and other:                                     # before the old links: Gramps shows the first one that fits the date
                first = min(other, key=refs.index)
                link["position"], link["above"] = refs.index(first), first.get("ref")
            proposals.append(link)
            offer_shortcuts(inserted, None, link_key)                        # the new link is placed before them; they stay until the user chooses
            for r, _reason in different:
                _need(out, "%s is also linked to %s, and the response places it under %s (from %s): both links will be retained, with the "
                           "new link prioritized for matching years", _lbl(tree, chain_from), _lbl(tree, r.get("ref")), c["name"],
                      c["from"] or "?")
            disconnect_notes(link_key)                                       # C5: the links in the tree that are wrong: disconnects, chosen by the user
        chain_from = parent


def chain_notes(a):
    """The note of the links that already exist, and the levels that the user chose as places."""
    aliases, already, out = a.aliases, a.already, a.out
    proposals, rec, tree = a.proposals, a.rec, a.tree
    units = a.units
    if already:                                                              # one line for all of them: nothing is to be done about them
        _need(out, "These links already exist and require no changes: %s", "; ".join(already))
    # the names of the matched units must cover the years the answer gives them (or the chain shows "?")
    for u in units:
        if not u.get("handle"):
            continue
        c = u["mention"]
        lo, hi = _bound(c["from"], False), _bound(c["to"], True)
        names = tree.all_names(u["handle"])
        wanted = {t for alt in _alternatives(c["name"], aliases) for t in _tokens(alt)}
        idx = max(range(len(names)), key=lambda i: len(wanted & set(_tokens(names[i].get("value") or ""))) * 2 - (1 if i else 0))
        name_date = names[idx].get("date")
        iv = None if is_empty(name_date) else interval(name_date)
        if iv is None or (iv[0] <= lo + 1 and hi <= iv[1]) or lo > iv[1] + 1 or hi < iv[0] - 1:
            continue
        proposals.append({"kind": "set-name-date", "confidence": "assumption", "basis": "assumption", "place": u["handle"],
                          "value": names[idx].get("value"), "lang": names[idx].get("lang") or "", "index": idx,
                          "old": name_date, "new": _piece(min(iv[0], lo), max(iv[1], hi)), "conflict": False, "origin": "ai-answer",
                          "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None})
