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
"""The levels of the answer: which place of the tree each level is, what the user chose or left out, and the chain of units that the answer makes.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import hierarchy
from . import names as namelib
from .i18n import _ as tr
from .kinds import _same_kind, _state_type, _type_matches
from .matching import _alternatives, _shares_a_word, match_container
from .periods import _covers_text
from .screen import _need
from .words import fold


def check_levels(a):
    """The remarks of the reader, and the levels that the country has on that date and the answer lacks."""
    country, date_text, out = a.country, a.date_text, a.out
    rec = a.rec

    for note in rec.get("unit_notes", []):                       # remarks of the reader itself: not translated
        out["needs"].append(note)
        out["needs_local"].append(note)
    # the levels that the country has on that date (data/hierarchies.json): a level that the answer lacks is said, not made up
    entry = country or (hierarchy.find_country(rec["state"]["name"]) if rec["state"] else None)
    for kind, local in hierarchy.missing(entry, hierarchy.year_of(date_text), [c["type"] for c in rec["containers"]]):
        _need(out, "response omits administrative tier %s (%s) present for %s on date %s", kind, local or "-", entry["names"][0], date_text)


def prepare_levels(a):
    """The set-up for the levels of the answer: what the user chose, how a level is matched to a place of the tree, and the language of a level."""
    aliases, choices, out = a.aliases, a.choices, a.out
    rec, sv, tree = a.rec, a.sv, a.tree
    # the units, smallest first, then the state on top
    units = []
    choices = choices or {}
    out["ambiguous"] = []
    chosen = set()                                                         # the slots that the user answered with a place of the tree
    LEFT_OUT = object()

    def resolve(slot, mention, kind_text):
        """(handle, ranked) of a unit; LEFT_OUT when the unit is not used: by the user's choice, or until the user has chosen between
        places that could each be it (a new place is never made while one that exists may be the same)."""
        choice = choices.get(slot)
        if slot == "state" and any(choices.get("c%d" % n) == "skip" and fold(c["name"]) == fold(mention["name"])
                                   for n, c in enumerate(rec["containers"], 1)):
            choice = "skip"                                                # the state is also listed as a level, and that level was left out
        if choice == "skip":
            _need(out, "%s excluded per user selection", mention["name"])
            return LEFT_OUT
        if choice == "new":
            return None, []
        if choice in tree.places:
            chosen.add(slot)
            return choice, []
        handle, ranked = match_container(tree, mention["name"], kind_text, sv, aliases=aliases)
        if not handle and ranked and ranked[0][0] >= 9:                  # a name that is the same, but not clearly one place: ask
            near = [(sc, h) for sc, h in ranked if sc >= ranked[0][0] - 3]          # those that are about as good as the best
            out["ambiguous"].append({"slot": slot, "name": mention["name"], "type": mention["type"],
                                     "candidates": [{"handle": h, "label": tree.label(h), "score": sc} for sc, h in near][:4]})
            _need(out, "ACTION REQUIRED: %s matches existing places (%s). Select target entity (excluded until resolved)", mention["name"], " or ".join(tree.label(h) for _sc, h in near[:3]))
            return LEFT_OUT
        return handle, ranked

    main_settlement = namelib.settlement_like(rec["type_value"], rec["type_text"])
    def unit_names(mention):
        """The names the answer gives a unit, with those a regional pack knows for it (United States = USA), and their plain forms."""
        found = set()
        for alt in _alternatives(mention["name"], aliases):
            found |= {fold(alt), fold(namelib.plain_name(alt, None, mention["type"]))}
        return found

    ruling = (rec["state"] or {}).get("name") or ""
    # The answer writes the name in the language of the state that ruled on the date: so the name was in use from the day that state began.
    # Only when the answer is not in English, the state is one with a single language and that language is the name's (an inference).
    state_began = None
    if rec["state"] and rec["state"]["from"] and rec["language"] and rec["language"] != "en" and namelib.state_language(ruling) == rec["language"]:
        state_began = rec["state"]["from"]

    def unit_lang(c):
        """The language of the name of a unit: English when the whole answer is in English; else the language of the state the answer says
        the unit belonged to (Romania -> ro), or of the state that ruled on the date; empty when that is not a state with one language."""
        if rec["language"] == "en":
            return "en"
        return (namelib.state_language(c.get("state")) or (namelib.state_language(c["name"]) if c.get("is_state") else "")
                or namelib.state_language(ruling))
    untouched = set()                                                        # places of the levels that were skipped: nothing is known about them
    typed_changed = set()                                                    # places whose type is offered to be changed (once each)
    a.keep(locals(), "LEFT_OUT", "choices", "chosen", "main_settlement", "resolve", "ruling", "state_began", "typed_changed", "unit_lang", "unit_names", "units", "untouched")


def read_levels(a):
    """The levels of the answer made into units: each matched to a place of the tree or to a new place, the state, and the chain of the units."""
    LEFT_OUT, aliases, child = a.LEFT_OUT, a.aliases, a.child
    choices, chosen, date_text = a.choices, a.chosen, a.date_text
    main_settlement, name, name_plain = a.main_settlement, a.name, a.name_plain
    out, rec, resolve = a.out, a.rec, a.resolve
    skip, sv, tree = a.skip, a.sv, a.tree
    units, untouched = a.units, a.untouched
    for number, c in enumerate(rec["containers"], 1):
        if number in skip:
            _need(out, "administrative level %d (%s) excluded per user selection", number, c["name"])
            left_alone = match_container(tree, c["name"], c["type"], sv, aliases=aliases)[0]
            if left_alone:
                untouched.add(left_alone)                                      # a link to it is not a conflict: the user doubts that level
            continue
        if main_settlement and namelib.settlement_like(None, c["type"]) and \
                fold(namelib.plain_name(c["name"], None, c["type"])) == fold(name_plain):
            _need(out, "%s is identical to %s (listed as municipal container). Duplicate entity creation prevented", c["name"], name)
            continue
        if rec["state"] and fold(c["name"]) == fold(rec["state"]["name"]):
            c["is_state"] = True                                         # the top level that is the state itself: a country, an empire ...
        found = resolve("c%d" % number, c, ("empire" if _state_type(c["name"])["value"] == 0 else "state") if c.get("is_state") else c["type"])
        if found is LEFT_OUT:
            continue
        handle, ranked = found
        units.append({"mention": c, "handle": handle, "ranked": ranked, "covers": _covers_text(c, sv), "slot": "c%d" % number,
                      "chosen": "c%d" % number in chosen})
    state = rec["state"]
    if state:
        s_unit = {"mention": {"name": state["name"], "type": "state", "from": state["from"], "to": state["to"], "state": "",
                              "is_state": True}, "slot": "state"}
        found = resolve("state", s_unit["mention"], "empire" if _state_type(state["name"])["value"] == 0 else "state")
        if found is not LEFT_OUT:
            s_unit["handle"], s_unit["ranked"] = found
            s_unit["chosen"] = "state" in chosen
            s_unit["covers"] = _covers_text(s_unit["mention"], sv)
            units.append(s_unit)
    # A unit that was not found by its NAME is often a place of the tree under another name or in another language (the answer says Repubblica
    # Italiana, the tree has Italy). The tree itself suggests which: the place above the unit below it. It is a suggestion, not a decision (the
    # tree may hold that place for other years): the user is asked, and nothing is created until the answer. It is suggested when it is the only
    # parent of that unit that is of the type the answer gives (a state above a region) and no other unit of the answer is already that place.
    taken = {u["handle"] for u in units if u.get("handle")} | {child}
    kept = []
    for position, u in enumerate(units):
        below = kept[-1]["handle"] if kept and kept[-1].get("handle") else (child if not kept and child in tree.places else None)
        if u.get("handle") or choices.get(u["slot"]) in ("new", "skip") or not below:
            kept.append(u)                                                # found, or already answered, or nothing to go by
            continue
        mention = u["mention"]
        if any(fold(a["name"]) == fold(mention["name"]) for a in out["ambiguous"]):
            continue                                                      # the same name as a level that is being asked about (the state is also listed as a level)
        above = [r["ref"] for r in tree.places[below].get("refs") or [] if r.get("ref") in tree.places and r["ref"] not in taken
                 and (_type_matches(tree, r["ref"], "state" if mention.get("is_state") else mention["type"])         # a kind that the types name (Kaunas County, Kauno apskritis)
                      or (_same_kind(tree, r["ref"], mention["type"]) and _shares_a_word(tree, r["ref"], mention["name"])))]     # or of the same kind with a word in common
        above = list(dict.fromkeys(above))
        if len(above) != 1:
            kept.append(u)
            continue
        label, below_label = tree.label(above[0]), tree.label(below)
        out["ambiguous"].append({"slot": u["slot"], "name": mention["name"], "type": mention["type"],
                                 "candidates": [{"handle": above[0], "label": label, "score": 0}],
                                 "why": tr("«%s» is not in your tree under that name, but «%s» holds «%s» there. Is it the same place? "
                                           "Nothing is created until you choose.") % (mention["name"], label, below_label)})
        _need(out, "ACTION REQUIRED: %s matches existing %s (containing %s). Select target entity (excluded until resolved)",
              mention["name"], label, below_label)
    units = kept
    cleaned = []
    for u in units:
        prev = cleaned[-1] if cleaned else None
        if prev and ((u["handle"] and u["handle"] == prev["handle"]) or fold(u["mention"]["name"]) == fold(prev["mention"]["name"])):
            continue                                                          # (the state is listed as a level and as the state: it is used once)
        cleaned.append(u)
    units = cleaned
    for u in units:
        c = u["mention"]
        if u["handle"]:
            u["label"] = tree.label(u["handle"])
            where = "in the tree: " + u["label"]
        elif u["ranked"]:
            where = "NOT SURE which: " + "; ".join(tree.label(h) for _, h in u["ranked"][:3])
        else:
            u["label"], where = c["name"], "NEW place (not in the tree)"
        out["chain"].append({"child_label": "", "parent_label": c["name"] + " | " + c["type"], "start": c["from"], "end": c["to"],
                             "basis": "assumption", "stop": bool(u["handle"]), "where": where})
        if not u["covers"]:
            _need(out, "%s is not historically valid on %s according to defined time boundaries", c["name"], date_text)
    # chain rendering uses child -> parent: link every unit to the next one
    previous = None
    for step, u in zip(out["chain"], units):
        step["child_label"] = previous or name
        previous = u["mention"]["name"]
    a.keep(locals(), "units")
