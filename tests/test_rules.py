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
"""placecompleter/rules.py: every rule has an id and a switch; with every rule on nothing changes, with one off exactly that rule stops."""
import contextlib
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import citations, ingest, rules, session as sess, table                   # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402
import test_citations                                                                         # noqa: E402
import test_existing_data as ted                                                              # noqa: E402
import test_real_answers as tra                                                               # noqa: E402
import test_ingest as ti                                                                      # noqa: E402
import test_same_names as same                                                                # noqa: E402
import test_settlement_types as types_                                                        # noqa: E402
import test_table as tab                                                                      # noqa: E402

spec = importlib.util.spec_from_file_location("replay_answers", os.path.join(ROOT, "tools", "replay_answers.py"))
replay_answers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_answers)


class RegistryTests(unittest.TestCase):
    def test_every_note_of_the_program_belongs_to_a_rule_and_every_rule_has_a_note(self):
        declared = [t for _f, t in replay_answers.declared_messages()]
        self.assertGreater(len(declared), 30)
        for template in declared:
            self.assertIsNotNone(rules.message_id(template), template)
        used = {rules.message_id(t) for t in declared}
        self.assertEqual(used, {m[0] for m in rules.MESSAGES})

    def test_the_ids_are_unique_and_the_groups_are_known(self):
        ids = [r["id"] for r in rules.all_rules()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertLessEqual({r["group"] for r in rules.all_rules()}, set("ABCDIN"))

    def test_the_rules_that_are_not_switchable_are_said_to_be_so(self):
        fixed = [r for r in rules.all_rules() if not r["switchable"]]
        self.assertTrue(fixed)
        self.assertTrue(all(r["kind"] == "fixed" for r in fixed))
        with self.assertRaises(ValueError):
            with rules.disabled("P0"):
                pass

    def test_every_rule_is_on_by_default_and_the_switch_is_undone(self):
        self.assertTrue(all(rules.on(r["id"]) for r in rules.all_rules()))
        with rules.disabled("LV1", "M21"):
            self.assertFalse(rules.on("LV1"))
            self.assertFalse(rules.on("M21"))
            self.assertTrue(rules.on("LV2"))
            with rules.disabled("LV2"):
                self.assertFalse(rules.on("LV1"))
                self.assertFalse(rules.on("LV2"))
            self.assertTrue(rules.on("LV2"))
        self.assertTrue(rules.on("LV1"))

    def test_the_environment_can_switch_rules_off_for_a_run(self):
        with mock.patch.dict(os.environ, {"PLACECOMPLETER_RULES_OFF": "LV1, M21"}):
            self.assertEqual((rules.on("LV1"), rules.on("M21"), rules.on("ST6")), (False, False, True))
        self.assertTrue(rules.on("LV1"))

    def test_a_rule_that_does_not_exist_cannot_be_switched(self):
        with self.assertRaises(ValueError):
            with rules.disabled("NOPE"):
                pass


class MessageRuleTests(unittest.TestCase):
    def screen(self):
        """The table answer of Aussonne, asked about 2026: two levels are not valid then (the canton of Grenade, Midi-Pyrenees): two notes of the rule M21."""
        return ingest.ingest(Tree({}, []), ingest.parse_structured(table.convert(tab.tsv(tab.ROWS))[0]), "2026")

    def test_a_note_is_not_made_when_its_rule_is_off_and_nothing_else_changes(self):
        on = self.screen()
        with rules.disabled("M21"):
            off = self.screen()
        self.assertEqual(len([n for n in on["needs"] if "according to defined time boundaries" in n]), 2)
        self.assertFalse(any("according to defined time boundaries" in n for n in off["needs"]))
        self.assertEqual(len(on["needs"]) - 2, len(off["needs"]))
        self.assertEqual(len(on["needs"]), len(on["needs_local"]))                                  # the two lists stay together
        self.assertEqual(len(off["needs"]), len(off["needs_local"]))
        self.assertEqual(replay_answers.fingerprint(on)[0], replay_answers.fingerprint(off)[0])     # what is proposed is the same

    def test_the_notes_of_the_table_reader_have_rules_too(self):
        rows = [(r[0], r[1], r[2], r[3], r[4], "wikipedia.org") for r in tab.ROWS]
        text = tab.tsv(rows, part_one=["Name: Aussonne | Language: fr | From: 1200 | Source: wikipedia.org", "Alternatives: NONE", ""])
        _out, notes = table.convert(text)
        self.assertEqual(len(notes), 2)
        with rules.disabled("M46", "M48"):
            self.assertEqual(table.convert(text)[1], [])


class BehaviorRuleTests(unittest.TestCase):
    def test_ST3_a_bare_word_of_the_list_decides(self):
        self.assertEqual(types_.parse("metropolis | commune"), (types_.CITY, ""))
        with rules.disabled("ST3"):
            self.assertEqual(types_.parse("metropolis | commune"), (None, "Metropolis"))

    def test_ST6_a_settlement_type_of_the_tree_can_change(self):
        self.assertEqual(len(types_.type_proposals(types_.MUNICIPALITY, "town | commune")), 1)
        with rules.disabled("ST6"):
            self.assertEqual(types_.type_proposals(types_.MUNICIPALITY, "town | commune"), [])

    def test_LV1_an_overlapping_structure_is_not_a_level(self):
        self.assertEqual(len(ingest.parse_structured(same.answer())["containers"]), 5)
        with rules.disabled("LV1"):
            self.assertEqual(len(ingest.parse_structured(same.answer())["containers"]), 6)

    def test_LV2_a_level_with_the_name_of_the_place_is_a_place_of_its_own(self):
        def handles():
            screen = ingest.ingest(same.tree(), ingest.parse_structured(same.answer("Blagnac")), "2026")
            return [p["handle"] for p in screen["proposals"] if p["kind"] == "add-place"]
        self.assertEqual(len(set(handles())), len(handles()))
        with rules.disabled("LV2"):
            self.assertNotEqual(len(set(handles())), len(handles()))                              # the old collision comes back

    def test_LV3_an_area_with_the_name_is_not_a_candidate(self):
        t = same.tree()
        t.places["pp"] = ti.typed("pp", "Parma", 8, lang="it")
        t.places["pc"] = ti.typed("pc", "Parma", 4, lang="it")
        rec = ingest.parse_structured(same.answer().replace("Blagnac", "Parma").replace("town | commune", "city | comune"))
        self.assertEqual(ingest.ingest(t, rec, "2026")["child"], "pc")
        with rules.disabled("LV3"):
            self.assertNotEqual(ingest.ingest(t, rec, "2026")["child"], "pc")

    def test_LK_web_links_are_offered_for_the_place(self):
        text = same.answer().replace("https://fr.wikipedia.org/wiki/Blagnac", "https://en.wikipedia.org/wiki/Blagnac")           # English is the default language of the links
        def urls():
            screen = ingest.ingest(same.tree(with_commune=True), ingest.parse_structured(text), "2026")
            return [p for p in screen["proposals"] if p["kind"] == "add-url"]
        self.assertTrue(urls())
        with rules.disabled("LK"):
            self.assertEqual(urls(), [])

    def test_CT2_CT5_the_citations_of_a_place_are_limited_and_go_where_they_belong(self):
        helper = test_citations.DatabaseTests("test_what_is_skipped_is_not_cited")
        db = helper.open()
        parma = test_citations.SessionTests("test_a_source_is_cited_on_the_place_that_it_is_about_and_not_on_every_place_of_the_chain")
        with rules.disabled("CT2"):
            with test_citations.DbTxn("cite", db) as txn:
                added = citations.attach(db, txn, "city", dict(helper.FIVE), test_citations.prov(), {})
        self.assertEqual(len(added), 5)                                                             # the limit of three is off
        got = parma.parma_run(alt_names=["Parma"])
        self.assertEqual((got["Parma"], got["Provincia di Parma"]), (["Wikipedia: Parma"], []))
        with rules.disabled("CT5"):
            got = parma.parma_run(alt_names=["Parma"])
        self.assertEqual((got["Parma"], got["Provincia di Parma"]), ([], ["Wikipedia: Parma"]))     # every place that is touched takes the sources of its change

    def test_CT4_a_tourism_site_is_cited_at_most_with_low_confidence(self):
        info = {"claims": ["CONTAINERS"], "wikidata": False}
        url = "https://www.tripadvisor.com/Tourism-Johnston.html"
        self.assertEqual(citations.confidence_for(info, test_citations.prov(), url)[0], citations.LOW)
        with rules.disabled("CT4"):
            self.assertEqual(citations.confidence_for(info, test_citations.prov(), url)[0], citations.NORMAL)


SISSA_MOVED = (tra.SissaMovedTests, "test_the_province_is_added_and_the_link_to_the_city_is_offered_as_a_disconnect_that_needs_it")
LOOP = (ted.DuplicateAndLoopNotesTests, "test_a_level_that_would_make_a_loop_is_left_out_with_a_note")
# the rules of the names and the links, each with a test that already shows what it does: the test passes with every rule on and fails when the rule is off
SHOWN_BY = {
    "NP1": (ted.NamePeriodTests, "test_a_name_in_the_tree_that_ends_with_the_place_is_offered_to_be_opened"),
    "NP3": (ti.RomanianCountyTests, "test_the_name_of_the_place_is_given_the_time_the_state_that_ruled_began"),
    "T1": LOOP,
    "T2": SISSA_MOVED,
    "C3": (tra.MessyLinksTests, "test_a_link_that_ends_before_it_starts_is_offered_the_period_of_the_answer"),
    "C4": (ti.ScreenTests, "test_the_old_link_is_kept_and_the_new_one_is_placed_before_it_so_each_year_has_its_chain"),
    "C5": SISSA_MOVED,
    "C6": (ti.InsertedLevelTests, "test_a_level_put_between_a_place_and_its_parent_is_not_a_conflict"),
    "C8": LOOP,
}


def passes(case, method, *off):
    result = unittest.TestResult()
    with rules.disabled(*off) if off else contextlib.nullcontext():
        case(method).run(result)
    return result.wasSuccessful()


class OldRulesTests(unittest.TestCase):
    """The rules that were in the code before the switches: a test that shows each passes while the rule is on and fails while it is off."""
    def test_every_one_of_them_is_in_the_registry_and_switchable(self):
        ids = {r["id"] for r in rules.all_rules() if r["switchable"]}
        self.assertLessEqual(set(SHOWN_BY), ids)

    def test_a_test_that_shows_a_rule_passes_with_the_rule_on(self):
        for rule_id, (case, method) in SHOWN_BY.items():
            self.assertTrue(passes(case, method), (rule_id, method))

    def test_the_same_test_fails_when_the_rule_is_off(self):
        for rule_id, (case, method) in SHOWN_BY.items():
            self.assertFalse(passes(case, method, rule_id), (rule_id, method))

    def test_a_rule_that_is_off_does_not_switch_off_the_others(self):
        case, method = SHOWN_BY["NP3"]
        self.assertTrue(passes(case, method, "NP1", "C3", "M21"))

    def test_NP5_a_name_of_a_level_of_the_tree_gets_the_period_of_the_answer(self):
        case = ti.RomanianCountyTests("test_the_name_of_the_place_is_given_the_time_the_state_that_ruled_began")
        text = case.ANSWER.replace("OTHER_NAMES:\nhu: D\u00e9va (1867-1918)\n", "")
        def fills():
            screen = ingest.ingest(case.tree(), ingest.parse_structured(text), "1990")
            return [p["place"] for p in screen["proposals"] if p["kind"] == "set-name-date" and p["place"] != "deva"]
        self.assertTrue(fills())
        with rules.disabled("NP5"):
            self.assertEqual(fills(), [])


class RecordingTests(unittest.TestCase):
    def test_the_notes_that_are_made_are_counted_by_their_rule_inside_a_recording(self):
        with rules.recording() as fired:
            ingest.ingest(Tree({}, []), ingest.parse_structured(table.convert(tab.tsv(tab.ROWS))[0]), "2026")
        self.assertEqual(fired["M21"], 2)
        with rules.recording() as again:
            pass
        self.assertEqual(dict(again), {})                                                          # a recording starts empty and nothing leaks outside

    def test_a_rule_that_is_off_is_not_counted(self):
        with rules.recording() as fired:
            with rules.disabled("M21"):
                ingest.ingest(Tree({}, []), ingest.parse_structured(table.convert(tab.tsv(tab.ROWS))[0]), "2026")
        self.assertNotIn("M21", fired)


class AblationTests(unittest.TestCase):
    def items(self):
        return [("Aussonne_2026.txt", "Aussonne", "2026", tab.tsv(tab.ROWS)), ("Blagnac_2026.txt", "Blagnac", "2026", same.answer())]

    def test_the_rules_are_switched_off_one_at_a_time_and_the_answers_that_change_are_counted(self):
        rows = {r["id"]: r for r in replay_answers.ablate(Tree({}, []), self.items())}
        self.assertEqual((rows["LV1"]["proposals"], rows["LV1"]["labels"]), (1, ["Blagnac_2026.txt"]))      # only the answer with an intercommunality
        self.assertEqual((rows["M21"]["proposals"], rows["M21"]["notes"]), (0, 1))                          # a note: the notes of one answer change, what is written does not
        self.assertEqual(rows["LV2"]["proposals"], 0)                                                       # no level here has the name of the place
        self.assertNotIn("CT2", rows)                                                                       # seen by writing, not by replay

    def test_the_analysis_is_not_run_again_for_a_rule_of_a_note(self):
        calls = []
        real = replay_answers.ingest.ingest

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)
        with mock.patch.object(replay_answers.ingest, "ingest", counting):
            replay_answers.ablate(Tree({}, []), self.items())
        behavior = len([r for r in rules.all_rules() if r["kind"] == "behavior" and r["measured"] == "replay"])
        self.assertEqual(len(calls), (1 + behavior) * 2)                                           # the answers once with every rule on, and once for each behavior rule

    def test_the_progress_is_told_while_it_runs(self):
        said = []
        replay_answers.ablate(Tree({}, []), self.items(), progress=said.append)
        self.assertEqual(said[0], "the answers, all the rules on ...")
        self.assertTrue(any(s.startswith("rule LV1 switched off") for s in said))

    def test_the_report_names_the_rules_without_an_effect_and_the_rules_with_notes_only(self):
        text = replay_answers.ablation_report(replay_answers.ablate(Tree({}, []), self.items()))
        self.assertIn("no effect on any answer:", text)
        self.assertIn("only notes change", text)
        self.assertIn("M21", text.split("only notes change")[1].splitlines()[0])
        self.assertIn("LV1 changes the proposals of: Blagnac_2026.txt", text)

    def test_a_rule_switched_off_for_a_whole_run_is_not_in_the_report(self):
        import contextlib
        import io
        work = tempfile.mkdtemp(prefix="pc-rules-")
        answers = os.path.join(work, "answers")
        os.makedirs(answers)
        with open(os.path.join(answers, "Aussonne_2026.txt"), "w", encoding="utf-8") as fh:
            fh.write(tab.tsv(tab.ROWS))
        for flag, expect in (([], True), (["--without", "M21"], False)):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                replay_answers.main(["--answers", answers, "--out", os.path.join(work, "r.tsv")] + flag)
            fired = buffer.getvalue().split("did NOT fire")[0]                                      # (the rule is in the list of those that did not fire)
            self.assertEqual("according to defined time boundaries" in fired, expect, flag)


if __name__ == "__main__":
    unittest.main()
