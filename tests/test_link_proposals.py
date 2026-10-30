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
"""The web links of an answer as proposals (Table 5 of docs/ANALYZER_RULES.md): what is offered, what is chosen by itself, what is written."""
import copy
import os
import shutil
import sys
import tempfile
import types
import unittest.mock
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

TMP = tempfile.mkdtemp(prefix="pc-links-")
os.environ["GRAMPSHOME"] = os.path.join(TMP, "home")

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.lib import Place, PlaceName, PlaceType, Url, UrlType
    HAVE_GRAMPS = True
except Exception:                        # pragma: no cover
    HAVE_GRAMPS = False

import test_ingest as ti                                                                      # noqa: E402
from placecompleter import ingest, plan as planlib, session, settings, writer                  # noqa: E402

WD = "https://www.wikidata.org/wiki/Q1041949"
WP_EN = "https://en.wikipedia.org/wiki/Bajmok"
WP_HE = "https://he.wikipedia.org/wiki/Bajmok"
COMUNE = "https://www.comune.bajmok.example.it/storia"
HISTORY = "https://www.bajmok-history.example.org/"
TOUR = "https://www.tripadvisor.com/Tourism-Bajmok.html"


def answer_with(urls):
    rec = ti.answer()
    rec["sources"] = [{"url": u, "supports": "the place"} for u in urls]
    return rec


def links_of(screen):
    return {p["path"]: p for p in screen["proposals"] if p["kind"] == "add-url"}


class OfferTests(unittest.TestCase):
    def run_ingest(self, urls, **kw):
        return ingest.ingest(ti.tree(), answer_with(urls), "1850", skip={2}, **kw)

    def test_a_place_of_the_tree_is_offered_the_links_that_the_rules_accept_and_not_the_tourism_page(self):
        found = links_of(self.run_ingest([WD, WP_EN, COMUNE, HISTORY, TOUR]))
        self.assertEqual(set(found), {WD, WP_EN, COMUNE, HISTORY})
        self.assertNotIn(TOUR, found)
        self.assertEqual({u: p["optional"] for u, p in found.items()}, {WD: False, WP_EN: False, COMUNE: False, HISTORY: True})
        self.assertTrue(all(p["place"] == "baj" and not p.get("existing") and not p["conflict"] for p in found.values()))   # an addition, never a change

    def test_a_link_that_the_place_has_is_not_offered_again_in_another_form(self):
        t = ti.tree()
        t.places["baj"]["urls"] = ["http://en.m.wikipedia.org/wiki/Bajmok/"]
        screen = ingest.ingest(t, answer_with([WP_EN, WD]), "1850", skip={2})
        self.assertEqual(set(links_of(screen)), {WD})

    def test_the_languages_of_the_user_choose_the_wikipedia_articles(self):
        screen = self.run_ingest([WP_EN, WP_HE], languages=("he", "en"))
        self.assertEqual(set(links_of(screen)), {WP_HE, WP_EN})
        screen = self.run_ingest([WP_EN, WP_HE], languages=("he",))
        self.assertEqual(set(links_of(screen)), {WP_HE})                       # one article for the language chosen; English only as a fallback
        screen = self.run_ingest([WP_EN], languages=("he",))
        self.assertEqual(set(links_of(screen)), {WP_EN})

    def test_a_new_place_gets_the_links_that_are_chosen_by_themselves_and_the_other_sites_are_only_named(self):
        rec = answer_with([WD, WP_EN, COMUNE, HISTORY, TOUR])
        rec["name"] = "Bajmokpuszta"
        screen = ingest.ingest(ti.tree(), rec, "1850", skip={2})
        made = next(p for p in screen["proposals"] if p["kind"] == "add-place")
        self.assertEqual([u["path"] for u in made["urls"]], [WD, WP_EN, COMUNE])
        self.assertFalse(any(p["kind"] == "add-url" for p in screen["proposals"]))
        self.assertTrue(any("potential official web links" in n and HISTORY in n and TOUR not in n for n in screen["needs"]))

    def test_nothing_is_offered_when_the_answer_has_no_page(self):
        self.assertEqual(links_of(self.run_ingest([])), {})


class ChoiceTests(unittest.TestCase):
    def setUp(self):
        screen = ingest.ingest(ti.tree(), answer_with([WD, HISTORY]), "1850", skip={2})
        self.plan = planlib.make_plan(ti.tree(), screen["proposals"])
        self.by_path = {p["path"]: p for p in self.plan["proposals"] if p["kind"] == "add-url"}

    def test_the_plan_keeps_the_address_and_whether_it_is_doubtful(self):
        self.assertFalse(self.by_path[WD]["optional"])
        self.assertTrue(self.by_path[HISTORY]["optional"])
        self.assertEqual(self.by_path[HISTORY]["label"], ti.tree().label("baj"))

    def test_the_window_selects_the_sure_link_by_itself_and_never_the_doubtful_site(self):
        fake = types.SimpleNamespace(plan=self.plan, selected=set())
        session.Session.select_all(fake)
        self.assertIn(self.by_path[WD]["id"], fake.selected)
        self.assertNotIn(self.by_path[HISTORY]["id"], fake.selected)

    def test_choosing_by_basis_leaves_the_doubtful_site_and_choosing_by_number_takes_it(self):
        by_basis = {p["path"] for p in planlib.select(self.plan, bases={"assumption"}) if p["kind"] == "add-url"}
        self.assertEqual(by_basis, {WD})
        by_number = {p["path"] for p in planlib.select(self.plan, ids={self.by_path[HISTORY]["id"]})}
        self.assertEqual(by_number, {HISTORY})

    def test_the_text_of_the_proposal_names_the_link_and_the_place(self):
        text = session.describe_proposal(ti.tree(), self.by_path[WD], {})
        self.assertIn(WD, text)
        self.assertIn(ti.tree().label("baj"), text)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.old = os.environ.get("PLACECOMPLETER_SETTINGS")
        os.environ["PLACECOMPLETER_SETTINGS"] = os.path.join(tempfile.mkdtemp(prefix="pc-settings-"), "settings.json")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("PLACECOMPLETER_SETTINGS", None)
        else:
            os.environ["PLACECOMPLETER_SETTINGS"] = self.old

    def test_the_default_is_the_language_of_the_session_and_then_english(self):
        with unittest.mock.patch.dict(os.environ, {"LANGUAGE": "he_IL:en"}):
            self.assertEqual(settings.wikipedia_languages(), ["he", "en"])
        with unittest.mock.patch.dict(os.environ, {"LANGUAGE": "en", "LC_ALL": "C", "LANG": "C"}):
            self.assertEqual(settings.wikipedia_languages(), ["en"])
        with unittest.mock.patch.dict(os.environ, {"LANGUAGE": "", "LC_ALL": "C", "LANG": "C"}):
            self.assertEqual(settings.wikipedia_languages(), ["en"])

    def test_the_languages_typed_by_the_user_are_kept_in_their_order(self):
        self.assertEqual(settings.set_wikipedia_languages("zh"), (["zh"], []))
        self.assertEqual(settings.wikipedia_languages(), ["zh"])
        self.assertEqual(settings.set_wikipedia_languages("FR; es, fr"), (["fr", "es"], []))
        self.assertEqual(settings.wikipedia_languages(), ["fr", "es"])

    def test_a_word_that_is_not_a_language_code_is_reported_and_left_out(self):
        self.assertEqual(settings.set_wikipedia_languages("he, Hebrew, en"), (["he", "en"], ["hebrew"]))
        self.assertEqual(settings.wikipedia_languages(), ["he", "en"])

    def test_nothing_valid_changes_nothing(self):
        settings.set_wikipedia_languages("fr")
        self.assertEqual(settings.set_wikipedia_languages("1234, !!"), ([], ["1234", "!!"]))
        self.assertEqual(settings.wikipedia_languages(), ["fr"])
        settings.reset_wikipedia_languages()
        self.assertNotEqual(settings.wikipedia_languages(), ["fr"])

    def test_a_damaged_file_is_not_a_problem(self):
        os.makedirs(os.path.dirname(settings.path()), exist_ok=True)
        with open(settings.path(), "w") as fh:
            fh.write("{not json")
        self.assertTrue(settings.wikipedia_languages())


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class WriterTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(TMP, "db-%d" % id(self))
        self.db = make_database("sqlite")
        os.makedirs(self.path)
        self.db.load(self.path)
        with DbTxn("build", self.db) as txn:
            place, name = Place(), PlaceName()
            name.set_value("Bajmok")
            place.set_name(name)
            place.set_type(PlaceType.VILLAGE)
            self.handle = self.db.add_place(place, txn)

    def tearDown(self):
        self.db.close()

    def proposal(self, path, number=1):
        return {"id": number, "kind": "add-url", "place": self.handle, "path": path, "basis": "assumption", "old": {}, "new": {}}

    def urls(self):
        return [u.get_path() for u in self.db.get_place_from_handle(self.handle).get_url_list()]

    def test_a_dry_run_writes_nothing_and_the_real_run_adds_the_link_in_one_undo(self):
        self.assertEqual(writer.apply_proposals(self.db, [self.proposal(WP_EN)], dry_run=True)[0]["status"], "dry-run")
        self.assertEqual(self.urls(), [])
        self.assertEqual(writer.apply_proposals(self.db, [self.proposal(WP_EN)], dry_run=False)[0]["status"], "applied")
        self.assertEqual(self.urls(), [WP_EN])
        link = self.db.get_place_from_handle(self.handle).get_url_list()[0]
        self.assertEqual((link.get_type().xml_str(), link.get_path()), ("Web Home", WP_EN))
        self.db.undo()
        self.assertEqual(self.urls(), [])

    def test_a_link_that_is_there_now_is_skipped_even_in_another_form(self):
        with DbTxn("a link", self.db) as txn:
            place = self.db.get_place_from_handle(self.handle)
            url = Url()
            url.set_path("http://en.m.wikipedia.org/wiki/Bajmok/")
            url.set_type(UrlType(UrlType.WEB_HOME))
            place.add_url(url)
            self.db.commit_place(place, txn)
        result = writer.apply_proposals(self.db, [self.proposal(WP_EN)], dry_run=False)[0]
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(len(self.urls()), 1)

    def test_a_place_that_is_gone_is_skipped(self):
        stale = self.proposal(WD)
        stale["place"] = "no-such-place"
        self.assertEqual(writer.apply_proposals(self.db, [stale], dry_run=False)[0]["status"], "skipped")

    def test_a_new_place_with_the_wikipedia_link_of_an_existing_one_in_another_form_is_not_made_twice(self):
        with DbTxn("a link", self.db) as txn:
            place = self.db.get_place_from_handle(self.handle)
            url = Url()
            url.set_path(WD)
            place.add_url(url)
            self.db.commit_place(place, txn)
        new = {"id": 1, "kind": "add-place", "handle": "new:x", "gramps_id": "NEW-x", "names": [{"value": "Bajmok", "lang": "", "date": {}}],
               "type_value": PlaceType.VILLAGE, "type_string": "", "lat": "", "lon": "", "urls": [{"path": "https://m.wikidata.org/wiki/Q1041949/"}]}
        self.assertEqual(writer.apply_proposals(self.db, [new], dry_run=False)[0]["status"], "skipped")
        self.assertEqual(len(list(self.db.get_place_handles())), 1)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
