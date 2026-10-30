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
"""Coordinates from Wikidata for the places of an analysis.

A coordinate of Wikidata (property P625, deprecated statements dropped) is used when Wikidata knows ONE place of that name where the
answer says it is. When there are several or none, nothing is chosen here: the caller keeps what the answer said, and says so.
Only the names of places are sent to wikidata.org.
"""

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import complete, links as linklib, wikidata
from .i18n import _ as tr

RADIUS_KM = 50          # a Wikidata place farther than this from where the answer puts the place is another place of the same name
MARGIN = 3              # the best candidate must beat the next one by this much (see complete.candidates) if there is no distance to use


def lookup(client, name, region=None, near=None, languages=("en",), radius=RADIUS_KM, articles=()):
    """{'found': True, 'lat', 'lon', 'qid', 'label', 'url', 'km'} or {'found': False, 'reason': ...}.

    near: (lat, lon) where the answer (or the tree) puts the place, to tell it from others of the same name; km is the distance to it.
    articles: the Wikipedia languages of the user: when given, 'articles' is the list of the addresses of the articles that Wikidata lists for the item."""
    found = [c for c in complete.candidates(client, name, region, languages) if c["coordinates"]]
    if not found:
        return {"found": False, "reason": tr("No matching place with spatial coordinates found on Wikidata")}
    if near:
        close = [c for c in found if wikidata.km(near, c["coordinates"]) <= radius]
        if not close:
            return {"found": False, "reason": tr("matching Wikidata locations exceed the %d km distance threshold from the location returned in the answer") % radius}
        found = close
        found.sort(key=lambda c: (-c["score"], wikidata.km(near, c["coordinates"])))
        if len(found) > 1 and found[0]["score"] == found[1]["score"] and \
                wikidata.km(near, found[1]["coordinates"]) - wikidata.km(near, found[0]["coordinates"]) < 5:
            return {"found": False, "reason": tr("multiple nearby places match this name on Wikidata: %s") % ", ".join(c["qid"] for c in found[:4])}
    elif len(found) > 1 and found[0]["score"] - found[1]["score"] < MARGIN:
        return {"found": False, "reason": tr("multiple places match this name on Wikidata: %s") % ", ".join(c["qid"] for c in found[:4])}
    best = found[0]
    lat, lon = best["coordinates"]
    out = {"found": True, "lat": "%g" % lat, "lon": "%g" % lon, "qid": best["qid"], "label": best["label"],
           "url": "https://www.wikidata.org/wiki/%s" % best["qid"], "km": wikidata.km(near, best["coordinates"]) if near else None}
    if articles:
        try:                                                      # (a failure here must not lose the coordinates)
            out["articles"] = linklib.sitelink_urls(client.sitelinks(best["qid"], articles), articles)
        except Exception:
            out["articles"] = []
    return out


def lookup_many(client, targets, articles=()):
    """{key: lookup result} for the targets [{key, name, region, near, main}] (slow: the network; the window runs it in a thread).
    The articles of Wikipedia (the languages in `articles`) are asked for the target that is the main place only."""
    out = {}
    for t in targets:
        try:
            out[t["key"]] = lookup(client, t["name"], t.get("region"), t.get("near"), articles=articles if t.get("main") else ())
        except Exception as exc:                                  # one place failing must not lose the others
            out[t["key"]] = {"found": False, "reason": tr("Could not query Wikidata: %s") % exc}
    return out
