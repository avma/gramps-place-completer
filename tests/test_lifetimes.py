#!/usr/bin/env python3
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
"""A place that ceased to exist: its lifetime ends the links to it, a successor takes over.

The structure follows a real case of the user's tree (a Hungarian district abolished in
1920 whose town then belonged to a Romanian county).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import agent, gaps, packs, wikidata                  # noqa: E402
from placecompleter.dates import M_FROM, M_NONE, M_SPAN                  # noqa: E402
from placecompleter.model import Tree                                    # noqa: E402
from test_engine import D, EMPTY, event, place                           # noqa: E402


def tree():
    t = Tree({
        "k": place("k", "Szilagy County", 3),
        "j": place("j", "Szilagycsehi jaras", 0, name_date=D(M_SPAN, 1850, y2=1920), refs=[("k", EMPTY)]),
        "t": place("t", "Szilagycsehi", 4, refs=[("j", EMPTY)]),
        "r": place("r", "Salaj County", 3, name_date=D(M_FROM, 1920))},
        [event("e1", "t", D(M_NONE, 1900, 5, 1)), event("e2", "t", D(M_NONE, 1950, 5, 1))])
    return t


def pack(with_successor=True):
    p = {"schema": packs.SCHEMA, "pack": {"id": "life", "origin": "user"},
         "places": [{"key": "j", "names": ["Szilagycsehi jaras"], "lifetime": {"valid_from": "1850", "valid_to": "1920"}},
                    {"key": "t", "names": ["Szilagycsehi"]}, {"key": "r", "names": ["Salaj County"]}],
         "edges": []}
    if with_successor:
        p["edges"].append({"child": "t", "parent": "r", "valid_from": "1921", "valid_to": "2100", "origin": "user"})
    return packs.validate(p)


class LifetimeTests(unittest.TestCase):
    def shown(self, t, props):
        return {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}

    def test_the_district_shows_a_question_mark_after_it_ended(self):
        rows = gaps.analyse(tree())
        self.assertEqual({r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in rows}["E2"],
                         "Szilagycsehi, ?, Szilagy County")

    def test_ending_the_link_works_together_with_the_successor(self):
        t = tree()
        props, notes = packs.propose_from_pack(t, pack())
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "end-link"])
        end = next(p for p in props if p["kind"] == "end-link")
        self.assertEqual((end["child"], end["parent"], end["basis"]), ("t", "j", "evidence"))
        self.assertEqual(end["new"]["dateval"], [0, 0, 1850, False, 0, 0, 1920, False])
        shown = self.shown(t, props)
        self.assertEqual(shown["E1"], "Szilagycsehi, Szilagycsehi jaras, Szilagy County")
        self.assertEqual(shown["E2"], "Szilagycsehi, Salaj County")

    def test_ending_the_link_alone_is_explained_not_proposed(self):
        props, notes = packs.propose_from_pack(tree(), pack(with_successor=False))
        self.assertEqual(props, [])
        self.assertTrue(any("no parent at all instead of a '?'" in n for n in notes))

    def test_a_lifetime_needs_evidence_unless_it_is_the_users_own(self):
        bad = {"schema": packs.SCHEMA, "pack": {"id": "x"}, "edges": [],
               "places": [{"key": "j", "names": ["Szilagycsehi jaras"], "origin": "agent",
                           "lifetime": {"valid_from": "1850", "valid_to": "1920", "origin": "agent"}}]}
        with self.assertRaises(packs.PackError):
            packs.validate(bad)

    def test_the_request_asks_the_child_about_its_successor(self):
        t = tree()
        request = agent.build_request(t, gaps.analyse(t))
        by_id = {x["gramps_id"]: x for x in request["tasks"]}
        self.assertEqual(set(by_id), {"J", "T"})
        self.assertIn("lifetime", by_id["J"]["gaps"][0]["question"])
        self.assertEqual(by_id["T"]["gaps"][0]["cause"], "parent ended")
        self.assertIn("belong to afterwards", by_id["T"]["gaps"][0]["question"])

    def test_the_request_lists_the_places_a_link_may_point_at(self):
        t = tree()
        request = agent.build_request(t, gaps.analyse(t))
        names = {c["name"]: c for c in request["tree_places"]}
        self.assertIn("Salaj County", names)                       # an administrative level with no children yet
        self.assertIn("Szilagycsehi jaras", names)                 # a custom-typed place that has a child
        self.assertEqual(names["Szilagycsehi jaras"]["children"], 1)
        self.assertNotIn("Szilagycsehi", names)                    # a town without anything under it is not a parent candidate
        self.assertEqual(names["Salaj County"]["names"][0]["language"], "")

    def test_addresses_are_left_out_of_the_request_by_default(self):
        t = tree()
        t.places["a"] = place("a", "Strada Andrei Mocioni 3", 7, name_date=D(M_FROM, 1990), refs=[("t", EMPTY)])
        t.events.append(event("ea", "a", D(M_NONE, 1950, 5, 1)))
        rows = gaps.analyse(t)
        self.assertIn("A", {x["gramps_id"] for x in agent.build_request(t, rows, skip_addresses=False)["tasks"]})
        request = agent.build_request(t, rows)
        self.assertNotIn("A", {x["gramps_id"] for x in request["tasks"]})
        self.assertEqual(request["skipped_addresses"], 1)

    def test_the_successor_task_of_a_place_that_ended_joins_beyond_the_limit(self):
        t = tree()
        t.events += [event("j%d" % k, "j", D(M_NONE, 1950 + k, 5, 1)) for k in range(5)]      # the district itself is busiest
        for i in range(3):
            h = "x%d" % i
            t.places[h] = place(h, "Busy %d" % i, 4, name_date=D(M_FROM, 1990))
            t.events += [event("b%d_%d" % (i, k), h, D(M_NONE, 1950 + k, 5, 1)) for k in range(4)]
        request = agent.build_request(t, gaps.analyse(t), max_tasks=1)
        self.assertEqual([x["gramps_id"] for x in request["tasks"]], ["J", "T"])           # the pair, nothing else
        for task in request["tasks"]:
            self.assertFalse(any("_parent_handle" in g for g in task["gaps"]))

    def test_an_agent_answer_with_a_lifetime_and_a_successor_is_accepted(self):
        t = tree()
        request = agent.build_request(t, gaps.analyse(t))
        ids = {x["gramps_id"]: x["task_id"] for x in request["tasks"]}
        ev = [{"url": "https://example.org/jaras", "quote": "the district was abolished in 1920", "supports": "period",
               "source_kind": "gazetteer"}]
        response = {"schema": agent.RESPONSE_SCHEMA, "request_id": request["request_id"], "results": [
            {"task_id": ids["J"], "status": "found", "names": [], "unresolved": [],
             "lifetime": {"valid_from": "1850", "valid_to": "1920", "evidence": ev}},
            {"task_id": ids["T"], "status": "found", "names": [], "unresolved": [],
             "links": [{"parent_name": "Salaj County", "valid_from": "1921", "valid_to": "2100", "evidence": ev}]}]}
        result = agent.validate_response(response, request, t)
        self.assertEqual(result["rejected"], [])
        props, _ = packs.propose_from_pack(t, result["pack"])
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "end-link"])
        self.assertEqual(self.shown(t, props)["E2"], "Szilagycsehi, Salaj County")
        self.assertTrue(all(p["origin"] == "agent" for p in props))

    def test_a_place_that_continues_ends_no_link(self):
        t = tree()
        request = agent.build_request(t, gaps.analyse(t))
        ids = {x["gramps_id"]: x["task_id"] for x in request["tasks"]}
        ev = [{"url": "https://example.org/x", "quote": "it went on", "supports": "period", "source_kind": "other"}]
        response = {"schema": agent.RESPONSE_SCHEMA, "request_id": request["request_id"], "results": [
            {"task_id": ids["J"], "lifetime": {"valid_from": "1850", "valid_to": None, "continues": True, "evidence": ev}}]}
        result = agent.validate_response(response, request, t)
        self.assertIsNone(result["pack"])
        self.assertTrue(any("continues to exist" in n for n in result["notes"]))
        response["results"][0]["lifetime"].pop("continues")
        self.assertIn("valid_to is required", " ".join(r for x in agent.validate_response(response, request, t)["rejected"] for r in x["reasons"]))

    def test_wikidata_never_looks_an_address_up(self):
        calls = []
        c = wikidata.Client(fetch=lambda url: calls.append(url) or {"search": []}, pause=0)
        street = place("s", "Strada Andrei Mocioni 3", 7)
        t = Tree({"s": street}, [event("e", "s", D(M_NONE, 1900))])
        pack_, notes = wikidata.build_pack(t, ["s"], c)
        self.assertEqual(calls, [])
        self.assertTrue(any("an address, not looked up" in n for n in notes))

    def test_a_dissolution_in_wikidata_becomes_a_lifetime(self):
        c = wikidata.Client(cache_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json"))
        import urllib.parse
        url = "%s?action=wbsearchentities&search=%s&language=en&limit=5&format=json" % (wikidata.API, urllib.parse.quote("Austrian Empire"))
        c.answers[url] = {"search": [{"id": "Q131964"}]}
        t = Tree({"e": place("e", "Austrian Empire", 0)}, [])
        pack_, _ = wikidata.build_pack(t, ["e"], c)
        life = pack_["places"][0]["lifetime"]
        self.assertEqual((life["valid_from"], life["valid_to"], life["origin"]), ("1804-08-11", "1867-06-08", "wikidata"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
