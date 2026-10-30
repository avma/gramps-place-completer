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
"""Read an answer in the fixed template (Google AI mode, a chatbot or a person) and make it a control screen.

The template is the one the program asks for (see agent/search_prompt.md): labelled lines such as
PLACE_NAME_ON_DATE, COORDINATES and CONTAINERS (one administrative level per line, smallest first).
Everything taken from such an answer has the basis "assumption" until a source or the user confirms it.
The answer is matched to the places the tree already has (by name, with spelling tolerance, and by whether
the place's names are valid on the date), and what it contradicts in the tree is shown, not overwritten.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import re                                          # noqa: F401  (this module re-exports the names that the topic modules took over: the tests and the tools use them)

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import gaps, hierarchy, levels, links as linklib, names as namelib, rules                       # noqa: F401  (re-exported)
from .complete import _bound, _iso, parse_date                                                        # noqa: F401  (re-exported)
from .dates import INF, describe, interval, is_empty, ymd                                              # noqa: F401  (re-exported)
from .i18n import _ as tr                                                                              # noqa: F401  (re-exported)
from .wikidata import km, tree_coordinates                                                             # noqa: F401  (re-exported)

# The topics of the analysis, each in its own module: words (the folding of names, the word lists), kinds (the types of places), periods (the
# arithmetic of dates), reader (the text of the answer), matching (the places of the tree), compare (two answers). The names are read here too,
# by the rest of the program and by the tests, as they always were.
from .analysis import Analysis
from .findplace import find_place
from .resolve import check_levels, prepare_levels, read_levels
from .makeplaces import new_place, fix_levels
from .chainlinks import existing_place, link_chain, chain_notes
from .namefixes import names_and_links
from .screen import finish
from .screen import (_need, preview_for, _lbl)   # noqa: F401
from .evidence import (url_proposal, MAIN_FIELDS, UNIT_FIELDS, _ALL_LABELS, _FIELD_WORDS, _supported_fields, _sources)   # noqa: F401
from .words import (_KIND_OF_PLACE, UNKNOWN_WORDS, UNIT_WORDS, CONNECTORS, GENERIC, fold, is_unknown, _tokens, _says_something, _short_form, _unit_words)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)
from .kinds import (OVERLAY_WORDS, SETTLEMENT_CLASSES, SETTLEMENT_TYPES, load_tree_types, TREE_TYPES, _custom, CONTAINER_TYPES, _type_matches, _SUBDIVISIONS, _AREA_TYPES, _SETTLEMENT_TYPES, _type_conflict, _same_kind, _state_type, _TYPE_WORDS, _own_type, _container_type)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)
from .periods import (_name_really_ended, _date, _covers_text, _intersect, _overlaps, _tuple, _piece, _split)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)
from .reader import (LABELS, _period, _candidate, candidate_hints, refined_place, _split_remark, _clean_type, _restore_lines, parse_structured)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)
from .matching import (SAME_PLACE_KM, _is_unit_name, _ancestors, _shares_a_word, _homonym_settlement, _alternatives, alias_map, _covers, match_container)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)
from .compare import (_key, _answer_year, _same_place, compare_answers, compare_with_saved)   # noqa: F401  (the names of the analysis that moved: the rest of the program and the tests still read them here)


def ingest(tree, rec, date_text, about=None, skip=(), aliases=None, choices=None, country=None, languages=None):
    """The control screen for a parsed answer: same shape as complete.complete_place()."""
    date, sv = parse_date(date_text)
    name = rec["name"] or "?"
    out = {"name": name, "date": date_text, "child": None, "rows": [], "needs": [], "similar": [], "proposals": [], "chain": [],
           "preview": [], "candidates": [], "selected": {"qid": "pasted answer", "label": name, "score": 0},
           "mode": "new", "covered": None, "needs_local": []}
    if not rec["name"] and not rec["ambiguous"]:                           # nothing can be made of an answer that has no name (the question given back, UNKNOWN)
        _need(out, "response lacks place name; no changes proposed")
        return out
    if rec["ambiguous"]:
        out["selected"] = None
        if rec["candidates"]:
            _need(out, "place name is ambiguous. Select target location and query again using --hint \"%s\":", rec["candidates"][0]["region"] or rec["candidates"][0]["country"])
            for i, h in enumerate(candidate_hints(tree, rec["candidates"]), 1):
                _need(out, "  %d. %s  (%s, %s)%s", i, h["candidate"]["text"].split(", %s" % h["candidate"]["coordinates"][0])[0], h["candidate"]["coordinates"][0], h["candidate"]["coordinates"][1], "  <- " + "; ".join(h["notes"]) if h["notes"] else "")
        else:
            _need(out, "response indicates ambiguous place name: %s", " ".join(rec["ambiguous"])[:200])
        return out
    unsure = rec["not_sure"]
    rows = out["rows"]
    rows.append({"field": "name", "value": "%s (%s)" % (name, rec["language"] or "?"),
                 "source": "pasted answer", "basis": "assumption"})
    if rec["coordinates"]:
        rows.append({"field": "coordinates", "value": "%s, %s" % rec["coordinates"], "source": "pasted answer",
                     "basis": "assumption"})
    rows.append({"field": "type", "value": "%s (%s)" % (rec["type_text"] or "?", {16: "Village", 17: "Hamlet", 15: "Town", 4: "City", 6: "Locality"}.get(rec["type_value"], "?")),
                 "source": "pasted answer, NOT SURE" if "SETTLEMENT_TYPE_ON_DATE" in unsure else "pasted answer", "basis": "assumption"})
    a = Analysis(about=about, aliases=aliases, choices=choices, country=country, date_text=date_text, languages=languages, name=name, out=out, rec=rec, rows=rows, skip=skip, sv=sv, tree=tree)
    find_place(a)
    check_levels(a)
    prepare_levels(a)
    read_levels(a)
    new_place(a)
    fix_levels(a)
    existing_place(a)
    link_chain(a)
    chain_notes(a)
    names_and_links(a)
    finish(a)
    return out


