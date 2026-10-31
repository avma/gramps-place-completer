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
"""The structure of the analysis: ingest() is a list of steps, each topic has its own module, the modules do not import each other in a circle, and the names that
the rest of the program and the tests read from ingest are still there."""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import ingest                                                             # noqa: E402

TOPICS = {"words": "the folding of names and the word lists", "kinds": "the types of places", "periods": "the arithmetic of dates", "reader": "the text of the answer",
          "matching": "the places of the tree", "compare": "two answers", "screen": "what the screen shows", "evidence": "the sources of a proposal",
          "findplace": "the place of the question", "resolve": "the levels of the answer", "makeplaces": "the places that the answer makes",
          "chainlinks": "the links of the chain", "namefixes": "the names and the web links", "analysis": "the state that the steps share"}
STEPS = ["find_place", "check_levels", "prepare_levels", "read_levels", "new_place", "fix_levels", "existing_place", "link_chain", "chain_notes", "names_and_links", "finish"]
# what the program and the tests read from ingest (from the answers to the helpers): none of them may disappear
READ_FROM_INGEST = ["parse_structured", "ingest", "alias_map", "_container_type", "TREE_TYPES", "_type_matches", "match_container", "_tokens", "_piece", "preview_for",
                    "_short_form", "INF", "load_tree_types", "_type_conflict", "_sources", "_period", "_state_type", "SETTLEMENT_CLASSES", "refined_place", "candidate_hints",
                    "compare_with_saved", "compare_answers", "_custom", "url_proposal", "_unit_words", "_supported_fields", "_need", "parse_date", "_bound", "fold",
                    "_ancestors", "_name_really_ended", "SAME_PLACE_KM", "LABELS", "_lbl"]


def source(name):
    with open(os.path.join(ROOT, "placecompleter", name + ".py"), encoding="utf-8") as fh:
        return fh.read()


def imported_modules(name):
    """The modules of the package that a module imports at its top level."""
    found = set()
    for node in ast.parse(source(name)).body:
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            found.add((node.module or "").split(".")[0])
            found.update(a.name for a in node.names if not node.module)
    return {m for m in found if m}


class StructureTests(unittest.TestCase):
    def test_every_topic_has_its_module_with_a_docstring(self):
        for name in TOPICS:
            tree = ast.parse(source(name))
            self.assertTrue(ast.get_docstring(tree), name)

    def test_ingest_is_a_list_of_steps_and_short(self):
        tree = ast.parse(source("ingest"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ingest")
        self.assertLess(fn.end_lineno - fn.lineno + 1, 60)
        calls = [n.value.func.id for n in fn.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)]
        self.assertEqual(calls, STEPS)

    def test_every_step_is_a_function_of_the_analysis_in_the_module_of_its_topic(self):
        where = {"findplace": ["find_place"], "resolve": ["check_levels", "prepare_levels", "read_levels"], "makeplaces": ["new_place", "fix_levels"],
                 "chainlinks": ["existing_place", "link_chain", "chain_notes"], "namefixes": ["names_and_links"], "screen": ["finish"]}
        for module, names in where.items():
            tree = ast.parse(source(module))
            defined = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            for name in names:
                self.assertIn(name, defined, (module, name))
                self.assertEqual([a.arg for a in defined[name].args.args], ["a"], name)

    def test_the_modules_of_the_topics_do_not_import_each_other_in_a_circle(self):
        graph = {name: {m for m in imported_modules(name) if m in TOPICS} for name in TOPICS}
        done, stack = set(), []

        def visit(name):
            self.assertNotIn(name, stack, "a circle: %s" % " -> ".join(stack + [name]))
            if name in done:
                return
            stack.append(name)
            for other in graph[name]:
                visit(other)
            stack.pop()
            done.add(name)
        for name in graph:
            visit(name)

    def test_no_topic_module_imports_ingest(self):
        for name in TOPICS:
            self.assertNotIn("ingest", imported_modules(name), name)

    def test_what_the_rest_of_the_program_reads_from_ingest_is_still_there(self):
        for name in READ_FROM_INGEST:
            self.assertTrue(hasattr(ingest, name), name)

    def test_the_names_that_moved_are_the_same_objects_in_ingest_and_in_their_module(self):
        from placecompleter import kinds, reader, matching
        self.assertIs(ingest.parse_structured, reader.parse_structured)
        self.assertIs(ingest.TREE_TYPES, kinds.TREE_TYPES)                                         # one dictionary: a test that patches it patches it for all
        self.assertIs(ingest.match_container, matching.match_container)


if __name__ == "__main__":
    unittest.main()


class VersionTests(unittest.TestCase):
    def test_the_registration_and_the_engine_say_the_same_version(self):
        import re
        import placecompleter
        with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
            versions = set(re.findall(r'version="([0-9.]+)"', fh.read()))
        self.assertEqual(versions, {placecompleter.__version__})

    def test_the_user_agent_names_the_version(self):
        import placecompleter
        from placecompleter import wikidata
        self.assertIn("PlaceCompleter/" + placecompleter.__version__, wikidata.USER_AGENT)
        self.assertIn("https://github.com/avma/gramps-place-completer", wikidata.USER_AGENT)         # a way to reach the author, as Wikimedia asks


class RegistrationTests(unittest.TestCase):
    """What the addon manager of Gramps shows about the addon: it says that it is experimental, who wrote it, and where the help is."""

    def registrations(self):
        import ast
        with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        return [{kw.arg: kw.value for kw in node.keywords} for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "register"]

    def test_every_registration_is_experimental_and_has_a_help_address(self):
        import ast
        regs = self.registrations()
        self.assertEqual(len(regs), 4)                                                         # the tool, two gramplets, the quick view
        for kw in regs:
            self.assertEqual(ast.unparse(kw["status"]), "EXPERIMENTAL", kw["id"].value)
            self.assertEqual(ast.unparse(kw["help_url"]), "HELP_URL", kw["id"].value)

    def test_the_help_address_is_the_guide_that_the_help_button_opens(self):
        import ast
        import placecompleter
        with open(os.path.join(ROOT, "PlaceCompleter.gpr.py"), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        value = next(n.value.value for n in tree.body if isinstance(n, ast.Assign) and n.targets[0].id == "HELP_URL")
        self.assertEqual(value, placecompleter.GUIDE_URL)
        self.assertTrue(placecompleter.GUIDE_URL.startswith(placecompleter.HOMEPAGE + "/"))
        self.assertTrue(placecompleter.GUIDE_URL.endswith("docs/USER_GUIDE.md"))

    def test_the_author_is_the_holder_of_the_copyright(self):
        import ast
        for kw in self.registrations():
            if "authors" in kw:
                self.assertEqual([e.value for e in kw["authors"].elts], ["Avi Markovitz"], kw["id"].value)
