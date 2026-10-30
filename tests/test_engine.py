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
"""Unit tests of the PlaceCompleter engine. They need no Gramps and no database.

Run from the PlaceCompleter folder: python3 -m unittest discover -s tests -v
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from placecompleter import gaps                                   # noqa: E402
from placecompleter.chain import chain                            # noqa: E402
from placecompleter.dates import (INF, M_AFTER, M_BEFORE, M_FROM, M_NONE,  # noqa: E402
                                  M_RANGE, M_SPAN, M_TO, M_ABOUT, M_TEXT, interval,
                                  match_exact, sdn)
from placecompleter.model import Tree                             # noqa: E402

EMPTY = {"modifier": 0, "quality": 0, "calendar": 0, "dateval": [0, 0, 0, False],
         "text": "", "sortval": 0}


def D(mod, y1, m1=0, d1=0, y2=None, m2=0, d2=0, quality=0):
    dv = [d1, m1, y1, False]
    if mod in (M_RANGE, M_SPAN):
        dv += [d2, m2, y2, False]
    return {"modifier": mod, "quality": quality, "calendar": 0, "dateval": dv, "text": "",
            "sortval": sdn(y1, m1 or 1, d1 or 1)}


def place(handle, name, ptype=0, refs=(), alts=(), name_date=None, lang=""):
    return {"handle": handle, "id": handle.upper(), "type": {"value": ptype, "string": ""},
            "name": {"value": name, "lang": lang, "date": name_date or EMPTY},
            "alt_names": [{"value": v, "lang": l, "date": d} for v, l, d in alts],
            "refs": [{"ref": r, "date": d} for r, d in refs], "urls": [], "lat": "", "lon": ""}


def event(eid, handle, date):
    return {"handle": eid, "id": eid.upper(), "type": {"value": 0}, "date": date, "place": handle}


def bajmok_tree(events):
    """The structure of the user's Bajmok hierarchy (dates as stored in his tree)."""
    places = {p["handle"]: p for p in [
        place("kais", "Kaisertum Osterreich", 0, name_date=D(M_SPAN, 1804, y2=1867)),
        place("mon", "Osztrak-Magyar Monarchia", 0, name_date=D(M_SPAN, 1867, y2=1918)),
        place("hun", "Magyarorszag", 1, name_date=D(M_FROM, 1000), lang="hu",
              alts=[("Hungary", "", EMPTY)],
              refs=[("mon", D(M_FROM, 1867)), ("kais", D(M_NONE, 1859))]),
        place("cty", "Bacs-Bodrog varmegye", 3, name_date=D(M_FROM, 1849), lang="hu",
              refs=[("hun", D(M_FROM, 1000))]),
        place("jar", "Bacsalmasi jaras", 0, name_date=D(M_TO, 1920), lang="hu",
              refs=[("cty", D(M_SPAN, 1849, y2=1920))]),
        place("baj", "Bajmok", 16, name_date=D(M_FROM, 1462), lang="hu",
              alts=[("Bajmok", "", EMPTY)], refs=[("jar", D(M_TO, 1920))])]}
    return Tree(places, events)


class DatesTests(unittest.TestCase):
    def test_julian_day_numbers_match_the_values_gramps_stores(self):
        for ymd_, stored in [((1859, 1, 1), 2400046), ((1867, 1, 1), 2402968), ((1920, 1, 1), 2422325),
                             ((1896, 10, 27), 2413860), ((1849, 1, 1), 2396394), ((1841, 12, 18), 2393823)]:
            self.assertEqual(sdn(*ymd_), stored)

    def test_interval_agrees_with_the_branches_of_match_exact(self):
        rng = random.Random(7)
        for _ in range(3000):
            link = D(rng.choice([M_NONE, M_BEFORE, M_AFTER, M_FROM, M_TO, M_RANGE, M_SPAN]),
                     rng.randint(1700, 2000), rng.randint(0, 12), 0, rng.randint(1700, 2100), 0, 0,
                     quality=rng.choice([0, 0, 1]))
            if link["modifier"] in (M_RANGE, M_SPAN):
                link["dateval"][6] = max(link["dateval"][6], link["dateval"][2])
            ev = D(M_NONE, rng.randint(1650, 2100), rng.randint(0, 12), 0)
            lo, hi = interval(link)
            self.assertEqual(match_exact(ev, link), lo <= ev["sortval"] <= hi)
        self.assertIsNone(interval(D(M_ABOUT, 1900)))
        text_date = dict(EMPTY, modifier=M_TEXT, text="words")
        self.assertIsNone(interval(text_date))

    def test_estimated_ranges_are_widened_by_fifty_years(self):
        link = D(M_RANGE, 1926, y2=1940, quality=1)
        self.assertTrue(match_exact(D(M_NONE, 1945), link))
        self.assertFalse(match_exact(D(M_NONE, 1945), D(M_RANGE, 1926, y2=1940)))


class ChainTests(unittest.TestCase):
    def names(self, tree, handle, date):
        result = chain(tree.places, handle, date)
        return ", ".join(result["names"]), result["end"]

    def test_chain_follows_the_dates_like_gramps(self):
        t = bajmok_tree([])
        self.assertEqual(self.names(t, "baj", D(M_NONE, 1905, 11, 14)),
                         ("Bajmok, Bacsalmasi jaras, Bacs-Bodrog varmegye, Hungary, Osztrak-Magyar Monarchia", "top"))
        self.assertEqual(self.names(t, "baj", D(M_NONE, 1865, 7, 5))[0],
                         "Bajmok, Bacsalmasi jaras, Bacs-Bodrog varmegye, Hungary")
        self.assertEqual(self.names(t, "baj", D(M_NONE, 1865, 7, 5))[1], "truncated")   # no link to an empire
        self.assertEqual(self.names(t, "baj", D(M_NONE, 1845, 1, 1)), ("Bajmok, Bacsalmasi jaras", "truncated"))
        self.assertEqual(self.names(t, "baj", D(M_NONE, 1950)), ("Bajmok", "truncated"))

    def test_range_events_are_matched_by_their_first_day_only(self):
        t = bajmok_tree([])
        self.assertEqual(self.names(t, "baj", D(M_RANGE, 1866, y2=1875))[1], "truncated")
        self.assertEqual(self.names(t, "baj", D(M_BEFORE, 1896, 10, 27))[1], "top")

    def test_undated_events_match_only_to_and_before_links(self):
        t = bajmok_tree([])
        self.assertEqual(self.names(t, "baj", dict(EMPTY)), ("Bajmok, Bacsalmasi jaras", "truncated"))

    def test_a_country_after_all_its_links_ended_is_a_normal_top_level_place(self):
        t = bajmok_tree([])
        t.places["hun"]["refs"][0]["date"] = D(M_SPAN, 1867, y2=1918)
        self.assertEqual(chain(t.places, "hun", D(M_NONE, 1925))["end"], "after-links")
        self.assertEqual(chain(t.places, "hun", D(M_NONE, 1840))["end"], "truncated")   # before the links
        self.assertEqual(chain(t.places, "baj", D(M_NONE, 1925))["end"], "truncated")   # a village is not


class ProposalTests(unittest.TestCase):
    def tree(self):
        t = bajmok_tree([])
        t.places["zom"] = place("zom", "Zombor", 4, refs=[("hun", EMPTY)])
        t.events.extend([event("e1", "zom", D(M_NONE, 1900, 5, 1)), event("e2", "zom", D(M_NONE, 1925, 5, 1)),
                         event("e3", "zom", D(M_NONE, 1950))])
        return t

    def test_open_link_to_a_parent_that_ended_shows_a_question_mark(self):
        rows = gaps.analyse(self.tree())
        shown = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in rows}
        self.assertEqual(shown["E1"], "Zombor, Hungary, Osztrak-Magyar Monarchia")
        self.assertEqual(shown["E2"], "Zombor, Hungary, ?")
        self.assertEqual(shown["E3"], "Zombor, Hungary, ?")

    def test_the_link_is_shortened_to_the_last_day_of_the_parent(self):
        t = self.tree()
        rows = gaps.analyse(t)
        props = gaps.propose_end_clips(t, rows)
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual((p["child"], p["parent"], p["events"]), ("hun", "mon", 2))
        self.assertEqual(p["new"]["modifier"], M_SPAN)
        self.assertEqual(p["new"]["dateval"], [0, 0, 1867, False, 0, 0, 1918, False])
        after = gaps.analyse(gaps.apply(t, props))
        self.assertEqual([r["unnamed"] for r in after if r["event"]["id"] in ("E2", "E3")], [[], []])
        self.assertEqual(gaps.compare(rows, after)["? names removed (events)"], 2)
        self.assertEqual(gaps.compare(rows, after).get("? names introduced (events)", 0), 0)
        self.assertEqual(", ".join(next(r for r in after if r["event"]["id"] == "E2")["chain"]["names"]), "Zombor, Hungary")
        self.assertEqual([r["chain"]["end"] for r in after if r["event"]["id"] in ("E2", "E3")], ["after-links"] * 2)
        self.assertEqual(t.places["hun"]["refs"][0]["date"]["modifier"], M_FROM)   # the original tree is untouched

    def test_nothing_is_proposed_when_the_parent_has_no_end(self):
        t = self.tree()
        t.places["mon"]["name"]["date"] = D(M_FROM, 1867)
        self.assertEqual(gaps.propose_end_clips(t, gaps.analyse(t)), [])

    def test_a_parent_that_has_parents_is_never_shortened(self):
        # a county whose recorded names end in 1848 but that obviously went on: only a name is missing
        t = Tree({}, [])
        t.places = {"town": place("town", "Town", 4, refs=[("cty", EMPTY)]),
                    "cty": place("cty", "County", 3, refs=[("hun", EMPTY)], name_date=D(M_SPAN, 1820, y2=1848)),
                    "hun": place("hun", "Hungary", 1)}
        t.events = [event("e1", "town", D(M_NONE, 1870))]
        rows = gaps.analyse(t)
        self.assertEqual(rows[0]["unnamed"], ["cty"])
        self.assertEqual(gaps.propose_end_clips(t, rows), [])
        fix = gaps.name_gaps(t, rows)[0]
        self.assertEqual((fix["cause"], fix["top_level"], fix["likely_fix"]),
                         ("place ended", False, "extend the name (outside source)"))

    def test_an_undated_link_gets_the_whole_existence_of_the_parent(self):
        t = Tree({}, [])
        t.places = {"p": place("p", "Province", 0, refs=[("k", EMPTY)]),
                    "k": place("k", "Empire", 0, name_date=D(M_SPAN, 1804, y2=1867))}
        t.events = [event("e1", "p", D(M_NONE, 1900))]
        props = gaps.propose_end_clips(t, gaps.analyse(t))
        self.assertEqual(len(props), 1)
        self.assertEqual(props[0]["new"]["dateval"], [0, 0, 1804, False, 0, 0, 1867, False])

    def test_link_gaps_and_name_gaps_are_reported_with_years(self):
        t = bajmok_tree([event("a", "baj", D(M_NONE, 1950)), event("b", "baj", D(M_NONE, 1930)),
                         event("c", "baj", D(M_NONE, 1845))])
        rows = gaps.analyse(t)
        lg = {g["place"]: g for g in gaps.link_gaps(rows)}
        self.assertEqual((lg["baj"]["events"], lg["baj"]["years"]), (2, (1930, 1950)))
        self.assertEqual((lg["jar"]["events"], lg["jar"]["years"]), (1, (1845, 1845)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
