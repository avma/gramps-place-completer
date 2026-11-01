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
"""Learn the custom place types of a tree from the tree itself.

A tree keeps the types that its owner made up (village, kibbutz, canton ... in the language of the tree) as text on its places, and the same type is
often written in more than one way: with a space before or after it, with a no-break space, with an invisible mark of direction, in another case, with a dash
or a space between the words. This module

  * reads the custom types that places use (only those in use: a type that no place has any more is not read), and joins the ways of writing one type
    into one (`type_key` is the key that two writings share; the writing that is used for a new place is the tidiest and most used of them);
  * tells, by a vocabulary of synonyms in several languages (data/type-vocabulary.json, and the user's own file), which of them is a province, an empire,
    a district, a canton, a settlement ...;
  * gives the conventions of the tree in the form of the file type-conventions.json, so that kinds.py can merge them with the file of the user,
    which always comes first.

The engine does not need Gramps for any of this: it reads the `Tree` (dicts)."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import collections
import copy
import functools
import os
import re
import unicodedata

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import data as datalib
from .words import fold

ROLES = ("province", "empire", "monarchy", "district", "canton", "settlement")
SINGLE = ("province", "empire", "monarchy")                  # roles that the conventions hold as one type
_APOSTROPHES = dict.fromkeys("\u2019\u2018\u02bc\u02b9`\u00b4\u05f3\u2032", "'")
_QUOTES = dict.fromkeys("\u201c\u201d\u201e\u05f4\u00ab\u00bb", '"')
_DASHES = dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212\u05be-_", " ")
_LETTERS = {"\u0142": "l", "\u00f8": "o", "\u0111": "d", "\u0131": "i"}
_TABLE = str.maketrans({**_APOSTROPHES, **_QUOTES, **_DASHES, **_LETTERS})


@functools.lru_cache(maxsize=65536)
def type_key(text):
    """The key that every writing of one custom type shares: ' village', 'Village ', 'VILLAGE', 'vil\u00adlage' and 'village' (with a no-break space or a mark of
    direction), 'tat-mahoz', 'tat mahoz' and 'tat\u05beMahoz' all have the same key. Empty for a text with nothing in it."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = re.sub(r"\s+", " ", text)                                    # every kind of space (no-break, tab, line break) is one space
    text = "".join(c for c in text if unicodedata.category(c) not in ("Cf", "Cc", "Mn"))    # marks of direction, zero-width, soft hyphen, points, accents
    text = text.translate(_TABLE).casefold()
    return re.sub(r" +", " ", text).strip(" .,;:")


def same_type_text(a, b):
    """Do two texts of custom types write the same type? (Two empty texts do not: nothing is written.)"""
    key = type_key(a)
    return bool(key) and key == type_key(b)


def in_types(text, texts):
    """Is `text` one of the types in `texts`, by their keys?"""
    key = type_key(text)
    return bool(key) and any(key == type_key(t) for t in texts or ())


def tidy(text):
    """Is a writing free of what is surely a slip: a space before or after, two spaces, a no-break space, an invisible mark?"""
    text = str(text or "")
    return text == re.sub(r" +", " ", text).strip() and not any(unicodedata.category(c) in ("Cf", "Cc") or (c.isspace() and c != " ") for c in text)


def census(tree):
    """The custom types that places use, as writings: {text as written: number of places}. A place with a type of Gramps, or with no type, is not counted."""
    counts = collections.Counter()
    for place in tree.places.values():
        kind = place.get("type") or {}
        text = kind.get("string") or ""
        if kind.get("value") == 0 and type_key(text):
            counts[text] += 1
    return counts


def pick_writing(variants):
    """The writing of one type to use for a new place: a tidy one before a writing with slips, then the most used, then the one that sorts first."""
    return sorted(variants, key=lambda w: (not tidy(w), -variants[w], w))[0]


def unify(counts):
    """The writings joined by their key: {key: {\"name\": the writing to use, \"variants\": {writing: places}, \"count\": places}}."""
    by_key = collections.defaultdict(dict)
    for text, n in counts.items():
        by_key[type_key(text)][text] = n
    return {key: {"name": pick_writing(variants), "variants": dict(variants), "count": sum(variants.values())} for key, variants in by_key.items()}


def within_one_edit(a, b):
    """Are two texts one edit apart: one letter changed, added, left out, or two neighbouring letters swapped? (Equal texts are not.)"""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    i = 0
    while i < len(short) and short[i] == long_[i]:
        i += 1
    return short[i:] == long_[i + 1:]


def possible_duplicates(types, known=(), shortest=5):
    """The types of the tree whose keys are one edit apart (Cemetery, Cemetary): [{"a", "a_count", "b", "b_count"}], the most used first. Only a report: a typo
    and a real difference look the same to a program. Keys shorter than `shortest` letters (Town, Tower) and two words that the vocabulary knows (`known`: keys)
    are not compared."""
    keys = sorted((t for t in types if len(t["key"]) >= shortest), key=lambda t: t["key"])
    found = []
    for i, first in enumerate(keys):
        for second in keys[i + 1:]:
            if within_one_edit(first["key"], second["key"]) and not (first["key"] in known and second["key"] in known):
                found.append({"a": first["name"], "a_count": first["count"], "b": second["name"], "b_count": second["count"]})
    return sorted(found, key=lambda d: (-(d["a_count"] + d["b_count"]), d["a"], d["b"]))


def vocabulary_files():
    """The vocabulary that comes with the addon, then the user's own (PLACECOMPLETER_VOCABULARY, else ~/.config/placecompleter/type-vocabulary.json)."""
    files = [os.path.join(datalib.DATA_DIR, "type-vocabulary.json")]
    for candidate in (os.environ.get("PLACECOMPLETER_VOCABULARY", ""), os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "type-vocabulary.json")):
        if candidate and os.path.isfile(candidate):
            files.append(candidate)
            break
    return files


def load_vocabulary(files=None):
    """The groups of synonyms: [{\"role\", \"words\" (as written), \"keys\" (their keys)}], the ones that come with the addon first. A group with an unknown role, or with no
    words, is ignored."""
    groups = []
    for path in files if files is not None else vocabulary_files():
        data = datalib.load_path(path, {})
        for group in data.get("groups") if isinstance(data, dict) and isinstance(data.get("groups"), list) else []:
            if not isinstance(group, dict) or group.get("role") not in ROLES or not isinstance(group.get("words"), list):
                continue
            words = [str(w) for w in group["words"] if type_key(w)]
            builtin = group.get("builtin")
            builtin = builtin if isinstance(builtin, int) and not isinstance(builtin, bool) and 1 <= builtin <= 20 else 0       # the type of Gramps that the engine gives these words
            if words:
                groups.append({"role": group["role"], "words": words, "keys": {type_key(w) for w in words}, "builtin": builtin})
    return groups


def learn(tree, vocabulary=None):
    """What the tree says about its own types: {\"types\": [one entry for each type in use, the most used first: key, name, variants, count, role (or \"\")],
    \"conventions\": {province, empire, monarchy, district, settlements, rules}} (the shape of type-conventions.json; an empty entry knows nothing).

    The type of a province, an empire or a monarchy is the most used type of that role. A district or a settlement type is listed. A rule (an answer
    that calls a level by a word of a group gets the type of the tree) is made for a group only when ONE type of the tree matches it: two types that fit one
    group (two kinds of district) are a distinction that only the owner can decide, and it stays in the file of the user. A group whose words the engine gives a
    type of Gramps (district: 12) makes a rule only when the type of the tree is used by MORE places than that type of Gramps: one custom District among forty
    Districts of Gramps does not turn every new district into a custom one (the rule that is left out is in "skipped"). "duplicates" are the types that are one
    letter apart: told, never joined."""
    groups = load_vocabulary() if vocabulary is None else vocabulary
    types = unify(census(tree))
    for key, found in types.items():
        found["key"] = key
        found["group"] = next((g for g in groups if key in g["keys"]), None)
        found["role"] = found["group"]["role"] if found["group"] else ""
    ordered = sorted(types.values(), key=lambda t: (-t["count"], t["key"]))
    conventions = {"province": "", "empire": "", "monarchy": "", "district": [], "settlements": [], "rules": []}
    for role in SINGLE:
        match = [t for t in ordered if t["role"] == role]
        conventions[role] = match[0]["name"] if match else ""
    conventions["district"] = [t["name"] for t in ordered if t["role"] == "district"]
    conventions["settlements"] = [t["name"] for t in ordered if t["role"] == "settlement"]
    skipped = []
    values = collections.Counter((place.get("type") or {}).get("value") for place in tree.places.values())
    for group in groups:
        if group["role"] not in ("district", "canton"):
            continue
        match = [t for t in ordered if t["group"] is group]
        if len(match) != 1:
            continue
        if group["builtin"] and match[0]["count"] <= values[group["builtin"]]:
            skipped.append({"name": match[0]["name"], "count": match[0]["count"], "builtin": group["builtin"], "builtin_count": values[group["builtin"]]})
            continue
        conventions["rules"].append({"words": [fold(w) for w in group["words"]], "value": 0, "string": match[0]["name"]})
    known = set().union(*[g["keys"] for g in groups]) if groups else set()
    duplicates = possible_duplicates(ordered, known)
    for t in ordered:
        del t["group"]
    return {"types": ordered, "conventions": conventions, "skipped": skipped, "duplicates": duplicates}


def merge(base, learned):
    """The conventions of the user's file (`base`) and what was learned from the tree: the file always comes first. A type of a province, an empire or a monarchy
    that the file gives stays; a district or a settlement type is added to the lists unless the file has it (by its key); a rule is added after the rules of
    the file unless one of its words is already in a rule of the file. Neither argument is changed."""
    out = copy.deepcopy(base)
    for role in SINGLE:
        if not out.get(role) and learned.get(role):
            out[role] = learned[role]
    for role in ("district", "settlements"):
        have = list(out.get(role) or [])
        out[role] = have + [t for t in learned.get(role, []) if not in_types(t, have)]
    taken = {w for rule in out.get("rules") or [] for w in rule.get("words", [])}
    out["rules"] = list(out.get("rules") or []) + [r for r in learned.get("rules", []) if not taken & set(r["words"])]
    return out
