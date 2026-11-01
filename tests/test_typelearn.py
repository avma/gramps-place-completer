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
"""Learning the custom place types of a tree (typelearn.py): the ways of writing one type are joined, the types in use are read, the file of the user comes first."""
import copy
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

from placecompleter import kinds, levels, typelearn                                           # noqa: E402
from placecompleter.model import Tree                                                         # noqa: E402

VILLAGE = "\u05db\u05e4\u05e8"                  # a word of the language of the tree, written with escapes (no Hebrew letters in a .py file)
SUBDISTRICT = "\u05ea\u05ea \u05de\u05d7\u05d5\u05d6"
EMPTY = {"province": "", "empire": "", "monarchy": "", "district": [], "settlements": [], "rules": []}


def tree_of(*types):
    """A tree with one place for each type given: a text (a custom type) or a number (a type of Gramps)."""
    places = {}
    for i, t in enumerate(types):
        kind = {"value": 0, "string": t} if isinstance(t, str) else {"value": t, "string": ""}
        places["h%d" % i] = {"handle": "h%d" % i, "id": "P%d" % i, "type": kind, "name": {"value": "n%d" % i}, "alt_names": [], "refs": [], "urls": [], "lat": "", "lon": ""}
    return Tree(places, [])


class TypeKeyTests(unittest.TestCase):
    def test_the_ways_of_writing_one_type_have_one_key(self):
        writings = [VILLAGE, " " + VILLAGE, VILLAGE + " ", " " + VILLAGE + " ", "\u200f" + VILLAGE + "\u200e", "\u202a" + VILLAGE + "\u202c",
                    VILLAGE + "\u00a0", "\t" + VILLAGE, VILLAGE + ".", VILLAGE + "\n"]
        self.assertEqual({typelearn.type_key(w) for w in writings}, {VILLAGE})

    def test_case_accents_points_dashes_quotes_and_inner_spaces(self):
        self.assertEqual(typelearn.type_key("Village"), typelearn.type_key(" VILLAGE "))
        self.assertEqual(typelearn.type_key("J\u00e1r\u00e1s"), typelearn.type_key("jaras"))
        self.assertEqual(typelearn.type_key("\u0142\u00f3d\u017a"), typelearn.type_key("lodz"))
        self.assertEqual(typelearn.type_key(SUBDISTRICT), typelearn.type_key(SUBDISTRICT.replace(" ", "-")))
        self.assertEqual(typelearn.type_key(SUBDISTRICT), typelearn.type_key(SUBDISTRICT.replace(" ", "\u05be")))
        self.assertEqual(typelearn.type_key(SUBDISTRICT), typelearn.type_key(SUBDISTRICT.replace(" ", "   ")))
        self.assertEqual(typelearn.type_key("Market town"), typelearn.type_key("market  town"))
        self.assertEqual(typelearn.type_key("\u05e0\u05d9\u05e7\u05d5\u05d3"), typelearn.type_key("\u05e0\u05b4\u05d9\u05e7\u05d5\u05bc\u05d3"))     # points of the letters

    def test_different_types_have_different_keys(self):
        self.assertNotEqual(typelearn.type_key("jaras"), typelearn.type_key("kerulet"))
        self.assertNotEqual(typelearn.type_key("Town"), typelearn.type_key("Township"))
        self.assertNotEqual(typelearn.type_key(VILLAGE), typelearn.type_key(VILLAGE + "\u05d9\u05dd"))

    def test_nothing_is_written(self):
        for text in ("", None, "  ", "\u200f", " . "):
            self.assertEqual(typelearn.type_key(text), "")
        self.assertFalse(typelearn.same_type_text("", ""))
        self.assertFalse(typelearn.same_type_text(None, " "))
        self.assertFalse(typelearn.in_types("", [""]))

    def test_same_type_text_and_in_types(self):
        self.assertTrue(typelearn.same_type_text(" " + VILLAGE, VILLAGE + " "))
        self.assertTrue(typelearn.in_types(VILLAGE + " ", [SUBDISTRICT, " " + VILLAGE]))
        self.assertFalse(typelearn.in_types(VILLAGE, [SUBDISTRICT]))
        self.assertFalse(typelearn.in_types(VILLAGE, None))


class CensusTests(unittest.TestCase):
    def test_only_custom_types_in_use_are_counted(self):
        tree = tree_of(VILLAGE, VILLAGE, 16, -1, 4, "", " ", SUBDISTRICT)
        self.assertEqual(dict(typelearn.census(tree)), {VILLAGE: 2, SUBDISTRICT: 1})

    def test_a_type_that_no_place_uses_is_not_read(self):
        class Db:
            def get_place_types(self):                       # what Gramps remembers: it never forgets a type
                return [VILLAGE, "old type that no place has any more"]
        self.assertNotIn("old type that no place has any more", typelearn.census(tree_of(VILLAGE)))

    def test_the_writings_are_joined_and_the_tidy_most_used_one_is_the_name(self):
        counts = typelearn.census(tree_of(*([" " + VILLAGE] * 5 + [VILLAGE + " "] * 4 + [VILLAGE] * 2 + [SUBDISTRICT])))
        types = typelearn.unify(counts)
        self.assertEqual(set(types), {VILLAGE, SUBDISTRICT})
        village = types[VILLAGE]
        self.assertEqual(village["count"], 11)
        self.assertEqual(village["name"], VILLAGE)                       # tidy, though the writings with a slip are used more
        self.assertEqual(village["variants"], {" " + VILLAGE: 5, VILLAGE + " ": 4, VILLAGE: 2})

    def test_with_no_tidy_writing_the_most_used_is_the_name(self):
        types = typelearn.unify(typelearn.census(tree_of(*([" " + VILLAGE] * 3 + [VILLAGE + " "] * 2))))
        self.assertEqual(types[VILLAGE]["name"], " " + VILLAGE)

    def test_the_most_used_tidy_writing_wins_then_the_first_in_order(self):
        self.assertEqual(typelearn.pick_writing({"Village": 3, "village": 7}), "village")
        self.assertEqual(typelearn.pick_writing({"b": 2, "a": 2}), "a")

    def test_tidy(self):
        self.assertTrue(typelearn.tidy("Market town"))
        for bad in (" x", "x ", "a  b", "a\u00a0b", "\u200fx", "a\tb"):
            self.assertFalse(typelearn.tidy(bad), repr(bad))


class VocabularyTests(unittest.TestCase):
    def test_the_vocabulary_that_comes_with_the_addon_is_sound(self):
        groups = typelearn.load_vocabulary([os.path.join(ROOT, "data", "type-vocabulary.json")])
        self.assertGreaterEqual(len(groups), 10)
        seen = {}
        for group in groups:
            self.assertIn(group["role"], typelearn.ROLES)
            for key in group["keys"]:
                self.assertNotIn(key, seen, "%r is in two groups" % key)
                seen[key] = group["role"]
        self.assertEqual(seen[typelearn.type_key("J\u00e1r\u00e1s")], "district")
        self.assertNotEqual(next(g for g in groups if "jaras" in g["keys"]), next(g for g in groups if "kerulet" in g["keys"]))      # never joined

    def test_the_user_adds_groups_and_a_bad_group_is_ignored(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"groups": [{"role": "settlement", "words": [VILLAGE, "  "]}, {"role": "no such role", "words": ["x"]}, {"role": "district", "words": []},
                                      "text", {"role": "canton"}]}, fh)
            mine = typelearn.load_vocabulary([path])
            self.assertEqual([(g["role"], g["words"]) for g in mine], [("settlement", [VILLAGE])])
            with mock.patch.dict(os.environ, {"PLACECOMPLETER_VOCABULARY": path}):
                both = typelearn.load_vocabulary()
        self.assertEqual(both[-1]["words"], [VILLAGE])
        self.assertGreater(len(both), 10)


class LearnTests(unittest.TestCase):
    def setUp(self):
        self.groups = typelearn.load_vocabulary([os.path.join(ROOT, "data", "type-vocabulary.json")])

    def learn(self, *types):
        return typelearn.learn(tree_of(*types), self.groups)

    def test_a_tree_with_no_custom_types_knows_nothing(self):
        got = self.learn(16, 4, -1)
        self.assertEqual(got["types"], [])
        self.assertEqual(got["conventions"], EMPTY)

    def test_the_roles_come_from_the_vocabulary(self):
        got = self.learn("Kronland", "Kaiserreich", "Monarchie", "Falu", "Falu", "Kanton", VILLAGE)
        c = got["conventions"]
        self.assertEqual((c["province"], c["empire"], c["monarchy"]), ("Kronland", "Kaiserreich", "Monarchie"))
        self.assertEqual(c["settlements"], ["Falu"])
        roles = {t["name"]: t["role"] for t in got["types"]}
        self.assertEqual(roles, {"Kronland": "province", "Kaiserreich": "empire", "Monarchie": "monarchy", "Falu": "settlement", "Kanton": "canton", VILLAGE: ""})

    def test_a_type_that_the_vocabulary_does_not_know_is_listed_with_no_role(self):
        got = self.learn(VILLAGE, VILLAGE)
        self.assertEqual(got["types"][0]["role"], "")
        self.assertEqual(got["conventions"], EMPTY)

    def test_every_writing_of_a_type_gives_one_type(self):
        got = self.learn("Falu", "Falu", " Falu", "falu ", "FALU", "Falu\u200f")
        self.assertEqual(len(got["types"]), 1)
        self.assertEqual(got["types"][0]["count"], 6)
        self.assertEqual(got["conventions"]["settlements"], ["Falu"])

    def test_the_most_used_type_of_a_role_is_the_one(self):
        got = self.learn("Provinz", "Kronland", "Kronland", "Kronland")
        self.assertEqual(got["conventions"]["province"], "Kronland")

    def test_a_rule_is_made_when_one_type_fits_the_group(self):
        got = self.learn("Kanton", "Bezirk")
        rules = {r["string"]: r["words"] for r in got["conventions"]["rules"]}
        self.assertEqual(set(rules), {"Kanton", "Bezirk"})
        self.assertIn("cantone", rules["Kanton"])
        self.assertEqual(rules["Bezirk"], ["bezirk"])                  # a district of its own: not joined with kreis or okres
        self.assertEqual(sorted(got["conventions"]["district"]), ["Bezirk"])

    def test_two_types_of_one_group_are_a_distinction_that_the_owner_decides(self):
        got = self.learn("District", "district ", "Distretto")      # one group: the writings of District are one type, Distretto is another
        self.assertEqual(sorted(t["name"] for t in got["types"]), ["Distretto", "District"])
        self.assertEqual(got["conventions"]["rules"], [])               # no rule: which of the two an answer means is not guessed
        self.assertEqual(sorted(got["conventions"]["district"]), ["Distretto", "District"])


class MergeTests(unittest.TestCase):
    def test_the_file_of_the_user_comes_first(self):
        base = dict(EMPTY, province="Mine", district=["Dist A"], settlements=[VILLAGE], rules=[{"words": ["kanton"], "value": 0, "string": "Own canton"}])
        learned = dict(EMPTY, province="Learned", empire="Kaiserreich", district=["dist a", "Dist B"], settlements=[" " + VILLAGE, "Falu"],
                       rules=[{"words": ["kanton", "canton"], "value": 0, "string": "Kanton"}, {"words": ["bezirk"], "value": 0, "string": "Bezirk"}])
        before = copy.deepcopy((base, learned))
        out = typelearn.merge(base, learned)
        self.assertEqual(out["province"], "Mine")
        self.assertEqual(out["empire"], "Kaiserreich")                                   # what the file leaves empty is filled
        self.assertEqual(out["district"], ["Dist A", "Dist B"])                          # 'dist a' is the type of the file: not added again
        self.assertEqual(out["settlements"], [VILLAGE, "Falu"])
        self.assertEqual([r["string"] for r in out["rules"]], ["Own canton", "Bezirk"])  # the rule that shares a word with the file's is not added
        self.assertEqual((base, learned), before, "merge changes neither argument")


class KindsTests(unittest.TestCase):
    def tearDown(self):
        kinds.forget_tree()

    def test_learning_fills_the_conventions_in_place_and_the_file_alone_is_the_base(self):
        identity = id(kinds.TREE_TYPES)
        with mock.patch.dict(kinds.FILE_TYPES, copy.deepcopy(EMPTY), clear=True):
            kinds.learn_from(tree_of("Kronland", "Falu"))
            self.assertEqual(id(kinds.TREE_TYPES), identity)
            self.assertEqual(kinds.TREE_TYPES["province"], "Kronland")
            self.assertEqual(kinds.TREE_TYPES["settlements"], ["Falu"])
            kinds.learn_from(tree_of(16))                                                   # another tree: the first is forgotten
            self.assertEqual((kinds.TREE_TYPES["province"], kinds.TREE_TYPES["settlements"]), ("", []))
            self.assertEqual(kinds.LEARNED["types"], [])

    def test_the_type_of_the_tree_is_the_type_of_a_unit_that_the_answer_names(self):
        with mock.patch.dict(kinds.FILE_TYPES, copy.deepcopy(EMPTY), clear=True):
            kinds.learn_from(tree_of(16))                                                   # a tree with no custom type, and a file with none: the types of Gramps
            self.assertEqual(kinds._container_type("Kronland"), {"value": 8, "string": ""})
            kinds.learn_from(tree_of(" Kronland", "Kronland", "Kanton", "Kanton"))
            self.assertEqual(kinds._container_type("Kronland (crown land)"), {"value": 0, "string": "Kronland"})          # the tidy writing
            self.assertEqual(kinds._container_type("canton"), {"value": 0, "string": "Kanton"})
            kinds.learn_from(tree_of(" Kronland", " Kronland"))
            self.assertEqual(kinds._container_type("Kronland"), {"value": 0, "string": " Kronland"})                      # no tidy writing in the tree: the one it has, so that no second type is made

    def test_a_place_with_a_writing_of_the_type_is_the_kind_that_the_answer_names(self):
        with mock.patch.dict(kinds.FILE_TYPES, copy.deepcopy(EMPTY), clear=True):
            tree = tree_of("Kronland", " Kronland ", "Falu")
            kinds.learn_from(tree)
            self.assertTrue(kinds._type_matches(tree, "h0", "Kronland"))
            self.assertTrue(kinds._type_matches(tree, "h1", "Kronland"))                    # the writing with spaces is the same type
            self.assertFalse(kinds._type_matches(tree, "h2", "Kronland"))

    def test_levels_see_the_writings_of_one_type_as_one(self):
        conv = dict(EMPTY, settlements=[VILLAGE], district=[SUBDISTRICT])
        self.assertEqual(levels.level({"value": 0, "string": " " + VILLAGE + " "}, conv), levels.SETTLEMENT)
        self.assertEqual(levels.level({"value": 0, "string": SUBDISTRICT.replace(" ", "-")}, conv), levels.AREA)
        self.assertIsNone(levels.level({"value": 0, "string": VILLAGE + "x"}, conv))
        self.assertTrue(levels._same({"value": 0, "string": VILLAGE}, {"value": 0, "string": VILLAGE + "\u200f "}))

    def test_the_file_of_the_user_still_gives_the_same_answers(self):
        """With the file of the tests (the author's) and a tree with none of its types, nothing that the file says changes."""
        before = copy.deepcopy(kinds.FILE_TYPES)
        kinds.learn_from(tree_of(16, 4, -1))
        self.assertEqual(kinds.TREE_TYPES, before)


class BuiltinTests(unittest.TestCase):
    """A rule from a custom type of the tree must not turn the type of Gramps, which the tree uses far more, into a custom one."""
    def setUp(self):
        self.groups = typelearn.load_vocabulary([os.path.join(ROOT, "data", "type-vocabulary.json")])

    def learn(self, *types):
        return typelearn.learn(tree_of(*types), self.groups)

    def test_one_custom_type_among_many_of_gramps_makes_no_rule(self):
        got = self.learn(*([12] * 40 + ["District"]))
        self.assertEqual(got["conventions"]["rules"], [])
        self.assertEqual(got["skipped"], [{"name": "District", "count": 1, "builtin": 12, "builtin_count": 40}])
        self.assertEqual(got["conventions"]["district"], ["District"])                      # it is still a type of an area

    def test_a_custom_type_that_the_tree_uses_more_makes_the_rule(self):
        got = self.learn(*([12] + ["District"] * 3))
        self.assertEqual([r["string"] for r in got["conventions"]["rules"]], ["District"])
        self.assertEqual(got["skipped"], [])

    def test_the_same_number_of_places_makes_no_rule(self):
        got = self.learn(*([12] * 2 + ["District"] * 2))
        self.assertEqual(got["conventions"]["rules"], [])
        self.assertEqual(len(got["skipped"]), 1)

    def test_a_group_with_no_type_of_gramps_makes_the_rule_whatever_the_count(self):
        got = self.learn(*([12] * 40 + ["Okres"]))
        self.assertEqual([r["string"] for r in got["conventions"]["rules"]], ["Okres"])      # the engine has no type of Gramps for okres: it would be a custom type anyway
        self.assertEqual(got["skipped"], [])

    def test_the_answer_gets_the_type_of_gramps_when_the_rule_is_left_out(self):
        with mock.patch.dict(kinds.FILE_TYPES, copy.deepcopy(EMPTY), clear=True):
            self.addCleanup(kinds.forget_tree)
            kinds.learn_from(tree_of(*([12] * 40 + ["District"])))
            self.assertEqual(kinds._container_type("district"), {"value": 12, "string": ""})
            self.assertEqual(kinds.LEARNED["skipped"][0]["name"], "District")
            kinds.learn_from(tree_of(*([12] + ["District"] * 5)))
            self.assertEqual(kinds._container_type("district"), {"value": 0, "string": "District"})

    def test_the_vocabulary_checks_the_number_of_the_type(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"groups": [{"role": "district", "words": ["a1"], "builtin": 12}, {"role": "district", "words": ["a2"], "builtin": True},
                                      {"role": "district", "words": ["a3"], "builtin": 99}, {"role": "district", "words": ["a4"], "builtin": "12"},
                                      {"role": "district", "words": ["a5"]}]}, fh)
            self.assertEqual([g["builtin"] for g in typelearn.load_vocabulary([path])], [12, 0, 0, 0, 0])

    def test_the_vocabulary_agrees_with_the_types_that_the_engine_gives(self):
        """A group that says `builtin` has a word that the engine gives that type of Gramps; a group that does not say it has no word that the engine gives one."""
        with mock.patch.dict(kinds.TREE_TYPES, {"rules": []}):
            for group in self.groups:
                if group["role"] not in ("district", "canton"):
                    continue
                values = {kinds._container_type(w)["value"] for w in group["words"]}
                if group["builtin"]:
                    self.assertIn(group["builtin"], values, group["words"])
                else:
                    self.assertEqual(values, {0}, group["words"])


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.groups = typelearn.load_vocabulary([os.path.join(ROOT, "data", "type-vocabulary.json")])

    def test_one_edit(self):
        edit = typelearn.within_one_edit
        for a, b in (("cemetery", "cemetary"), ("hospital", "hospitl"), ("hospital", "hospitall"), ("school", "scohol"), ("a", "")):
            self.assertTrue(edit(a, b), (a, b))
            self.assertTrue(edit(b, a), (b, a))
        for a, b in (("cemetery", "cemetery"), ("cemetery", "cemetaries"), ("school", "scholar"), ("abcd", "badc"), ("ab", "abcd")):
            self.assertFalse(edit(a, b), (a, b))

    def test_two_types_one_letter_apart_are_told_the_most_used_first(self):
        got = typelearn.learn(tree_of(*(["Cemetery"] * 9 + ["Cemetary"] * 7 + ["Hospital"] * 4 + ["Hospitel"])), self.groups)
        self.assertEqual(got["duplicates"], [{"a": "Cemetary", "a_count": 7, "b": "Cemetery", "b_count": 9}, {"a": "Hospital", "a_count": 4, "b": "Hospitel", "b_count": 1}])

    def test_the_writings_of_one_type_are_not_duplicates_and_nothing_is_joined(self):
        got = typelearn.learn(tree_of(" Cemetery", "Cemetery", "Cemetary"), self.groups)
        self.assertEqual([(d["a"], d["b"]) for d in got["duplicates"]], [("Cemetary", "Cemetery")])
        self.assertEqual(len(got["types"]), 2)                                                # a typo is not joined with its type

    def test_short_words_are_not_compared(self):
        self.assertEqual(typelearn.learn(tree_of("Town", "Tower", "Farm", "Form"), self.groups)["duplicates"], [])

    def test_two_words_that_the_vocabulary_knows_are_not_duplicates(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"groups": [{"role": "settlement", "words": ["alphax"]}, {"role": "settlement", "words": ["alphay"]}]}, fh)
            groups = typelearn.load_vocabulary([path])
        self.assertEqual(typelearn.learn(tree_of("Alphax", "Alphay"), groups)["duplicates"], [])
        self.assertEqual(len(typelearn.learn(tree_of("Alphax", "Alphaz"), groups)["duplicates"]), 1)    # one of the two is not known


try:
    from gramps.gen.db.utils import make_database
    HAVE_GRAMPS = True
except Exception:                                                              # pragma: no cover
    HAVE_GRAMPS = False


@unittest.skipUnless(HAVE_GRAMPS, "the Gramps library is not available")
class GrampsTests(unittest.TestCase):
    """The types that a real Gramps database keeps: read through the file, through the open database, and shown by the command `types`."""
    def setUp(self):
        import shutil
        import tempfile
        from test_writer import IngestWriterTests
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.addCleanup(kinds.forget_tree)
        self.path = os.path.join(self.folder, "db")
        IngestWriterTests().build_from(tree_of(*([" Falu"] * 3 + ["Falu\u200f"] * 2 + ["Falu "] + ["Falu"] + ["Kronland"] + [16, 4] + ["Cemetery"] * 2 + ["Cemetary"] + [12] * 5 + ["District"])), self.path)
        self.sqlite = os.path.join(self.path, "sqlite.db")

    def test_the_same_types_are_read_from_the_file_and_from_the_open_database(self):
        from_file = typelearn.census(Tree.from_sqlite(self.sqlite))
        db = make_database("sqlite")
        db.load(self.path)
        self.addCleanup(db.close)
        self.assertEqual(typelearn.census(Tree.from_db(db)), from_file)
        self.assertEqual(sum(from_file.values()), 12)                                      # the two places with a type of Gramps are not counted

    def test_the_command_types_shows_the_writings_that_were_joined(self):
        import contextlib
        import io
        from placecompleter import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(["types", self.sqlite])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn("Falu", text)
        self.assertIn("settlement", text)
        self.assertIn("(3)", text)                                                           # ' Falu' is written on 3 places
        self.assertEqual(len([ln for ln in text.splitlines() if ln.startswith("Falu ")]), 1)   # one line for the type
        self.assertIn("Kronland", text)
        self.assertIn("no rule for District (1 places): the type of Gramps (District) is used by 5", text)
        self.assertIn("possible duplicates", text)
        self.assertIn("Cemetery (2)  /  Cemetary (1)", text.replace("Cemetary (1)  /  Cemetery (2)", "Cemetery (2)  /  Cemetary (1)"))

    def test_the_command_types_marks_what_the_file_of_the_user_says(self):
        import contextlib
        import io
        from placecompleter import cli
        mine = dict(copy.deepcopy(EMPTY), settlements=[" falu"], district=["district"], province="KRONLAND", rules=[{"words": ["canton"], "value": 0, "string": "Kanton"}])
        with mock.patch.dict(kinds.FILE_TYPES, mine, clear=True):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                cli.main(["types", self.sqlite])
            self.assertEqual([cli.file_role(n) for n in ("Kanton", " kronland ", "Falu", "District", "Cemetery", "")], ["rule", "province", "settlement", "district", "", ""])
        lines = {ln.split()[0]: ln for ln in out.getvalue().splitlines() if ln[:1].isalpha() and ln.split()[0] in ("Falu", "District", "Kronland", "Cemetery")}
        self.assertIn("settlement*", lines["Falu"])                          # the writing of the file differs from the tree's by a space and a capital: one type
        self.assertIn("district*", lines["District"])
        self.assertIn("province*", lines["Kronland"])
        self.assertNotIn("*", lines["Cemetery"])
        self.assertIn("* what your file type-conventions.json says", out.getvalue())

    def test_the_commands_of_the_tree_learn_its_types(self):
        from placecompleter import cli
        cli.open_tree(self.sqlite)
        self.assertIn("Falu", kinds.TREE_TYPES["settlements"])
        self.assertEqual(kinds.TREE_TYPES["province"], kinds.FILE_TYPES["province"] or "Kronland")


if __name__ == "__main__":
    unittest.main()
