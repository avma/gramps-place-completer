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
"""Coordinates from Wikidata: used when ONE place of that name is found where the answer puts it. The entities below are built in the
shape of the real ones (labels, P625 coordinates, P131 the administrative unit, P17 the country): the network is not used."""
import os
import sys
import tempfile
import types
import unittest
import urllib.parse

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from placecompleter import complete, geo, plan as planlib, session as sess, settings, wikidata          # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
from test_engine import EMPTY                                                                 # noqa: E402
from test_ingest import WORLD, typed                                                          # noqa: E402


def link(qid):
    return {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"id": qid}}}}


def entity(label, lat, lon, inside=None, country=None):
    claims = {"P625": [{"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"latitude": lat, "longitude": lon}}}}]}
    if inside:
        claims["P131"] = [link(inside)]
    if country:
        claims["P17"] = [link(country)]
    return {"labels": {"en": {"language": "en", "value": label}}, "claims": claims}


ENTITIES = {
    "Q1": entity("Johnston", 41.6856, -93.7172, inside="Q2", country="Q30"),                 # Johnston, Iowa
    "Q3": entity("Johnston", 41.8218, -71.5034, inside="Q4", country="Q30"),                 # Johnston, Rhode Island
    "Q2": entity("Polk County", 41.6849, -93.5738, inside="Q1546", country="Q30"),           # Polk County, Iowa
    "Q9": entity("Polk County", 47.8, -95.9, inside="Q1527", country="Q30"),                 # Polk County, Minnesota
    "Q4": entity("Providence County", 41.87, -71.58, inside="Q1387", country="Q30"),
    "Q1546": entity("Iowa", 42.07, -93.5, country="Q30"),
    "Q1527": entity("Minnesota", 46.4, -94.6, country="Q30"),
    "Q1387": entity("Rhode Island", 41.7, -71.5, country="Q30"),
    "Q30": entity("United States", 39.8, -98.6),
}
SEARCH = {"Johnston": ["Q1", "Q3"], "Polk County": ["Q2", "Q9"], "Iowa": ["Q1546"], "Nowhere": []}


class FakeClient:
    """The two calls of the Wikidata client that the search uses, answered from the table above."""
    def __init__(self, search=None, entities=None):
        self.table, self.ents, self.searched = search or SEARCH, entities or ENTITIES, []

    def search(self, text, language="en", limit=5):
        self.searched.append((text, language))
        return [{"id": q} for q in self.table.get(text, [])]

    def entities(self, ids):
        return {i: self.ents[i] for i in ids if i in self.ents}

    def sitelinks(self, qid, languages):
        self.sitelinks_asked = getattr(self, "sitelinks_asked", []) + [(qid, tuple(languages))]
        return {"sitelinks": {k: v for k, v in SITELINKS.get(qid, {}).items() if k[:-4].replace("_", "-") in languages}}


SITELINKS = {"Q1": {"enwiki": {"title": "Johnston, Iowa"}, "frwiki": {"title": "Johnston (Iowa)"}, "hewiki": {"title": "\u05d2\u05f3\u05d5\u05e0\u05e1\u05d8\u05d5\u05df"}}}
EN_JOHNSTON = "https://en.wikipedia.org/wiki/Johnston,_Iowa"
FR_JOHNSTON = "https://fr.wikipedia.org/wiki/Johnston_(Iowa)"
WD_JOHNSTON = "https://www.wikidata.org/wiki/Q1"

NEAR = (41.673, -93.6977)          # where an AI answer put Johnston: 2.9 km from Wikidata's coordinates


class LookupTests(unittest.TestCase):
    def test_the_place_near_where_the_answer_puts_it_is_found_and_the_homonym_far_away_is_not(self):
        f = geo.lookup(FakeClient(), "Johnston", near=NEAR)
        self.assertEqual((f["found"], f["qid"], f["lat"], f["lon"], f["label"]), (True, "Q1", "41.6856", "-93.7172", "Johnston"))
        self.assertEqual(f["url"], "https://www.wikidata.org/wiki/Q1")
        self.assertAlmostEqual(f["km"], 2.0, delta=1.5)

    def test_without_a_distance_the_region_decides_if_it_can(self):
        f = geo.lookup(FakeClient(), "Johnston", region="Polk County")
        self.assertEqual((f["found"], f["qid"]), (True, "Q1"))
        self.assertIsNone(f["km"])

    def test_without_a_distance_and_without_a_region_two_places_of_the_name_are_not_chosen_between(self):
        f = geo.lookup(FakeClient(), "Johnston")
        self.assertFalse(f["found"])
        self.assertIn("places match this name on Wikidata: Q1, Q3", f["reason"])

    def test_a_county_is_told_from_the_one_of_another_state_by_its_state(self):
        self.assertEqual(geo.lookup(FakeClient(), "Polk County", region="Iowa")["qid"], "Q2")
        self.assertEqual(geo.lookup(FakeClient(), "Polk County", region="Minnesota")["qid"], "Q9")

    def test_places_only_far_from_where_the_answer_puts_it_are_not_taken(self):
        f = geo.lookup(FakeClient(), "Johnston", near=(47.0, 8.0))
        self.assertEqual(f["found"], False)
        self.assertIn("the 50 km", f["reason"])

    def test_a_name_wikidata_does_not_know(self):
        self.assertIn("place with spatial coordinates", geo.lookup(FakeClient(), "Nowhere")["reason"])

    def test_an_entity_without_coordinates_is_not_used(self):
        ents = dict(ENTITIES)
        ents["Q1"] = {"labels": {"en": {"language": "en", "value": "Johnston"}}, "claims": {"P131": [link("Q2")]}}
        f = geo.lookup(FakeClient(entities=ents), "Johnston", near=NEAR)
        self.assertFalse(f["found"])

    def test_a_deprecated_statement_is_dropped(self):
        ents = dict(ENTITIES)
        bad = entity("Johnston", 10.0, 10.0, inside="Q2")
        bad["claims"]["P625"][0]["rank"] = "deprecated"
        ents["Q1"] = bad
        self.assertFalse(geo.lookup(FakeClient(entities=ents), "Johnston", near=(10.0, 10.0))["found"])

    def test_only_the_asked_languages_are_searched(self):
        client = FakeClient()
        geo.lookup(client, "Johnston", near=NEAR)
        self.assertEqual({lang for _t, lang in client.searched}, {"en"})
        client2 = FakeClient()
        geo.lookup(client2, "Johnston", near=NEAR, languages=("en", "hu"))
        self.assertEqual({lang for _t, lang in client2.searched}, {"en", "hu"})

    def test_candidates_default_to_all_the_search_languages(self):
        client = FakeClient()
        complete.candidates(client, "Iowa")
        self.assertEqual({lang for _t, lang in client.searched}, set(complete.SEARCH_LANGUAGES))

    def test_one_place_failing_does_not_lose_the_others(self):
        class Broken(FakeClient):
            def search(self, text, language="en", limit=5):
                if text == "Johnston":
                    raise OSError("network is down")
                return super().search(text, language, limit)
        out = geo.lookup_many(Broken(), [{"key": "a", "name": "Johnston", "near": NEAR}, {"key": "b", "name": "Iowa", "region": None}])
        self.assertIn("Wikidata: network is down", out["a"]["reason"])
        self.assertTrue(out["b"]["found"])


ANSWER = """PLACE_NAME_ON_DATE: Johnston
LANGUAGE: en
SETTLEMENT_TYPE_ON_DATE: city
COORDINATES: 41.673, -93.6977
CONTAINERS:
1 | Polk County | county | 1846-present | Iowa
2 | Iowa | state | 1846-present | United States
STATE_ON_DATE: United States | 1776-present
"""


def tree():
    t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1),
              "city": typed("city", "Johnston", 4, lang="en")}, [])
    t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
    return t


class SessionTests(unittest.TestCase):
    def session(self, t=None, answer=ANSWER):
        s = sess.Session(t or tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(answer)
        return s

    def find(self, s, kind, **match):
        return next(p for p in s.result["proposals"] if p["kind"] == kind and all(p.get(k) == v for k, v in match.items()))

    def test_the_answers_coordinates_are_there_first_and_marked_as_coming_from_the_answer(self):
        s = self.session()
        p = self.find(s, "set-coordinates", place="city")
        self.assertEqual((p["lat"], p["lon"], p["basis"]), ("41.673", "-93.6977", "assumption"))
        self.assertIn("from AI response: verify accuracy", [c["steps"][0]["text"] for c in s.changes() if "coordinates for «Johnston" in c["title"]][0])

    def test_what_is_asked_is_the_place_the_new_county_and_the_state_without_coordinates(self):
        targets = {t["name"]: t for t in self.session().coordinate_targets()}
        self.assertEqual(set(targets), {"Johnston", "Polk County", "Iowa"})
        self.assertEqual((targets["Johnston"]["near"], targets["Johnston"]["region"]), ((41.673, -93.6977), "Polk County"))
        self.assertEqual((targets["Polk County"]["near"], targets["Polk County"]["region"]), (None, "Iowa"))
        self.assertEqual(targets["Iowa"]["region"], "USA")

    def test_a_country_is_not_asked_about_its_coordinates_mean_nothing(self):
        self.assertNotIn("USA", [x["name"] for x in self.session().coordinate_targets()])

    def test_a_place_that_has_coordinates_is_not_asked_about(self):
        t = tree()
        t.places["iowa"]["lat"], t.places["iowa"]["lon"] = "42.0", "-93.5"
        self.assertNotIn("Iowa", [x["name"] for x in self.session(t).coordinate_targets()])

    def test_wikidata_replaces_the_answers_coordinates_and_the_basis_becomes_evidence(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        p = self.find(s, "set-coordinates", place="city")
        self.assertEqual((p["lat"], p["lon"], p["basis"]), ("41.6856", "-93.7172", "evidence"))
        self.assertEqual(p["evidence"], [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/Q1", "claim": "P625 (coordinates) of Johnston"}])
        change = next(c for c in s.changes() if "coordinates for «Johnston" in c["title"])
        self.assertIn("from Wikidata Q1 «Johnston»", change["title"])
        self.assertEqual(change["basis"], "evidence")

    def test_the_new_county_gets_its_coordinates_from_wikidata_when_it_is_created(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        county = self.find(s, "add-place")
        self.assertEqual((county["names"][0]["value"], county["lat"], county["lon"], county["basis"]), ("Polk County", "41.6849", "-93.5738", "evidence"))
        self.assertIn("coordinates 41.6849, -93.5738 from Wikidata Q2", [st["text"] for c in s.changes() for st in c["steps"] if "Polk County" in st["text"]][0])

    def test_an_existing_place_without_coordinates_that_the_answer_does_not_give_gets_a_proposal_of_its_own(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        iowa = self.find(s, "set-coordinates", place="iowa")
        self.assertEqual((iowa["lat"], iowa["lon"], iowa["basis"], iowa["origin"]), ("42.07", "-93.5", "evidence", "wikidata"))

    def test_the_numbers_of_the_proposals_and_what_is_checked_are_kept(self):
        s = self.session()
        before = {p["id"]: p["kind"] for p in s.plan["proposals"]}
        change = next(c for c in s.changes() if c["title"].startswith("Insert"))
        s.toggle_change(change["id"])
        chosen = set(s.selected)
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        after = {p["id"]: p["kind"] for p in s.plan["proposals"]}
        self.assertTrue(all(after[i] == k for i, k in before.items()))                  # the old ones are where they were
        self.assertGreater(len(after), len(before))                                      # the new one is added at the end
        self.assertEqual(s.selected, chosen)

    def test_what_wikidata_could_not_settle_keeps_the_answers_coordinates_and_says_so(self):
        s = self.session()
        client = FakeClient(search={"Johnston": ["Q3"]})                                 # only the Johnston of Rhode Island
        s.apply_coordinates(geo.lookup_many(client, [t for t in s.coordinate_targets() if t["name"] == "Johnston"]))
        p = self.find(s, "set-coordinates", place="city")
        self.assertEqual((p["lat"], p["basis"]), ("41.673", "assumption"))
        notes = [n for n, _l in s.needs() if n.startswith("Wikidata: Johnston")]
        self.assertEqual(len(notes), 1)
        self.assertIn("the answer; coordinates from", notes[0])

    def test_the_distance_to_the_answers_coordinates_is_told(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        self.assertTrue(any(n.startswith("Wikidata: Johnston: coordinates 41.6856, -93.7172 from Q1 (") and "km from the location returned in the answer" in n
                            for n, _l in s.needs()))

    def test_asking_twice_does_not_ask_again_for_what_was_answered(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        self.assertEqual(s.coordinate_targets(), [])

    def test_a_new_place_asks_with_the_coordinates_of_the_answer_as_the_distance(self):
        t = tree()
        del t.places["city"]
        s = self.session(t)
        main = next(x for x in s.coordinate_targets() if x["name"] == "Johnston")
        self.assertEqual(main["near"], (41.673, -93.6977))

    def test_no_answer_no_targets_and_nothing_to_apply(self):
        s = sess.Session(tree(), tempfile.mkdtemp())
        self.assertEqual((s.coordinate_targets(), s.apply_coordinates({})), ([], 0))

    def test_the_plan_that_is_written_carries_the_source(self):
        s = self.session()
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets()))
        items = {(i["kind"], i.get("place")): i for i in s.plan["proposals"] if i["kind"] in ("set-coordinates", "add-place")}
        self.assertEqual(items[("set-coordinates", "city")]["source_note"], "Wikidata Q1 «Johnston»")
        self.assertEqual(items[("add-place", None)]["source_note"], "Wikidata Q2 «Polk County»")
        self.assertEqual(items[("set-coordinates", "city")]["evidence"][0]["source"], "wikidata")


class ArticleTests(unittest.TestCase):
    """The Wikipedia articles of the languages of the user, taken from the sitelinks that Wikidata lists for the item."""
    def test_the_articles_are_asked_only_when_languages_are_given_and_come_in_their_order(self):
        client = FakeClient()
        f = geo.lookup(client, "Johnston", near=NEAR)
        self.assertNotIn("articles", f)
        self.assertFalse(hasattr(client, "sitelinks_asked"))
        f = geo.lookup(client, "Johnston", near=NEAR, articles=("fr", "en", "es"))
        self.assertEqual(f["articles"], [FR_JOHNSTON, EN_JOHNSTON])                    # no article in Spanish: nothing is guessed
        self.assertEqual(client.sitelinks_asked, [("Q1", ("fr", "en", "es"))])

    def test_a_failure_of_the_sitelinks_does_not_lose_the_coordinates(self):
        class Broken(FakeClient):
            def sitelinks(self, qid, languages):
                raise OSError("no network")
        f = geo.lookup(Broken(), "Johnston", near=NEAR, articles=("en",))
        self.assertEqual((f["found"], f["lat"], f["articles"]), (True, "41.6856", []))

    def test_only_the_main_place_is_asked_for_its_articles(self):
        client = FakeClient()
        targets = [{"key": "a", "name": "Johnston", "near": NEAR, "main": True}, {"key": "b", "name": "Polk County", "region": "Iowa"}]
        found = geo.lookup_many(client, targets, articles=("en",))
        self.assertEqual(found["a"]["articles"], [EN_JOHNSTON])
        self.assertNotIn("articles", found["b"])
        self.assertEqual([q for q, _l in client.sitelinks_asked], ["Q1"])

    def test_the_client_asks_for_the_sitelinks_in_one_small_request_and_keeps_the_answer(self):
        from placecompleter import wikidata
        asked = []

        def fetch(url):
            asked.append(url)
            return {"entities": {"Q1": {"sitelinks": {"hewiki": {"title": "x"}}}}}
        client = wikidata.Client(fetch=fetch, pause=0)
        self.assertEqual(client.sitelinks("Q1", ("he", "en")), {"sitelinks": {"hewiki": {"title": "x"}}})
        client.sitelinks("Q1", ("en", "he"))                                           # the same question: no second request
        self.assertEqual(len(asked), 1)
        self.assertIn("props=sitelinks", asked[0])
        self.assertIn("sitefilter=enwiki%7Chewiki", asked[0])
        self.assertEqual(client.entity_cache, {})                                      # an item without claims is not kept as an entity
        self.assertEqual(wikidata.Client(fetch=lambda url: None, pause=0).sitelinks("Q1", ("en",)), {})


class LinksFromWikidataTests(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("PLACECOMPLETER_SETTINGS")
        os.environ["PLACECOMPLETER_SETTINGS"] = os.path.join(tempfile.mkdtemp(prefix="pc-settings-"), "settings.json")
        settings.set_wikipedia_languages("en, fr")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLACECOMPLETER_SETTINGS", None)
        else:
            os.environ["PLACECOMPLETER_SETTINGS"] = self.old

    def ask(self, s):
        s.apply_coordinates(geo.lookup_many(FakeClient(), s.coordinate_targets(), articles=settings.wikipedia_languages()))

    def urls(self, s, place):
        return [p["path"] for p in s.result["proposals"] if p["kind"] == "add-url" and p["place"] == place]

    session = SessionTests.session                                                      # the same setup as the session tests above
    find = SessionTests.find

    def test_the_wikidata_item_and_the_articles_of_the_languages_become_links_of_a_place_of_the_tree(self):
        s = self.session()
        self.ask(s)
        self.assertEqual(self.urls(s, "city"), [WD_JOHNSTON, EN_JOHNSTON, FR_JOHNSTON])
        link = next(p for p in s.result["proposals"] if p["kind"] == "add-url")
        self.assertEqual((link["origin"], link["basis"], link["optional"]), ("wikidata", "evidence", False))
        fake = types.SimpleNamespace(plan=s.plan, selected=set())
        sess.Session.select_all(fake)                                                   # chosen by the window: an addition
        chosen = {p["path"] for p in s.plan["proposals"] if p["kind"] == "add-url" and p["id"] in fake.selected}
        self.assertEqual(chosen, {WD_JOHNSTON, EN_JOHNSTON, FR_JOHNSTON})

    def test_the_other_places_of_the_chain_get_no_links(self):
        s = self.session()
        self.ask(s)
        self.assertEqual(self.urls(s, "iowa"), [])
        county = self.find(s, "add-place")
        self.assertEqual(county.get("urls", []), [])

    def test_what_the_place_has_in_another_form_is_not_added_again(self):
        t = tree()
        t.places["city"]["urls"] = ["http://en.m.wikipedia.org/wiki/Johnston,_Iowa/"]
        s = self.session(t)
        self.ask(s)
        self.assertEqual(self.urls(s, "city"), [WD_JOHNSTON, FR_JOHNSTON])

    def test_the_languages_of_the_user_decide_which_articles(self):
        settings.set_wikipedia_languages("he")
        s = self.session()
        self.ask(s)
        title = "\u05d2\u05f3\u05d5\u05e0\u05e1\u05d8\u05d5\u05df"
        self.assertEqual(self.urls(s, "city"), [WD_JOHNSTON, "https://he.wikipedia.org/wiki/" + urllib.parse.quote(title, safe="_(),'!*~:@")])

    def test_a_new_place_gets_the_links_in_its_own_urls(self):
        t = tree()
        del t.places["city"]
        s = self.session(t)
        self.ask(s)
        made = self.find(s, "add-place", handle=s.result["child"])
        self.assertEqual([u["path"] for u in made["urls"]], [WD_JOHNSTON, EN_JOHNSTON, FR_JOHNSTON])
        self.assertEqual([p for p in s.result["proposals"] if p["kind"] == "add-url"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
