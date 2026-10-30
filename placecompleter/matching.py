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
"""Matching what an answer names to what the tree has: the names that a place has by the regional packs, the place of the tree that a level of the
answer is, and what covers a date.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import difflib
import functools

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import names as namelib
from . import packs
from .dates import interval, is_empty
from .kinds import _same_kind, _type_conflict, _type_matches
from .words import _short_form, _tokens, _unit_words, fold, is_unknown



def _is_unit_name(value, kind, wanted, mention_names):
    """Is this name of a tree place the name the answer gives the unit? It is when it (or its plain form) is one of the names the answer
    gives, or when it is the same but for the word that says what the unit is and the TREE's name carries the word (Județul Hunedoara =
    Hunedoara; the city Johnston is not Johnston County)."""
    if {fold(value), fold(namelib.plain_name(value, kind.get("value"), kind.get("string", "")))} & wanted:
        return True
    have = set(_tokens(value or ""))
    return bool(have) and any(have == set(_tokens(m)) and (_unit_words(value) or not _unit_words(m)) for m in mention_names)


def _ancestors(tree, handle):
    """Every place above this one in the tree, through any link (cycle safe)."""
    seen, todo = set(), [handle]
    while todo:
        for r in tree.places.get(todo.pop(), {}).get("refs") or []:
            if r.get("ref") in tree.places and r["ref"] not in seen:
                seen.add(r["ref"])
                todo.append(r["ref"])
    return seen


def _shares_a_word(tree, handle, name):
    """Does a name of the place have a word (not a word that says what a unit is) in common with this name? Zona Emilia-Romagna, Emilia-Romagna: yes; another province: no."""
    wanted = set(_tokens(name))
    return any(wanted & set(_tokens(n.get("value") or "")) for n in tree.all_names(handle))


def _homonym_settlement(tree, handle, mention):
    """The place of the tree is a settlement that has the name of the area the answer names: Parma the city, for the Provincia di Parma."""
    return (handle in tree.places and _type_conflict(tree, handle, mention["type"])
            and any(_short_form(n.get("value") or "", mention["name"]) for n in tree.all_names(handle)))


def _alternatives(mention, aliases=None):
    alts = [a.strip() for a in mention.split("/") if a.strip()]
    extra = []
    for a in alts:
        extra += (aliases or {}).get(fold(a), [])
    return alts + [x for x in extra if x not in alts]


def alias_map(pack_paths):
    """Every name a regional pack knows for a place, by each of its names (Kingdom of Hungary = Magyarország ...)."""
    out = {}
    for path in pack_paths:
        for place in packs.load_pack(path)["places"]:
            names = packs._names(place)
            for n in names:
                out.setdefault(fold(n), [])
                out[fold(n)] += [x for x in names if x != n and x not in out[fold(n)]]
    return out


def _covers(tree, handle, sv):
    """+4 if one of the place's dated names covers the date, -3 if all its dated names exclude it."""
    dated = [interval(n.get("date")) for n in tree.all_names(handle) if not is_empty(n.get("date"))]
    if len(dated) < len(tree.all_names(handle)):
        return 1 if not dated else 4
    if any(iv and iv[0] <= sv <= iv[1] for iv in dated):
        return 4
    return -3


SIMILAR_RATIO = 0.8                       # two words are one word, misspelt, when difflib finds them this much alike
# how sure a name of the tree matches the name of a unit of the answer
SCORE_SAME_NAME = 10                      # the same name
SCORE_SAME_WORDS = 9                      # the same words but for the word that says what the unit is
SCORE_ALL_WORDS_LIKE = 6                  # every word of the answer is like a word of the name
SCORE_SOME_WORDS_LIKE = 3                 # at least half of the words are


@functools.lru_cache(maxsize=262144)
def _similar(a, b):
    """Is the ratio of difflib for two words at least 0.8? The two cheap upper bounds of the ratio are asked first: they give the same answer, only sooner
    (the same words come back for every place of the tree, so the answers are kept)."""
    if a == b:
        return True
    matcher = difflib.SequenceMatcher(None, a, b)
    return matcher.real_quick_ratio() >= SIMILAR_RATIO and matcher.quick_ratio() >= SIMILAR_RATIO and matcher.ratio() >= SIMILAR_RATIO


def match_container(tree, mention, type_text, sv, threshold=8, aliases=None):
    """Best tree place for a unit named in the answer: (handle or None, ranked candidates)."""
    ranked = []
    if is_unknown(mention):
        return None, []
    alternatives = [(alt, fold(alt), _tokens(alt)) for alt in _alternatives(mention, aliases)]          # the same for every place of the tree: made once
    for handle in tree.places:
        best = 0
        kind = tree.places[handle]["type"] or {}
        tree_names = tree.all_names(handle)
        names = [fold(n.get("value")) for n in tree_names] + \
            [fold(namelib.plain_name(n.get("value"), kind.get("value"), kind.get("string", ""))) for n in tree_names]
        have_of = None                                                                                 # the words of each name of the place: made when needed
        for alt, alt_folded, wanted in alternatives:
            if alt_folded in names:
                best = max(best, SCORE_SAME_NAME)
                continue
            if not wanted:
                continue
            if have_of is None:
                have_of = [_tokens(n.get("value") or "") for n in tree_names]
            for n, have in zip(tree_names, have_of):
                hits = sum(1 for w in wanted if any(_similar(w, h) for h in have))
                if have and set(have) == set(wanted) and (_unit_words(n.get("value")) or not _unit_words(alt) or _same_kind(tree, handle, type_text)):
                    # the same name but for the word that says what the unit is, and it is the TREE's name that carries the word (Hunedoara =
                    # Județul Hunedoara); the other way round it is not (Johnston County is not the city Johnston) unless the place is of the type
                    # the word says (New York State is the state New York, a state of the tree)
                    best = max(best, SCORE_SAME_WORDS)
                elif hits == len(wanted):
                    best = max(best, SCORE_ALL_WORDS_LIKE)
                elif hits and hits * 2 >= len(wanted):
                    best = max(best, SCORE_SOME_WORDS_LIKE)
        if not best:
            continue
        if _type_conflict(tree, handle, type_text):
            continue                                                       # Parma the province is not Parma the city
        covers = _covers(tree, handle, sv)
        if best >= 9 and covers < 0:
            covers = -1                  # the name is the same: a period of the name that does not reach the date is widened later, it is no reason to make a second place
        score = best + covers + (2 if _type_matches(tree, handle, type_text) else 0)
        ranked.append((score, handle))
    ranked.sort(key=lambda r: -r[0])
    if ranked and ranked[0][0] >= threshold and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 2):
        return ranked[0][1], ranked
    return None, ranked


# The answer to SETTLEMENT_TYPE_ON_DATE is ONE word of a closed list (see prompts.SETTLEMENT_WORDS): its size class, not its legal status. A metropolis is a City of Gramps
# (a rule of the tree may give it a type of its own: {"words": ["metropolis"], "value": 0, "string": ...} in the conventions file of the tree: see kinds.conventions_file).
SAME_PLACE_KM = 30                       # two places of one name that are farther apart than this are two places (ID1)
