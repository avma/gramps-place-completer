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
"""What the screen of the analysis shows: the notes, the label of a place, and the preview of what Gramps would display.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import gaps
from . import rules
from .i18n import _ as tr
from .complete import parse_date
from .dates import is_empty


def _need(out, msgid, *args):
    """A note for the user: in English in out["needs"] (the tests, the command line and the classification of its importance read that) and in
    the language of the window in out["needs_local"] (the same place in the list)."""
    if not rules.message_on(msgid):                                          # the rule of this note is switched off (placecompleter/rules.py)
        return
    values = args[0] if len(args) == 1 and isinstance(args[0], dict) else args
    out["needs"].append(msgid % values if args else msgid)
    out["needs_local"].append(tr(msgid) % values if args else tr(msgid))


def preview_for(tree, proposals, child, date_text, about=None):
    """What Gramps would display for an event on that date at the place, once these proposals are written: (names, how the chain ends)."""
    date, _sv = parse_date(date_text)
    trial = gaps.apply(tree, proposals)
    trial.events = list(tree.events) + [{"handle": "synthetic", "id": "NEW", "type": {}, "date": date, "place": child}]
    rows = [r for r in gaps.analyse(trial, about) if r["event"]["handle"] == "synthetic"]
    return (rows[0]["chain"]["names"], rows[0]["chain"]["end"]) if rows else ([], None)


def _lbl(tree, handle):
    return tree.label(handle) if handle in tree.places else str(handle)


def finish(a):
    """The proposals made into the screen: nothing is selected for the user, the units, the chain, the preview."""
    about, child, date_text = a.about, a.child, a.date_text
    out, proposals, tree = a.out, a.proposals, a.tree
    units = a.units
    for q in proposals:                                                       # P0: a change to data that exists is chosen one by one, never by itself
        if q["kind"] in ("rename-place", "set-link", "remove-link", "move-link", "change-type") or (q["kind"] == "set-name-date" and not is_empty(q.get("old"))):
            q["existing"] = True
    out["proposals"] = proposals
    out["units"] = [{"name": u["mention"]["name"], "type": u["mention"]["type"], "handle": u.get("handle"), "key": u.get("key")} for u in units]
    if units:
        top = units[-1]
        in_tree = top.get("handle")
        is_state = (tree.places[in_tree]["type"].get("value") == 2 and not tree.places[in_tree]["refs"]) if in_tree else \
            top["mention"]["type"].lower().strip() == "state"
        if is_state:
            _need(out, "hierarchy chain terminates at state «%s» without national container; please attach sovereign country entity", top["mention"]["name"])
    # what Gramps would display
    out["preview"], out["preview_end"] = preview_for(tree, proposals, child, date_text, about)
