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
"""In-memory model of the places and events of a Gramps tree.

Loaded from the JSON that Gramps keeps in its SQLite database, opened
read-only. Persons, notes and everything else are never read.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import copy
import json
import pathlib
import sqlite3


class Tree:
    def __init__(self, places, events):
        self.places = places      # handle -> place dict
        self.events = events      # list of event dicts (only events with a place)

    @staticmethod
    def _place(handle, o):
        return {"handle": handle, "id": o.get("gramps_id"),
                "type": o.get("place_type") or {},
                "name": o.get("name") or {},
                "alt_names": o.get("alt_names") or [],
                "refs": o.get("placeref_list") or [],
                "urls": [u.get("path") for u in (o.get("urls") or [])],
                "lat": o.get("lat") or "", "lon": o.get("long") or ""}

    @staticmethod
    def _event(handle, o):
        return {"handle": handle, "id": o.get("gramps_id"), "type": o.get("type") or {},
                "date": o.get("date") or {}, "place": o["place"]}

    @classmethod
    def from_sqlite(cls, path):
        uri = pathlib.Path(path).resolve().as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True)
        places, events = {}, []
        try:
            for handle, raw in con.execute("SELECT handle, json_data FROM place"):
                places[handle] = cls._place(handle, json.loads(raw))
            for handle, raw in con.execute("SELECT handle, json_data FROM event"):
                o = json.loads(raw)
                if o.get("place"):
                    events.append(cls._event(handle, o))
        finally:
            con.close()
        return cls(places, events)

    @classmethod
    def from_db(cls, db):
        """The same tree, read through the API of an open Gramps database (what a tool inside Gramps has)."""
        from gramps.gen.lib.json_utils import object_to_dict
        places, events = {}, []
        for place in db.iter_places():
            places[place.get_handle()] = cls._place(place.get_handle(), object_to_dict(place))
        for event in db.iter_events():
            o = object_to_dict(event)
            if o.get("place"):
                events.append(cls._event(event.get_handle(), o))
        return cls(places, events)

    def clone(self):
        """A copy whose places can be edited (events are shared, they never change)."""
        return Tree(copy.deepcopy(self.places), self.events)

    def name_of(self, handle):
        place = self.places.get(handle)
        return (place["name"].get("value") or "?") if place else "?"

    def label(self, handle):
        place = self.places.get(handle)
        return "%s [%s]" % (self.name_of(handle), place["id"]) if place else "?"

    def all_names(self, handle):
        place = self.places[handle]
        return [place["name"]] + list(place["alt_names"])
