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
"""The Hebrew of the addon: what is translated keeps what the code reads, the catalog compiles, and the window speaks it.

The interface is English until the translation is finished (the Hebrew is the last stage: it is not shipped by default, see deploy_addon.py).
Until then the catalog may lack texts or keep old ones; the two checks of completeness run when PLACECOMPLETER_FINAL_TRANSLATION=1."""
import collections
import gettext
import io
import os
import re
import sys
import tempfile
import types
import unittest

os.environ["PLACECOMPLETER_KEYSTORE"] = "none"
os.environ["PLACECOMPLETER_ENGINES"] = "/nonexistent/engines.json"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import deploy_addon                                                                         # noqa: E402
import extract_strings                                                                      # noqa: E402
from placecompleter import i18n, ingest, msgfmt, session as sess                            # noqa: E402
from placecompleter.model import Tree                                                       # noqa: E402
from test_engine import EMPTY                                                               # noqa: E402
from test_ingest import WORLD, typed                                                        # noqa: E402

PO = os.path.join(ROOT, "po", "he-local.po")
TEXTS = list(extract_strings.extract())
CATALOG = msgfmt.parse_po(open(PO, encoding="utf-8").read())
IN_BOTH = [t for t in TEXTS if t in CATALOG]                                                # what is translated so far
FINAL = os.environ.get("PLACECOMPLETER_FINAL_TRANSLATION") == "1"
# the program reads these words in the texts it shows (an error code, a key prefix, a command): a translation must keep them
PROTECTED = ("HTTP", "sk-ant-", "chmod 600", "key_file", "PLACECOMPLETER_KEYSTORE", "YYYY-MM-DD", "--hint", "$%s", '{"engines"', "secret-tool",
             "libsecret")
PLACEHOLDER = re.compile(r"%\(\w+\)[sdrf]|%[-+ #0]*\d*(?:\.\d+)?[sdrf]|%%")


def hebrew():
    return gettext.GNUTranslations(io.BytesIO(msgfmt.compile_mo(CATALOG)))


class CatalogTests(unittest.TestCase):
    @unittest.skipUnless(FINAL, "the translation is finished at the last stage: PLACECOMPLETER_FINAL_TRANSLATION=1 checks that it is complete")
    def test_every_text_has_a_hebrew_translation(self):
        self.assertEqual([t for t in TEXTS if t not in CATALOG], [])

    @unittest.skipUnless(FINAL, "the translation is finished at the last stage: PLACECOMPLETER_FINAL_TRANSLATION=1 checks that nothing is old")
    def test_there_is_no_translation_of_a_text_that_does_not_exist_any_more(self):
        self.assertEqual([m for m in CATALOG if m and m not in set(TEXTS)], [])

    def test_the_placeholders_are_the_same_in_both_languages(self):
        bad = [m for m in IN_BOTH if collections.Counter(PLACEHOLDER.findall(m)) != collections.Counter(PLACEHOLDER.findall(CATALOG[m]))]
        self.assertEqual(bad, [])

    def test_what_the_program_reads_in_a_text_is_kept(self):
        bad = [(m[:50], token) for m in IN_BOTH for token in PROTECTED if token in m and token not in CATALOG[m]]
        self.assertEqual(bad, [])

    def test_spaces_and_signs_at_the_ends_are_kept_because_the_texts_are_joined(self):
        bad = []
        for m in IN_BOTH:
            h = CATALOG[m]
            joined_with_a_hyphen = m in ("from ", "to ")                                   # a Hebrew prefix is written against the number with a hyphen
            if m.startswith((" ", ";", ",")) != h.startswith((" ", ";", ",")) or (m.endswith(" ") != h.endswith(" ") and not joined_with_a_hyphen):
                bad.append(m)
        self.assertEqual(bad, [])

    def test_the_translations_are_hebrew(self):
        english_only = [m for m in IN_BOTH if not re.search(r"[\u0590-\u05ff]", CATALOG[m]) and m not in ("Google AI mode", "%(type)s, %(date)s", "Wikidata: %s: %s%s",
                                                                                                         "  %d. %s  (%s, %s)%s", "%s…%s, %d characters")]
        self.assertEqual(english_only, [])

    def test_the_texts_of_the_registration_file_are_translated(self):
        """The names in the menu and the titles of the gramplets are read from PlaceCompleter.gpr.py: they must be in the catalog, in Hebrew."""
        import ast
        with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        texts = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_"
                 and n.args and isinstance(n.args[0], ast.Constant)}
        self.assertGreaterEqual(len(texts), 5)
        for text in texts:
            self.assertIn(text, CATALOG, text)
            self.assertTrue(re.search(r"[\u0590-\u05ff]", CATALOG[text]), text)

    def test_the_template_is_up_to_date(self):
        pot = open(os.path.join(ROOT, "po", "template.pot"), encoding="utf-8").read()
        self.assertEqual(len(re.findall(r"^msgid ", pot, re.M)), len(TEXTS) + 1)          # and the header

    def test_a_text_in_the_code_is_never_a_variable_the_extractor_cannot_see(self):
        """tr(x) and _(x) with something that is not a text hide a text from the catalog. The few known ones are named here."""
        import ast
        allowed = {("placecompleter_tool.py", "_(change['basis'])"), ("placecompleter_tool.py", "_(change['flag'])"), ("placecompleter/session.py", "tr(same)"), ("placecompleter/session.py", "tr(message)"),
                   ("placecompleter/screen.py", "tr(msgid)")}
        unseen = set()
        for rel in extract_strings.FILES:
            tree = ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "tr") and node.args \
                        and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    unseen.add((rel, ast.unparse(node)))
        self.assertEqual(unseen - allowed, set())



class GrampsCatalogLeakTests(unittest.TestCase):
    """Gramps's own catalog translates the words that it knows. A word of a sentence of this addon that goes through the translator alone comes out in Hebrew inside an
    English sentence (the word after, for instance). Sentences are whole texts; the words of Gramps that this addon shows on purpose (buttons, labels, types, levels of confidence) are named."""
    ON_PURPOSE = {"_Close", "_Cancel", "_OK", "Confidence", "Download", "Remove", "Select", "Select all", "Place", "Date", "Very Low", "Low", "Normal", "type",
                  "Country", "State", "County", "City", "Parish", "Locality", "Street", "Province", "Region", "Department", "Neighborhood", "District", "Borough",
                  "Municipality", "Town", "Village", "Hamlet", "Farm", "Building", "Number"}

    def test_no_word_of_a_sentence_is_translated_by_the_catalog_of_gramps_alone(self):
        import gettext
        path = os.path.join(os.environ.get("GRAMPS_RESOURCES", ""), "locale", "he", "LC_MESSAGES", "gramps.mo")
        if not os.path.exists(path):
            self.skipTest("the catalog of Gramps in Hebrew is not here")
        with open(path, "rb") as fh:
            gramps = gettext.GNUTranslations(fh)
        template = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "po", "template.pot")
        with open(template, encoding="utf-8") as fh:
            ids = re.findall(r'^msgid "(.*)"$', fh.read(), re.M)
        leaks = sorted(m for m in ids if m and gramps.gettext(m) != m)
        self.assertEqual([m for m in leaks if m not in self.ON_PURPOSE], [])

class CompilerTests(unittest.TestCase):
    def test_parse_handles_continuation_lines_escapes_comments_and_fuzzy(self):
        text = ('# comment\nmsgid ""\nmsgstr ""\n"Language: he\\n"\n\n#: x.py:1\nmsgid "one \\"two\\"\\n"\nmsgstr "ünï "\n"cödé"\n\n'
                '#, fuzzy\nmsgid "fuzzy"\nmsgstr "not used"\n\nmsgid "empty"\nmsgstr ""\n')
        got = msgfmt.parse_po(text)
        self.assertEqual(got["one \"two\"\n"], "ünï cödé")                              # (non-ASCII text, whatever the language)
        self.assertNotIn("fuzzy", got)                                                   # a doubtful translation is not used
        self.assertNotIn("empty", got)                                                   # and a missing one is shown in English
        self.assertIn("Language: he", got[""])

    def test_the_compiled_file_is_read_back_by_the_standard_library(self):
        t = hebrew()
        for msgid in IN_BOTH:
            self.assertEqual(t.gettext(msgid), CATALOG[msgid])
        self.assertEqual(t.gettext("not a text of the addon"), "not a text of the addon")
        self.assertEqual(t.charset(), "UTF-8")

    def test_a_text_with_a_newline_and_quotes_survives(self):
        text = "Could not launch web browser. Please open this URL manually:\n%s"
        self.assertEqual(hebrew().gettext(text), CATALOG[text])
        self.assertIn("\n\u202a%s\u202c", CATALOG[text])                  # the address is wrapped in the marks of direction (LRE ... PDF)


class InstallTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_translator(None)

    def test_the_translator_of_the_addon_is_installed_for_the_whole_engine(self):
        from unittest import mock
        fake = types.SimpleNamespace(get_addon_translator=lambda filename: types.SimpleNamespace(gettext=lambda s: "<" + s + ">"),
                                     translation=types.SimpleNamespace(gettext=lambda s: s))
        with mock.patch("gramps.gen.const.GRAMPS_LOCALE", fake):
            function = i18n.install_from_gramps(__file__)
        self.assertEqual(function("Ask"), "<Ask>")
        self.assertEqual(i18n._("Ask"), "<Ask>")

    def test_without_a_translation_of_the_addon_the_language_of_gramps_alone_is_used(self):
        from unittest import mock

        def refuse(filename):
            raise OSError("no locale folder")
        fake = types.SimpleNamespace(get_addon_translator=refuse, translation=types.SimpleNamespace(gettext=lambda s: s.upper()))
        with mock.patch("gramps.gen.const.GRAMPS_LOCALE", fake):
            function = i18n.install_from_gramps(__file__)
        self.assertEqual((function("Ask"), i18n._("Ask")), ("ASK", "ASK"))


class DeployTests(unittest.TestCase):
    def test_the_deploy_compiles_the_translation_into_the_folder_gramps_reads(self):
        target = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(target, ignore_errors=True))
        report = deploy_addon.deploy(target, translations=True)
        rel = os.path.join("locale", "he", "LC_MESSAGES", "addon.mo")
        self.assertIn(rel, report["written"])
        t = gettext.GNUTranslations(open(os.path.join(target, rel), "rb"))
        self.assertEqual(t.gettext("Ask"), CATALOG["Ask"])
        self.assertIn(rel, deploy_addon.deploy(target, translations=True)["same"])       # nothing is written twice

    def test_a_dry_run_writes_no_translation(self):
        target = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(target, ignore_errors=True))
        report = deploy_addon.deploy(target, dry_run=True, translations=True)
        self.assertIn(os.path.join("locale", "he", "LC_MESSAGES", "addon.mo"), report["written"])
        self.assertFalse(os.path.exists(os.path.join(target, "locale")))


class SpeakingTests(unittest.TestCase):
    """With the Hebrew installed the engine's texts are Hebrew, while what the code and the tests read stays English."""
    def setUp(self):
        i18n.set_translator(hebrew().gettext)
        self.addCleanup(lambda: i18n.set_translator(None))

    def tree(self):
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["city"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        return t

    ANSWER = ("PLACE_NAME_ON_DATE: Johnston\nLANGUAGE: en\nSETTLEMENT_TYPE_ON_DATE: city\nCONTAINERS:\n1 | Polk County | county | 1846-present | Iowa\n"
              "2 | Iowa | state | 1846-present | United States\nSTATE_ON_DATE: United States | 1776-present\n"
              "SOURCES: https://en.wikipedia.org/wiki/Johnston,_Iowa | PLACE_NAME_ON_DATE\n")

    def h(self, msgid):
        """The translation of a text, from the catalogue; the test waits when it is not made yet (the translation is finished at the last stage)."""
        if msgid not in CATALOG:
            self.skipTest("the translation of %r is not made yet" % msgid[:50])
        return CATALOG[msgid]

    def session(self):
        s = sess.Session(self.tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(self.ANSWER)
        return s

    def test_a_message_of_the_session_is_in_hebrew(self):
        s = sess.Session(self.tree(), tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        with self.assertRaises(ValueError) as ctx:
            s.apply(None)                                                                  # nothing is checked yet
        self.assertEqual(str(ctx.exception), self.h("No items selected."))
        self.assertNotEqual(str(ctx.exception), "No items selected.")

    def test_the_words_of_a_proposal_and_its_change_are_in_hebrew(self):
        titles = [c["title"] for c in self.session().changes()]
        pieces = self.h("Insert %s between %s and %s").split("%s")
        self.assertTrue(any(t.startswith(pieces[0]) and pieces[1] in t for t in titles), titles)
        flags = {c["flag"] for c in self.session().changes()}
        self.assertTrue(flags & {self.h("inserts intermediate level"), self.h("populates unassigned field")}, flags)

    def test_the_notes_are_shown_in_hebrew_and_the_english_stays_for_the_code(self):
        r = ingest.ingest(self.tree(), ingest.parse_structured(self.ANSWER), "1995", aliases=ingest.alias_map([WORLD]))
        self.assertEqual(len(r["needs"]), len(r["needs_local"]))
        index = next(i for i, n in enumerate(r["needs"]) if n.startswith("These links already exist and require no changes:"))
        self.assertEqual(r["needs"][index], "These links already exist and require no changes: Iowa [IOWA] -> United States")
        self.assertEqual(r["needs_local"][index], self.h("These links already exist and require no changes: %s") % "Iowa [IOWA] -> United States")

    def test_a_conflict_is_a_warning_in_hebrew_too(self):
        self.h("CONFLICT: in the tree %s is linked to %s, but the answer puts it under %s (from %s), and the program cannot tell which is right. Result "
               "if you apply it: %s is moved to %s, and its link to %s is kept only for the years before. It is not selected: check which is right first")
        t = Tree({"iowa": typed("iowa", "Iowa", 2, lang="en"), "kansas": typed("kansas", "Kansas", 2, lang="en"), "usa": typed("usa", "USA", 1, lang="en"),
                  "polk": typed("polk", "Polk County", 3, lang="en"), "city": typed("city", "Johnston", 4, lang="en")}, [])
        t.places["city"]["refs"] = [{"ref": "kansas", "date": EMPTY}]
        t.places["polk"]["refs"] = [{"ref": "iowa", "date": EMPTY}]
        t.places["iowa"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        t.places["kansas"]["refs"] = [{"ref": "usa", "date": EMPTY}]
        s = sess.Session(t, tempfile.mkdtemp(), pack_files=[WORLD])
        s.begin("Johnston", "1995", engine="manual")
        s.receive(self.ANSWER)
        conflicts = [(text, level) for text, level in s.needs() if text.startswith(self.h("CONFLICT") + ":")]
        self.assertTrue(conflicts)
        self.assertEqual({level for _t, level in conflicts}, {"warning"})                 # the importance is read from the English

    def test_the_importance_of_a_disagreement_with_a_saved_answer_survives_the_translation(self):
        s = self.session()
        s._extra_needs.append(("CONFLICTS WITH SAVED RESPONSE: x", i18n._("CONFLICTS WITH SAVED RESPONSE: ") + "x"))
        prefix = self.h("CONFLICTS WITH SAVED RESPONSE: ")
        shown = [(t, level) for t, level in s.needs() if t.startswith(prefix)]
        self.assertEqual(shown, [(prefix + "x", "warning")])

    def test_the_type_names_of_a_new_place_are_in_hebrew(self):
        start = self.h("Create place «%s»%s").split("%s")[0]
        steps = [st["text"] for c in self.session().changes() for st in c["steps"] if st["text"].startswith(start)]
        from gramps.gen.lib import PlaceType
        # the type is the word that Gramps shows for it (in a real window Gramps and the addon speak the same language), the period is the addon's Hebrew
        self.assertTrue(steps and str(PlaceType(3)) in steps[0] and (self.h("from ") + "1846") in steps[0], steps)

    def test_an_error_keeps_http_so_that_a_refused_key_is_still_recognised(self):
        from placecompleter import engines
        text = i18n._("service returned HTTP error %s: %s") % (401, "x")
        self.assertIn("HTTP 401", text)
        self.assertTrue(engines.tr is not None)

    def test_without_a_translator_the_texts_are_english(self):
        i18n.set_translator(None)
        self.assertEqual(i18n._("Ask"), "Ask")


if __name__ == "__main__":
    unittest.main(verbosity=2)
