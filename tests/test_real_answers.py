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
"""Real answers of an AI to the question of this addon (New York City and Zürich, 1990), kept as they came, and what the analysis must make of them.
They showed three faults of the program (a short form of the name taken for a contradiction, "New York State" not found as the state New York of the tree,
the sovereign state made a "state") and two faults of the question (the level number taken for an official code, a note put inside NOT_SURE)."""
import os
import sys
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

from placecompleter import ingest, prompts                                                   # noqa: E402
from placecompleter.dates import describe                                                     # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
from test_ingest import typed                                                                 # noqa: E402

WORLD = os.path.join(os.path.dirname(HERE), "packs", "world-basics.json")


def answer(name):
    with open(os.path.join(HERE, "data", name), encoding="utf-8") as fh:
        return fh.read()


def run(name, tree, date="1990", **kw):
    return ingest.ingest(tree, ingest.parse_structured(answer(name)), date, aliases=ingest.alias_map([WORLD]), **kw)


def new_places(result):
    return {p["names"][0]["value"]: (p["type_value"], p.get("type_string")) for p in result["proposals"] if p["kind"] == "add-place"}


def usa_with_state(state_type=2, city_type=None):
    t = Tree({"usa": typed("usa", "USA", 1, lang="en"), "ny": typed("ny", "New York", state_type, lang="en")}, [])
    t.places["ny"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    return t


class NewYorkCityTests(unittest.TestCase):
    def test_a_short_form_of_the_name_is_not_a_contradiction(self):
        r = run("answer_nyc_1990.txt", usa_with_state())
        self.assertFalse([n for n in r["needs"] if n.startswith("THE ANSWER CONTRADICTS ITSELF")], r["needs"])

    def test_new_york_state_is_the_state_new_york_of_the_tree(self):
        r = run("answer_nyc_1990.txt", usa_with_state())
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]][:1], [("New York State", "ny")])
        self.assertEqual(set(new_places(r)), {"New York City"})                                  # no second state
        self.assertEqual(r["ambiguous"], [])

    def test_a_city_called_new_york_is_not_the_state(self):
        t = Tree({"usa": typed("usa", "USA", 1, lang="en"), "nyc": typed("nyc", "New York", 4, lang="en")}, [])
        t.places["nyc"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        r = run("answer_nyc_1990.txt", t)
        self.assertIn("New York State", new_places(r))                                         # the type of the place says it is not the state

class ZurichTests(unittest.TestCase):
    def test_the_levels_are_made_whatever_the_first_column_holds(self):
        r = run("answer_zurich_1990.txt", Tree({}, []))
        self.assertEqual(set(new_places(r)), {"Zürich", "Bezirk Zürich", "Kanton Zürich", "Schweizerische Eidgenossenschaft"})
        self.assertEqual([c["parent_label"].split(" | ")[0] for c in r["chain"]], ["Bezirk Zürich", "Kanton Zürich", "Schweizerische Eidgenossenschaft"])

    def test_the_sovereign_state_is_a_country_not_a_state(self):
        r = run("answer_zurich_1990.txt", Tree({}, []))
        self.assertEqual(new_places(r)["Schweizerische Eidgenossenschaft"][0], 1)               # Country (it said "federal state" in the type column)

    def test_the_municipality_is_not_a_container_of_itself_and_the_state_is_made_once(self):
        r = run("answer_zurich_1990.txt", Tree({}, []))
        self.assertTrue(any("Zürich is identical to Zürich" in n for n in r["needs"]))
        self.assertEqual(sum(1 for p in r["proposals"] if p["kind"] == "add-place" and "Eidgenossenschaft" in p["names"][0]["value"]), 1)

    def test_the_country_of_the_tree_is_found_under_its_name_in_the_language_of_the_state(self):
        t = Tree({"ch": typed("ch", "Switzerland", 1, lang="en"), "zh": typed("zh", "Zürich", 4, lang="de")}, [])
        r = run("answer_zurich_1990.txt", t)
        self.assertEqual(r["child"], "zh")                                                      # the place of the tree is the one asked about
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]][-1], ("Schweizerische Eidgenossenschaft", "ch"))
        self.assertNotIn("Schweizerische Eidgenossenschaft", new_places(r))                    # no second Switzerland (the pack knows the name)


class SissaTests(unittest.TestCase):
    """The province Parma and the city Parma have one name. The answer names the province; the tree had the city, and Sissa was placed inside the city."""
    def tree(self, parma_type=4):
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 1, lang="en"),
                  "parma": typed("parma", "Parma", parma_type, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        return t

    def units(self, r):
        return [(u["name"], u["handle"]) for u in r["units"]]

    def test_the_province_is_not_the_city_of_the_same_name(self):
        r = run("answer_sissa_1990.txt", self.tree())
        self.assertEqual(self.units(r), [("Parma", None), ("Emilia-Romagna", "er"), ("Italia", "it")])
        made = new_places(r)
        self.assertEqual(made["Parma"][0], 8)                                                   # Province
        self.assertEqual(made["Sissa"][0], 15)                                                  # Town
        self.assertEqual(r["ambiguous"], [])

    def test_the_new_province_is_a_second_place_with_its_own_links(self):
        r = run("answer_sissa_1990.txt", self.tree())
        links = [(p["kind"], p.get("child"), p.get("parent")) for p in r["proposals"] if p["kind"] == "add-link"]
        self.assertTrue(any(child == "new:Sissa" or "Sissa" in str(child) for _k, child, _p in links) or links, links)
        self.assertNotIn(("add-link", "parma", "er"), links)                                      # the city keeps its link: nothing is done to it

    def test_a_province_of_the_tree_with_that_name_is_found(self):
        for kind in (8, 12, 3, -1):
            r = run("answer_sissa_1990.txt", self.tree(kind))
            self.assertEqual(self.units(r)[0], ("Parma", "parma"), kind)
            self.assertNotIn("Parma", new_places(r), kind)

    def test_an_area_is_never_a_settlement_and_a_settlement_is_not_barred(self):
        city, province, unknown = self.tree(4), self.tree(8), self.tree(-1)
        for text in ("provincia / province", "state", "Kanton, canton", "county", "region", "Bezirk, district"):
            self.assertTrue(ingest._type_conflict(city, "parma", text), text)
            self.assertFalse(ingest._type_conflict(province, "parma", text), text)
            self.assertFalse(ingest._type_conflict(unknown, "parma", text), text)
        for text in ("comune / municipality", "city", "town", "village", "", None):
            self.assertFalse(ingest._type_conflict(city, "parma", text), text)                 # a settlement mention is matched as before

    def test_a_country_is_not_a_city_of_the_same_name(self):
        t = Tree({"lu": typed("lu", "Luxembourg", 4, lang="en")}, [])
        text = answer("answer_sissa_1990.txt").replace("Italia | stato / state", "Luxembourg | state").replace("Repubblica Italiana", "Luxembourg")
        r = ingest.ingest(t, ingest.parse_structured(text), "1990", aliases={})
        self.assertIn("Luxembourg", [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"])

    def test_the_levels_of_italy_are_all_there(self):
        r = run("answer_sissa_1990.txt", self.tree())
        self.assertEqual([n for n in r["needs"] if n.startswith("the answer has no ")], [])      # province and region are in the answer


class SissaMovedTests(unittest.TestCase):
    """Sissa is inside the CITY Parma in the tree (a link of an earlier run). The answer puts it under the PROVINCE Parma. By the rules of the levels the link to
    the city is wrong (settlements are on one level): the province is added (chosen by itself) and the disconnect from the city is a change to data that
    exists, so it is chosen one by one."""
    def tree(self, old_parent="parma", old_type=4, old_name="Parma"):
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "parma": typed("parma", "Parma", 4, lang="en"),
                  "sissa": typed("sissa", "Sissa", 15, lang="en")}, [])
        if old_parent != "parma":
            t.places[old_parent] = typed(old_parent, old_name, old_type, lang="en")
            t.places[old_parent]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["sissa"]["refs"] = [{"ref": old_parent, "date": EMPTY}]
        return t

    def run_it(self, tree):
        return run("answer_sissa_1990_v2.txt", tree)

    def steps(self, r):
        return {p["kind"]: p for p in r["proposals"] if p.get("child") == "sissa" and p["kind"] in ("add-link", "remove-link")}

    def test_the_province_is_added_and_the_link_to_the_city_is_offered_as_a_disconnect_that_needs_it(self):
        r = self.run_it(self.tree())
        steps = self.steps(r)
        add, cut = steps["add-link"], steps["remove-link"]
        self.assertEqual((add["conflict"], add.get("existing", False), add["position"], add["above"]), (False, False, 0, "parma"))      # before the old link
        self.assertEqual((cut["parent"], cut["existing"], cut["conflict"], cut["inferred"], cut["requires_key"]), ("parma", True, False, True, add["key"]))
        notes = [n for n in r["needs"] if n.startswith("CONFLICT")]
        self.assertEqual(notes, ["CONFLICT: in the tree, Sissa [SISSA] is linked to Parma [PARMA], but the response places it under Provincia di Parma (from 1861), "
                                 "and the existing link is incorrect: settlement places belong to a single tier; nesting settlements is invalid. Result if you disconnect: "
                                 "Sissa [SISSA] will no longer be inside Parma [PARMA]. Not selected automatically: changes to existing data must be approved one by one."])

    def test_nothing_is_cut_to_the_years_before_any_more(self):
        r = self.run_it(self.tree())
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "set-link"])

    def test_the_province_is_made_and_linked_to_the_region(self):
        r = self.run_it(self.tree())
        self.assertEqual(new_places(r)["Provincia di Parma"][0], 8)
        self.assertTrue([p for p in r["proposals"] if p["kind"] == "add-link" and p["parent"] == "er"])

    def test_a_link_to_a_place_that_is_not_wrong_is_kept_and_the_new_one_goes_first(self):
        r = self.run_it(self.tree(old_parent="other", old_type=8, old_name="Piacenza"))                # another province: nothing says it is wrong
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "remove-link"])
        self.assertTrue(any("Sissa [SISSA] is also linked to Piacenza [OTHER], and the response places it under Provincia di Parma (from 1861): both links will be retained"
                            in n for n in r["needs"]), r["needs"])
        self.assertEqual(self.steps(r)["add-link"]["position"], 0)

    def test_a_link_to_another_settlement_is_wrong_too(self):
        for name in ("Fidenza", "Parma Nord"):
            r = self.run_it(self.tree(old_parent="other", old_type=4, old_name=name))
            self.assertEqual([p["parent"] for p in r["proposals"] if p["kind"] == "remove-link"], ["other"], name)

    def test_a_province_of_the_tree_with_the_name_is_not_a_homonym_settlement(self):
        r = self.run_it(self.tree(old_parent="other", old_type=8, old_name="Provincia di Parma"))
        self.assertFalse([n for n in r["needs"] if n.startswith("CONFLICT")])                     # it is the province: matched, and already linked

    def test_the_changes_are_titled_by_what_they_do_and_the_disconnect_brings_the_new_link(self):
        import tempfile
        from placecompleter import session as sess
        s = sess.Session(self.tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Sissa", "1990", engine="manual")
        s.receive(answer("answer_sissa_1990_v2.txt"))
        s.select_all()
        cut = next(c for c in s.changes() if c["title"].startswith("Disconnect "))
        self.assertEqual(cut["title"], "Disconnect «Sissa [SISSA]» from «Parma [PARMA]» (removes hierarchy link; retains place entities)")
        self.assertEqual((cut["selected"], cut["existing"], cut["flag"], cut["confidence_level"]), (False, True, "disconnects place link", "inferred"))
        self.assertIn("Requires the new link", cut["why"])
        self.assertTrue(any(c["selected"] for c in s.changes()))                                  # the addition is chosen by itself
        s.toggle_change(cut["id"])
        self.assertTrue(all(c["selected"] for c in s.changes() if c["existing"] or "Provincia di Parma" in c["title"]))


class NamesInOtherLanguagesTests(unittest.TestCase):
    """A name in another language that is valid on the date is not a contradiction: Sissa, and Sésa (the dialect) valid since 1806."""
    def test_a_dialect_name_valid_today_is_not_a_contradiction_and_does_not_make_everything_unsure(self):
        r = run("answer_sissa_1990_v2.txt", Tree({}, []))
        self.assertFalse([n for n in r["needs"] if n.startswith("THE ANSWER CONTRADICTS ITSELF")], r["needs"])

    def test_the_confidence_of_the_changes_is_not_lowered_for_such_a_name(self):
        import tempfile
        from placecompleter import session as sess
        s = sess.Session(Tree({}, []), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Sissa", "1990", engine="manual")
        s.receive(answer("answer_sissa_1990_v2.txt"))
        self.assertEqual(s._doubts_about_the_answer(), [])
        self.assertNotEqual({c["confidence_level"] for c in s.changes()}, {"unsure"})


class EvidenceFromFreeTextTests(unittest.TestCase):
    """The AI says what a page supports in its own words ("supports name, coordinates and administrative history"), not with the labels of the answer.
    A page that is said to support something else is no evidence for a field; a page that is said nothing definite about is a general one."""
    def test_the_words_are_taken_for_the_fields_they_are_about(self):
        f = ingest._supported_fields
        self.assertEqual(f("supports name, coordinates, status as independent comune in 1996, and 2014 merger"),
                         {"PLACE_NAME_ON_DATE", "OTHER_NAMES", "COORDINATES", "SETTLEMENT_TYPE_ON_DATE", "CONTAINERS"})
        self.assertEqual(f("supports local dialect name Sésa, coordinates, and administrative history"),
                         {"PLACE_NAME_ON_DATE", "OTHER_NAMES", "LANGUAGE", "COORDINATES", "CONTAINERS"})
        self.assertEqual(f("COORDINATES and SETTLEMENT_TYPE_ON_DATE"), {"COORDINATES", "SETTLEMENT_TYPE_ON_DATE"})        # the labels as written still count
        self.assertEqual(f("general details on New York City"), set())                                                      # a general page
        self.assertEqual(f(""), set())
        self.assertEqual(f(None), set())

    def test_a_page_that_supports_other_things_is_no_evidence_for_the_containers(self):
        text = answer("answer_sissa_1990_v2.txt").replace("supports name, coordinates, status as independent comune in 1996, and 2014 merger", "supports coordinates")
        r = ingest.ingest(Tree({}, []), ingest.parse_structured(text), "1990", aliases={})
        province = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Provincia di Parma")
        self.assertEqual([e["url"].split("/")[2] for e in province["evidence"]], ["it.wikipedia.org"])           # "administrative history"; the other says coordinates

class NotesOfTheAnalysisTests(unittest.TestCase):
    """The issues to review say what is to be reviewed, and clearly: no line for a field that says NONE, one line for the links that need nothing, and a
    period that is not changed says who holds the years."""
    def tree(self, links):
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "prov": typed("prov", "Provincia di Parma", 8, lang="en"),
                  "parma": typed("parma", "Parma", 4, lang="en"), "sissa": typed("sissa", "Sissa", 15, lang="en")}, [])
        for child, parent, date in links:
            t.places[child].setdefault("refs", []).append({"ref": parent, "date": date})
        return t

    def run_it(self, tree, text=None):
        return ingest.ingest(tree, ingest.parse_structured(text or answer("answer_sissa_1990_v2.txt")), "1990", aliases=ingest.alias_map([WORLD]))

    def test_a_field_that_says_none_has_no_line(self):
        for none in ("NONE", "None.", "none", "UNKNOWN", "n/a", ""):
            text = answer("answer_sissa_1990_v2.txt").replace("NOTES: NONE", "NOTES: %s" % none).replace("NOT_SURE: NONE", "NOT_SURE: %s" % none)
            r = self.run_it(Tree({}, []), text)
            self.assertFalse([n for n in r["needs"] if n.startswith("the answer's own")], none)

    def test_the_links_that_exist_are_one_line(self):
        t = self.tree([("sissa", "prov", EMPTY), ("prov", "er", EMPTY), ("er", "it", EMPTY)])
        r = self.run_it(t)
        lines = [n for n in r["needs"] if "already exist" in n or "already has a link" in n]
        self.assertEqual(lines, ["These links already exist and require no changes: Sissa [SISSA] -> Provincia di Parma; "
                                 "Provincia di Parma [PROV] -> Emilia-Romagna; Emilia-Romagna [ER] -> Italia"])

    def test_no_line_when_no_link_exists_yet(self):
        r = self.run_it(Tree({}, []))
        self.assertFalse([n for n in r["needs"] if n.startswith("These links already exist")])

    def test_a_period_that_is_not_changed_says_what_the_tree_has_and_who_holds_the_years(self):
        from test_engine import D
        from placecompleter.dates import M_FROM, M_TO
        t = self.tree([("sissa", "prov", D(M_FROM, 1862)), ("sissa", "parma", D(M_TO, 1865)), ("prov", "er", EMPTY), ("er", "it", EMPTY)])
        r = self.run_it(t)
        line = [n for n in r["needs"] if n.startswith("Sissa [SISSA] -> Provincia di Parma:")]
        self.assertEqual(line, ["Sissa [SISSA] -> Provincia di Parma: the response specifies 1861-present, but the tree contains from 1862, and Parma [PARMA] covers the "
                                "intervening years; date period left unchanged for verification"])

    def test_a_gap_that_nothing_holds_is_said_differently(self):
        from test_engine import D
        from placecompleter.dates import M_TO
        t = self.tree([("sissa", "prov", D(M_TO, 1800)), ("prov", "er", EMPTY), ("er", "it", EMPTY)])
        r = self.run_it(t)
        line = [n for n in r["needs"] if n.startswith("Sissa [SISSA] -> Provincia di Parma:")]
        self.assertEqual(len(line), 1)
        self.assertIn("with gaps not covered by the link; date period was left unchanged", line[0])


class MessyLinksTests(unittest.TestCase):
    """The tree of the user after several runs: a direct link to the region that stands first, a link to the province whose period runs backwards, the link to the
    city. Every change to what exists is offered, none is chosen by itself, and when they are chosen Sissa is under the province."""
    def tree(self, links):
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "parma": typed("parma", "Parma", 4, lang="en"),
                  "prov": typed("prov", "Provincia di Parma", 8, lang="en"), "sissa": typed("sissa", "Sissa", 15, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["sissa"]["refs"] = [{"ref": parent, "date": date} for parent, date in links]
        return t

    def run_it(self, tree, **kw):
        return ingest.ingest(tree, ingest.parse_structured(answer("answer_sissa_1990_v2.txt")), "1990", aliases=ingest.alias_map([WORLD]), **kw)

    def kinds(self, r, child="sissa"):
        return sorted((p["kind"], p.get("parent")) for p in r["proposals"] if p.get("child") == child and p["kind"].endswith("link"))

    def test_a_period_never_runs_backwards(self):
        from placecompleter.dates import sdn
        self.assertIsNone(ingest._piece(sdn(1900, 1, 1), sdn(1800, 1, 1)))
        self.assertIsNotNone(ingest._piece(sdn(1800, 1, 1), sdn(1900, 1, 1)))
        self.assertIsNone(ingest._piece(-ingest.INF, ingest.INF))

    def test_a_link_that_ends_before_it_starts_is_offered_the_period_of_the_answer(self):
        from test_engine import D
        from placecompleter.dates import M_SPAN
        r = self.run_it(self.tree([("prov", D(M_SPAN, 1969, y2=1861))]))
        fix = [p for p in r["proposals"] if p["kind"] == "set-link" and p["parent"] == "prov"]
        self.assertEqual(len(fix), 1)
        self.assertEqual((describe(fix[0]["new"]), fix[0]["conflict"], fix[0]["existing"]), ("from 1861", False, True))
        self.assertTrue(any("has an invalid date range" in n and "will replace it if selected" in n for n in r["needs"]), r["needs"])

    def test_a_direct_link_that_stands_first_and_has_years_before_is_offered_to_be_cut_to_them(self):
        from test_engine import D
        from placecompleter.dates import M_FROM
        r = self.run_it(self.tree([("er", D(M_FROM, 1800)), ("prov", D(M_FROM, 1861))]))
        cut = [p for p in r["proposals"] if p["kind"] == "set-link" and p["parent"] == "er"]
        self.assertEqual([(describe(p["new"]), p["existing"]) for p in cut], [("span 1800..1860", True)])            # a year, not "1800-1-2"
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "remove-link"])

    def test_a_direct_link_that_stands_first_and_covers_all_the_years_is_offered_to_be_disconnected(self):
        from test_engine import D
        from placecompleter.dates import M_FROM
        r = self.run_it(self.tree([("er", D(M_FROM, 1946)), ("prov", D(M_FROM, 1861))]))
        cuts = [p for p in r["proposals"] if p["kind"] == "remove-link"]
        self.assertEqual([(p["parent"], p["index"], p["existing"], p.get("requires_key", "")) for p in cuts], [("er", 0, True, "")])      # nothing else is needed: the province link is there
        self.assertFalse([p for p in r["proposals"] if p["kind"] in ("set-link", "move-link")])
        self.assertTrue(any("Disconnecting will lose no data" in n for n in r["needs"]), r["needs"])

    def test_a_direct_link_that_stands_after_the_link_of_the_answer_is_redundant_and_offered_too(self):
        from test_engine import D
        from placecompleter.dates import M_FROM
        r = self.run_it(self.tree([("prov", D(M_FROM, 1861)), ("er", D(M_FROM, 1946))]))
        cuts = [p for p in r["proposals"] if p["kind"] == "remove-link"]
        self.assertEqual([(p["parent"], p["existing"], p.get("requires_key", "")) for p in cuts], [("er", True, "")])        # the link of the answer is there: nothing else needed
        self.assertTrue(any("after link Provincia di Parma) covering the same date range" in n for n in r["needs"]), r["needs"])

    def test_the_link_to_the_city_is_offered_whatever_its_years(self):
        from test_engine import D
        from placecompleter.dates import M_FROM, M_TO
        r = self.run_it(self.tree([("prov", D(M_FROM, 1861)), ("parma", D(M_TO, 1800))]))
        self.assertEqual([(p["kind"], p["parent"]) for p in r["proposals"] if p["kind"] == "remove-link"], [("remove-link", "parma")])

    def test_the_places_of_the_levels_that_were_skipped_are_not_touched(self):
        from test_engine import D
        from placecompleter.dates import M_FROM
        r = self.run_it(self.tree([("prov", D(M_FROM, 1861))]), skip=(1, 2, 3))
        self.assertFalse([n for n in r["needs"] if n.startswith("CONFLICT")], r["needs"])
        self.assertFalse([p for p in r["proposals"] if p["kind"] in ("set-link", "remove-link")])

    def test_the_preview_changes_only_when_the_user_chooses_the_changes_to_what_exists(self):
        import tempfile
        from test_engine import D
        from placecompleter.dates import M_FROM, M_SPAN, M_TO
        from placecompleter import session as sess
        t = self.tree([("er", D(M_FROM, 1946)), ("prov", D(M_SPAN, 1969, y2=1861)), ("parma", D(M_TO, 1861))])
        s = sess.Session(t, tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Sissa", "1990", engine="manual")
        s.receive(answer("answer_sissa_1990_v2.txt"))
        s.select_all()
        self.assertTrue(s.preview()[0].startswith("Sissa, Emilia-Romagna"), s.preview()[0])        # by itself nothing that exists is changed
        s.select_existing()
        self.assertTrue(s.preview()[0].startswith("Sissa, Provincia di Parma"), s.preview()[0])


class OfficialNameTests(unittest.TestCase):
    """The levels between the municipality and the country are written with the word of their type when it is part of the official name (Provincia di Parma),
    and no other name gets a type word (Tel Aviv, Israel, Kfar Hess)."""
    def tree(self, parma_type):
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 9, lang="en"), "parma": typed("parma", "Parma", parma_type, lang="en")}, [])
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        return t

    def sissa(self):
        return answer("answer_sissa_1990.txt").replace("2 | [Parma]", "2 | [Provincia di Parma]")

    def run_it(self, tree):
        return ingest.ingest(tree, ingest.parse_structured(self.sissa()), "1990", aliases=ingest.alias_map([WORLD]))

    def test_the_province_with_its_official_name_is_found_in_the_tree_under_the_short_name(self):
        r = self.run_it(self.tree(8))
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]][0], ("Provincia di Parma", "parma"))
        self.assertNotIn("Provincia di Parma", new_places(r))

    def test_the_province_is_a_place_of_its_own_beside_the_city_of_the_same_name(self):
        r = self.run_it(self.tree(4))                                                              # the tree has the city Parma
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]][0], ("Provincia di Parma", None))
        self.assertEqual(new_places(r)["Provincia di Parma"][0], 8)                                # named as the answer wrote it: two places are not both "Parma"

    def test_the_connecting_words_of_a_name_are_no_part_of_the_name(self):
        for a, b in (("Provincia di Parma", "Parma"), ("Provincia di Reggio Emilia", "Reggio Emilia"), ("Kanton Zürich", "Zürich")):
            self.assertEqual(set(ingest._tokens(a)), set(ingest._tokens(b)), a)
        self.assertEqual(ingest._unit_words("Provincia di Parma"), {"provincia"})                    # "di" is a connector, not a word of a type
        self.assertNotEqual(set(ingest._tokens("Provincia di Parma")), set(ingest._tokens("Provincia di Piacenza")))

    def test_every_form_of_the_question_gives_the_rule_and_the_examples(self):
        for form in ("classic", "dated", "long", "short"):
            text = prompts.build_prompt("Parma", "1990", form)
            self.assertIn("Provincia di Parma", text, form)
            self.assertIn("Kanton Zürich", text, form)
            self.assertIn("Kfar Hess", text, form)
        text = prompts.build_prompt("Parma", "1990")
        self.assertIn("between the municipality and the country (district, county, province, region, canton)", text)
        self.assertIn("Never add a type word to the name of a municipality, city, town, village or the country", text)
        self.assertIn("Israel, not State of Israel", text)


class NameVariantTests(unittest.TestCase):
    def test_a_name_and_a_short_form_of_it_are_one_name(self):
        self.assertTrue(ingest._short_form("New York", "New York City"))
        self.assertTrue(ingest._short_form("Rotterdam", "Rotterdam"))
        self.assertTrue(ingest._short_form("Zürich", "Stadt Zürich"))

    def test_two_different_names_are_not(self):
        self.assertFalse(ingest._short_form("Johnston", "Johnston Station"))                      # Station is part of a name, City is not
        self.assertFalse(ingest._short_form("Pozsony", "Pressburg"))
        self.assertFalse(ingest._short_form("New York", "Old York"))
        self.assertFalse(ingest._short_form("", "Zürich"))

    def test_state_in_the_words_of_a_type_is_the_type_state(self):
        state = Tree({"p": typed("p", "X", 2)}, [])
        country = Tree({"p": typed("p", "X", 1)}, [])
        city = Tree({"p": typed("p", "X", 4)}, [])
        for text in ("state", "State of New York", "Bundesstaat, federal state"):
            self.assertTrue(ingest._type_matches(state, "p", text), text)
            self.assertTrue(ingest._type_matches(country, "p", text), text)
            self.assertFalse(ingest._type_matches(city, "p", text), text)
        self.assertFalse(ingest._type_matches(state, "p", "Bezirk, district"))


class QuestionTests(unittest.TestCase):
    FORMS = ("classic", "short", "dated", "long")

    def test_every_form_still_fills_in_the_place_and_the_date(self):
        for form in self.FORMS:
            text = prompts.build_prompt("Brooklyn", "1990", form)
            self.assertIn("Brooklyn", text, form)
            self.assertIn("1990", text, form)
            self.assertNotIn("{", text, form)

    def test_the_first_column_is_a_level_number_and_not_an_official_code(self):
        for form in ("classic", "dated", "long", "short"):
            self.assertIn("level number" if form != "short" else "level number (1, 2, 3 ...)", prompts.build_prompt("X", "1990", form), form)
        self.assertIn("not an official code", prompts.build_prompt("X", "1990"))

    def test_there_is_a_line_for_the_notes_and_the_answer_is_told_not_to_put_them_in_not_sure(self):
        for form in self.FORMS:
            self.assertIn("NOTES:", prompts.build_prompt("X", "1990", form), form)
        r = ingest.parse_structured(answer("answer_zurich_1990.txt"))
        self.assertIn("ambiguous", r["notes"] + r["not_sure_text"])                               # either way the program shows it

    def test_the_main_place_is_chosen_when_the_name_is_ambiguous_and_the_others_named(self):
        for form in ("classic", "dated", "long"):
            text = prompts.build_prompt("Brooklyn", "1990", form)
            self.assertIn("choose the best-known place", text, form)
            self.assertIn("AMBIGUOUS:", text, form)                                              # still there for the case with no main place

    def test_the_last_level_is_the_sovereign_state_and_the_types_are_generic_english_words(self):
        text = prompts.build_prompt("Rotterdam", "1990")
        self.assertIn("sovereign state", text)
        self.assertIn("generic English type (state, county, province, region, district, municipality, canton ...)", text)
        self.assertIn("the lowest level that is a place, not a building or a street", text)
        self.assertNotIn("borough, municipality ...", text)                                          # the old list mixed size and legal status: it is a closed list now (test_settlement_types.py)
        self.assertIn("exactly one of: metropolis | city | town | village | hamlet | neighborhood | locality", text)

    def test_other_names_are_not_the_current_name_or_a_short_form_of_it(self):
        self.assertIn("not the name above or a short form of it", prompts.build_prompt("X", "1990"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
