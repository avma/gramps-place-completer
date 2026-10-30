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
"""Finding the place of the question in the tree: the places that have its name, the one that is the place of the answer (ID1, LV3), and the web links that are offered for it.
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
from . import links as linklib
from . import names as namelib
from . import rules
from .wikidata import km, tree_coordinates
from .kinds import TREE_TYPES, _AREA_TYPES, _SETTLEMENT_TYPES
from .matching import SAME_PLACE_KM
from .screen import _need
from .words import fold


def find_place(a):
    """The place of the question in the tree: the places that have its name, the one that is the place of the answer, and the web links offered for it."""
    languages, name, out = a.languages, a.name, a.out
    rec, rows, tree = a.rec, a.rows, a.tree
    # does the place exist already?
    name_plain = namelib.plain_name(name, rec["type_value"], rec["type_text"])
    sought = {fold(name), fold(name_plain)}

    def known(handle):
        kind = tree.places[handle]["type"] or {}
        out = set()
        for n in tree.all_names(handle):
            out |= {fold(n.get("value")), fold(namelib.plain_name(n.get("value"), kind.get("value"), kind.get("string", "")))}
        return out
    existing = [h for h in tree.places if sought & known(h)]
    if rules.on("LV3") and len(existing) > 1 and rec["type_value"] in _SETTLEMENT_TYPES:
        # the answer is a settlement: a canton, a province or another area of the tree that has the same name is not the place of the question (Blagnac, its canton)
        def is_area(h):
            held = tree.places[h]["type"] or {}
            return held.get("value") in _AREA_TYPES or (held.get("value") == 0 and bool(held.get("string")) and held.get("string") not in TREE_TYPES.get("settlements", ()))
        settlements = [h for h in existing if not is_area(h)]
        if settlements:
            existing = settlements
    if rules.on("ID1") and existing and rec["coordinates"]:
        # ID1: a place of the tree with the name of the answer, and coordinates, that is far from the coordinates of the answer is ANOTHER place with the
        # same name (Johnston in Iowa and Johnston in Rhode Island are 1,600 km apart; the names of the places above are not compared: one place has
        # many names in the languages and the periods). A place with no coordinates cannot be compared and is taken as before.
        near, far = [], []
        for h in existing:
            here = tree_coordinates(tree.places[h])
            (far if here and km(here, rec["coordinates"]) > SAME_PLACE_KM else near).append(h)
        if far:
            _need(out, "tree contains a place named «%s» (%s) located %.0f km from query location; treated as a distinct place and "
                       "left unchanged",
                  name, "; ".join(tree.label(h) for h in far[:3]), km(tree_coordinates(tree.places[far[0]]), rec["coordinates"]))
            existing = near
    if len(existing) == 1:
        out["mode"] = "existing"
        here = tree_coordinates(tree.places[existing[0]])
        if here and rec["coordinates"]:
            apart = km(here, rec["coordinates"])
            for r in rows:
                if r["field"] == "coordinates":
                    r["value"] += "   (the tree has %s, %s: %.1f km apart, %s)" % (here[0], here[1], apart,
                                                                              "kept" if apart < 3 else "DIFFERENT: check")
    elif len(existing) > 1:
        _need(out, "%d places in the tree match this name: select target place", len(existing))
    out["similar"] = [{"handle": h, "label": tree.label(h), "reasons": ["same name"]} for h in existing]
    child = existing[0] if len(existing) == 1 else "new:ai-%s" % re.sub(r"\W+", "", fold(name))
    link_offer, _link_left_out = linklib.select_links([x["url"] for x in rec["sources"]], tree.places[child]["urls"] if child in tree.places else (),
                                                      languages or ("en",))                  # LK1-LK5: which web links of the answer may become links of the place
    if not rules.on("LK"):
        link_offer = []
    out["child"] = child
    a.keep(locals(), "child", "link_offer", "name_plain")
