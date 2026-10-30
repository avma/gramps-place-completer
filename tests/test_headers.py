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
"""The license header and the banners above the imports (tools/add_headers.py): every file has them, and the tool changes nothing the second time."""
import ast
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

spec = importlib.util.spec_from_file_location("add_headers", os.path.join(ROOT, "tools", "add_headers.py"))
add_headers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(add_headers)

HOLDER = "Avi Markovitz <avi.markovitz@gmail.com>"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


class FilesTests(unittest.TestCase):
    def test_every_python_file_has_the_header_and_the_banners_that_it_needs(self):
        lacking = [(os.path.relpath(p, ROOT), m) for p in add_headers.python_files() for m in [add_headers.process(p, "x", "2026")[1]] if m]
        self.assertEqual(lacking, [])

    def test_the_copyright_line_names_the_holder_in_every_file(self):
        for path in add_headers.python_files():
            head = "\n".join(open(path, encoding="utf-8").read().splitlines()[:12])
            self.assertIn("Copyright (C) 2026       " + HOLDER, head, path)

    def test_the_license_is_the_one_of_gramps(self):
        head = read("placecompleter/session.py")
        for line in ("# This program is free software; you can redistribute it and/or modify",
                     "# the Free Software Foundation; either version 2 of the License, or",
                     "# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA."):
            self.assertIn(line, head)

    def test_the_banners_are_those_of_the_files_of_gramps(self):
        text = read("placecompleter_tool.py")
        for name in ("Standard python modules", "GTK/Gnome modules", "Gramps modules", "Place Completer modules"):
            self.assertIn("# -------------------------------------------------------------------------\n#\n# %s\n#\n# -------------------------------------------------------------------------\n" % name, text)
        self.assertLess(text.index("# Standard python modules"), text.index("# GTK/Gnome modules"))
        self.assertLess(text.index("# GTK/Gnome modules"), text.index("# Gramps modules"))
        self.assertLess(text.index("# Gramps modules"), text.index("# Place Completer modules"))

    def test_the_engine_has_no_gtk_or_gramps_banner_because_it_imports_neither_at_the_top(self):
        text = read("placecompleter/session.py")
        self.assertIn("# Standard python modules", text)
        self.assertIn("# Place Completer modules", text)
        self.assertNotIn("# GTK/Gnome modules", text)
        self.assertNotIn("# Gramps modules", text)

    def test_the_registration_file_has_the_header_and_no_banner(self):
        text = read("PlaceCompleter.gpr.py")
        self.assertIn("# This program is free software", text)
        self.assertNotIn("# Standard python modules", text)


class ToolTests(unittest.TestCase):
    SAMPLE = "import os\nimport sys\nfrom gi.repository import Gtk\nfrom gramps.gen.lib import Place\nfrom . import model\nfrom .dates import describe\nx = 1\n"

    def test_a_banner_is_written_where_the_kind_of_the_imports_changes_and_nothing_is_moved(self):
        out = add_headers.add_banners(self.SAMPLE)
        names = [l[2:] for l in out.splitlines() if l.startswith("# ") and not l.startswith("# -")]
        self.assertEqual(names, ["Standard python modules", "GTK/Gnome modules", "Gramps modules", "Place Completer modules"])
        before = [ast.dump(n) for n in ast.parse(self.SAMPLE).body]
        after = [ast.dump(n) for n in ast.parse(out).body]
        self.assertEqual(before, after)                                                              # the same statements in the same order

    def test_running_it_twice_changes_nothing(self):
        once = add_headers.add_banners(self.SAMPLE)
        self.assertEqual(add_headers.add_banners(once), once)

    def test_the_header_goes_after_a_shebang_and_only_once(self):
        lines = add_headers.add_header(["#!/usr/bin/env python3", '"""doc"""', "x = 1"], HOLDER, "2026")
        self.assertEqual(lines[0], "#!/usr/bin/env python3")
        self.assertEqual(lines[1], "#")
        self.assertEqual(lines[-2:], ['"""doc"""', "x = 1"])
        self.assertTrue(add_headers.has_header("\n".join(lines)))
        self.assertEqual(sum(l.startswith("# Copyright (C)") for l in lines), 1)

    def test_the_words_of_the_license_inside_a_string_are_not_a_header(self):
        self.assertFalse(add_headers.has_header('x = ("# This program is free software; you can redistribute it and/or modify")\n'))
        self.assertTrue(add_headers.has_header("#\n# This program is free software; you can redistribute it and/or modify\n"))

    def test_a_file_that_lacks_the_header_is_reported_by_check(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.py")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('"""doc"""\nimport os\n')
            out, missing = add_headers.process(path, HOLDER, "2026")
            self.assertEqual(missing, ["header"])                                                    # (a file outside the folders of the addon: no banners)
            self.assertIn("Copyright (C) 2026       " + HOLDER, out)


if __name__ == "__main__":
    unittest.main()
