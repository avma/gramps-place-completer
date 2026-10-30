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
"""Tests of the Wikidata source against REAL Wikidata answers (tests/data/wikidata_mini.json).

The fixture holds the answers the API gave for places of the user's region. No
network is used. A few search answers that were never recorded are added by the
tests, pointing at real entities from the fixture.
"""
import os
import sys
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import gaps, packs, wikidata                          # noqa: E402
from placecompleter.dates import M_FROM, M_NONE, M_SPAN                   # noqa: E402
from test_engine import D, EMPTY, event, place                           # noqa: E402
from placecompleter.model import Tree                                    # noqa: E402

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "wikidata_mini.json")


def client():
    return wikidata.Client(cache_path=FIXTURE, fetch=None)


def add_search(c, text, language, *ids):
    url = "%s?action=wbsearchentities&search=%s&language=%s&limit=5&format=json" % (
        wikidata.API, urllib.parse.quote(text), language)
    c.answers[url] = {"search": [{"id": i} for i in ids]}


class ReadingTests(unittest.TestCase):
    def setUp(self):
        self.c = client()
        self.e = lambda q: self.c.entity_cache[q]

    def test_the_fixture_loads_into_the_entity_cache(self):
        self.assertIn("Q171150", self.c.entity_cache)
        self.assertEqual(wikidata.labels(self.e("Q171150"))["hu"], "Magyar Királyság")

    def test_time_values_become_partial_iso_dates(self):
        t = lambda s, p=9: {"time": s, "precision": p}
        self.assertEqual(wikidata.iso_time(t("+1804-00-00T00:00:00Z")), "1804")
        self.assertEqual(wikidata.iso_time(t("+1944-07-31T00:00:00Z", 11)), "1944-07-31")
        self.assertEqual(wikidata.iso_time(t("+1944-07-00T00:00:00Z", 10)), "1944-07")
        self.assertIsNone(wikidata.iso_time(t("+1800-00-00T00:00:00Z", 7)))     # a century is too coarse
        self.assertIsNone(wikidata.iso_time(None))

    def test_the_real_dated_link_of_the_kingdom_of_hungary(self):
        links = {wikidata.entity_id(c["value"]): (c["start"], c["end"]) for c in wikidata.claims(self.e("Q171150"), "P131")}
        self.assertEqual(links["Q131964"], ("1804", "1867"))
        self.assertEqual(links["Q696970"], ("1867", "1918"))

    def test_deprecated_claims_are_ignored(self):
        self.assertEqual(wikidata.claims(self.e("Q403"), "P131"), [])           # Serbia: all three are deprecated

    def test_lifetime_and_official_names(self):
        self.assertEqual(wikidata.lifetime(self.e("Q852564")), ("1802", "1950"))
        names = wikidata.official_names(self.e("Q269864"))
        self.assertIn({"name": "Народная Республика Сербия", "language": "ru", "start": "1946-02-19", "end": "1963-04-07"}, names)

    def test_only_places_are_place_like(self):
        self.assertTrue(wikidata.place_like(self.e("Q204475")))                  # Sombor, city
        self.assertTrue(wikidata.place_like(self.e("Q131964")))                  # Austrian Empire
        self.assertFalse(wikidata.place_like(self.e("Q134877952")))              # the family name Zombor
        self.assertFalse(wikidata.place_like(self.e("Q7631793")))                # a racehorse named Subotica


class ResolveTests(unittest.TestCase):
    def tree(self, name, lat="", lon=""):
        p = place("z", name, 4)
        p["lat"], p["lon"] = lat, lon
        return Tree({"z": p}, [])

    def test_coordinates_tell_two_places_with_the_same_name_apart(self):
        r = wikidata.resolve(self.tree("Zombor", "45.7833", "19.1122"), "z", client())
        self.assertEqual(r["qid"], "Q204475")                                    # Sombor in Serbia, not the Slovak village

    def test_without_coordinates_the_two_places_stay_ambiguous(self):
        r = wikidata.resolve(self.tree("Zombor"), "z", client())
        self.assertEqual({q for q, _l in r["ambiguous"]}, {"Q204475", "Q219814"})

    def test_names_that_are_not_places_never_match(self):
        r = wikidata.resolve(self.tree("Subotica"), "z", client())
        self.assertEqual(r["qid"], "Q170287")                                    # not the horse, not the family name

    def test_an_unknown_name_has_no_match(self):
        self.assertEqual(wikidata.resolve(self.tree("Nowhere-on-Sea"), "z", client()), {"none": True})


class PackTests(unittest.TestCase):
    def test_a_dated_link_and_a_lifetime_become_proposals_that_fix_events(self):
        c = client()
        add_search(c, "Kingdom of Hungary", "en", "Q171150")
        add_search(c, "Austrian Empire", "en", "Q131964")
        add_search(c, "Bács-Bodrog vármegye", "hu", "Q852564")
        county = place("cty", "Bács-Bodrog vármegye", 3, name_date=D(M_FROM, 1849), lang="hu",
                       refs=[("hun", EMPTY)])
        county["lat"], county["lon"] = "45.7736", "19.5301"
        t = Tree({
            "hun": place("hun", "Kingdom of Hungary", 1, name_date=D(M_FROM, 1000),
                         refs=[("kais", D(M_NONE, 1859))]),
            "kais": place("kais", "Austrian Empire", 0, name_date=D(M_SPAN, 1804, y2=1867)),
            "cty": county},
            [event("a", "hun", D(M_NONE, 1810, 3, 1)), event("b", "hun", D(M_NONE, 1850, 3, 1)),
             event("c", "cty", D(M_NONE, 1810, 3, 1)), event("d", "cty", D(M_NONE, 1900, 3, 1))])
        pack, notes = wikidata.build_pack(t, ["hun", "kais", "cty"], c)
        existing = [(e["child"], e["parent"], e["valid_from"], e["valid_to"]) for e in pack["edges"]
                    if not e["parent"].startswith("wd-")]
        self.assertEqual(existing, [("p-HUN", "p-KAIS", "1804", "1867")])
        self.assertIn("wd-Q696970", {e["parent"] for e in pack["edges"]})          # a parent the tree lacks: offered as new
        props, _ = packs.propose_from_pack(t, pack)
        self.assertEqual(sorted(p["kind"] for p in props if p["kind"] in ("set-link", "set-name-date")), ["set-link", "set-name-date"])
        for p in props:
            self.assertEqual(p["origin"], "wikidata")
            self.assertTrue(p["evidence"][0]["url"].startswith("https://www.wikidata.org/wiki/Q"))
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}
        self.assertEqual(after["A"], "Kingdom of Hungary, Austrian Empire")
        self.assertEqual(after["B"], "Kingdom of Hungary, Austrian Empire")
        self.assertTrue(after["C"].startswith("Bács-Bodrog vármegye"))           # the name now covers 1810
        self.assertNotIn("?", after["C"])

    def test_a_deprecated_statement_is_not_offered(self):
        c = client()
        add_search(c, "Serbia", "en", "Q403")
        add_search(c, "Socialist Federal Republic of Yugoslavia", "en", "Q83286")
        t = Tree({"s": place("s", "Serbia", 1, refs=[("y", EMPTY)]),
                  "y": place("y", "Socialist Federal Republic of Yugoslavia", 0)}, [])
        pack, notes = wikidata.build_pack(t, ["s", "y"], c)
        self.assertEqual(pack["edges"], [])

    def test_ambiguity_is_reported_not_guessed(self):
        c = client()
        t = Tree({"z": place("z", "Zombor", 4)}, [event("e", "z", D(M_NONE, 1900))])
        pack, notes = wikidata.build_pack(t, ["z"], c)
        self.assertEqual(pack["places"], [])
        self.assertTrue(any("ambiguous in Wikidata" in n for n in notes))

    def test_the_client_never_touches_the_network_without_a_fetch_function(self):
        c = wikidata.Client(cache_path=FIXTURE)
        self.assertEqual(c.search("A name that was never cached", "en"), [])
        self.assertEqual(c.network_calls, 0)

    def test_a_fetch_function_is_called_once_per_new_url_and_cached(self):
        calls = []
        c = wikidata.Client(fetch=lambda url: calls.append(url) or {"search": [{"id": "Q1"}]}, pause=0)
        c.search("X", "en")
        c.search("X", "en")
        self.assertEqual(len(calls), 1)


class CommandLineTests(unittest.TestCase):
    def test_the_command_runs_from_the_cache_alone(self):
        import contextlib
        import io
        import json
        import tempfile
        from placecompleter import cli
        from test_agent_loop import write_db
        county = place("c", "Bács-Bodrog vármegye", 3, name_date=D(M_FROM, 1849), lang="hu")
        county["lat"], county["lon"] = "45.7736", "19.5301"
        t = Tree({"c": county}, [event("e", "c", D(M_NONE, 1810, 5, 1)), event("f", "c", D(M_NONE, 1900, 5, 1))])
        with tempfile.TemporaryDirectory() as tmp:
            db, extra = os.path.join(tmp, "t.db"), os.path.join(tmp, "extra.json")
            write_db(t, db)
            probe = wikidata.Client()
            add_search(probe, "Bács-Bodrog vármegye", "hu", "Q852564")
            with open(extra, "w", encoding="utf-8") as fh:
                json.dump(probe.answers, fh)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = cli.main(["wikidata-pack", db, "--no-packs", "--seed", FIXTURE, "--seed", extra,
                                 "--cache", os.path.join(tmp, "c.json"), "--out", os.path.join(tmp, "p.json")])
            text = out.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("(cache only)", text)
            self.assertIn("PROPOSALS FROM WIKIDATA: 1", text)
            self.assertIn("SET NAME DATE", text)
            self.assertIn("P571 1802", text)
            self.assertTrue(os.path.exists(os.path.join(tmp, "p.json")))

    def test_a_century_precision_date_is_not_used(self):
        # Sombor's inception in Wikidata is "1200" with century precision: no lifetime is derived from it
        self.assertEqual(wikidata.lifetime(client().entity_cache["Q204475"]), (None, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class RetryAfterTests(unittest.TestCase):
    """A server says how long to wait with Retry-After: a number of seconds or a date. Neither may crash the program or hold it for an hour."""

    def test_a_number_of_seconds_is_waited(self):
        self.assertEqual(wikidata.retry_after("7", 99), 7.0)

    def test_a_date_is_waited_until(self):
        import datetime
        import email.utils
        when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=30)
        wait = wikidata.retry_after(email.utils.format_datetime(when, usegmt=True), 99)
        self.assertTrue(25 <= wait <= 30, wait)

    def test_what_cannot_be_read_gives_the_default_and_is_never_negative_or_long(self):
        self.assertEqual(wikidata.retry_after("soon", 4), 4.0)
        self.assertEqual(wikidata.retry_after(None, 6), 6.0)
        self.assertEqual(wikidata.retry_after("-5", 6), 0.0)
        self.assertEqual(wikidata.retry_after("86400", 6), float(wikidata.MAX_RETRY_WAIT))      # a day is not waited
        self.assertEqual(wikidata.retry_after("Wed, 21 Oct 2015 07:28:00 GMT", 6), 0.0)         # a date in the past

    def test_a_429_with_a_date_does_not_crash_the_fetch_and_waits_at_most_the_limit(self):
        import io
        import urllib.error
        slept = []
        calls = {"n": 0}

        def refuse(req, timeout=0):
            calls["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 429, "busy", {"Retry-After": "Wed, 21 Oct 2099 07:28:00 GMT"}, io.BytesIO(b""))
        with mock.patch("urllib.request.urlopen", refuse), mock.patch("time.sleep", slept.append):
            self.assertIsNone(wikidata.urllib_fetch("https://www.wikidata.org/w/api.php?x=1", retries=3))
        self.assertEqual(calls["n"], 3)
        self.assertTrue(slept and max(slept) <= wikidata.MAX_RETRY_WAIT, slept)
