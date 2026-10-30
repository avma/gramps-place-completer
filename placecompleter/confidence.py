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
"""How far the program can rely on a proposed change, in four words that say only what the program really knows.

  Confirmed  independent data agrees: Wikidata, a regional pack, or the tree itself.
  Reported   the answer of the AI states it and cites a page (a full link) for it, and does not doubt it.
  Inferred   worked out by the program from other data, by a rule (a name given the period of its unit, a language from the state, a level put
             in between): to be checked.
  Unsure     there is a sign of doubt: the answer says it is NOT SURE about the field, or contradicts itself, or is identical to an answer
             saved for another date, or states it without citing any page.

The program cannot tell a fact from an invention: it can only tell what supports a change and where there is doubt. A change made of several
steps has the level of its least sure step. The same signs give the confidence of the citation that is written with the change (citations.py).
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
from .i18n import _ as tr

CONFIRMED, REPORTED, INFERRED, UNSURE = "confirmed", "reported", "inferred", "unsure"
ORDER = (CONFIRMED, REPORTED, INFERRED, UNSURE)                       # from the surest to the least sure
RULE_KINDS = {"set-name-date", "set-name-language", "end-link", "rename-place"}      # changes that the program works out by a rule
# the fields of the answer (as the answer names them) that a change rests on, when its evidence does not name them
KIND_FIELDS = {"set-coordinates": {"COORDINATES"}, "set-type": {"SETTLEMENT_TYPE_ON_DATE"},
               "add-place": {"CONTAINERS"}, "add-link": {"CONTAINERS"}, "set-link": {"CONTAINERS"}, "move-link": {"CONTAINERS"}, "remove-link": {"CONTAINERS"}, "change-type": {"CONTAINERS"}, "end-link": {"CONTAINERS"},
               "add-url": {"SOURCES"}, "add-name": {"PLACE_NAME_ON_DATE", "OTHER_NAMES"}, "set-name-date": {"PLACE_NAME_ON_DATE", "OTHER_NAMES"},
               "set-name-language": {"PLACE_NAME_ON_DATE", "OTHER_NAMES"}, "rename-place": {"PLACE_NAME_ON_DATE"}}
_LABEL = re.compile(r"^[A-Z][A-Z_]{2,}$")


def label(level):
    """The word of the level, as the window shows it."""
    return {CONFIRMED: tr("Confirmed"), REPORTED: tr("Reported"), INFERRED: tr("Inferred"), UNSURE: tr("Unsure")}[level]


def explanation():
    """What the column means, for the tooltip of its title."""
    return tr("Confidence level rating for proposed changes:\nConfirmed: Verified by independent sources (Wikidata, regional "
              "pack, or existing tree data).\nReported: Stated directly in the AI response with a cited web source.\nInferred: "
              "Derived automatically by analyzing related data (requires user review).\nUnsure: AI indicated uncertainty, "
              "contradicted itself, or lacked citations.\nNote: Multi-step changes inherit the confidence level of their "
              "least-certain step.")


def fields_of(proposal):
    """The fields of the answer that a proposal rests on: those its evidence names, else those of its kind."""
    found = set()
    for item in proposal.get("evidence") or []:
        claim = item.get("claim")
        for part in ([claim] if isinstance(claim, str) else list(claim or [])):
            found |= {t for t in re.split(r"[,;\s]+", part or "") if _LABEL.match(t)}
    return found or set(proposal.get("fields") or KIND_FIELDS.get(proposal["kind"], ()))


def level_of(proposal, unsure=(), doubtful=False):
    """(level, why) of one proposal. unsure: the fields the answer says it is not sure about; doubtful: the answer contradicts itself or
    disagrees with a saved answer (the notes of the analysis say so)."""
    if (proposal.get("origin") or "") != "ai-answer":
        if proposal.get("basis") in ("evidence", "tree"):
            return CONFIRMED, tr("verified by independent sources (Wikidata, regional dataset, or existing tree)")
        return INFERRED, tr("derived automatically from related data; verify correctness")
    doubts = sorted(fields_of(proposal) & set(unsure))
    if doubts:
        return UNSURE, tr("the response indicated uncertainty about %s") % ", ".join(doubts)
    if doubtful:
        return UNSURE, tr("the response contains internal contradictions or conflicts with saved historical data")
    if proposal.get("inferred"):
        return INFERRED, tr("deduced automatically from existing place names and types in the tree; verify correctness")
    if proposal.get("refines") or proposal["kind"] in RULE_KINDS:
        return INFERRED, tr("deduced automatically from the AI response; verify correctness")
    if any((item.get("url") or "").strip() for item in proposal.get("evidence") or []):
        return REPORTED, tr("stated in the AI response with a supporting source citation")
    return UNSURE, tr("stated in the AI response without supporting web citations")


def of_steps(proposals, unsure=(), doubtful=False):
    """(level, why) of a change: that of its least sure step."""
    levels = [level_of(p, unsure, doubtful) for p in proposals]
    return max(levels, key=lambda item: ORDER.index(item[0])) if levels else (CONFIRMED, "")
