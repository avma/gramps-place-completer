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
"""Reading the answer in the fixed template: the REAL answer Google AI gave for Bajmok in 1850."""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"                                 # never the keyring or the files of the user
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"      # never the user's own file
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import cli, complete, gaps, ingest, plan as planlib                  # noqa: E402
from placecompleter.dates import M_FROM, M_NONE, M_SPAN, M_TO, describe                  # noqa: E402
from placecompleter.model import Tree                                                    # noqa: E402
from test_engine import D, EMPTY, event, place                                           # noqa: E402

TT = ingest.TREE_TYPES                                                                       # the custom place types of the tree (data/type-conventions.json)

SAMPLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_bajmok_1850.txt")


def typed(handle, name, ptype, string="", **kw):
    p = place(handle, name, ptype, **kw)
    p["type"] = {"value": ptype, "string": string}
    return p


def tree():
    """The structure of the places in the user's tree around Bajmok."""
    places = [
        typed("hun", "Magyarország", 1, name_date=D(M_FROM, 1000)),
        typed("kais", "Kaisertum Österreich", 0, TT["empire"], name_date=D(M_SPAN, 1804, y2=1867),
              alts=[("Austrian Empire", "en", EMPTY)]),
        typed("prov", "Szerb Vajdaság és Temesi Bánság", 0, TT["province"], name_date=D(M_FROM, 1849), lang="hu",
              alts=[("Voivodeship of Serbia and Banat of Temeschwar", "en", EMPTY)], refs=[("kais", EMPTY)]),
        typed("zk", "Zombori kerület", 0, TT["district"][1], name_date=D(M_SPAN, 1849, y2=1860), refs=[("prov", EMPTY)]),
        typed("zj", "Zombori járás", 0, TT["district"][0], name_date=D(M_SPAN, 1867, y2=1920)),
        typed("zc", "Zombor", 4, name_date=D(M_NONE, 1913), refs=[("hun", EMPTY)]),
        typed("cty", "Bács-Bodrog vármegye", 3, name_date=D(M_FROM, 1849), lang="hu", refs=[("hun", EMPTY)]),
        typed("jar", "Bácsalmási járás", 0, TT["district"][0], name_date=D(M_TO, 1920), refs=[("cty", D(M_SPAN, 1849, y2=1920))]),
        typed("baj", "Bajmok", 16, name_date=D(M_FROM, 1462), lang="hu", refs=[("jar", D(M_TO, 1920))]),
    ]
    by_handle = {p["handle"]: p for p in places}
    by_handle["baj"]["lat"], by_handle["baj"]["lon"] = "45.966667", "19.416667"       # a place with its fields filled: nothing to complete
    return Tree(by_handle, [])


def answer():
    with open(SAMPLE, encoding="utf-8") as fh:
        return ingest.parse_structured(fh.read())


class ParserTests(unittest.TestCase):
    def test_every_field_of_the_real_answer_is_read(self):
        r = answer()
        self.assertEqual((r["name"], r["language"], r["type_value"], r["coordinates"]), ("Bajmok", "de", 16, (45.9667, 19.4167)))
        self.assertEqual([(o["lang"], o["name"], o["from"], o["to"]) for o in r["other_names"]],
                         [("hu", "Bajmok", "1462", None), ("sr", "Бајмок", "1918", None)])
        self.assertEqual([(c["name"], c["from"], c["to"]) for c in r["containers"]],
                         [("Zombor District", "1849", "1860"), ("Batsch-Bodrog", "1849", "1860"),
                          ("Voivodeship of Serbia and Banat of Temeschwar", "1849", "1860")])
        self.assertEqual(r["state"], {"name": "Austrian Empire", "from": "1804", "to": "1867"})
        self.assertEqual(len(r["sources"]), 2)
        self.assertEqual(r["not_sure"], {"LANGUAGE", "SETTLEMENT_TYPE_ON_DATE", "CONTAINERS"})

    def test_a_missing_field_is_simply_absent(self):
        r = ingest.parse_structured("PLACE_NAME_ON_DATE: Hadad\nCOORDINATES: UNKNOWN")
        self.assertEqual((r["name"], r["coordinates"], r["containers"], r["state"]), ("Hadad", None, [], None))

    def test_an_ambiguous_answer_stops_there(self):
        r = ingest.parse_structured("AMBIGUOUS: Zombor, Serbia (45.78, 19.11); Zombor, Slovakia (48.9, 21.2)")
        self.assertIn("Slovakia", " ".join(r["ambiguous"]))
        self.assertIsNone(ingest.ingest(tree(), r, "1850")["selected"])


class MatchingTests(unittest.TestCase):
    def test_the_district_is_the_unit_that_existed_on_that_date(self):
        # three places of the tree resemble "Zombor District"; only one had that name in 1850
        handle, ranked = ingest.match_container(tree(), "Zombor / Sombor District", "District / Bezirk", ingest.parse_date("1850")[1])
        self.assertEqual(handle, "zk")
        self.assertGreater(len(ranked), 1)

    def test_the_district_in_1900_is_another_place(self):
        handle, _ = ingest.match_container(tree(), "Zombor District", "District / Bezirk", ingest.parse_date("1900")[1])
        self.assertEqual(handle, "zj")

    def test_spelling_differences_and_the_type_word_are_tolerated(self):
        t, sv = tree(), ingest.parse_date("1850")[1]
        self.assertEqual(ingest.match_container(t, "Batsch-Bodrog", "Komitat / County", sv)[0], "cty")
        self.assertEqual(ingest.match_container(t, "Voivodeship of Serbia and Banat of Temeschwar", "Kronland / Crownland", sv)[0], "prov")
        self.assertEqual(ingest.match_container(t, "Austrian Empire", "empire", sv)[0], "kais")

    def test_an_unknown_unit_is_not_forced_onto_a_place(self):
        self.assertIsNone(ingest.match_container(tree(), "Duchy of Nowhere", "Duchy", 2400000)[0])


class ScreenTests(unittest.TestCase):
    def setUp(self):
        self.t = tree()
        self.r = ingest.ingest(self.t, answer(), "1850", skip={2})        # the user drops the doubtful Bács-Bodrog level

    def test_the_place_is_the_one_the_tree_already_has(self):
        self.assertEqual(self.r["mode"], "existing")
        self.assertEqual(self.r["similar"][0]["label"], "Bajmok [BAJ]")

    def test_what_gramps_would_display_follows_the_answer(self):
        self.assertEqual(self.r["preview"], ["Bajmok", "Zombori kerület", "Szerb Vajdaság és Temesi Bánság", "Kaisertum Österreich"])

    def test_the_old_link_is_kept_and_the_new_one_is_placed_before_it_so_each_year_has_its_chain(self):
        kinds = sorted(p["kind"] for p in self.r["proposals"])
        self.assertEqual(kinds, ["add-link", "add-url", "set-name-date", "set-name-date"])    # nothing that exists is changed (the link is an addition)
        trial = gaps.apply(self.t, self.r["proposals"])
        trial.events = [event("a", "baj", D(M_NONE, 1845, 5, 1)), event("b", "baj", D(M_NONE, 1850, 5, 1)),
                        event("c", "baj", D(M_NONE, 1900, 5, 1))]
        shown = {r["event"]["id"]: ", ".join(r["chain"]["names"]) for r in gaps.analyse(trial)}
        self.assertEqual(shown["A"], "Bajmok, Bácsalmási járás")      # 1845: as before (the tree's link to the county starts in 1849)
        self.assertEqual(shown["B"], "Bajmok, Zombori kerület, Szerb Vajdaság és Temesi Bánság, Kaisertum Österreich")
        self.assertEqual(shown["C"], "Bajmok, Bácsalmási járás, Bács-Bodrog vármegye, Magyarország")

    def test_everything_is_an_assumption_and_nothing_is_a_conflict_or_a_change_to_existing_data(self):
        self.assertTrue(all(p["basis"] == "assumption" for p in self.r["proposals"]))
        self.assertFalse(any(p["conflict"] or p.get("existing") for p in self.r["proposals"]))
        self.assertTrue(any("is also linked to Bácsalmási járás [JAR], and the response places it under Zombor District" in n and "both links will be retained" in n
                            for n in self.r["needs"]))
        plan = planlib.make_plan(self.t, self.r["proposals"])
        automatic = planlib.select(plan, bases={"assumption"})
        self.assertEqual(sorted(p["kind"] for p in automatic), ["add-link", "add-url", "set-name-date", "set-name-date"])       # (with the Wikipedia link of the answer)
        link = next(p for p in plan["proposals"] if p["kind"] == "add-link")
        self.assertEqual(link["position"], 0)                                                         # before the old link: Gramps shows the first that fits the date

    def test_with_all_three_levels_the_screen_shows_what_the_tree_disagrees_with(self):
        full = ingest.ingest(self.t, answer(), "1850")
        text = " ".join(full["needs"])
        # the tree keeps Bács-Bodrog under Hungary while the answer puts it under the Voivodeship: not wrong in itself, so both are kept ...
        self.assertIn("Bács-Bodrog vármegye [CTY] is also linked to Magyarország [HUN], and the response places it under", text)
        self.assertIn("both links will be retained, with the new link prioritized for matching years", text)
        self.assertNotIn("CONFLICT", text)
        # ... whereas the level put between the kerület and its parent is only an insertion, said without the word CONFLICT
        self.assertIn("Zombori kerület [ZK] is also linked directly to Szerb Vajdaság és Temesi Bánság [PROV] (listed after the link to Batsch-Bodrog", text)
        self.assertNotIn("CONFLICT", text)
        self.assertEqual(len([p for p in full["proposals"] if p["kind"] == "add-place"]), 0)   # all four units exist already

    def test_the_screen_renders(self):
        text = complete.render(self.r)
        self.assertIn("GRAMPS WOULD DISPLAY: Bajmok, Zombori kerület", text)


class NewPlaceTests(unittest.TestCase):
    def test_a_place_that_is_not_in_the_tree_is_created_with_its_units(self):
        t = tree()
        rec = answer()
        rec["name"] = "Bajmokpuszta"
        r = ingest.ingest(t, rec, "1850", skip={2})
        made = [p for p in r["proposals"] if p["kind"] == "add-place"]
        self.assertEqual(len(made), 1)
        self.assertEqual((made[0]["names"][0]["value"], made[0]["type_value"], made[0]["lat"]), ("Bajmokpuszta", 16, "45.9667"))
        self.assertEqual([u["path"] for u in made[0]["urls"]], ["https://en.wikipedia.org/wiki/Bajmok"])      # the Wikipedia page of the answer is the link of the new place
        self.assertEqual(r["preview"][:2], ["Bajmokpuszta", "Zombori kerület"])

    def test_an_unknown_unit_becomes_a_new_place_of_the_users_own_type(self):
        t = tree()
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: Hadad\nCOORDINATES: 47.1, 23.0\nCONTAINERS: 1 | Silvania Region | Region | 1850-1900 | Hungary")
        r = ingest.ingest(t, rec, "1870")
        unit = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Silvania Region")
        self.assertEqual(unit["type_value"], 9)                  # Region: the type of Gramps


SAMPLE_1900 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_bajmok_1900.txt")
PACK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "hu-habsburg.json")


def answer_1900():
    with open(SAMPLE_1900, encoding="utf-8") as fh:
        return ingest.parse_structured(fh.read())


def plain_tree():
    """The tree without any English names: only what the regional pack knows can connect the answer to it."""
    t = tree()
    for h in ("kais", "prov", "hun"):
        t.places[h]["alt_names"] = []
    return t


class Answer1900Tests(unittest.TestCase):
    def test_text_the_page_adds_after_the_answer_is_not_part_of_it(self):
        r = answer_1900()
        self.assertEqual(r["not_sure"], set())                          # "NOT_SURE: None" and the sentence after it
        self.assertEqual(len(r["containers"]), 2)
        self.assertEqual(r["sources_without_link"], ["wikipedia.org", "wikipedia.org"])
        self.assertEqual(len(r["sources"]), 1)

    def test_the_answer_agrees_with_the_tree_and_changes_only_what_it_adds(self):
        aliases = ingest.alias_map([PACK])
        r = ingest.ingest(plain_tree(), answer_1900(), "1900", aliases=aliases)
        self.assertEqual(r["preview"], ["Bajmok", "Bácsalmási járás", "Bács-Bodrog vármegye", "Magyarország"])
        self.assertEqual(sorted(p["kind"] for p in r["proposals"]), ["add-url", "set-link", "set-name-date", "set-name-language", "set-name-language"])
        link = next(p for p in r["proposals"] if p["kind"] == "add-url")                  # the page of the lexicon: a site of unknown kind, offered and not chosen by itself
        self.assertEqual((link["place"], link["url_kind"], link["optional"]), ("baj", "other", True))
        # the names of the units that have no language get the language of the state they belonged to (the Kingdom of Hungary: Hungarian)
        self.assertEqual(sorted((p["place"], p["value"], p["lang"]) for p in r["proposals"] if p["kind"] == "set-name-language"),
                         [("hun", "Magyarország", "hu"), ("jar", "Bácsalmási járás", "hu")])
        widen = next(p for p in r["proposals"] if p["kind"] == "set-link")
        self.assertEqual((widen["child"], widen["parent"], widen["conflict"]), ("jar", "cty", False))
        self.assertEqual(widen["new"]["dateval"], [0, 0, 1802, False, 0, 0, 1920, False])      # the county link now starts in 1802

    def test_the_name_of_the_county_is_widened_too_or_it_would_show_a_question_mark(self):
        r = ingest.ingest(plain_tree(), answer_1900(), "1900", aliases=ingest.alias_map([PACK]))
        name = next(p for p in r["proposals"] if p["kind"] == "set-name-date")
        self.assertEqual((name["place"], name["value"], name["old"]["modifier"], name["new"]["modifier"]), ("cty", "Bács-Bodrog vármegye", M_FROM, M_FROM))
        self.assertLess(name["new"]["sortval"], name["old"]["sortval"])             # it starts earlier than before

    def test_widening_the_county_link_closes_the_old_gap_before_1849(self):
        r = ingest.ingest(plain_tree(), answer_1900(), "1900", aliases=ingest.alias_map([PACK]))
        trial = gaps.apply(plain_tree(), r["proposals"])
        trial.events = [event("a", "baj", D(M_NONE, 1845, 5, 1))]
        self.assertEqual(", ".join(gaps.analyse(trial)[0]["chain"]["names"]), "Bajmok, Bácsalmási járás, Bács-Bodrog vármegye, Magyarország")

    def test_the_english_state_name_is_connected_to_the_tree_by_the_regional_pack(self):
        without = ingest.ingest(plain_tree(), answer_1900(), "1900")
        with_pack = ingest.ingest(plain_tree(), answer_1900(), "1900", aliases=ingest.alias_map([PACK]))
        # without the pack the name is not found, but the tree suggests the place (Magyarország holds Bács-Bodrog vármegye there): it is asked
        # about, and no second Hungary is made until the user has answered
        self.assertEqual([(a["name"], [c["label"] for c in a["candidates"]]) for a in without["ambiguous"]], [("Kingdom of Hungary", ["Magyarország [HUN]"])])
        self.assertFalse(any(p["kind"] == "add-place" and p["names"][0]["value"] == "Kingdom of Hungary" for p in without["proposals"]))
        self.assertFalse(any(p["kind"] == "add-place" for p in with_pack["proposals"]))
        self.assertEqual(with_pack["ambiguous"], [])                                              # with the pack nobody is asked

    def test_the_1850_answer_finds_the_empire_and_the_voivodeship_through_the_pack(self):
        r = ingest.ingest(plain_tree(), answer(), "1850", skip={2}, aliases=ingest.alias_map([PACK]))
        self.assertEqual(r["preview"], ["Bajmok", "Zombori kerület", "Szerb Vajdaság és Temesi Bánság", "Kaisertum Österreich"])
        self.assertFalse(any(p["kind"] == "add-place" for p in r["proposals"]))

    def test_coordinates_are_compared_with_those_of_the_tree(self):
        t = plain_tree()
        t.places["baj"]["lat"], t.places["baj"]["lon"] = "45.966667", "19.416667"
        r = ingest.ingest(t, answer_1900(), "1900", aliases=ingest.alias_map([PACK]))
        row = next(x for x in r["rows"] if x["field"] == "coordinates")
        self.assertIn("km apart, kept", row["value"])


class UnitedStatesTests(unittest.TestCase):
    """A place outside the Habsburg lands: the reader must not invent an empire or a duplicate country."""
    MOCK = """PLACE_NAME_ON_DATE: Johnston
LANGUAGE: en
OTHER_NAMES: none
SETTLEMENT_TYPE_ON_DATE: city
COORDINATES: 41.6731, -93.6975
CONTAINERS:
1 | Polk County | county | 1846-present | Iowa
2 | Iowa | state | 1846-present | United States
STATE_ON_DATE: United States | 1776-present
NOT_SURE: None
"""

    def us_tree(self):
        return Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])

    def test_a_modern_country_is_created_as_a_country_not_as_an_empire(self):
        r = ingest.ingest(self.us_tree(), ingest.parse_structured(self.MOCK), "1950")
        top = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "United States")
        self.assertEqual((top["type_value"], top["type_string"]), (1, ""))
        county = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Polk County")
        self.assertEqual(county["type_value"], 3)

    def test_the_world_pack_connects_united_states_to_the_tree_usa(self):
        world = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "world-basics.json")
        r = ingest.ingest(self.us_tree(), ingest.parse_structured(self.MOCK), "1950", aliases=ingest.alias_map([world]))
        self.assertEqual(r["preview"], ["Johnston", "Polk County", "Iowa", "USA"])
        self.assertEqual(sorted(p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"), ["Johnston", "Polk County"])

    def test_negative_longitudes_none_and_present_are_read(self):
        rec = ingest.parse_structured(self.MOCK)
        self.assertEqual(rec["coordinates"], (41.6731, -93.6975))
        self.assertEqual((rec["other_names"], rec["state"]["to"], rec["containers"][0]["to"]), ([], None, None))

    def test_the_hebrew_name_of_a_country_in_the_tree_is_found_through_the_pack(self):
        world = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "world-basics.json")
        names = next(p["names"] for p in json.load(open(world, encoding="utf-8"))["places"] if p["key"] == "israel")
        hebrew_name = next(n for n in names if re.search("[\u0590-\u05ff]", n))                      # the name the pack gives in the language of the tree
        handle, _ = ingest.match_container(Tree({"il": typed("il", hebrew_name, 1)}, []), "Israel", "state", 2400000,
                                           aliases=ingest.alias_map([world]))
        self.assertEqual(handle, "il")


SAMPLE_JOHNSTON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_1950.txt")
WORLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "world-basics.json")


class JohnstonTests(unittest.TestCase):
    """The real answer Google AI mode gave for a small Iowa city: a place far from the Habsburg lands."""
    def run_it(self):
        with open(SAMPLE_JOHNSTON, encoding="utf-8") as fh:
            rec = ingest.parse_structured(fh.read())
        t = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])
        return ingest.ingest(t, rec, "1950", aliases=ingest.alias_map([WORLD]))

    def test_no_place_is_linked_to_itself(self):
        r = self.run_it()
        links = [(p["child"], p["parent"]) for p in r["proposals"] if p["kind"] == "add-link"]
        self.assertFalse([1 for c, p in links if c == p])
        self.assertEqual(links, [("new:ai-johnston", "new:ai-polkcounty"), ("new:ai-polkcounty", "iowa"), ("iowa", "usa")])

class DateMattersTests(unittest.TestCase):
    """The same text, read for two dates: the name follows the former names the answer itself lists."""
    def run_year(self, year):
        with open(SAMPLE_JOHNSTON, encoding="utf-8") as fh:
            rec = ingest.parse_structured(fh.read())
        t = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])
        return ingest.ingest(t, rec, year, aliases=ingest.alias_map([WORLD]))

    def test_in_1995_the_place_is_johnston(self):
        r = self.run_year("1995")
        self.assertEqual(r["preview"], ["Johnston", "Polk County", "Iowa", "USA"])
        self.assertFalse(any("CONTRADICTS" in n for n in r["needs"]))

SAMPLE_JOHNSTON_V2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_1950_v2.txt")


class JohnstonSecondAnswerTests(unittest.TestCase):
    """The answer Google gave once the question asked for the date: type and name of 1950, with links around the names."""
    def rec(self):
        with open(SAMPLE_JOHNSTON_V2, encoding="utf-8") as fh:
            return ingest.parse_structured(fh.read())

    def tree(self):
        return Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])

    def test_the_links_google_puts_around_names_are_removed(self):
        r = self.rec()
        self.assertEqual([c["name"] for c in r["containers"]], ["Webster Township", "Polk County", "Iowa"])
        self.assertEqual((r["type_text"], r["type_value"]), ("unincorporated community", 6))
        self.assertEqual(len(r["sources"]), 2)

    def test_a_township_gets_a_type_of_its_own_and_is_not_left_open(self):
        r = ingest.ingest(self.tree(), self.rec(), "1950", aliases=ingest.alias_map([WORLD]))
        township = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Webster Township")
        self.assertEqual((township["type_value"], township["type_string"]), (0, "Township"))       # Gramps has no township: the unit gets one
        self.assertIn("1878", " ".join(str(v) for v in township["names"][0]["date"]["dateval"]))

SAMPLE_STATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_station_1950.txt")


class CompactAnswerTests(unittest.TestCase):
    """A shorter answer (probably from a short form): right name and type for 1950, but pipes in the coordinates, a county
    called "Polk", one level only and no country."""
    def rec(self):
        with open(SAMPLE_STATION, encoding="utf-8") as fh:
            return ingest.parse_structured(fh.read())

    def tree(self):
        return Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])

    def test_coordinates_separated_by_a_pipe_are_read(self):
        self.assertEqual(self.rec()["coordinates"], (41.6736, -93.6977))

    def test_a_repeated_type_is_shown_once(self):
        r = self.rec()
        self.assertEqual((r["type_text"], r["type_value"]), ("unincorporated community", 6))

    def test_the_county_is_created_with_its_full_name(self):
        r = ingest.ingest(self.tree(), self.rec(), "1950")
        names = [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"]
        self.assertEqual(names, ["Johnston Station", "Polk County"])
        self.assertEqual(r["preview"], ["Johnston Station", "Polk County", "Iowa"])

    def test_a_chain_that_stops_at_a_state_is_pointed_out(self):
        r = ingest.ingest(self.tree(), self.rec(), "1950")
        self.assertTrue(any("terminates at state «Iowa» without national container" in n for n in r["needs"]))

    def test_with_the_country_in_the_tree_the_chain_is_complete_and_nothing_is_pointed_out(self):
        t = self.tree()
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        r = ingest.ingest(t, self.rec(), "1950")
        self.assertEqual(r["preview"], ["Johnston Station", "Polk County", "Iowa", "USA"])
        self.assertFalse(any("no country above it" in n for n in r["needs"]))


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SAMPLE_V3 = os.path.join(DATA_DIR, "answer_johnston_1950_v3.txt")


class CrossAnswerTests(unittest.TestCase):
    """The same place asked several times gives different answers: where they disagree is the first thing to check."""
    def rec(self):
        with open(SAMPLE_V3, encoding="utf-8") as fh:
            return ingest.parse_structured(fh.read())

    def messages(self):
        return ingest.compare_with_saved(self.rec(), DATA_DIR, "1950", skip_path=SAMPLE_V3)

    def test_the_links_and_the_doubled_types_of_the_newest_answer_are_read(self):
        r = self.rec()
        self.assertEqual([(c["name"], c["type"]) for c in r["containers"]], [("Webster Township", "township"), ("Polk County", "county"), ("Iowa", "state")])
        self.assertEqual(r["other_names"][0]["name"], "Johnston Station")
        self.assertEqual(r["not_sure"], set())

    def test_the_start_of_a_unit_that_two_answers_give_differently_is_reported(self):
        self.assertIn("Webster Township: valid 1846-present here, 1878-present in answer_johnston_1950_v2.txt", self.messages())

    def test_the_end_of_a_former_name_is_reported(self):
        self.assertIn("name 'Johnston Station': 1905-1970 here, 1905-1969 in answer_johnston_1950_v2.txt", self.messages())

    def test_the_type_and_the_name_on_the_same_date_are_compared(self):
        m = " | ".join(self.messages())
        self.assertIn("'city' in answer_johnston_1950.txt", m)
        self.assertIn("answer_johnston_station_1950.txt says 'Johnston Station'", m)

    def test_coordinates_that_are_more_than_a_kilometre_apart_are_reported(self):
        self.assertTrue(any(m.startswith("coordinates are 1.4 km apart") for m in self.messages()))

    def test_answers_about_other_places_are_left_out(self):
        m = " | ".join(self.messages())
        self.assertNotIn("bajmok", m.lower())
        self.assertNotIn("ambiguous", m.lower())

    def test_the_name_and_type_are_not_compared_across_different_dates(self):
        m = ingest.compare_with_saved(self.rec(), DATA_DIR, "1995", skip_path=SAMPLE_V3)
        self.assertFalse([x for x in m if "type on this date" in x or "names the place" in x])
        self.assertTrue([x for x in m if x.startswith("Webster Township")])          # but the facts that do not depend on the date are

    def test_the_command_prints_the_disagreements(self):
        from test_agent_loop import write_db
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "t.db")
            write_db(Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, []), db)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.main(["ingest-text", SAMPLE_V3, "--date", "1950", "--db", db, "--compare-dir", DATA_DIR, "--out", os.path.join(tmp, "p.json")])
            self.assertIn("CONFLICTS WITH SAVED RESPONSE: Webster Township: valid 1846-present here, 1878-present in answer_johnston_1950_v2.txt", buf.getvalue())


SAMPLE_CLAUDE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_johnston_1950_claude.txt")


class ApiAnswerTests(unittest.TestCase):
    """The real answer of the Claude API: a code or UNKNOWN in the number column, remarks inside fields, partial periods, a paragraph
    of doubts. The word UNKNOWN once matched a place of the user's tree (Auschwitz-Birkenau)."""
    def rec(self):
        with open(SAMPLE_CLAUDE, encoding="utf-8") as fh:
            return ingest.parse_structured(fh.read())

    def tree(self):
        return Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1)}, [])

    def tree_with_a_place_named_unknown(self):
        t = self.tree()
        t.places["ausch"] = typed("ausch", "Auschwitz-Birkenau", 0, "Death Camp")
        t.places["ausch"]["alt_names"] = [{"value": "Unknown", "lang": "", "date": t.places["ausch"]["name"]["date"]}]
        t.places["ausch"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        return t

    def test_the_remark_is_not_part_of_the_name(self):
        r = self.rec()
        self.assertEqual((r["name"], r["name_remark"]), ("Johnston", "the community was also called Johnston Station"))

    def test_the_first_column_is_a_number_a_code_or_unknown_and_the_unit_is_the_second(self):
        r = self.rec()
        self.assertEqual([(c["name"], c["type"], c["from"], c["to"]) for c in r["containers"]],
                         [("Webster Township", "township", None, None), ("Polk County", "county", "1846", None), ("Iowa", "state", "1846", None)])
        self.assertEqual(r["unit_notes"], ["Webster Township: the answer remarks: the current city also covers Jefferson Township"])

    def test_a_period_with_an_unknown_start_or_end_is_read(self):
        self.assertEqual(ingest._period("UNKNOWN-1969"), (None, "1969"))
        self.assertEqual(ingest._period("1846-?"), ("1846", None))
        self.assertEqual(ingest._period("UNKNOWN-UNKNOWN"), (None, None))
        self.assertEqual(ingest._period("1846-present"), ("1846", None))
        r = self.rec()
        self.assertEqual([(o["name"], o["from"], o["to"]) for o in r["other_names"]],
                         [("Johnston Station", None, "1969"), ("Beaver Creek Settlement", None, None), ("Ridgedale", None, None), ("Huntsville", None, None)])

    def test_a_unit_written_in_the_type_column_is_still_read_from_there(self):
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: X\nCONTAINERS:\nUNKNOWN | UNKNOWN | Webster Township (the current city also covers Jefferson) | UNKNOWN | United States")
        self.assertEqual([c["name"] for c in rec["containers"]], ["Webster Township"])
        self.assertTrue(any("written where the type belongs" in n for n in rec["unit_notes"]))

    def test_a_list_of_labels_in_the_not_sure_line_is_not_a_paragraph(self):
        self.assertEqual(ingest.parse_structured("PLACE_NAME_ON_DATE: X\nNOT_SURE: CONTAINERS, LANGUAGE")["not_sure_text"], "")
        self.assertEqual(ingest.parse_structured("PLACE_NAME_ON_DATE: X\nNOT_SURE: None")["not_sure_text"], "")

    def test_the_word_unknown_is_never_matched_to_a_place(self):
        for word in ("UNKNOWN", "unknown", "?", "N/A", "none", ""):
            self.assertEqual(ingest.match_container(self.tree_with_a_place_named_unknown(), word, "township", 2400000), (None, []), word)

    def test_nothing_of_the_tree_is_touched(self):
        r = ingest.ingest(self.tree_with_a_place_named_unknown(), self.rec(), "1950", aliases=ingest.alias_map([WORLD]))
        self.assertFalse(any("ausch" in (p.get("child"), p.get("parent"), p.get("place")) for p in r["proposals"]))
        self.assertFalse(any("Auschwitz" in n for n in r["needs"]))

    def test_a_name_written_without_brackets_is_read(self):
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: Hadad\nOTHER_NAMES: en: Huntsville\nhu: Hadad (1876-1918)")
        self.assertEqual([(o["name"], o["from"]) for o in rec["other_names"]], [("Huntsville", None), ("Hadad", "1876")])

    def test_a_unit_that_is_unknown_everywhere_is_left_out_with_a_note(self):
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: Hadad\nCONTAINERS:\n1 | UNKNOWN | UNKNOWN | UNKNOWN | Romania\n2 | Sălaj County | county | 1876-1918 | Hungary")
        self.assertEqual([c["name"] for c in rec["containers"]], ["Sălaj County"])
        self.assertTrue(any("without a unit name was left out" in n for n in rec["unit_notes"]))


class CommandLineTests(unittest.TestCase):
    def test_the_command_prints_the_screen_and_writes_a_plan(self):
        from test_agent_loop import write_db
        with tempfile.TemporaryDirectory() as tmp:
            db, out = os.path.join(tmp, "t.db"), os.path.join(tmp, "plan.json")
            write_db(tree(), db)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = cli.main(["ingest-text", SAMPLE, "--date", "1850", "--db", db, "--skip", "2", "--out", out, "--compare-dir", tmp])
            self.assertEqual(code, 0)
            self.assertIn("GRAMPS WOULD DISPLAY: Bajmok, Zombori kerület", buf.getvalue())
            self.assertEqual(len(planlib.load_plan(out)["proposals"]), 5)             # (4, the language of the name of a unit from its state, and the link of the answer)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class InsertedLevelTests(unittest.TestCase):
    """The user's own screen: "City of Johnston" is linked directly to Iowa; the answer puts Polk County in between."""
    def tree(self):
        t = Tree({"iowa": typed("iowa", "Iowa", 2), "usa": typed("usa", "USA", 1), "city": typed("city", "City of Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        return t

    def run_it(self, year="1995"):
        rec = ingest.parse_structured("PLACE_NAME_ON_DATE: City of Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
                                      "1 | Polk | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\n"
                                      "STATE_ON_DATE: United States | 1776-present\n")
        return ingest.ingest(self.tree(), rec, year, aliases=ingest.alias_map([WORLD]))

    def test_a_level_put_between_a_place_and_its_parent_is_not_a_conflict(self):
        r = self.run_it()
        self.assertFalse(any(p["conflict"] for p in r["proposals"]))
        self.assertFalse(any("CONFLICT" in n for n in r["needs"]))
        self.assertEqual([p["kind"] for p in r["proposals"] if p.get("refines")], ["add-link"])          # the old link is not touched
        self.assertTrue(any("is also linked directly to Iowa [IOWA] (listed after the link to Polk): it applies only to the years before this link takes effect" in n for n in r["needs"]))

    def test_the_four_steps_are_one_bundle_and_the_result_is_the_chain_through_the_new_level(self):
        r = self.run_it()
        self.assertEqual(len({p["bundle"] for p in r["proposals"] if p["bundle"]}), 1)
        self.assertEqual(r["preview"], ["Johnston", "Polk County", "Iowa", "USA"])          # all proposals applied, the rename of the place too

    def test_the_new_link_goes_before_the_old_one_and_the_old_one_is_offered_to_be_cut_to_the_years_before(self):
        """Gramps uses the first link that fits the date: put before the undated link to Iowa, the new one is used for its years. The old link is redundant for those
        years: it is offered to be kept only for the years before, a change to what exists that the user chooses (and that needs the new link)."""
        r = self.run_it()
        t = self.tree()
        link = next(p for p in r["proposals"] if p["kind"] == "add-link" and p["child"] == "city")
        self.assertEqual((link["position"], link["above"]), (0, "iowa"))
        cut = [p for p in r["proposals"] if p["kind"] == "set-link"]
        self.assertEqual([(p["parent"], p["existing"], p["requires_key"], describe(p["new"])) for p in cut], [("iowa", True, link["key"], "to 1846")])
        by_itself = [p for p in r["proposals"] if not p.get("existing")]                                 # what the window selects: the old link is not touched
        after = gaps.apply(t, by_itself)
        self.assertEqual([ref["ref"] for ref in after.places["city"]["refs"]], ["new:ai-polkcounty", "iowa"])
        self.assertEqual(after.places["city"]["refs"][1]["date"], EMPTY)

    def test_the_years_before_the_new_level_keep_the_old_chain(self):
        r = self.run_it()
        self.assertEqual(ingest.preview_for(self.tree(), r["proposals"], r["child"], "1995")[0], ["Johnston", "Polk County", "Iowa", "USA"])
        no_fill = [p for p in r["proposals"] if p["kind"] != "set-name-date"]         # (a name given a period would show "?" before it)
        self.assertEqual(ingest.preview_for(self.tree(), no_fill, r["child"], "1800")[0], ["Johnston", "Iowa", "USA"])
        self.assertEqual(ingest.preview_for(self.tree(), r["proposals"], r["child"], "1800")[0], ["Johnston", "?", "USA"])     # the cost of that choice

    def test_the_chain_is_complete_only_with_all_the_steps_of_the_change(self):
        r = self.run_it()
        place = next(p for p in r["proposals"] if p["kind"] == "add-place")
        first = next(p for p in r["proposals"] if p["kind"] == "add-link" and p["child"] == "city")
        up = next(p for p in r["proposals"] if p["kind"] == "add-link" and p["child"] == place["handle"])
        self.assertEqual(ingest.preview_for(self.tree(), [place, first], r["child"], "1995")[0], ["City of Johnston", "Polk County"])      # stops there
        self.assertEqual(ingest.preview_for(self.tree(), [place, first, up], r["child"], "1995")[0],
                         ["City of Johnston", "Polk County", "Iowa", "USA"])                    # (the rename is a choice of its own)


class OtherNamesOfAUnitTests(unittest.TestCase):
    """The user's Iowa has the names Iowa, Iowa (twice), Hawkeye State and IA, none with a period; the answer gives the state "Iowa" the
    years 1846-present. Only the names that ARE Iowa get that period: a nickname and an abbreviation of the same place are not what the
    answer dated (they were all given it before, so the same choice appeared again and again)."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\n"
              "STATE_ON_DATE: United States | 1776-present\n")

    def run_it(self, alts):
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en", alts=alts), "usa": typed("usa", "USA", 1, lang="en"),
                  "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        return ingest.ingest(t, ingest.parse_structured(self.ANSWER), "1995", aliases={})

    def given_a_period(self, r):
        return [(p["value"], p["index"]) for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "iowa"]

    def test_a_nickname_and_an_abbreviation_of_the_place_get_no_period(self):
        r = self.run_it([("Hawkeye State", "en", EMPTY), ("IA", "en", EMPTY)])
        self.assertEqual(self.given_a_period(r), [("Iowa", 0)])

    def test_a_name_that_is_in_the_place_twice_gets_the_period_twice(self):
        r = self.run_it([("Iowa", "en", EMPTY), ("Hawkeye State", "en", EMPTY), ("IA", "en", EMPTY)])
        self.assertEqual(self.given_a_period(r), [("Iowa", 0), ("Iowa", 1)])

class RomanianCountyTests(unittest.TestCase):
    """Deva was linked to the county Județul Hunedoara; the answer calls the county Hunedoara (1925-1938). The county was not recognised: a second
    county Hunedoara of an unknown type was made, with the old link cut around it. The county is now recognised, and what it lacks is filled."""
    ANSWER = ("PLACE_NAME_ON_DATE: Deva\nLANGUAGE: ro\nOTHER_NAMES:\nhu: Déva (1867-1918)\nSETTLEMENT_TYPE_ON_DATE: city (oraș)\n"
              "CONTAINERS:\n1 | Hunedoara | county (județ) | 1925-1938 | Romania\nSTATE_ON_DATE: Romania | 1918-present\n")

    def tree(self, ptype=3, string="", name_date=None, lang="", deva_name_date=None, extra=None):
        t = Tree({"ro": typed("ro", "România", 1, lang="ro"),
                  "hun": typed("hun", "Județul Hunedoara", ptype, string, name_date=name_date, lang=lang),
                  "deva": typed("deva", "Deva", 4, name_date=deva_name_date), **(extra or {})}, [])
        t.places["hun"]["refs"] = [{"ref": "ro", "date": EMPTY}]
        t.places["deva"]["refs"] = [{"ref": "hun", "date": EMPTY}]
        return t

    def run_it(self, t, text=None, date="1930", choices=None):
        return ingest.ingest(t, ingest.parse_structured(text or self.ANSWER), date, aliases={}, choices=choices)

    def made(self, r):
        return [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"]

    def test_the_county_is_recognised_whatever_state_its_type_and_its_name_periods_are_in(self):
        for label, tr_ in (("county, undated", self.tree()), ("custom type", self.tree(0, "custom county")), ("no type", self.tree(-1)),
                           ("name from 1938", self.tree(3, name_date=D(M_FROM, 1938))),
                           ("custom type, name from 1938", self.tree(0, "custom county", name_date=D(M_FROM, 1938))),
                           ("name until 1925", self.tree(3, name_date=D(M_SPAN, 1800, y2=1925)))):
            r = self.run_it(tr_)
            self.assertEqual(self.made(r), [], label)
            self.assertEqual([u["handle"] for u in r["units"]], ["hun", "ro"], label)

    def test_the_answer_may_also_give_the_full_name(self):
        r = self.run_it(self.tree(0, "custom county", name_date=D(M_FROM, 1938)), self.ANSWER.replace("1 | Hunedoara", "1 | Județul Hunedoara"))
        self.assertEqual((self.made(r), [u["handle"] for u in r["units"]]), ([], ["hun", "ro"]))

    def test_a_city_of_the_same_name_is_not_the_county_and_nobody_needs_to_be_asked(self):
        """The answer names an area (a county) and the tree has a city with the same name: the city cannot be it, so the county is the only one."""
        city = {"city": typed("city", "Hunedoara", 4, lang="ro")}
        r = self.run_it(self.tree(extra=city))
        self.assertEqual((self.made(r), r["ambiguous"], [u["handle"] for u in r["units"]]), ([], [], ["hun", "ro"]))
        full = self.run_it(self.tree(extra=city), self.ANSWER.replace("1 | Hunedoara", "1 | Județul Hunedoara"))
        self.assertEqual(([a for a in full["ambiguous"]], [u["handle"] for u in full["units"]]), ([], ["hun", "ro"]))

    def test_the_county_of_a_city_is_still_another_place(self):
        """A county that has the name of a city is not the city; the tree holds the place of Deva as a county under another name, so the user is
        asked whether it is that one, and nothing is created until the answer."""
        t = self.tree(extra={"city": typed("city", "Hunedoara", 4, lang="ro")})
        t.places["hun"]["name"]["value"] = "Alt județ"
        r = self.run_it(t, self.ANSWER.replace("1 | Hunedoara | county (județ)", "1 | Hunedoara County | county"))
        self.assertNotIn("city", [u["handle"] for u in r["units"] if u["handle"]])
        self.assertEqual(([a["name"] for a in r["ambiguous"]], [c["label"].split(" [")[0] for a in r["ambiguous"] for c in a["candidates"]]),
                         (["Hunedoara County"], ["Alt județ"]))
        new = self.run_it(t, self.ANSWER.replace("1 | Hunedoara | county (județ)", "1 | Hunedoara County | county"), choices={"c1": "new"})
        self.assertEqual(self.made(new), ["Hunedoara County"])

    def test_the_name_of_the_county_gets_its_language_and_its_period_and_the_missing_type_is_filled(self):
        r = self.run_it(self.tree(-1))
        got = sorted((p["kind"], p["place"], describe(p["new"]) if p["kind"] == "set-name-date" else p.get("lang") or p.get("type_value"))
                     for p in r["proposals"] if p["place"] == "hun") if all("place" in p for p in r["proposals"]) else None
        self.assertEqual(got, [("set-name-date", "hun", "span 1925..1938"), ("set-name-language", "hun", "ro"), ("set-type", "hun", 3)])

    def test_a_type_that_the_county_has_is_never_touched(self):
        r = self.run_it(self.tree(0, "custom county"))
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "set-type"])

    def test_the_name_of_the_place_is_given_the_time_the_state_that_ruled_began(self):
        no_former = self.ANSWER.replace("OTHER_NAMES:\nhu: Déva (1867-1918)\n", "")
        r = self.run_it(self.tree(), no_former)
        (fill,) = [p for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "deva"]
        self.assertEqual(describe(fill["new"]), "from 1918")
        self.assertTrue(any("(establishment of ruling state Romania)" in n for n in r["needs"]))

    def test_that_is_left_alone_when_the_name_is_not_in_the_language_of_the_state_or_the_state_is_not_one_with_a_language(self):
        no_former = self.ANSWER.replace("OTHER_NAMES:\nhu: Déva (1867-1918)\n", "")
        english = self.run_it(self.tree(), no_former.replace("LANGUAGE: ro", "LANGUAGE: en"))
        hungarian = self.run_it(self.tree(), no_former.replace("LANGUAGE: ro", "LANGUAGE: hu"))                  # Romania is not hu
        habsburg = self.run_it(self.tree(), no_former.replace("| Romania", "| Austria-Hungary").replace("STATE_ON_DATE: Romania", "STATE_ON_DATE: Austria-Hungary"))
        for r in (english, hungarian, habsburg):
            self.assertFalse([p for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "deva"])

    def test_a_name_that_has_a_period_is_not_given_another(self):
        r = self.run_it(self.tree(deva_name_date=D(M_FROM, 1920)))
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "deva"])

    def test_a_new_place_is_named_from_the_time_the_state_began_and_with_the_language_of_the_answer(self):
        t = self.tree()
        del t.places["deva"]
        r = self.run_it(t)
        deva = next(p for p in r["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Deva")
        self.assertEqual((deva["names"][0]["lang"], describe(deva["names"][0]["date"])), ("ro", "from 1918"))         # the first level is the county, the parent:
        self.assertTrue(any("name «Deva» applies from 1918 (establishment of ruling state" in n for n in r["needs"]), r["needs"])     # its years are not the name's
        nothing = self.ANSWER.replace("1925-1938", "UNKNOWN")                                  # a unit with no period: the state's start
        deva = next(p for p in self.run_it(t, nothing)["proposals"] if p["kind"] == "add-place" and p["names"][0]["value"] == "Deva")
        self.assertEqual(describe(deva["names"][0]["date"]), "from 1918")


class NamesInManyLanguagesTests(unittest.TestCase):
    """A place can have the same spelling as several names, one for each language. An answer in one language dates the name in that language and
    the one with no language, not all of them; a single name is the unit's whatever its language (an answer in German may write a unit in English)."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\n"
              "STATE_ON_DATE: United States | 1776-present\n")

    def dated(self, languages, text=None, primary_lang=""):
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang=primary_lang, alts=[("Iowa", l, EMPTY) for l in languages]),
                  "usa": typed("usa", "USA", 1, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        r = ingest.ingest(t, ingest.parse_structured(text or self.ANSWER), "1995", aliases={})
        return [(p["index"], p["lang"]) for p in r["proposals"] if p["kind"] == "set-name-date" and p["place"] == "iowa"]

    def test_only_the_name_in_the_language_of_the_answer_and_the_one_with_no_language_are_dated(self):
        self.assertEqual(self.dated(["en", "de", "fr", "hu", "es"]), [(0, ""), (1, "en")])

    def test_when_none_of_them_is_in_the_language_of_the_answer_they_all_stay_candidates(self):
        self.assertEqual(self.dated(["de", "fr"], primary_lang="hu"), [(0, "hu"), (1, "de"), (2, "fr")])

    def test_a_single_name_is_the_units_whatever_its_language(self):
        self.assertEqual(self.dated([], primary_lang="de"), [(0, "de")])

    def test_two_names_with_no_language_are_both_dated(self):
        self.assertEqual(self.dated(["", ""]), [(0, ""), (1, ""), (2, "")])


class AnotherNameOfAHigherLevelTests(unittest.TestCase):
    """The answer names the state in the language of the state (Lietuvos Respublika) and the tree has it under another name (Lithuania). A new
    place was made for it. The tree itself suggests which place it is (the one above the unit below it); the user is asked, and nothing is
    created until the answer."""
    ANSWER = ("PLACE_NAME_ON_DATE: Kaunas\nLANGUAGE: lt\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Kauno apskritis | county | 1950-present | Lietuvos Respublika\n"
              "2 | Lietuvos Respublika | state | 1990-present |\nSTATE_ON_DATE: Lietuvos Respublika | 1990-present\n"
              "SOURCES: https://lt.wikipedia.org/wiki/Kaunas | PLACE_NAME_ON_DATE\n")

    def tree(self, state_type=1, county_type=3, link_date=None):
        t = Tree({"lt": typed("lt", "Lithuania", state_type, lang="en"), "kc": typed("kc", "Kaunas County", county_type, lang="en"),
                  "k": typed("k", "Kaunas", 4, lang="en")}, [])
        t.places["kc"]["refs"] = [{"ref": "lt", "date": link_date or EMPTY}]
        t.places["k"]["refs"] = [{"ref": "kc", "date": EMPTY}]
        return t

    def run_it(self, t=None, choices=None, text=None):
        r = ingest.ingest(t or self.tree(), ingest.parse_structured(text or self.ANSWER), "1995", aliases={}, choices=choices)
        return r, [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"]

    def asks(self, r):
        return [(a["slot"], a["name"], [c["label"] for c in a["candidates"]]) for a in r["ambiguous"]]

    def test_the_place_that_holds_the_unit_below_is_suggested_and_not_taken(self):
        r, made = self.run_it()
        self.assertEqual(self.asks(r), [("c1", "Kauno apskritis", ["Kaunas County [KC]"])])
        self.assertNotIn("Kauno apskritis", made)                                            # nothing is created for it until the answer
        self.assertIn("«Kauno apskritis» is not in your tree under that name, but «Kaunas County [KC]» holds «Kaunas [K]» there. Is it the same place?",
                      r["ambiguous"][0]["why"])
        self.assertTrue(any(n.startswith("ACTION REQUIRED: Kauno apskritis matches existing Kaunas County [KC] (containing Kaunas [K]") for n in r["needs"]))

    def test_the_next_level_is_asked_after_the_first_is_answered_and_the_state_is_asked_once(self):
        r, made = self.run_it(choices={"c1": "kc"})
        self.assertEqual(self.asks(r), [("c2", "Lietuvos Respublika", ["Lithuania [LT]"])])        # (the state is listed twice: asked once)
        r, made = self.run_it(choices={"c1": "kc", "c2": "lt"})
        self.assertEqual((self.asks(r), made), ([], []))                                        # both are places of the tree: nothing is made
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]], [("Kauno apskritis", "kc"), ("Lietuvos Respublika", "lt")])

    def test_a_name_the_user_confirmed_is_offered_as_a_name_of_that_place(self):
        r, _made = self.run_it(choices={"c1": "kc", "c2": "lt"})
        names = [(p["place"], p["value"], describe(p["new"])) for p in r["proposals"] if p["kind"] == "add-name"]
        self.assertEqual(names, [("kc", "Kauno apskritis", "from 1950"), ("lt", "Lietuvos Respublika", "from 1990")])

    def test_a_name_the_place_already_has_is_not_offered_again(self):
        t = self.tree()
        t.places["lt"]["alt_names"] = [{"value": "Lietuvos Respublika", "lang": "lt", "date": EMPTY}]
        r, _made = self.run_it(t, choices={"c1": "kc", "c2": "lt"})
        self.assertEqual([p["value"] for p in r["proposals"] if p["kind"] == "add-name"], ["Kauno apskritis"])

    def test_when_the_user_says_new_it_is_made_and_not_asked_again(self):
        r, made = self.run_it(choices={"c1": "new", "c2": "new"})
        self.assertEqual((self.asks(r), made), ([], ["Kauno apskritis", "Lietuvos Respublika"]))

    def test_when_the_user_leaves_a_level_out_it_is_left_out(self):
        r, made = self.run_it(choices={"c1": "skip", "c2": "skip"})
        self.assertEqual((self.asks(r), made), ([], []))

    def test_a_parent_of_another_type_is_not_suggested(self):
        r, _made = self.run_it(self.tree(county_type=4))                                          # the place above Kaunas is not a county
        self.assertEqual(self.asks(r), [])

    def test_two_parents_of_the_type_are_not_suggested_because_there_is_nothing_to_choose_by(self):
        t = self.tree()
        t.places["other"] = typed("other", "Samogitia County", 3, lang="en")
        t.places["k"]["refs"].append({"ref": "other", "date": EMPTY})
        r, _made = self.run_it(t)
        self.assertEqual(self.asks(r), [])

    def test_a_place_that_another_level_already_is_is_not_suggested_again(self):
        text = self.ANSWER.replace("1 | Kauno apskritis | county", "1 | Kaunas County | county")                  # the first level is found by its name
        r, made = self.run_it(text=text)
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]][:1], [("Kaunas County", "kc")])
        self.assertEqual(self.asks(r), [("c2", "Lietuvos Respublika", ["Lithuania [LT]"])])

    def test_a_name_that_a_pack_knows_is_found_by_its_name_and_nobody_is_asked(self):
        italy = ("PLACE_NAME_ON_DATE: Parma\nLANGUAGE: it\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
                 "1 | Emilia-Romagna | region | 1970-present | Repubblica Italiana\n2 | Repubblica Italiana | state | 1946-present |\n"
                 "STATE_ON_DATE: Repubblica Italiana | 1946-present\n")
        t = Tree({"it": typed("it", "Italy", 1, lang="en"), "er": typed("er", "Emilia-Romagna", 1, lang="en"), "p": typed("p", "Parma", 4, lang="en")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["p"]["refs"] = [{"ref": "er", "date": EMPTY}]
        world = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "packs", "world-basics.json")
        r = ingest.ingest(t, ingest.parse_structured(italy), "1950", aliases=ingest.alias_map([world]))
        self.assertEqual(([a["name"] for a in r["ambiguous"]], [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"]), ([], []))
        self.assertEqual([(u["name"], u["handle"]) for u in r["units"]], [("Emilia-Romagna", "er"), ("Repubblica Italiana", "it")])


class SameAsThePlaceTests(unittest.TestCase):
    """The answer lists "City of Johnston, municipal corporation" as the container of the place "Johnston": in the tree that is one place."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | City of Johnston | city, municipal corporation | 1969-present | Polk County\n"
              "2 | Polk County | county | 1846-present | Iowa\n3 | Iowa | state | 1846-present | United States\n"
              "STATE_ON_DATE: United States | 1776-present\n")

    def tree(self, with_city=True):
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        if with_city:
            t.places["city"] = typed("city", "Johnston", 4, lang="en")
            t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        return t

    def run_it(self, t):
        return ingest.ingest(t, ingest.parse_structured(self.ANSWER), "1995", aliases=ingest.alias_map([WORLD]))

    def test_the_municipality_is_not_made_a_separate_place_inside_the_place(self):
        r = self.run_it(self.tree())
        made = [p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place"]
        self.assertEqual(made, ["Polk County"])                                          # no second "Johnston"
        self.assertTrue(any("City of Johnston is identical to Johnston" in n for n in r["needs"]))

    def test_the_chain_goes_from_the_place_to_the_county(self):
        r = self.run_it(self.tree())
        self.assertEqual(r["preview"], ["Johnston", "Polk County", "Iowa", "USA"])

    def test_it_is_the_same_when_the_place_is_new(self):
        r = self.run_it(self.tree(with_city=False))
        made = sorted(p["names"][0]["value"] for p in r["proposals"] if p["kind"] == "add-place")
        self.assertEqual(made, ["Johnston", "Polk County"])                              # one Johnston, not two

    def test_a_county_with_the_name_of_the_city_is_another_place_and_stays(self):
        text = self.ANSWER.replace("2 | Polk County | county", "2 | Johnston County | county")
        made = [p["names"][0]["value"] for p in self.run_it(self.tree())["proposals"] if p["kind"] == "add-place"]
        made2 = [p["names"][0]["value"] for p in ingest.ingest(self.tree(), ingest.parse_structured(text), "1995", aliases=ingest.alias_map([WORLD]))["proposals"] if p["kind"] == "add-place"]
        self.assertEqual(made2, ["Johnston County"])
        self.assertEqual(made, ["Polk County"])


class ChoiceTests(unittest.TestCase):
    """A unit that could be several places of the tree is not turned into a new place: the user chooses."""
    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n"
              "1 | Polk County | county | 1846-present | Iowa\n2 | United States of America | country | 1776-present | United States\n")

    def tree(self):
        t = Tree({"usa": typed("usa", "USA", 1, lang="en"), "usa2": typed("usa2", "United States of America", 1, lang="en"),
                  "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["city"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        return t

    def run_it(self, choices=None):
        return ingest.ingest(self.tree(), ingest.parse_structured(self.ANSWER), "1995", aliases=ingest.alias_map([WORLD]), choices=choices)

    def test_two_places_that_could_be_it_are_asked_about_and_nothing_is_created_for_them(self):
        r = self.run_it()
        (amb,) = r["ambiguous"]
        self.assertEqual((amb["slot"], amb["name"]), ("c2", "United States of America"))
        self.assertEqual({c["handle"] for c in amb["candidates"]}, {"usa", "usa2"})
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "add-place" and "United States" in p["names"][0]["value"]])
        self.assertTrue(any(n.startswith("ACTION REQUIRED: United States of America matches existing") for n in r["needs"]))

    def test_only_places_about_as_good_as_the_best_are_offered(self):
        t = self.tree()
        t.places["iowa"] = typed("iowa", "State of Iowa", 2, lang="en")                   # shares a word with the name, is no candidate
        r = ingest.ingest(t, ingest.parse_structured(self.ANSWER), "1995", aliases=ingest.alias_map([WORLD]))
        self.assertEqual({c["handle"] for c in r["ambiguous"][0]["candidates"]}, {"usa", "usa2"})

    def test_the_chosen_place_is_used(self):
        r = self.run_it({"c2": "usa"})
        self.assertEqual(r["ambiguous"], [])
        self.assertTrue(any(p["kind"] == "add-link" and p["parent"] == "usa" for p in r["proposals"]))
        self.assertFalse([p for p in r["proposals"] if p["kind"] == "add-place" and "United States" in p["names"][0]["value"]])

    def test_new_makes_a_new_place_and_skip_leaves_the_level_out(self):
        r = self.run_it({"c2": "new"})
        self.assertTrue(any(p["kind"] == "add-place" and p["names"][0]["value"] == "United States of America" for p in r["proposals"]))
        r2 = self.run_it({"c2": "skip"})
        self.assertFalse([p for p in r2["proposals"] if p["kind"] == "add-place" and "United States" in p["names"][0]["value"]])
        self.assertTrue(any("excluded per user selection" in n for n in r2["needs"]))

    def test_a_partial_name_hit_is_not_asked_about(self):
        t = self.tree()
        del t.places["usa2"]
        text = self.ANSWER.replace("1 | Polk County", "1 | Johnston County")
        r = ingest.ingest(t, ingest.parse_structured(text), "1995", aliases=ingest.alias_map([WORLD]))
        self.assertEqual(r["ambiguous"], [])
        self.assertTrue(any(p["kind"] == "add-place" and p["names"][0]["value"] == "Johnston County" for p in r["proposals"]))


class UnitTypeTests(unittest.TestCase):
    def test_the_types_of_new_units(self):
        from placecompleter.ingest import _container_type
        self.assertEqual(_container_type("country, federal republic")["value"], 1)
        self.assertEqual(_container_type("city, municipal corporation")["value"], 4)
        self.assertEqual(_container_type("county")["value"], 3)
        self.assertEqual(_container_type("village")["value"], 16)
        self.assertEqual(_container_type("township"), {"value": 0, "string": "Township"})       # not "town": a type of its own
        self.assertEqual(_container_type("region")["value"], 9)                                  # the type of Gramps
