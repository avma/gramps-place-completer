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
"""The names and the web links: the periods of the names of the levels and of the place (NP1, NP3, NP5, NL), the names of the levels that the user chose, the links.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import rules
from .complete import _bound
from .dates import INF, interval, is_empty
from .evidence import MAIN_FIELDS, UNIT_FIELDS, _sources, url_proposal
from .matching import _alternatives, _is_unit_name
from .periods import _date, _name_really_ended, _piece
from .screen import _need
from .words import fold


def names_and_links(a):
    """The periods of the names of the levels and of the place, the names of the levels that were chosen, and the web links."""
    aliases, child, link_offer = a.aliases, a.child, a.link_offer
    name, name_plain, out = a.name, a.name_plain, a.out
    proposals, rec, ruling = a.proposals, a.rec, a.ruling
    skip, state_began, tree = a.skip, a.state_began, a.tree
    unit_lang, unit_names, units = a.unit_lang, a.unit_names, a.units
    # A name that has NO period gets the period its unit has in the answer. It is a choice of its own: a name that is dated no longer shows
    # for an event before that date (the chain shows "?" there), so each change says so.
    def undated_matches(handle, wanted, mention_names=(), lang=""):
        kind = tree.places[handle]["type"] or {}
        # a name is the unit's when it, or its plain form ("City of Johnston" -> "Johnston"), is a name the answer gives the unit: another name
        # of the same place ("Hawkeye State", "IA" for Iowa) is not, and gets no period from the answer.
        found = [(position, n) for position, n in enumerate(tree.all_names(handle)) if is_empty(n.get("date")) and
                 _is_unit_name(n.get("value"), kind, wanted, mention_names)]
        # The same spelling can be several names of the place, one for each language (Iowa in English, German, French ...): the answer dates the
        # name in ITS language and the name that has none, not all of them. A single name is the one, whatever its language (an answer in German
        # may well write the name of a unit in English).
        if len(found) > 1 and lang:
            mine = [(position, n) for position, n in found if not (n.get("lang") or "") or (n.get("lang") or "") == lang]
            if mine:
                found = mine
        return found

    def period_fill(handle, position, n, new_date, fields):
        proposals.append({"kind": "set-name-date", "confidence": "assumption", "basis": "assumption", "place": handle,
                          "value": n.get("value"), "lang": n.get("lang") or "", "index": position, "old": n.get("date") or {},
                          "new": new_date, "conflict": False, "origin": "ai-answer", "evidence": _sources(rec, fields), "events": 0, "worse": 0,
                          "bundle": None})
    for u in units:
        c = u["mention"]
        if rules.on("NP5") and u.get("handle") and u["handle"] != child and (c["from"] or c["to"]):
            for position, n in undated_matches(u["handle"], unit_names(c), _alternatives(c["name"], aliases), unit_lang(c)):
                period_fill(u["handle"], position, n, _date(c["from"], c["to"]), UNIT_FIELDS)
    if child in tree.places:
        own = next((c2 for n2, c2 in enumerate(rec["containers"], 1) if n2 not in skip and fold(c2["name"]) in {fold(name), fold(name_plain)}), None)
        # (own: the line of the place itself, a municipality 1806-2013)
        if rules.on("NP1") and own and own.get("to") and not _name_really_ended(rec, own["to"]):
            for position, n in enumerate(tree.all_names(child)):
                span = interval(n.get("date") or {})
                if (not is_empty(n.get("date")) and span and span[1] < INF and fold(n.get("value")) in {fold(name), fold(name_plain)}
                        and abs(span[1] - _bound(own["to"], True)) <= 1 and (n.get("lang") or "") in ("", rec["language"] or "")):
                    _need(out, "name «%s» end date (%s) matches response boundary without successor name; period upper limit opened", n.get("value"), own["to"])
                    period_fill(child, position, n, _piece(span[0], INF), MAIN_FIELDS)
        if state_began and rules.on("NP3"):
            found = undated_matches(child, {fold(name), fold(name_plain)}, [name], rec["language"] or "")
            for position, n in found:
                period_fill(child, position, n, _date(state_began, None), ("STATE_ON_DATE", "PLACE_NAME_ON_DATE"))
            if found:
                _need(out, "name «%s» applies from %s (establishment of ruling state %s); provided in state official language (inferred)", name, state_began, ruling)
    for u in units:                                                        # a unit that the user chose as a place of the tree: its name is offered
        if u.get("chosen") and fold(u["mention"]["name"]) not in {fold(n.get("value")) for n in tree.all_names(u["handle"])}:
            c = u["mention"]
            proposals.append({"kind": "add-name", "confidence": "assumption", "basis": "assumption", "place": u["handle"], "value": c["name"],
                              "lang": unit_lang(c), "index": None, "old": {}, "new": _date(c["from"], c["to"]), "conflict": False,
                              "origin": "ai-answer", "evidence": _sources(rec, UNIT_FIELDS), "events": 0, "worse": 0, "bundle": None})
    if child in tree.places:                                                  # LK: a link of the answer that the place lacks is an addition (a doubtful site is offered unchecked)
        for o in link_offer:
            said = next((x["supports"] for x in rec["sources"] if x["url"] == o["path"]), "")
            proposals.append(url_proposal(child, o, [{"source": "ai-answer", "url": o["path"], "claim": said}]))
    else:
        maybe = [o["path"] for o in link_offer if not o["chosen"]]
        if maybe:
            _need(out, "response identifies potential official web links; excluded automatically (verify and attach manually if "
                       "valid): %s", "; ".join(maybe))
