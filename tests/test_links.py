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
"""Which web links of an answer become links of a place, and how many (LK1-LK5 of docs/ANALYZER_RULES.md)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import links                                                              # noqa: E402

WD = "https://www.wikidata.org/wiki/Q2683"
WP_EN = "https://en.wikipedia.org/wiki/Parma"
WP_HU = "https://hu.wikipedia.org/wiki/Parma"
WP_IT = "https://it.wikipedia.org/wiki/Parma"


def kinds(urls):
    return {u: links.classify(u)[0] for u in urls}


class ClassifyTests(unittest.TestCase):
    def test_wikipedia_and_wikidata_in_any_language_and_form(self):
        for url in (WP_EN, WP_HU, "https://en.m.wikipedia.org/wiki/Parma", "http://it.wikipedia.org/wiki/Parma#Storia"):
            self.assertEqual(links.classify(url)[0], links.WIKIPEDIA, url)
        for url in (WD, "https://m.wikidata.org/wiki/Q2683", "https://www.wikidata.org/entity/Q2683"):
            self.assertEqual(links.classify(url)[0], links.WIKIDATA, url)

    def test_tourism_hiking_booking_shops_and_social_sites_are_blocked(self):
        for url in ("https://www.tripadvisor.com/Tourism-Parma.html", "https://www.komoot.com/guide/parma", "https://www.booking.com/city/it/parma.html",
                    "https://www.alltrails.com/it/parma", "https://www.visitparma.it/tour-della-citta", "https://www.parma.it/hotels",
                    "https://www.facebook.com/comune.parma", "https://maps.google.com/?q=Parma", "https://example.com/trails/parma",
                    "https://www.amazon.it/s?k=parma", "https://www.viator.com/Parma"):
            self.assertEqual(links.classify(url)[0], links.BLOCKED, url)

    def test_what_is_not_a_web_address_is_blocked(self):
        for url in ("ftp://example.org/x", "mailto:a@b.it", "not a url", ""):
            self.assertEqual(links.classify(url)[0], links.BLOCKED, url)

    def test_addresses_of_the_shape_of_an_official_site_are_likely_official(self):
        for url in ("https://www.comune.parma.it/", "https://www.comune.sissatrecasali.pr.it/storia", "https://www.example.gov.it/", "https://www.hu.gov/x",
                    "https://bfs.admin.ch/page", "https://www.archivio.example.it/", "https://mairie-example.fr/histoire", "https://ec.europa.eu/eurostat"):
            self.assertEqual(links.classify(url)[0], links.LIKELY_OFFICIAL, url)

    def test_any_other_address_is_of_unknown_kind_and_not_chosen(self):
        for url in ("https://www.sissa.it/storia", "https://www.storiadiparma.org/", "https://citytours-example.com/info"):
            self.assertIn(links.classify(url)[0], (links.OTHER, links.BLOCKED), url)
        self.assertEqual(links.classify("https://www.storiadiparma.org/")[0], links.OTHER)
        self.assertEqual(links.classify("https://www.cityguide-example.org/")[0], links.OTHER)       # "city" inside a longer word is not an official shape

    def test_the_same_page_in_different_forms_has_one_normal_form(self):
        same = ("https://en.wikipedia.org/wiki/Parma", "http://en.m.wikipedia.org/wiki/Parma/", "https://EN.wikipedia.org/wiki/Parma#History",
                "https://en.wikipedia.org/wiki/Parma?utm_source=x")
        self.assertEqual(len({links.normalize(u) for u in same}), 1)
        self.assertEqual(links.normalize("https://m.wikidata.org/wiki/Q2683"), links.normalize("https://www.wikidata.org/entity/Q2683"))
        self.assertNotEqual(links.normalize(WP_EN), links.normalize(WP_HU))


class SelectTests(unittest.TestCase):
    def paths(self, offered):
        return [o["path"] for o in offered]

    def test_wikidata_and_wikipedia_are_chosen_and_come_first(self):
        offered, rejected = links.select_links([WP_EN, "https://www.comune.parma.it/", WD])
        self.assertEqual(self.paths(offered), [WD, WP_EN, "https://www.comune.parma.it/"])
        self.assertTrue(all(o["chosen"] for o in offered))
        self.assertEqual(rejected, [])

    def test_an_address_of_unknown_kind_is_offered_but_not_chosen(self):
        offered, _ = links.select_links(["https://www.storiadiparma.org/", WD])
        by = {o["path"]: o for o in offered}
        self.assertTrue(by[WD]["chosen"])
        self.assertFalse(by["https://www.storiadiparma.org/"]["chosen"])

    def test_blocked_addresses_are_left_out_with_the_reason(self):
        offered, rejected = links.select_links(["https://www.tripadvisor.com/x", WD])
        self.assertEqual(self.paths(offered), [WD])
        self.assertEqual([r["path"] for r in rejected], ["https://www.tripadvisor.com/x"])
        self.assertTrue(rejected[0]["reason"])

    def test_one_article_per_language_that_the_user_chose_in_the_order_of_the_choice(self):
        offered, rejected = links.select_links([WP_EN, WP_IT, WP_HU], languages=("hu", "it"))
        self.assertEqual(self.paths(offered), [WP_HU, WP_IT])
        self.assertEqual([r["path"] for r in rejected], [WP_EN])                      # English was not asked, and the chosen languages have articles
        offered, _ = links.select_links([WP_EN, "https://en.wikipedia.org/wiki/Province_of_Parma"], languages=("en",))
        self.assertEqual(self.paths(offered), [WP_EN])                                # two articles of one language: the first

    def test_english_only_when_none_of_the_chosen_languages_has_an_article(self):
        offered, rejected = links.select_links([WP_HU, WP_EN], languages=("he", "fr"))
        self.assertEqual(self.paths(offered), [WP_EN])
        self.assertEqual([r["path"] for r in rejected], [WP_HU])
        offered, rejected = links.select_links([WP_EN, WP_HU], languages=("hu",))
        self.assertEqual(self.paths(offered), [WP_HU])
        self.assertEqual([r["path"] for r in rejected], [WP_EN])
        offered, rejected = links.select_links([WP_EN], languages=("hu",), existing=[WP_HU])   # the place has its article: no fallback
        self.assertEqual((offered, [r["path"] for r in rejected]), ([], [WP_EN]))

    def test_a_language_that_was_not_asked_is_left_out_with_the_reason(self):
        _offered, rejected = links.select_links([WP_IT], languages=("he", "en"))
        self.assertEqual([r["path"] for r in rejected], [WP_IT])
        self.assertIn("language", rejected[0]["reason"])

    def test_the_total_grows_with_the_languages_the_user_chose(self):
        zh, fr, es, he = ("https://%s.wikipedia.org/wiki/Parma" % x for x in ("zh", "fr", "es", "he"))
        urls = [WD, zh, fr, es, he, "https://www.comune.a.it/", "https://www.comune.b.it/", "https://www.comune.c.it/"]
        offered, rejected = links.select_links(urls, languages=("he", "fr", "es", "zh"))
        self.assertEqual(len(offered), 1 + 4 + links.MAX_OFFICIAL)
        self.assertEqual([r["path"] for r in rejected], ["https://www.comune.c.it/"])
        self.assertEqual(self.paths(offered)[:5], [WD, he, fr, es, zh])               # Wikidata, then the languages in the order of the choice

    def test_the_default_is_english(self):
        offered, _ = links.select_links([WP_HU, WP_EN])
        self.assertEqual(self.paths(offered), [WP_EN])

    def test_at_most_two_other_sites(self):
        urls = ["https://www.comune.a.it/", "https://www.comune.b.it/", "https://www.comune.c.it/"]
        offered, rejected = links.select_links(urls)
        self.assertEqual(self.paths(offered), urls[:2])
        self.assertEqual([r["path"] for r in rejected], urls[2:])

    def test_what_the_place_already_has_is_not_offered_again_in_any_form(self):
        offered, rejected = links.select_links([WP_EN, WD], existing=["http://en.m.wikipedia.org/wiki/Parma/"])
        self.assertEqual(self.paths(offered), [WD])
        self.assertEqual([r["path"] for r in rejected], [WP_EN])

    def test_a_kind_that_the_place_already_has_is_not_added_a_second_time(self):
        offered, rejected = links.select_links(["https://en.wikipedia.org/wiki/Province_of_Parma", WD], existing=[WP_EN, WD])
        self.assertEqual(offered, [])
        self.assertEqual(len(rejected), 2)
        offered, _ = links.select_links([WP_HU], languages=("en", "hu"), existing=[WP_EN])   # another language is another link
        self.assertEqual(self.paths(offered), [WP_HU])

    def test_the_total_counts_the_links_that_exist(self):
        urls = [WD, WP_EN, "https://www.comune.a.it/", "https://www.comune.b.it/"]
        offered, rejected = links.select_links(urls, existing=["https://www.comune.old.it/"], max_total=3)
        self.assertEqual(self.paths(offered), [WD, WP_EN])
        self.assertEqual(len(rejected), 2)
        offered, _ = links.select_links(urls)
        self.assertEqual(len(offered), 4)                                              # Wikidata, one language, two others

    def test_the_same_address_twice_is_one_link(self):
        offered, rejected = links.select_links([WD, "https://m.wikidata.org/wiki/Q2683", WD])
        self.assertEqual(self.paths(offered), [WD])
        self.assertEqual(len(rejected), 2)

    def test_nothing_in_nothing_out(self):
        self.assertEqual(links.select_links([]), ([], []))


class SitelinkTests(unittest.TestCase):
    ENTITY = {"sitelinks": {"enwiki": {"title": "Parma"}, "hewiki": {"title": "\u05e4\u05e8\u05de\u05d4"}, "zh_yuewiki": {"title": "Parma"},
                            "itwiki": {"title": "Parma (citt\u00e0)"}}}

    def test_the_articles_of_the_languages_asked_are_taken_from_wikidata_in_that_order(self):
        urls = links.sitelink_urls(self.ENTITY, ("it", "en", "fr"))
        self.assertEqual(urls, ["https://it.wikipedia.org/wiki/Parma_%28citt%C3%A0%29".replace("%28", "(").replace("%29", ")"), "https://en.wikipedia.org/wiki/Parma"])

    def test_a_language_with_no_article_gives_nothing_and_no_address_is_guessed(self):
        self.assertEqual(links.sitelink_urls(self.ENTITY, ("fr", "es")), [])
        self.assertEqual(links.sitelink_urls({}, ("en",)), [])
        self.assertEqual(links.sitelink_urls(None, ("en",)), [])

    def test_the_address_is_a_wikipedia_address_that_the_selection_accepts(self):
        urls = links.sitelink_urls(self.ENTITY, ("he",))
        self.assertEqual(links.classify(urls[0])[0], links.WIKIPEDIA)
        offered, _ = links.select_links(urls, languages=("he",))
        self.assertEqual([o["path"] for o in offered], urls)
        self.assertEqual(links.sitelink_urls(self.ENTITY, ("zh-yue",)), ["https://zh-yue.wikipedia.org/wiki/Parma"])


if __name__ == "__main__":
    unittest.main()
