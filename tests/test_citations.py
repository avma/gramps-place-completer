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
"""Citations for the places that are written: where each piece of information came from. Real Gramps database."""
import datetime
import os
import sys
import tempfile
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from gramps.gen.db import DbTxn
    from gramps.gen.db.utils import make_database
    from gramps.gen.lib import Citation
    HAVE_GRAMPS = True
except Exception:                                   # pragma: no cover
    HAVE_GRAMPS = False

from placecompleter import citations, ingest, plan as planlib, session as sess, writer     # noqa: E402
from placecompleter.model import Tree                                                       # noqa: E402
from test_engine import EMPTY                                                               # noqa: E402
from test_ingest import WORLD, typed                                                        # noqa: E402

TODAY = datetime.date(2026, 10, 14)
JOHNSTON_PAGE = "https://en.wikipedia.org/wiki/Johnston,_Iowa"
POLK_PAGE = "https://en.wikipedia.org/wiki/Polk_County,_Iowa"
GENERAL_PAGE = "https://example.org/general-history"
ANSWER = ("PLACE_NAME_ON_DATE: City of Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCOORDINATES: 41.673, -93.6977\nCONTAINERS:\n"
          "1 | Polk County | county | 1846-present | Iowa\n2 | Iowa | state | 1846-present | United States\n"
          "STATE_ON_DATE: United States | 1776-present\n"
          "SOURCES: %s | PLACE_NAME_ON_DATE, SETTLEMENT_TYPE_ON_DATE, COORDINATES\n%s | CONTAINERS\n%s |\n"
          "NOT_SURE: COORDINATES\n" % (JOHNSTON_PAGE, POLK_PAGE, GENERAL_PAGE))


def tree():
    t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
              "city": typed("city", "City of Johnston", -1)}, [])
    t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
    t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
    return t


def run(t=None):
    return ingest.ingest(t or tree(), ingest.parse_structured(ANSWER), "1995", aliases=ingest.alias_map([WORLD]))


def prov(**kw):
    meta = {"engine": "google", "engine_label": "Google AI mode", "model": "not disclosed by the service", "form": "classic"}
    base = citations.provenance_record(meta, place="Johnston", date="1995", answer_file="/home/x/gramps-place-work/answers/Johnston_1995.txt",
                                       not_sure="COORDINATES", today=TODAY)
    base.update(kw)
    return base


class EvidenceTests(unittest.TestCase):
    def by_kind(self, r, kind, **match):
        return next(p for p in r["proposals"] if p["kind"] == kind and all(p.get(k) == v for k, v in match.items()))

    def test_a_page_that_says_nothing_about_a_field_is_no_evidence_for_it(self):
        rec = ingest.parse_structured(ANSWER)
        urls = [e["url"] for e in ingest._sources(rec, ("CONTAINERS",))]
        self.assertEqual(urls, [POLK_PAGE, GENERAL_PAGE])                                 # not the page about the place's name
        self.assertEqual([e["claim"] for e in ingest._sources(rec, ("CONTAINERS",))][0], "CONTAINERS")
        self.assertEqual([e["url"] for e in ingest._sources(rec, ("COORDINATES",))], [JOHNSTON_PAGE, GENERAL_PAGE])

    def test_a_page_listed_without_fields_counts_for_all_of_them(self):
        rec = ingest.parse_structured(ANSWER)
        general = [e for e in ingest._sources(rec, ("COORDINATES",)) if e["url"] == GENERAL_PAGE][0]
        self.assertEqual(general["claim"], "")

    def test_each_proposal_carries_the_pages_of_its_own_fields(self):
        r = run()
        coords = self.by_kind(r, "set-coordinates")
        self.assertEqual([e["url"] for e in coords["evidence"]], [JOHNSTON_PAGE, GENERAL_PAGE])
        self.assertEqual(coords["evidence"][0]["claim"], "COORDINATES")
        made = self.by_kind(r, "add-place")                                              # the county
        self.assertEqual([e["url"] for e in made["evidence"]], [POLK_PAGE, GENERAL_PAGE])
        link = self.by_kind(r, "add-link", child="city")
        self.assertEqual([e["url"] for e in link["evidence"]], [POLK_PAGE, GENERAL_PAGE])
        self.assertEqual([e["url"] for e in self.by_kind(r, "set-type")["evidence"]], [JOHNSTON_PAGE, GENERAL_PAGE])

    def test_a_rename_follows_a_convention_and_cites_nothing(self):
        t = tree()
        t.places["city"]["type"] = {"value": 4, "string": ""}                               # a city called "City of ...": a rename is proposed
        self.assertEqual(self.by_kind(run(t), "rename-place", place="city")["evidence"], [])

    def test_collect_merges_what_a_page_is_cited_for(self):
        a = citations.collect({"evidence": [{"source": "ai-answer", "url": "u", "claim": "A, B"}]})
        b = citations.collect({"evidence": [{"source": "ai-answer", "url": "u", "claim": "B, C"}, {"source": "wikidata", "url": "w", "claim": "P625"}]})
        merged = citations.merge(dict(a), b)
        self.assertEqual(merged["u"]["claims"], ["A, B", "B, C"])
        self.assertTrue(merged["w"]["wikidata"])
        self.assertEqual(citations.collect({"evidence": [{"source": "x", "url": "", "claim": "z"}]}), {})


class AboutTests(unittest.TestCase):
    """Which place a page is about, from its address (citations.about)."""
    def test_a_wikipedia_article_is_about_the_place_of_its_title(self):
        self.assertTrue(citations.about("https://en.wikipedia.org/wiki/Parma", ["Parma"]))
        self.assertFalse(citations.about("https://en.wikipedia.org/wiki/Parma", ["Provincia di Parma"]))             # the province has another name
        self.assertTrue(citations.about("https://it.wikipedia.org/wiki/Provincia_di_Parma", ["Provincia di Parma"]))
        self.assertFalse(citations.about("https://it.wikipedia.org/wiki/Provincia_di_Parma", ["Parma", "Emilia-Romagna"]))

    def test_what_follows_a_comma_is_the_qualifier_of_the_title_and_not_part_of_the_name(self):
        self.assertTrue(citations.about("https://en.wikipedia.org/wiki/Johnston,_Iowa", ["Johnston"]))
        self.assertFalse(citations.about("https://en.wikipedia.org/wiki/Johnston,_Iowa", ["Iowa"]))
        self.assertTrue(citations.about("https://en.wikipedia.org/wiki/Polk_County,_Iowa", ["Iowa", "Polk County"]))

    def test_names_are_compared_without_accents_case_or_punctuation(self):
        self.assertTrue(citations.about("https://de.wikipedia.org/wiki/Z%C3%BCrich", ["Zurich"]))
        self.assertTrue(citations.about("https://en.wikipedia.org/wiki/Emilia-Romagna", ["emilia romagna"]))

    def test_another_site_is_about_a_place_when_a_whole_part_of_its_address_is_the_name(self):
        self.assertTrue(citations.about("https://www.comune.parma.it/parma/storia", ["Parma"]))
        self.assertFalse(citations.about("https://www.comune.parma.it/storia", ["Parma"]))                           # (the host is not read)
        self.assertFalse(citations.about("https://example.org/general-history", ["Parma"]))

    def test_a_wikidata_page_is_never_decided_by_a_name_and_nothing_is_about_no_name(self):
        self.assertFalse(citations.about("https://www.wikidata.org/wiki/Q38", ["Q38"]))
        self.assertFalse(citations.about("https://en.wikipedia.org/wiki/Parma", []))
        self.assertFalse(citations.about("", ["Parma"]))


class TitleTests(unittest.TestCase):
    def test_titles_from_addresses(self):
        self.assertEqual(citations.source_title(JOHNSTON_PAGE), "Wikipedia: Johnston, Iowa")
        self.assertEqual(citations.source_title("https://hu.wikipedia.org/wiki/Bajmok"), "Wikipedia (hu): Bajmok")
        self.assertEqual(citations.source_title("https://www.wikidata.org/wiki/Q123"), "Wikidata Q123")
        self.assertEqual(citations.source_title("https://sos.iowa.gov/business/pdf/IncCities.pdf"), "sos.iowa.gov: IncCities.pdf")
        self.assertEqual(citations.source_title("https://example.org/"), "example.org")


class ConfidenceAndSiteTests(unittest.TestCase):
    """The confidence of a citation follows what the analysis already knows about how sure the answer is; and every source belongs to a site."""
    def info(self, *claims, wikidata=False):
        return {"claims": list(claims), "wikidata": wikidata}

    def test_a_page_cited_for_what_the_answer_does_not_doubt_is_normal(self):
        level, why = citations.confidence_for(self.info("CONTAINERS"), {"not_sure": "COORDINATES"})
        self.assertEqual(level, citations.NORMAL)
        self.assertIn("CONTAINERS", why)

    def test_a_page_cited_for_a_field_the_answer_is_not_sure_about_among_others_is_low(self):
        level, why = citations.confidence_for(self.info("PLACE_NAME_ON_DATE, COORDINATES"), {"not_sure": "COORDINATES"})
        self.assertEqual(level, citations.LOW)
        self.assertIn("part of this claim: COORDINATES", why)

    def test_a_page_cited_only_for_what_the_answer_is_not_sure_about_is_very_low(self):
        level, _why = citations.confidence_for(self.info("COORDINATES"), {"not_sure": "COORDINATES, CONTAINERS"})
        self.assertEqual(level, citations.VERY_LOW)

    def test_a_page_with_no_stated_support_is_low(self):
        for claims in ([], [""], ["something said in words"]):
            self.assertEqual(citations.confidence_for(self.info(*claims), {"not_sure": ""})[0], citations.LOW)

    def test_a_wikidata_statement_is_normal_whatever_the_answer_doubts(self):
        self.assertEqual(citations.confidence_for(self.info("P625", wikidata=True), {"not_sure": "P625, COORDINATES"})[0], citations.NORMAL)

    def test_doubts_about_the_whole_answer_lower_it_by_one_level_and_never_below_very_low(self):
        doubts = ["CONFLICTS WITH SAVED RESPONSE: this answer is IDENTICAL to the one saved for 1850"]
        self.assertEqual(citations.confidence_for(self.info("CONTAINERS"), {"not_sure": "", "doubts": doubts})[0], citations.LOW)
        self.assertEqual(citations.confidence_for(self.info("CONTAINERS, COORDINATES"), {"not_sure": "COORDINATES", "doubts": doubts})[0], citations.VERY_LOW)
        level, why = citations.confidence_for(self.info("COORDINATES"), {"not_sure": "COORDINATES", "doubts": doubts})
        self.assertEqual(level, citations.VERY_LOW)
        self.assertNotIn("one level lower", why)                                           # already at the bottom: nothing to lower

    def test_the_site_of_a_page_is_its_repository(self):
        self.assertEqual(citations.repository_identity(JOHNSTON_PAGE), ("Wikipedia", "https://www.wikipedia.org", "wikipedia.org"))
        self.assertEqual(citations.repository_identity("https://hu.wikipedia.org/wiki/Bajmok")[0], "Wikipedia")           # every language of it
        self.assertEqual(citations.repository_identity("https://www.wikidata.org/wiki/Q123")[0], "Wikidata")
        self.assertEqual(citations.repository_identity("https://sos.iowa.gov/business/pdf/IncCities.pdf"),
                         ("sos.iowa.gov", "https://sos.iowa.gov", "sos.iowa.gov"))
        self.assertEqual(citations.repository_identity("http://www.example.org/a")[:2], ("example.org", "http://example.org"))
        self.assertEqual(citations.repository_identity("not an address"), ("", "", ""))


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class DatabaseTests(unittest.TestCase):
    def open(self, t=None):
        from test_writer import IngestWriterTests
        path = os.path.join(tempfile.mkdtemp(), "db")
        self.addCleanup(lambda: __import__("shutil").rmtree(os.path.dirname(path), ignore_errors=True))
        IngestWriterTests().build_from(t or tree(), path)
        db = make_database("sqlite")
        db.load(path)
        self.addCleanup(db.close)
        return db

    def proposals(self, db, **keep):
        t = Tree.from_db(db)
        r = run(t)
        return planlib.make_plan(t, r["proposals"])["proposals"]

    def counts(self, db):
        return (db.get_number_of_sources(), db.get_number_of_citations(), db.get_number_of_notes())

    def named(self, db, name):
        return next(h for h in db.get_place_handles() if db.get_place_from_handle(h).get_name().get_value() == name)

    def cited_titles(self, db, name):
        return sorted(src.get_title() for src, _c in self.cites(db, self.named(db, name)))

    def cites(self, db, handle):
        out = []
        for h in db.get_place_from_handle(handle).get_citation_list():
            c = db.get_citation_from_handle(h)
            out.append((db.get_source_from_handle(c.get_reference_handle()), c))
        return out

    def test_the_place_that_is_written_gets_a_citation_for_each_page_of_its_changes(self):
        db = self.open()
        results = writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertNotIn("skipped", {r["status"] for r in results})
        titles = {s.get_title(): c for s, c in self.cites(db, "city")}
        self.assertEqual(set(titles), {"Wikipedia: Johnston, Iowa", "Wikipedia: Polk County, Iowa", "example.org: general-history"})

    def test_the_source_keeps_its_address_where_it_is_found_again(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        source = next(s for s, _c in self.cites(db, "city") if s.get_title() == "Wikipedia: Johnston, Iowa")
        self.assertEqual(source.get_publication_info(), JOHNSTON_PAGE)
        self.assertEqual([(str(a.get_type()), a.get_value()) for a in source.get_attribute_list()], [("URL", JOHNSTON_PAGE)])

    def test_the_citation_says_what_it_is_for_when_it_was_fetched_and_how_sure_it_is(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        citation = next(c for s, c in self.cites(db, "city") if s.get_title() == "Wikipedia: Johnston, Iowa")
        self.assertTrue(citation.get_page().startswith("Reported by AI search supporting: "))
        for field in ("COORDINATES", "SETTLEMENT_TYPE_ON_DATE"):
            self.assertIn(field, citation.get_page())
        self.assertNotIn("CONTAINERS", citation.get_page())                               # that page was not cited for them
        d = citation.get_date_object()
        self.assertEqual((d.get_year(), d.get_month(), d.get_day()), (2026, 10, 14))
        self.assertEqual(citation.get_confidence_level(), Citation.CONF_LOW)

    def test_the_note_tells_how_the_information_was_found(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        citation = next(c for s, c in self.cites(db, "city") if s.get_title() == "Wikipedia: Johnston, Iowa")
        (note_handle,) = citation.get_note_list()
        text = db.get_note_from_handle(note_handle).get()
        self.assertIn("Found by Google AI mode (not disclosed by the service) on 2026-10-14", text)
        self.assertIn("«Johnston» on 1995 (query format: classic)", text)
        self.assertIn("Saved response: /home/x/gramps-place-work/answers/Johnston_1995.txt", text)
        self.assertIn("The response indicates uncertainty regarding: COORDINATES", text)

    def test_the_note_of_a_citation_is_a_place_note(self):
        """The note says how the information about the PLACE was found: its type is Place (it was Citation)."""
        from gramps.gen.lib import NoteType
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        notes = [db.get_note_from_handle(h) for s, c in self.cites(db, "city") for h in c.get_note_list()]
        self.assertTrue(notes)
        self.assertEqual({n.get_type().value for n in notes}, {NoteType.PLACE})

    def test_a_new_place_is_cited_for_what_made_it(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        county = next(h for h in db.get_place_handles() if db.get_place_from_handle(h).get_name().get_value() == "Polk County")
        self.assertEqual({s.get_title() for s, _c in self.cites(db, county)}, {"Wikipedia: Polk County, Iowa", "example.org: general-history"})

    def test_one_page_is_one_source_cited_many_times(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertEqual(db.get_number_of_sources(), 3)                                    # three pages, however many places cite them
        county = next(h for h in db.get_place_handles() if db.get_place_from_handle(h).get_name().get_value() == "Polk County")
        self.assertGreater(db.get_number_of_citations(), 3)
        shared = [s.handle for s, _c in self.cites(db, county) if s.get_title() == "example.org: general-history"]
        self.assertEqual(shared, [next(s.handle for s, _c in self.cites(db, "city") if s.get_title() == "example.org: general-history")])

    def test_it_is_one_undo_and_leaves_no_source_citation_or_note_behind(self):
        db = self.open()
        before = self.counts(db)
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertNotEqual(self.counts(db), before)
        db.undo()
        self.assertEqual(self.counts(db), before)
        self.assertEqual(db.get_place_from_handle("city").get_citation_list(), [])

    def repositories(self, db):
        return [db.get_repository_from_handle(h) for h in db.get_repository_handles()]

    def test_every_source_that_is_made_is_linked_to_the_repository_of_its_site(self):
        from gramps.gen.lib import RepositoryType, SourceMediaType, UrlType
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        sources = [db.get_source_from_handle(h) for h in db.get_source_handles()]
        self.assertTrue(sources)
        for source in sources:
            links = source.get_reporef_list()
            self.assertEqual(len(links), 1, source.get_title())                                 # every source: one repository
            self.assertEqual(links[0].get_media_type().value, SourceMediaType.ELECTRONIC)       # (not str(): Gramps translates the words of its types)
        names = {r.get_name() for r in self.repositories(db)}
        self.assertEqual(names, {"Wikipedia", "example.org"})
        wikipedia = next(r for r in self.repositories(db) if r.get_name() == "Wikipedia")
        self.assertEqual(wikipedia.get_type().value, RepositoryType.WEBSITE)
        self.assertEqual([(u.get_path(), u.get_type().value) for u in wikipedia.get_url_list()], [("https://www.wikipedia.org", UrlType.WEB_HOME)])
        by_title = {s.get_title(): db.get_repository_from_handle(s.get_reporef_list()[0].get_reference_handle()).get_name() for s in sources}
        self.assertEqual(by_title["Wikipedia: Johnston, Iowa"], "Wikipedia")
        self.assertEqual(by_title["Wikipedia: Polk County, Iowa"], "Wikipedia")                 # two pages of one site: one repository
        self.assertEqual(by_title["example.org: general-history"], "example.org")

    def test_every_citation_is_linked_to_a_source_and_every_source_to_a_repository(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        repositories = set(db.get_repository_handles())
        sources = set(db.get_source_handles())
        for h in db.get_citation_handles():
            c = db.get_citation_from_handle(h)
            self.assertIn(c.get_reference_handle(), sources)
            self.assertTrue({r.get_reference_handle() for r in db.get_source_from_handle(c.get_reference_handle()).get_reporef_list()} <= repositories)

    def add_repository(self, db, name, address=""):
        from gramps.gen.lib import Repository, RepositoryType, Url, UrlType
        with DbTxn("repository", db) as txn:
            repo = Repository()
            repo.set_name(name)
            repo.set_type(RepositoryType.LIBRARY)
            if address:
                link = Url()
                link.set_path(address)
                link.set_type(UrlType.WEB_HOME)
                repo.add_url(link)
            return db.add_repository(repo, txn)

    def test_a_repository_of_the_tree_is_used_by_its_name_whatever_the_case(self):
        db = self.open()
        mine = self.add_repository(db, "wikipedia")
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertEqual({r.get_name() for r in self.repositories(db)}, {"wikipedia", "example.org"})              # no second Wikipedia
        wiki = [s for s in (db.get_source_from_handle(h) for h in db.get_source_handles()) if s.get_title().startswith("Wikipedia")]
        self.assertTrue(all(s.get_reporef_list()[0].get_reference_handle() == mine for s in wiki))

    def test_a_repository_of_the_tree_is_used_by_the_address_of_its_site_too(self):
        db = self.open()
        mine = self.add_repository(db, "The online encyclopedia", "https://en.wikipedia.org/")
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertEqual({r.get_name() for r in self.repositories(db)}, {"The online encyclopedia", "example.org"})
        wiki = [s for s in (db.get_source_from_handle(h) for h in db.get_source_handles()) if s.get_title().startswith("Wikipedia")]
        self.assertTrue(all(s.get_reporef_list()[0].get_reference_handle() == mine for s in wiki))

    def add_source(self, db, url, repository=None):
        from gramps.gen.lib import RepoRef, Source, SrcAttribute
        with DbTxn("source", db) as txn:
            source = Source()
            source.set_title("my own source")
            source.set_publication_info(url)
            attribute = SrcAttribute()
            attribute.set_type(citations.URL_ATTRIBUTE)
            attribute.set_value(url)
            source.add_attribute(attribute)
            if repository:
                link = RepoRef()
                link.set_reference_handle(repository)
                source.add_repo_reference(link)
            return db.add_source(source, txn)

    def test_a_source_that_is_found_with_no_repository_gets_one(self):
        db = self.open()
        handle = self.add_source(db, JOHNSTON_PAGE)
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        links = db.get_source_from_handle(handle).get_reporef_list()
        self.assertEqual([db.get_repository_from_handle(r.get_reference_handle()).get_name() for r in links], ["Wikipedia"])
        self.assertEqual(db.get_source_from_handle(handle).get_title(), "my own source")                          # nothing else of it is touched

    def test_a_source_that_is_found_with_a_repository_is_left_as_it_is(self):
        db = self.open()
        library = self.add_repository(db, "State Library")
        handle = self.add_source(db, JOHNSTON_PAGE, library)
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        links = db.get_source_from_handle(handle).get_reporef_list()
        self.assertEqual([r.get_reference_handle() for r in links], [library])

    def test_one_undo_takes_back_the_repositories_too(self):
        db = self.open()
        before = len(db.get_repository_handles())
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        self.assertGreater(len(db.get_repository_handles()), before)
        db.undo()
        self.assertEqual(len(db.get_repository_handles()), before)

    def test_a_dry_run_makes_no_repository(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=True, provenance=prov())
        self.assertEqual(db.get_repository_handles(), [])

    def level_of(self, db, title):
        for source, citation in self.cites(db, "city"):
            if source.get_title() == title:
                return citation.get_confidence_level(), db.get_note_from_handle(citation.get_note_list()[0]).get()
        self.fail("no citation of " + title)

    def test_the_confidence_of_each_citation_is_what_the_answer_is_sure_of(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())                          # the answer is not sure about COORDINATES
        level, note = self.level_of(db, "Wikipedia: Johnston, Iowa")
        self.assertEqual(level, Citation.CONF_LOW)                                                                 # cited for COORDINATES among others
        self.assertIn("Confidence level Low: the response expresses uncertainty regarding part of this claim: COORDINATES.", note)
        level, note = self.level_of(db, "example.org: general-history")
        self.assertEqual(level, Citation.CONF_LOW)                                                                 # it says nothing about what the page supports
        self.assertIn("does not specify which fields this page supports", note)

    def test_a_page_for_what_the_answer_is_sure_of_is_normal_and_a_doubted_answer_lowers_it(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        city = {s.get_title(): c for s, c in self.cites(db, "city")}
        # the city is linked to the county by CONTAINERS: that page is not doubted
        link_cites = [(s.get_title(), c.get_confidence_level()) for s, c in self.cites(db, "city")]
        self.assertIn(("Wikipedia: Polk County, Iowa", Citation.CONF_NORMAL), link_cites)
        db2 = self.open()
        writer.apply_proposals(db2, self.proposals(db2), dry_run=False,
                               provenance=prov(doubts=["CONFLICTS WITH SAVED RESPONSE: this answer is IDENTICAL to the one saved for 1850"]))
        link_cites = [(s.get_title(), c.get_confidence_level()) for s, c in self.cites(db2, "city")]
        self.assertIn(("Wikipedia: Polk County, Iowa", Citation.CONF_LOW), link_cites)
        self.assertTrue(city)

    def test_everything_the_answer_doubts_gives_very_low(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False,
                               provenance=prov(not_sure="PLACE_NAME_ON_DATE, SETTLEMENT_TYPE_ON_DATE, COORDINATES"))
        level, _note = self.level_of(db, "Wikipedia: Johnston, Iowa")
        self.assertEqual(level, Citation.CONF_VERY_LOW)

    def test_a_dry_run_and_a_write_without_provenance_cite_nothing(self):
        db = self.open()
        before = self.counts(db)
        writer.apply_proposals(db, self.proposals(db), dry_run=True, provenance=prov())
        self.assertEqual(self.counts(db), before)
        writer.apply_proposals(db, self.proposals(db), dry_run=False)
        self.assertEqual(self.counts(db), before)

    def test_what_is_skipped_is_not_cited(self):
        db = self.open()
        coords = [p for p in self.proposals(db) if p["kind"] == "set-coordinates"]
        place = db.get_place_from_handle("city")
        place.set_latitude("41.68559")
        place.set_longitude("-93.71725")
        with DbTxn("somebody", db) as txn:
            db.commit_place(place, txn)
        before = self.counts(db)
        results = writer.apply_proposals(db, coords, dry_run=False, provenance=prov())
        self.assertEqual([r["status"] for r in results], ["skipped"])
        self.assertNotIn("cited", results[0])
        self.assertEqual(self.counts(db), before)

    def test_citing_the_very_same_statement_twice_adds_nothing(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        before = self.counts(db)
        with DbTxn("again", db) as txn:
            added = citations.attach(db, txn, "city", {POLK_PAGE: {"claims": ["CONTAINERS"], "wikidata": False}}, prov(), {})
        self.assertEqual((added, self.counts(db)), ([], before))

    def test_the_same_page_cited_for_something_else_is_another_citation_of_the_same_source(self):
        db = self.open()
        writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        before = self.counts(db)
        with DbTxn("else", db) as txn:
            added = citations.attach(db, txn, "city", {POLK_PAGE: {"claims": ["STATE_ON_DATE"], "wikidata": False}}, prov(), {})
        self.assertEqual(added, ["Wikipedia: Polk County, Iowa"])
        sources, cites, notes = self.counts(db)
        self.assertEqual((sources, cites, notes), (before[0], before[1] + 1, before[2] + 1))      # the source is reused

    FIVE = {"https://www.tripadvisor.com/Tourism-Johnston.html": {"claims": ["CONTAINERS"], "wikidata": False},
            GENERAL_PAGE: {"claims": ["CONTAINERS"], "wikidata": False},
            "https://www.comune.example.it/storia": {"claims": ["CONTAINERS"], "wikidata": False},
            POLK_PAGE: {"claims": ["CONTAINERS"], "wikidata": False},
            "https://www.wikidata.org/wiki/Q1": {"claims": ["P131 (located in)"], "wikidata": True}}

    def test_a_place_gets_at_most_three_citations_in_one_run_the_strongest_first(self):
        db = self.open()
        left_out = []
        with DbTxn("cite", db) as txn:
            added = citations.attach(db, txn, "city", dict(self.FIVE), prov(), {}, left_out=left_out)
        self.assertEqual(added, ["Wikidata Q1", "Wikipedia: Polk County, Iowa", "comune.example.it: storia"])           # Wikidata, Wikipedia, an official site
        self.assertEqual(left_out, ["example.org: general-history", "tripadvisor.com: Tourism-Johnston.html"])        # another site, then the tourism page
        self.assertEqual(len(self.cites(db, "city")), 3)

    def test_the_limit_is_for_what_is_added_and_not_for_what_the_place_has(self):
        db = self.open()
        three = {u: i for u, i in list(self.FIVE.items())[2:]}
        with DbTxn("first", db) as txn:
            citations.attach(db, txn, "city", three, prov(), {})
        left_out = []
        more = dict(three)
        more["https://example.net/another"] = {"claims": ["CONTAINERS"], "wikidata": False}
        with DbTxn("second", db) as txn:
            added = citations.attach(db, txn, "city", more, prov(), {}, left_out=left_out)
        self.assertEqual((added, left_out), (["example.net: another"], []))                      # the three that exist are not counted again

    def test_a_higher_confidence_comes_before_a_better_kind_of_site(self):
        db = self.open()
        two = {POLK_PAGE: {"claims": ["COORDINATES"], "wikidata": False},                      # the answer is unsure about COORDINATES: Very Low
               GENERAL_PAGE: {"claims": ["CONTAINERS"], "wikidata": False}}                     # Normal
        left_out = []
        with DbTxn("cite", db) as txn:
            added = citations.attach(db, txn, "city", two, prov(), {}, limit=1, left_out=left_out)
        self.assertEqual((added, left_out), (["example.org: general-history"], ["Wikipedia: Polk County, Iowa"]))

    def test_a_tourism_page_is_cited_with_low_confidence_and_the_note_says_why(self):
        db = self.open()
        trip = "https://www.tripadvisor.com/Tourism-Johnston.html"
        with DbTxn("cite", db) as txn:
            citations.attach(db, txn, "city", {trip: {"claims": ["CONTAINERS"], "wikidata": False}}, prov(), {})
        ((source, citation),) = self.cites(db, "city")
        self.assertEqual(citation.get_confidence_level(), Citation.CONF_LOW)
        self.assertIn("than an official record", db.get_note_from_handle(citation.get_note_list()[0]).get())
        self.assertEqual(source.get_publication_info(), trip)

    def test_the_same_page_in_another_form_uses_the_source_that_the_tree_has(self):
        db = self.open()
        with DbTxn("first", db) as txn:
            citations.attach(db, txn, "city", {POLK_PAGE: {"claims": ["CONTAINERS"], "wikidata": False}}, prov(), {})
        before = self.counts(db)
        with DbTxn("again", db) as txn:
            citations.attach(db, txn, "city", {"http://en.m.wikipedia.org/wiki/Polk_County,_Iowa/": {"claims": ["STATE_ON_DATE"], "wikidata": False}}, prov(), {})
        sources, cites, notes = self.counts(db)
        self.assertEqual((sources, cites, notes), (before[0], before[1] + 1, before[2] + 1))

    def test_the_results_name_the_sources_that_the_limit_left_out(self):
        db = self.open()
        coords = [p for p in self.proposals(db) if p["kind"] == "set-coordinates"][0]
        coords["evidence"] = [{"source": "ai-answer", "url": u, "claim": ", ".join(i["claims"])} for u, i in self.FIVE.items()]
        results = writer.apply_proposals(db, [coords], dry_run=False, provenance=prov())
        self.assertEqual(len(results[0]["cited"]), 3)
        self.assertEqual(len(results[0]["not_cited"]), 2)

    def test_a_wikidata_statement_is_cited_with_normal_confidence(self):
        db = self.open()
        coords = [p for p in self.proposals(db) if p["kind"] == "set-coordinates"]
        coords[0]["evidence"] = [{"source": "wikidata", "url": "https://www.wikidata.org/wiki/Q1", "claim": "P625 (coordinates) of Johnston"}]
        writer.apply_proposals(db, coords, dry_run=False, provenance=prov())
        ((source, citation),) = self.cites(db, "city")
        self.assertEqual((source.get_title(), citation.get_page(), citation.get_confidence_level()),
                         ("Wikidata Q1", "P625 (coordinates) of Johnston", Citation.CONF_NORMAL))
        text = db.get_note_from_handle(citation.get_note_list()[0]).get()
        self.assertIn("from Wikidata on 2026-10-14 while completing «Johnston».", text)
        self.assertNotIn("not sure", text)

    def test_the_results_name_the_sources_cited_for_each_proposal(self):
        db = self.open()
        results = writer.apply_proposals(db, self.proposals(db), dry_run=False, provenance=prov())
        cited = [r for r in results if r.get("cited")]
        self.assertTrue(cited)
        self.assertTrue(all(isinstance(t, str) for r in cited for t in r["cited"]))

    def test_a_proposal_without_evidence_leaves_no_citation(self):
        db = self.open()
        rename = [p for p in self.proposals(db) if p["kind"] == "rename-place" and p["place"] == "city"]
        before = self.counts(db)
        writer.apply_proposals(db, rename, dry_run=False, provenance=prov())
        self.assertEqual(self.counts(db), before)


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class SessionTests(DatabaseTests):
    def session(self, db):
        s = sess.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(ANSWER)
        return s

    def test_the_session_writes_the_citations_and_says_so(self):
        db = self.open()
        s = self.session(db)
        s.select_all(include_conflicts=True)
        s.apply(db)
        self.assertRegex(s.message, r"\d+ source\(s\) cited on modified places")
        title, citation = next((src.get_title(), c) for src, c in self.cites(db, "city") if "Johnston" in src.get_title())
        note = db.get_note_from_handle(citation.get_note_list()[0]).get()
        self.assertIn("«Johnston» on 1995", note)
        self.assertIn("answers", note)                                                      # the saved answer, to look at again

    def test_a_source_is_cited_on_the_place_that_it_is_about_and_not_on_every_place_of_the_chain(self):
        db = self.open()
        s = self.session(db)
        s.select_all(include_conflicts=True)
        s.apply(db)
        self.assertEqual(self.cited_titles(db, "Polk County"), ["Wikipedia: Polk County, Iowa"])                # its own page, on the new county only
        self.assertEqual(self.cited_titles(db, "City of Johnston"), ["Wikipedia: Johnston, Iowa", "example.org: general-history"])   # the main place: its page, and the general one
        self.assertEqual(self.cited_titles(db, "Iowa"), [])                                                       # no page is about Iowa: it gets none
        self.assertEqual(self.cited_titles(db, "USA"), [])

    def iowa_page_session(self, db, with_iowa):
        s = self.session(db)
        s.rec["sources"].append({"url": "https://en.wikipedia.org/wiki/Iowa", "supports": "CONTAINERS"})
        s.result = ingest.ingest(Tree.from_db(db), s.rec, "1995", aliases=ingest.alias_map([WORLD]))
        s.plan = planlib.make_plan(s.tree, s.result["proposals"], "test")
        s.selected = {p["id"] for p in s.plan["proposals"] if p["kind"] != "add-url" and (with_iowa or p.get("place") != "iowa")}
        return s

    def test_a_page_about_a_place_of_the_chain_is_cited_on_it_when_it_is_written_and_nowhere_when_it_is_not(self):
        db = self.open()
        self.iowa_page_session(db, True).apply(db)                                  # Iowa is changed (the period of its name): its page is cited on it
        self.assertEqual(self.cited_titles(db, "Iowa"), ["Wikipedia: Iowa"])
        for name in ("Polk County", "City of Johnston", "USA"):
            self.assertNotIn("Wikipedia: Iowa", self.cited_titles(db, name), name)
        db = self.open()
        self.iowa_page_session(db, False).apply(db)                                 # Iowa is not written now: nothing is cited for it, not even on another place
        self.assertEqual(self.cited_titles(db, "Iowa"), [])
        self.assertNotIn("Wikipedia: Iowa", {src.get_title() for src in map(db.get_source_from_handle, db.get_source_handles())})

    PARMA_PAGE = "https://en.wikipedia.org/wiki/Parma"

    def parma_run(self, alt_names=(), url=None, touch="prov"):
        """The city Parma (the place of the question) under its province, only the province is written: where does the page land?"""
        t = Tree({"it": typed("it", "Repubblica Italiana", 1, lang="it"), "er": typed("er", "Emilia-Romagna", 1, lang="it"),
                  "prov": typed("prov", "Provincia di Parma", 8, lang="it"), "parma": typed("parma", "Parma", 4, lang="it")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["prov"]["refs"] = [{"ref": "er", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "prov", "date": EMPTY}]
        t.places["prov"]["alt_names"] = [{"value": v, "lang": "it", "date": {}} for v in alt_names]
        db = self.open(t)
        proposal = {"id": 1, "kind": "add-name", "place": touch, "value": "Parmigiana", "lang": "it", "index": None, "old": {}, "new": {}, "basis": "assumption",
                    "origin": "ai-answer", "evidence": [{"source": "ai-answer", "url": url or self.PARMA_PAGE, "claim": "CONTAINERS"}]}
        writer.apply_proposals(db, [proposal], dry_run=False, provenance=prov(main="parma", chain=["prov", "er", "it"]))
        return {n: self.cited_titles(db, n) for n in ("Parma", "Provincia di Parma", "Emilia-Romagna", "Repubblica Italiana")}

    def test_the_page_of_the_main_place_goes_to_it_even_when_only_the_province_is_written(self):
        got = self.parma_run()
        self.assertEqual(got, {"Parma": ["Wikipedia: Parma"], "Provincia di Parma": [], "Emilia-Romagna": [], "Repubblica Italiana": []})

    def test_a_province_that_carries_the_name_of_its_city_as_another_name_does_not_take_the_citation_of_the_city(self):
        got = self.parma_run(alt_names=["Parma"])
        self.assertEqual((got["Parma"], got["Provincia di Parma"]), (["Wikipedia: Parma"], []))

    def test_the_page_of_the_province_goes_to_the_province_by_its_own_name(self):
        got = self.parma_run(alt_names=["Parma"], url="https://it.wikipedia.org/wiki/Provincia_di_Parma")
        self.assertEqual((got["Parma"], got["Provincia di Parma"]), ([], ["Wikipedia (it): Provincia di Parma"]))

    def test_a_page_that_is_about_a_place_by_its_other_name_only_still_goes_to_that_place(self):
        got = self.parma_run(alt_names=["Parmense"], url="https://it.wikipedia.org/wiki/Parmense")
        self.assertEqual((got["Parma"], got["Provincia di Parma"]), ([], ["Wikipedia (it): Parmense"]))

    def test_the_real_parma_answer_cites_its_page_on_parma_and_not_on_the_levels_above(self):
        from placecompleter import session as sessionlib
        t = Tree({"it": typed("it", "Repubblica Italiana", 1, lang="it"), "er": typed("er", "Emilia-Romagna", 1, lang="it"),
                  "parma": typed("parma", "Parma", 4, lang="it")}, [])
        t.places["er"]["refs"] = [{"ref": "it", "date": EMPTY}]
        t.places["parma"]["refs"] = [{"ref": "er", "date": EMPTY}]
        db = self.open(t)
        s = sessionlib.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Parma", "1990", engine="manual")
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_parma_1990.txt"), encoding="utf-8") as fh:
            s.receive(fh.read())
        s.select_all(include_conflicts=True)
        s.apply(db)
        self.assertIn("Wikipedia: Parma", self.cited_titles(db, "Parma"))
        for above in ("Repubblica Italiana", "Emilia-Romagna"):
            self.assertNotIn("Wikipedia: Parma", self.cited_titles(db, above), above)

    def test_the_confidence_of_the_citations_follows_the_answer_through_the_session(self):
        db = self.open()
        s = self.session(db)
        s.select_all(include_conflicts=True)
        s.apply(db)
        levels = {src.get_title(): c.get_confidence_level() for src, c in self.cites(db, "city") + self.cites(db, self.named(db, "Polk County"))}
        self.assertEqual(levels["Wikipedia: Polk County, Iowa"], Citation.CONF_NORMAL)                          # the answer does not doubt the containers
        self.assertEqual(levels["Wikipedia: Johnston, Iowa"], Citation.CONF_LOW)                                # it is not sure about COORDINATES
        self.assertEqual(s._doubts_about_the_answer(), [])

    def test_an_answer_that_is_identical_to_one_saved_for_another_date_gives_a_lower_confidence(self):
        db = self.open()
        work = tempfile.mkdtemp()
        first = sess.Session(Tree.from_db(db), work, pack_files=[WORLD])
        first.begin("Johnston", "1850", engine="manual")
        first.receive(ANSWER)                                                                                    # saved for 1850
        second = sess.Session(Tree.from_db(db), work, pack_files=[WORLD])
        second.begin("Johnston", "1995", engine="manual")
        second.receive(ANSWER)                                                                                   # the same text for 1995
        self.assertTrue(second._doubts_about_the_answer())
        self.assertTrue(second._doubts_about_the_answer()[0].startswith("CONFLICTS WITH SAVED RESPONSE"))
        second.select_all(include_conflicts=True)
        second.apply(db)
        levels = {src.get_title(): c.get_confidence_level() for src, c in self.cites(db, "city") + self.cites(db, self.named(db, "Polk County"))}
        self.assertEqual(levels["Wikipedia: Polk County, Iowa"], Citation.CONF_LOW)                              # was Normal
        self.assertEqual(levels["Wikipedia: Johnston, Iowa"], Citation.CONF_VERY_LOW)                            # was Low

    def levels(self, s):
        kinds = {p["id"]: p["kind"] for p in s.plan["proposals"]}
        return {tuple(sorted({kinds[x["id"]] for x in c["steps"]})): c["confidence_level"] for c in s.changes()}

    def test_each_change_shows_how_far_the_answer_can_be_relied_on(self):
        s = self.session(self.open())
        got = self.levels(s)
        self.assertEqual(got[("set-coordinates",)], "unsure")                        # the answer says it is not sure about COORDINATES
        self.assertEqual(got[("set-type",)], "reported")                             # it states it and cites a page
        self.assertEqual(got[("add-link", "add-place")], "inferred")                 # the level is put in between by the program's rule
        self.assertEqual(got[("set-name-language",)], "inferred")
        self.assertEqual(got[("set-name-date",)], "inferred")

    def test_an_answer_identical_to_one_saved_for_another_date_makes_every_change_of_it_unsure(self):
        db = self.open()
        work = tempfile.mkdtemp()
        first = sess.Session(Tree.from_db(db), work, pack_files=[WORLD])
        first.begin("Johnston", "1850", engine="manual")
        first.receive(ANSWER)
        second = sess.Session(Tree.from_db(db), work, pack_files=[WORLD])
        second.begin("Johnston", "1995", engine="manual")
        second.receive(ANSWER)
        self.assertEqual(set(self.levels(second).values()), {"unsure"})
        why = {c["confidence_why"] for c in second.changes()}
        self.assertIn("the response contains internal contradictions or conflicts with saved historical data", why)

    def test_the_screen_says_that_citations_will_be_added(self):
        db = self.open()
        s = self.session(db)
        self.assertTrue(any(t.startswith("Modified places will receive source citations") for t, _l in s.needs()))

    def test_without_pages_in_the_answer_there_is_nothing_to_say_and_nothing_to_cite(self):
        db = self.open()
        s = sess.Session(Tree.from_db(db), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(ANSWER.split("SOURCES:")[0] + "NOT_SURE: None\n")
        self.assertFalse(any("citation" in t for t, _l in s.needs()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
