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
"""Tests of the agent loop: request, strict validation of the answer, and simulation."""
import contextlib
import copy
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import agent, cli, gaps, packs                       # noqa: E402
from placecompleter.dates import M_FROM, M_NONE                          # noqa: E402
from test_engine import D, EMPTY, bajmok_tree, event, place              # noqa: E402


def tree():
    t = bajmok_tree([])
    t.places["v"] = place("v", "Berechiu", 16, name_date=D(M_FROM, 1920), lang="ro", refs=[("hun", EMPTY)])
    t.places["yug"] = place("yug", "Yugoslavia", 1)
    t.events = [event("n1", "v", D(M_NONE, 1900, 5, 1)), event("n2", "v", D(M_NONE, 1950, 5, 1)),
                event("b1", "baj", D(M_NONE, 1935, 5, 1)), event("b2", "baj", D(M_NONE, 1905, 5, 1))]
    return t


def evidence(quote="the village was called Alsoberekszo until 1919"):
    return [{"url": "https://example.org/gazetteer", "quote": quote, "supports": "both", "source_kind": "gazetteer"}]


def good_response(request):
    by_id = {t["gramps_id"]: t["task_id"] for t in request["tasks"]}
    return {"schema": agent.RESPONSE_SCHEMA, "request_id": request["request_id"], "results": [
        {"task_id": by_id["V"], "status": "found", "names": [
            {"name": "Alsoberekszo", "language": "hu", "valid_from": "1700", "valid_to": "1919", "evidence": evidence()}],
         "links": [], "unresolved": []},
        {"task_id": by_id["BAJ"], "status": "found", "names": [], "unresolved": [],
         "links": [{"parent_name": "Yugoslavia", "valid_from": "1929", "valid_to": "1941",
                    "evidence": evidence("the Kingdom of Yugoslavia included Bajmok from 1929")}]}]}


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        self.t = tree()
        # like the command line: the engine's own fixes come first, the agent gets what is left
        self.after_tree = gaps.apply(self.t, gaps.propose_end_clips(self.t, gaps.analyse(self.t)))
        self.rows = gaps.analyse(self.after_tree)
        self.request = agent.build_request(self.after_tree, self.rows)

    def test_the_request_has_one_task_per_place_with_gaps(self):
        ids = {t["gramps_id"]: t for t in self.request["tasks"]}
        self.assertEqual(set(ids), {"V", "BAJ"})
        self.assertEqual([(g["kind"], g["cause"]) for g in ids["V"]["gaps"]], [("name", "place not yet named")])
        self.assertEqual(ids["V"]["gaps"][0]["years"], [1900, 1900])
        self.assertEqual(ids["BAJ"]["gaps"][0]["kind"], "link")
        self.assertEqual(ids["V"]["parents"][0]["name"], "Magyarorszag")
        self.assertEqual(len(self.request["request_id"]), 12)

    def test_a_good_answer_is_accepted_and_fixes_the_events(self):
        result = agent.validate_response(good_response(self.request), self.request, self.t)
        self.assertEqual(result["rejected"], [])
        self.assertEqual(len(result["accepted"]), 2)
        props, notes = packs.propose_from_pack(self.after_tree, result["pack"])
        self.assertEqual(sorted(p["kind"] for p in props), ["add-link", "add-name"])
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(self.after_tree, props))}
        self.assertTrue(after["N1"].startswith("Alsoberekszo"))
        self.assertIn("Yugoslavia", after["B1"])

    def _break(self, mutate):
        response = good_response(self.request)
        mutate(response)
        return agent.validate_response(response, self.request, self.t)

    def reasons(self, result):
        return " | ".join(" ".join(r["reasons"]) for r in result["rejected"])

    def test_an_item_without_evidence_is_rejected(self):
        def m(r): r["results"][0]["names"][0]["evidence"] = []
        result = self._break(m)
        self.assertIn("evidence must be a list", self.reasons(result))
        self.assertEqual(len(result["accepted"]), 1)

    def test_a_long_quote_is_rejected(self):
        def m(r): r["results"][0]["names"][0]["evidence"][0]["quote"] = "word " * 30
        self.assertIn("quote must be 1 to 25 words", self.reasons(self._break(m)))

    def test_a_non_web_address_is_rejected(self):
        def m(r): r["results"][0]["names"][0]["evidence"][0]["url"] = "ftp://example.org/x"
        self.assertIn("not a web address", self.reasons(self._break(m)))

    def test_a_bad_source_kind_a_bad_language_and_backwards_dates_are_rejected(self):
        def m(r):
            n = r["results"][0]["names"][0]
            n["evidence"][0]["source_kind"] = "my memory"
            n["language"] = "Hungarian"
            n["valid_from"], n["valid_to"] = "1919", "1700"
        text = self.reasons(self._break(m))
        self.assertIn("source_kind must be one of", text)
        self.assertIn("language must be a code", text)
        self.assertIn("valid_from is after valid_to", text)

    def test_an_unknown_task_and_a_wrong_schema_are_rejected(self):
        def m(r): r["results"].append({"task_id": "t99", "names": []})
        self.assertIn("unknown task_id", self.reasons(self._break(m)))
        bad = good_response(self.request)
        bad["schema"] = "something.else"
        self.assertIn("schema must be", self.reasons(agent.validate_response(bad, self.request, self.t)))

    def test_a_parent_that_is_not_in_the_tree_is_not_invented(self):
        def m(r): r["results"][1]["links"][0]["parent_name"] = "Kingdom of Nowhere"
        text = self.reasons(self._break(m))
        self.assertIn("must match exactly one place of the tree", text)

    def test_duplicates_and_too_many_names_are_rejected(self):
        def m(r):
            first = r["results"][0]["names"][0]
            r["results"][0]["names"] += [copy.deepcopy(first)] + [
                dict(copy.deepcopy(first), name="N%d" % i) for i in range(8)]
        result = self._break(m)
        self.assertIn("duplicate", self.reasons(result))
        self.assertIn("more than 6 names", self.reasons(result))

    def test_a_different_request_id_is_only_a_warning(self):
        r = good_response(self.request)
        r["request_id"] = "other"
        result = agent.validate_response(r, self.request, self.t)
        self.assertTrue(any("request_id differs" in n for n in result["notes"]))
        self.assertEqual(len(result["accepted"]), 2)


class QuoteYearTests(unittest.TestCase):
    def setUp(self):
        self.t = tree()
        self.after_tree = gaps.apply(self.t, gaps.propose_end_clips(self.t, gaps.analyse(self.t)))
        self.request = agent.build_request(self.after_tree, gaps.analyse(self.after_tree))
        self.ids = {x["gramps_id"]: x["task_id"] for x in self.request["tasks"]}

    def answer(self, quote, valid_from="1700", valid_to="1919"):
        ev = [{"url": "https://example.org/g", "quote": quote, "supports": "both", "source_kind": "gazetteer"}]
        return {"schema": agent.RESPONSE_SCHEMA, "request_id": self.request["request_id"], "results": [
            {"task_id": self.ids["V"], "names": [{"name": "Alsoberekszo", "language": "hu", "valid_from": valid_from,
                                                  "valid_to": valid_to, "evidence": ev}]}]}

    def test_years_that_all_appear_in_quotes_are_evidence(self):
        result = agent.validate_response(self.answer("called Alsoberekszo from 1700 until 1919"), self.request, self.t)
        self.assertEqual(result["pack"]["places"][0]["names"][-1]["basis"], "evidence")
        props, _ = packs.propose_from_pack(self.after_tree, result["pack"])
        self.assertEqual(props[0]["basis"], "evidence")

    def test_a_year_that_no_quote_contains_makes_the_item_an_assumption(self):
        result = agent.validate_response(self.answer("the village was called Alsoberekszo until 1919"), self.request, self.t)
        self.assertEqual(result["rejected"], [])
        self.assertIn("year 1700 is in no quote", result["accepted"][0])
        self.assertEqual(result["pack"]["places"][0]["names"][-1]["basis"], "assumption")
        props, _ = packs.propose_from_pack(self.after_tree, result["pack"])
        self.assertEqual(props[0]["basis"], "assumption")

    def test_unsupported_years_ignores_the_open_end_stand_in(self):
        item = {"valid_from": "1873", "valid_to": "2100",
                "evidence": [{"quote": "seceded from the county in 1873"}]}
        self.assertEqual(agent.unsupported_years(item), [])
        self.assertEqual(agent.unsupported_years(dict(item, valid_from="1854-05")), ["1854"])

    def test_adding_a_date_to_an_undated_link_is_not_a_conflict(self):
        from placecompleter.dates import M_SPAN
        from test_lifetimes import tree as district_tree
        pack = {"schema": packs.SCHEMA, "pack": {"id": "u", "origin": "user"},
                "places": [{"key": "t", "names": ["Szilagycsehi"]}, {"key": "j", "names": ["Szilagycsehi jaras"]},
                           {"key": "r", "names": ["Salaj County"]}],
                "edges": [{"child": "t", "parent": "j", "valid_from": "1850", "valid_to": "1920", "origin": "user"},
                          {"child": "t", "parent": "r", "valid_from": "1921", "valid_to": "2100", "origin": "user"}]}
        props, _ = packs.propose_from_pack(district_tree(), packs.validate(pack))
        dated = next(p for p in props if p["parent"] == "j")
        self.assertEqual((dated["kind"], dated["conflict"], dated["new"]["modifier"]), ("set-link", False, M_SPAN))


def write_db(t, path):
    con = sqlite3.connect(path)
    con.execute("create table place (handle text, json_data text)")
    con.execute("create table event (handle text, json_data text)")
    for h, p in t.places.items():
        con.execute("insert into place values (?, ?)", (h, json.dumps({
            "gramps_id": p["id"], "place_type": p["type"], "name": p["name"], "alt_names": p["alt_names"],
            "placeref_list": p["refs"], "lat": p["lat"], "long": p["lon"], "urls": []})))
    for e in t.events:
        con.execute("insert into event values (?, ?)", (e["handle"], json.dumps({
            "gramps_id": e["id"], "type": e["type"], "date": e["date"], "place": e["place"]})))
    con.commit()
    con.close()


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_request_and_validate_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, req_path, resp_path = (os.path.join(tmp, n) for n in ("t.db", "req.json", "resp.json"))
            write_db(tree(), db)
            code, out = self.run_cli("agent-request", db, "--out", req_path, "--no-packs")
            self.assertEqual(code, 0)
            self.assertIn("2 task(s)", out)
            bundle = os.path.join(tmp, "req_task.md")
            with open(bundle, encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("# Task for the research agent", text)
            self.assertIn('"request_id"', text)
            with open(req_path, encoding="utf-8") as fh:
                request = json.load(fh)
            with open(resp_path, "w", encoding="utf-8") as fh:
                json.dump(good_response(request), fh)
            code, out = self.run_cli("agent-validate", resp_path, "--request", req_path, "--db", db,
                                     "--out", os.path.join(tmp, "pack.json"), "--no-packs")
            self.assertEqual(code, 0)
            self.assertIn("ACCEPTED (2)", out)
            self.assertIn("REJECTED (0)", out)
            self.assertIn("ADD NAME 'Alsoberekszo'", out)
            self.assertTrue(os.path.exists(os.path.join(tmp, "pack.json")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
