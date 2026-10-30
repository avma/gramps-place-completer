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
"""Tests of regional packs: validation, matching and proposals (no Gramps needed)."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import gaps, packs                                   # noqa: E402
from placecompleter.dates import M_NONE, M_SPAN                          # noqa: E402
from test_engine import D, EMPTY, bajmok_tree, event, place              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(os.path.dirname(HERE), "packs", "hu-habsburg.json")


def tree_with_events():
    t = bajmok_tree([])
    t.events.extend([event("h1", "hun", D(M_NONE, 1810, 3, 4)), event("h2", "hun", D(M_NONE, 1850, 6, 1)),
                     event("h3", "hun", D(M_NONE, 1900, 6, 1))])
    return t


class PackTests(unittest.TestCase):
    def pack(self):
        return packs.load_pack(SAMPLE)

    def test_the_bundled_pack_is_valid(self):
        data = self.pack()
        self.assertEqual(data["pack"]["id"], "hu-habsburg")

    def test_validation_reports_every_problem(self):
        bad = copy.deepcopy(self.pack())
        bad["edges"][0].update(child="nowhere", valid_from="18x4", origin="agent", evidence=[])
        with self.assertRaises(packs.PackError) as ctx:
            packs.validate(bad)
        text = str(ctx.exception)
        self.assertIn("unknown place key", text)
        self.assertIn("bad date", text)
        self.assertIn("evidence is required", text)

    def test_an_edge_that_goes_backwards_in_time_is_rejected(self):
        bad = copy.deepcopy(self.pack())
        bad["edges"][0].update(valid_from="1867", valid_to="1804")
        with self.assertRaises(packs.PackError):
            packs.validate(bad)

    def test_iso_dates_keep_their_precision(self):
        self.assertEqual(packs.parse_iso("1804"), (0, 0, 1804))
        self.assertEqual(packs.parse_iso("1804-05"), (0, 5, 1804))
        self.assertEqual(packs.parse_iso("1804-05-17"), (17, 5, 1804))

    def test_names_match_without_case_or_accents(self):
        t = bajmok_tree([])
        pack = self.pack()
        self.assertEqual(packs.match_place(t, pack["places"][0]), ["hun"])
        self.assertEqual(packs.match_place(t, pack["places"][1]), ["kais"])

    def test_the_link_to_the_empire_is_widened_and_fixes_events(self):
        t = tree_with_events()
        props, notes = packs.propose_from_pack(t, self.pack())
        self.assertEqual(len(props), 1)
        p = props[0]
        self.assertEqual((p["kind"], p["child"], p["parent"], p["conflict"]), ("set-link", "hun", "kais", False))
        self.assertEqual(p["new"]["modifier"], M_SPAN)
        self.assertEqual(p["events"], 2)                # 1810 and 1850; 1900 is already fine
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}
        self.assertEqual(after["H1"], "Hungary, Kaisertum Osterreich")
        self.assertEqual(after["H2"], "Hungary, Kaisertum Osterreich")
        self.assertEqual(after["H3"], "Hungary, Osztrak-Magyar Monarchia")
        self.assertEqual(t.places["hun"]["refs"][1]["date"]["modifier"], M_NONE)   # the tree itself is untouched

    def test_a_missing_link_is_added(self):
        t = tree_with_events()
        t.places["hun"]["refs"] = [r for r in t.places["hun"]["refs"] if r["ref"] != "kais"]
        props, _ = packs.propose_from_pack(t, self.pack())
        self.assertEqual((props[0]["kind"], props[0]["index"]), ("add-link", 1))
        after = gaps.analyse(gaps.apply(t, props))
        self.assertEqual(", ".join(next(r for r in after if r["event"]["id"] == "H2")["chain"]["names"]),
                         "Hungary, Kaisertum Osterreich")

    def test_ambiguous_places_are_never_guessed(self):
        t = tree_with_events()
        t.places["hun2"] = place("hun2", "Hungary", 1)
        props, notes = packs.propose_from_pack(t, self.pack())
        self.assertEqual(props, [])
        self.assertTrue(any("2 place(s) match the child" in n for n in notes))

    def test_a_link_that_is_already_right_is_not_proposed_again(self):
        t = tree_with_events()
        first, _ = packs.propose_from_pack(t, self.pack())
        fixed = gaps.apply(t, first)
        props, notes = packs.propose_from_pack(fixed, self.pack())
        self.assertEqual(props, [])
        self.assertTrue(any("already has this link" in n for n in notes))

    def test_a_valid_edge_with_no_effect_here_is_only_a_note(self):
        t = tree_with_events()
        t.events = [e for e in t.events if e["id"] == "H3"]
        props, notes = packs.propose_from_pack(t, self.pack())
        self.assertEqual(props, [])
        self.assertTrue(any("fixes none of the events" in n for n in notes))


class NamePackTests(unittest.TestCase):
    def tree(self):
        from placecompleter.dates import M_FROM
        t = bajmok_tree([])
        t.places["v"] = place("v", "Berechiu", 16, name_date=D(M_FROM, 1920), lang="ro", refs=[("hun", EMPTY)])
        t.events = [event("n1", "v", D(M_NONE, 1900, 5, 1)), event("n2", "v", D(M_NONE, 1950, 5, 1))]
        return t

    def pack(self, first="1700", last="1919"):
        return {"schema": packs.SCHEMA, "pack": {"id": "names", "origin": "user"},
                "places": [{"key": "v", "names": ["Berechiu", {"name": "Alsoberekszo", "language": "hu",
                                                               "valid_from": first, "valid_to": last}]}],
                "edges": []}

    def test_a_missing_early_name_is_added(self):
        t = self.tree()
        props, _ = packs.propose_from_pack(t, packs.validate(self.pack()))
        self.assertEqual([(p["kind"], p["value"], p["lang"], p["events"]) for p in props], [("add-name", "Alsoberekszo", "hu", 1)])
        after = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(gaps.apply(t, props))}
        self.assertEqual(after["N1"].split(", ")[0], "Alsoberekszo")
        self.assertEqual(after["N2"].split(", ")[0], "Berechiu")
        self.assertEqual(len(t.places["v"]["alt_names"]), 0)       # the tree itself is untouched

    def test_the_period_of_an_existing_name_is_widened(self):
        t = self.tree()
        t.places["v"]["alt_names"] = [{"value": "Alsoberekszo", "lang": "hu", "date": D(M_SPAN, 1850, y2=1880)}]
        props, _ = packs.propose_from_pack(t, packs.validate(self.pack()))
        self.assertEqual((props[0]["kind"], props[0]["index"], props[0]["conflict"]), ("set-name-date", 1, False))
        after = gaps.analyse(gaps.apply(t, props))
        self.assertEqual(after[0]["unnamed"], [])

    def test_a_name_that_changes_nothing_here_is_only_a_note(self):
        t = self.tree()
        t.events = [e for e in t.events if e["id"] == "N2"]
        props, notes = packs.propose_from_pack(t, packs.validate(self.pack()))
        self.assertEqual(props, [])
        self.assertTrue(any("fixes none" in n for n in notes))

    def test_a_name_period_must_run_forwards(self):
        with self.assertRaises(packs.PackError):
            packs.validate(self.pack("1919", "1700"))

    def test_an_open_ended_name_period_uses_from(self):
        from placecompleter.dates import M_FROM
        props, _ = packs.propose_from_pack(self.tree(), packs.validate(self.pack("1700", None)))
        self.assertEqual(props[0]["new"]["modifier"], M_FROM)


class HarmTests(unittest.TestCase):
    def test_a_proposal_that_makes_more_events_worse_than_it_fixes_is_not_made(self):
        from placecompleter.dates import M_FROM
        t = bajmok_tree([])
        t.places["v"] = place("v", "Berechiu", 16, name_date=D(M_FROM, 1000), lang="ro", refs=[("hun", EMPTY)])
        t.events = [event("w1", "v", D(M_NONE, 1950, 5, 1)), event("w2", "v", D(M_NONE, 1960, 5, 1))]
        pack = {"schema": packs.SCHEMA, "pack": {"id": "narrow", "origin": "user"},
                "places": [{"key": "v", "names": [{"name": "Berechiu", "language": "ro", "valid_from": "1000", "valid_to": "1946"}]}],
                "edges": []}
        props, notes = packs.propose_from_pack(t, packs.validate(pack))
        self.assertEqual(props, [])
        self.assertTrue(any("fixes none" in n or "worse" in n for n in notes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
