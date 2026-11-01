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
"""The user guide says only what the program says: the labels it quotes are those of the window, the variables and the files it names are those of the code,
the examples of engines.json load, and its links go somewhere. When the program changes and the guide does not, a test here fails and names the line."""
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import engines                                                            # noqa: E402

GUIDE = os.path.join(ROOT, "docs", "USER_GUIDE.md")


def guide():
    with open(GUIDE, encoding="utf-8") as fh:
        return fh.read()


def program_text():
    parts = []
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "tests", "docs", "tools")]
        for name in files:
            if name.endswith(".py"):
                with open(os.path.join(folder, name), encoding="utf-8") as fh:
                    parts.append(fh.read())
    return "\n".join(parts)


def msgids():
    with open(os.path.join(ROOT, "po", "template.pot"), encoding="utf-8") as fh:
        text = fh.read()
    return [m.replace('"\n"', "") for m in re.findall(r'^msgid "(.*)"$', text, re.M)]


def slug(heading):
    """The anchor that GitHub makes of a heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class GuideTests(unittest.TestCase):
    def test_every_variable_that_the_program_reads_is_in_the_guide(self):
        names = set(re.findall(r"PLACECOMPLETER_[A-Z_]+", program_text()))
        self.assertGreaterEqual(len(names), 10)
        missing = sorted(n for n in names if n not in guide())
        self.assertEqual(missing, [], "variables that the guide does not mention")

    def test_the_labels_that_the_guide_quotes_for_the_window_are_labels_of_the_window(self):
        text = guide()
        table = text[text.index("## The Main Window"):text.index("## Interpreting Proposals")]
        labels = [label.replace("…", "…") for row in table.splitlines() if row.startswith("| **") for label in re.findall(r"\*\*(.+?)\*\*", row.split("|")[1])]
        self.assertGreaterEqual(len(labels), 14)
        ids = msgids()
        wrong = [label for label in labels if not any(m.replace("_", "", 1) == label or m.replace("_", "", 1).startswith(label) for m in ids)]      # (_Help: the mnemonic)
        self.assertEqual(wrong, [], "labels of the guide that the window does not have")

    def test_the_files_and_the_folders_of_the_table_are_those_of_the_program(self):
        code = program_text()
        for token in ("gramps-place-work", "answers", "window.json", "ollama-serve.log", "backups", "engines.json", "models.json", "settings.json", "keys",
                      "type-conventions.json", ".config"):
            self.assertIn(token, code, token)
            self.assertIn(token, guide(), token)

    def test_the_examples_of_engines_json_in_the_guide_load_as_engines(self):
        blocks = [json.loads(b) for b in re.findall(r"^    (\{\"engines\".*\})$", guide(), re.M)]
        self.assertGreaterEqual(len(blocks), 2)
        for block in blocks:
            with tempfile.TemporaryDirectory() as folder:
                path = os.path.join(folder, "engines.json")
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(block, fh)
                loaded = engines.load_engines(path)
            with open(os.path.join(ROOT, "placecompleter", "engines.py"), encoding="utf-8") as fh:
                engine_code = fh.read()
            for name, settings in block["engines"].items():
                self.assertIn(name, loaded)
                for key, value in settings.items():
                    self.assertEqual(loaded[name].get(key), value, "%s.%s" % (name, key))
                    self.assertIn('"%s"' % key, engine_code, "the engine code does not know the setting %r" % key)

    def test_the_contents_of_the_guide_lead_to_headings_that_exist(self):
        text = guide()
        anchors = {slug(h) for h in re.findall(r"^#{1,3} (.+)$", text, re.M)}
        links = re.findall(r"\]\(#([\w\-]+)\)", text)
        self.assertGreaterEqual(len(links), 10)
        self.assertEqual([a for a in links if a not in anchors], [])

    def test_the_files_that_the_guide_points_to_exist(self):
        for target in re.findall(r"\]\((?!http|#)([^)#]+)", guide()):
            self.assertTrue(os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", target))), target)
        for rel in ("data/type-conventions.json", "data/type-conventions.example-he.json", "docs/ANALYZER_RULES.md"):
            self.assertTrue(os.path.exists(os.path.join(ROOT, rel)), rel)

    def test_the_levels_of_confidence_and_the_forms_of_the_question_are_those_of_the_program(self):
        from placecompleter import prompts
        text = guide()
        for word in ("Confirmed", "Reported", "Inferred", "Unsure"):
            self.assertIn("**%s**" % word, text)
            self.assertIn(word, msgids())
        for form in ("auto", "table", "classic", "short", "dated", "long"):
            self.assertIn("`%s`" % form, text)
        self.assertEqual(sorted(f for f in prompts.FORMS if f != "auto"), sorted(["table", "classic", "short", "dated", "long"]))


    def test_the_numbers_of_the_guide_are_those_of_the_program(self):
        from placecompleter import citations, session
        words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
        text = guide()
        self.assertIn("at most %s new citations in one run" % words[citations.MAX_CITATIONS], text)
        self.assertIn("at most %s questions" % words[session.MAX_QUESTIONS], text)
        self.assertIn("up to %s questions in all" % words[session.MAX_QUESTIONS], text)
        from placecompleter import links
        self.assertIn("one Wikidata link, and at most %s other sites" % words[links.MAX_OFFICIAL], text)
        self.assertEqual(links.MAX_WIKIDATA, 1)

    def test_the_default_wikipedia_languages_are_those_that_the_guide_says(self):
        """The language of Gramps and then English (only English when Gramps is in English)."""
        from unittest import mock
        from placecompleter import settings
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"PLACECOMPLETER_SETTINGS": os.path.join(folder, "s.json")}):
            for variables, expected in (({"LANGUAGE": "he"}, ["he", "en"]), ({"LANGUAGE": "en"}, ["en"])):
                with mock.patch.dict(os.environ, dict({"LANGUAGE": "", "LC_ALL": "", "LANG": ""}, **variables)):
                    self.assertEqual(settings.wikipedia_languages(), expected)
        self.assertIn("The default** is the language of Gramps and then English (only English when Gramps is in English)", guide())

    def test_the_pictures_of_the_guide_exist(self):
        for target in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", guide()):
            self.assertTrue(os.path.exists(os.path.normpath(os.path.join(ROOT, "docs", target))), target)

    def test_the_pictures_have_one_width_a_modest_size_and_a_description_and_none_is_forgotten(self):
        import struct
        folder = os.path.join(ROOT, "docs", "screenshots")
        used = set(re.findall(r"!\[([^\]]+)\]\(screenshots/([^)]+)\)", guide()))
        names = {name for _alt, name in used}
        files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
        self.assertEqual(sorted(names), files, "a picture of the folder that the guide does not use, or the other way round")
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                header = fh.read(24)
            width, height = struct.unpack(">II", header[16:24])
            self.assertLessEqual(width, 800, name)                                                  # one width for all (a smaller picture is not enlarged)
            self.assertLessEqual(os.path.getsize(path), 450 * 1024, name)
            self.assertGreater(height, 100, name)
        self.assertTrue(all(alt.strip() for alt, _name in used))

    def test_the_guide_does_not_promise_what_the_program_does_not_do(self):
        """Things that were once written and were not true (each was found by reading the program)."""
        text = guide()
        for sentence in ("fully non-destructive", "safe additions", "fully offline", "completely offline", "alternative names, coordinates"):
            self.assertNotIn(sentence, text, sentence)


class GuideExampleTests(unittest.TestCase):
    """The snippets of JSON in the section Describing a type yourself are read by the loaders of the addon, and what the section says about them is true."""
    @staticmethod
    def blocks():
        import re
        with open(os.path.join(ROOT, "docs", "USER_GUIDE.md"), encoding="utf-8") as fh:
            text = fh.read()
        section = text[text.index("### Describing a type yourself"):]
        section = section[:section.find("\n## ")] if "\n## " in section else section
        return re.findall(r"<!-- json-(file|line):(\w+) -->\n```json\n(.*?)\n```", section, re.S)

    def test_the_section_has_its_examples(self):
        kinds_found = [(a, b) for a, b, _ in self.blocks()]
        self.assertGreaterEqual(kinds_found.count(("file", "conventions")), 2)
        self.assertGreaterEqual(kinds_found.count(("line", "conventions")), 5)
        self.assertEqual(kinds_found.count(("file", "vocabulary")), 1)

    def test_every_example_is_valid_json_that_the_addon_reads(self):
        import json
        import tempfile
        from placecompleter import kinds, typelearn
        for shape, which, code in self.blocks():
            text = code if shape == "file" else "{" + code.rstrip().rstrip(",") + "}"
            data = json.loads(text)                                                          # valid JSON, as the guide asks
            with tempfile.TemporaryDirectory() as d:
                if which == "conventions":
                    with open(os.path.join(d, "type-conventions.json"), "w", encoding="utf-8") as fh:
                        fh.write(text)
                    read = kinds.load_tree_types(d)
                    for key, value in data.items():
                        if key == "description":
                            continue
                        if key == "rules":
                            self.assertEqual([(r["words"], r["string"]) for r in read["rules"]], [([w.lower() for w in r["words"]], r["string"]) for r in value])
                            self.assertTrue(all(r["value"] == 0 for r in read["rules"]))
                        else:
                            self.assertEqual(read[key], value, key)
                else:
                    path = os.path.join(d, "type-vocabulary.json")
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(text)
                    groups = typelearn.load_vocabulary([path])
                    self.assertEqual([(g["role"], g["words"]) for g in groups], [(g["role"], g["words"]) for g in data["groups"]])

    def test_the_file_as_copied_is_the_empty_file_of_the_addon(self):
        import json
        shown = json.loads(self.blocks()[0][2])
        with open(os.path.join(ROOT, "data", "type-conventions.json"), encoding="utf-8") as fh:
            shipped = json.load(fh)
        self.assertEqual({k: v for k, v in shown.items() if k != "description"}, {k: v for k, v in shipped.items() if k != "description"})

    def test_a_file_with_a_mistake_is_ignored_as_a_whole_and_json_tool_names_it(self):
        import subprocess
        import tempfile
        from placecompleter import kinds
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "type-conventions.json")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"settlements": ["Homestead"], "district": ["Okres"],}')          # a comma after the last item
            read = kinds.load_tree_types(d)
            self.assertEqual((read["settlements"], read["district"]), ([], []))
            bad = subprocess.run([sys.executable, "-m", "json.tool", path], capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("line 1", bad.stderr)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"settlements": ["Homestead"], "district": ["Okres"]}')
            self.assertEqual(subprocess.run([sys.executable, "-m", "json.tool", path], capture_output=True, text=True).returncode, 0)
            self.assertEqual(kinds.load_tree_types(d)["settlements"], ["Homestead"])

    def test_the_vocabulary_is_read_at_every_question(self):
        from unittest import mock
        from placecompleter import typelearn
        from placecompleter.model import Tree
        with mock.patch.object(typelearn, "load_vocabulary", wraps=typelearn.load_vocabulary) as load:
            typelearn.learn(Tree({}, []))
            typelearn.learn(Tree({}, []))
        self.assertEqual(load.call_count, 2)


if __name__ == "__main__":
    unittest.main()
