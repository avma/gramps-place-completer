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
"""The rules of the analysis, each with an id and a switch (docs/ANALYZER_RULES.md, docs/RULES_REVIEW.md).

A rule can be switched off for an experiment: tools/replay_answers.py --ablate switches them off one at a time over the saved answers and says which
of them changes anything. Nothing here is for a user to set: every rule is on, and the switch is read from the environment variable
PLACECOMPLETER_RULES_OFF (ids separated by commas) or set by the tests and the tool with disabled(). A few rules are OFF by default
(DEFAULT_OFF); PLACECOMPLETER_RULES_ON, or enabled(), switches them on.

Two kinds of rule can be switched:
  behavior  changes what is proposed or written; it is switched in the code, at the place where the rule acts;
  message   a note that the analysis puts on the screen; it is switched in one place (ingest._need and table._note): off, the note is not made, and
            nothing that is proposed changes.
The rules that are not switchable yet are in the list too (switchable False), so that the list of the rules is complete.
Groups: A safety of the tree, B making up for the answer, C correcting what the tree has, D more than the first idea, I information from the answer,
N noise (a note that changes nothing).
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import collections
import contextlib
import os

# (id, group, what it does, where the effect is measured: "replay" over the saved answers, "write" by writing to a database, "network" by asking Wikidata)
BEHAVIOR = [
    ("ST3", "B", "one bare word of the closed list decides the type of the place; the local term after it cannot change it", "replay"),
    ("ST6", "C", "a settlement type of the tree is proposed to change when the answer gives another size class", "replay"),
    ("LV1", "B", "a structure that overlaps the levels (an intercommunality) is not a level of the chain", "replay"),
    ("LV2", "B", "a level with the name of the place, or of another level, is a place of its own", "replay"),
    ("LV3", "C", "an area of the tree with the name of a settlement is not a candidate for it", "replay"),
    ("LK", "D", "web links of Wikipedia, Wikidata and official sites are offered for the place", "replay"),
    ("WL", "D", "the Wikidata item and its articles become links of the main place", "network"),
    ("CT2", "D", "at most three new citations per place in one run, the strongest first", "write"),
    ("CT4", "D", "a tourism or commercial site is cited with confidence Low at most", "write"),
    ("CT5", "D", "a citation goes to the place that its source is about", "write"),
    ("NP1", "B", "the years of the place's own line end its name only when a later name is given", "replay"),
    ("NP3", "B", "a name starts when the state that ruled then began", "replay"),
    ("NP5", "B", "a name of a level of the tree that has no period gets the period that the answer gives it", "replay"),
    ("T1", "A", "a place is not inside itself, and there is no loop in the hierarchy", "replay"),
    ("T2", "A", "the levels of the types (T2-T4): the parent is higher, no place inside a place of its own type, settlements on one level", "replay"),
    ("C3", "C", "a link that exists with another period: the period of the answer (a widening, or a fix of a period that ends before it starts)", "replay"),
    ("C4", "C", "a link to another parent that is not wrong: the new link is placed before it", "replay"),
    ("C5", "C", "a link of the tree that the rules show to be wrong is offered as a disconnect", "replay"),
    ("C6", "C", "a direct link to a higher place that the chain makes redundant: a disconnect, or a cut to its own years (C6, C7)", "replay"),
    ("C8", "A", "a level that breaks the rules of the nesting is left out of the chain", "replay"),
    ("ID1", "A", "a place of the tree with the name of the answer, and coordinates, that is more than 30 km from the coordinates of the answer is another place", "replay"),
    ("NL", "B", "an existing name of a level that has no language gets the language of the answer", "replay"),
]

# off unless PLACECOMPLETER_RULES_ON names them (or a test or the tool switches them on): the periods and the languages of the names of the LEVELS are
# offered by the rules NP5 and NL, which a user did not ask for; and NP3 gives the name of a place a period that starts with the state that ruled
# (from 1958 for France): in Gramps a name with a period and no other name gives a "?" for an event that is earlier, so a name that has only one
# period is worse than a name with none. The name of the place itself keeps its language.
DEFAULT_OFF = {"NP3", "NP5", "NL"}

# not switchable yet (the code of these rules is not in one place): listed so that the list is complete
FIXED = [
    ("P0", "A", "what exists is changed one by one, never by itself"),
    ("C1-C2", "A", "the chain of the answer is made and linked; a link that is as the answer says is left alone"),
    ("C9", "A", "a level that the user unchecked is not touched"),
]

# (id, group, the beginning of the text of the note, what the note says): every note of the analysis is here (a test checks it)
MESSAGES = [
    ("M01", "I", "response lacks place nam", "the answer has no name: nothing is proposed"),
    ("M02", "A", "place name is ambiguous.", "the name is ambiguous: choose one (command line)"),
    ("M03", "A", "  %d. %s  (", "a candidate of an ambiguous name (command line)"),
    ("M04", "A", "response indicates ambiguous place name: %s", "the name is ambiguous: what the answer says"),
    ("M05", "A", "%d places in the tree ma", "several places of the tree have the name: choose which"),
    ("M14", "B", "response omits administr", "the answer lacks a level that the country has"),
    ("M15", "A", "%s excluded per user selection", "a level left out at the user's request"),
    ("M16", "A", "ACTION REQUIRED: %s matches existing p", "a level could be one of several places: the window asks"),
    ("M17", "A", "administrative level %d (%s) excluded per user selection", "a level skipped at the user's request"),
    ("M18", "B", "%s is identical to %s (l", "the answer lists the municipality as a container of the place"),
    ("M19", "A", "ACTION REQUIRED: %s matches existing %s", "a level could be one of several places, one holds a level of the tree"),
    ("M21", "B", "%s is not historically valid on %s according to defined time boundaries", "a level is not valid on the date"),
    ("M22", "B", "level «%s» (%s) matches ", "a level has the name of the place: it is a place of its own (LV2)"),
    ("M23", "B", "response defines period ", "the answer gives years for the name of the place itself"),
    ("M25", "B", "name «%s» applies from %s", "a name period inferred from the start of the state"),
    ("M28", "A", "%s -> %s excluded from h", "a level breaks a rule of the nesting: left out"),
    ("M29", "C", "CONFLICT: in the tree, %s", "the tree and the answer disagree about the parent"),
    ("M30", "C", "%s is also linked to %s, w", "a link to a place that looks the same: merge them"),
    ("M31", "C", "%s is also linked directly to %s (p", "a direct link to a higher place covers a link in the chain (before)"),
    ("M32", "C", "%s is also linked directly to %s (a", "a direct link to a higher place covers a link in the chain (after)"),
    ("M33", "C", "%s is also linked directly to %s (listed before the link to %s): it applies", "a direct link to a higher place can be kept for earlier years"),
    ("M34", "C", "%s is also linked directly to %s (listed after the link to %s): it applies", "a direct link to a higher place can be kept for later years"),
    ("M35", "C", "%s -> %s: existing tree ", "a link of the tree with a period that ends before it starts"),
    ("M36", "C", "%s -> %s: the response specifies %s-%s,", "the period of the answer differs: another link covers the years between"),
    ("M37", "C", "%s -> %s: the response specifies %s-%s ", "the period of the answer differs: years between are not covered"),
    ("M38", "C", "%s is also linked to %s, a", "a link to another parent that is not wrong: both are kept"),
    ("M39", "C", "These links already exis", "the links already exist"),
    ("M40", "B", "name «%s» end date (%s) ", "a name that ends in the tree as the place does"),
    ("M42", "D", "response identifies pote", "sites that may be official: not added as links"),
    ("M43", "B", "hierarchy chain terminat", "the chain ends at the state: add the country"),
    ("M46", "D", "response references doma", "a site is named and not the address of a page"),
    ("M47", "B", "administrative level %d (%s) lacks type classification in response", "a level of the table has no type"),
    ("M48", "B", "response specifies name ", "the year from which the name is used: not written"),
    ("M49", "A", "response lists alternati", "other places with this name: ask again with the region"),
    ("M51", "C", "the type of %s in the tree is", "the place of the tree has a type that is not a settlement: not changed (it may be another place of the same name)"),
    ("M52", "B", "the type «%s» is not used by any place of your tree yet", "a type of your own that no place of the tree uses yet: approving the place makes it a new type (a note: nothing changes)"),
    ("M50", "A", "tree contains a place na", "the tree has a place of this name that is far from the one of the answer: another place, not changed (ID1)"),
]

_forced = []                                                   # ids switched off by disabled() (a stack: the tests and the tool)
_forced_on = []                                                # ids switched on by enabled() (a stack)
_recorders = []                                                # counters that record the notes that are made (a stack: the tool)


def _from_environment():
    return {i.strip() for i in os.environ.get("PLACECOMPLETER_RULES_OFF", "").split(",") if i.strip()}


def _on_from_environment():
    return {i.strip() for i in os.environ.get("PLACECOMPLETER_RULES_ON", "").split(",") if i.strip()}


def off_ids():
    """The ids of the rules that are switched off now: those that are off by default (unless switched on), and those switched off."""
    switched_on = _on_from_environment()
    for ids in _forced_on:
        switched_on |= ids
    out = (DEFAULT_OFF - switched_on) | _from_environment()
    for ids in _forced:
        out |= ids
    return out


def on(rule_id):
    """Is the rule on? (Every rule is, unless a test or the tool switched it off.)"""
    return rule_id not in off_ids()


@contextlib.contextmanager
def disabled(*rule_ids):
    """Switch the rules off inside a with block."""
    known = {r[0] for r in BEHAVIOR} | {m[0] for m in MESSAGES}
    unknown = set(rule_ids) - known
    if unknown:
        raise ValueError("no such rule to switch: %s" % ", ".join(sorted(unknown)))
    _forced.append(set(rule_ids))
    try:
        yield
    finally:
        _forced.pop()


@contextlib.contextmanager
def enabled(*rule_ids):
    """Switch the rules that are off by default ON inside a with block (an experiment, a test)."""
    unknown = set(rule_ids) - {r[0] for r in BEHAVIOR}
    if unknown:
        raise ValueError("no such rule to switch: %s" % ", ".join(sorted(unknown)))
    _forced_on.append(set(rule_ids))
    try:
        yield
    finally:
        _forced_on.pop()


@contextlib.contextmanager
def recording():
    """Count, inside a with block, which message rules wrote a note: {id: how many notes}. (The replay uses it to know which rules fired.)"""
    counter = collections.Counter()
    _recorders.append(counter)
    try:
        yield counter
    finally:
        _recorders.pop()


def record(rule_id):
    if rule_id:
        for counter in _recorders:
            counter[rule_id] += 1


WARNING_IDS = {"M29", "M43"}                                   # the notes that are warnings (red): a conflict with the tree, a chain that ends without a country


def warning_starts():
    """The beginnings (up to the first %) of the notes that are warnings: the program reads them from the registry, so that a change of the English
    of a note changes them too."""
    return tuple(start.split("%", 1)[0] for rid, _g, start, _t in MESSAGES if rid in WARNING_IDS)


def message_id(text):
    """The id of the rule that writes a note (the note begins with the text of the rule), or None."""
    for rule_id, _group, start, _title in MESSAGES:
        if text.startswith(start):
            return rule_id
    return None


def message_on(text):
    """Is the note to be made? (it is counted when a recording is on and the rule is on)"""
    rule_id = message_id(text)
    if rule_id is not None and not on(rule_id):
        return False
    record(rule_id)
    return True


def all_rules():
    """Every rule, switchable or not: [{id, group, kind, switchable, title, measured}]."""
    rules = [{"id": i, "group": g, "kind": "behavior", "switchable": True, "title": t, "measured": m, "default_off": i in DEFAULT_OFF} for i, g, t, m in BEHAVIOR]
    rules += [{"id": i, "group": g, "kind": "message", "switchable": True, "title": t, "measured": "replay", "default_off": False} for i, g, _s, t in MESSAGES]
    rules += [{"id": i, "group": g, "kind": "fixed", "switchable": False, "title": t, "measured": "not yet", "default_off": False} for i, g, t in FIXED]
    return rules
