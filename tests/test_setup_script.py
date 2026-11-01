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
"""The setup of the Gramps versions: the check that names a missing Python package, and the words of the routine.

A fake Gramps (empty modules, or one that imports a package that does not exist) stands for the real one, so these tests need no Gramps and no network."""
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import tests                                                                                  # noqa: E402,F401

TOOL = os.path.join(ROOT, "tools", "check_gramps_import.py")
SCRIPT = os.path.join(ROOT, "tools", "setup_gramps_versions.sh")
MODULES = ("gramps/__init__.py", "gramps/gen/__init__.py", "gramps/gen/lib/__init__.py", "gramps/gen/db/__init__.py", "gramps/gen/db/utils.py",
           "gramps/gen/display/__init__.py", "gramps/gen/display/place.py")


def fake_gramps(folder, db_utils_text=""):
    """An importable `gramps` with the modules that the check imports; db_utils_text is the text of gramps.gen.db.utils."""
    for rel in MODULES:
        path = os.path.join(folder, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(db_utils_text if rel.endswith("db/utils.py") else "")


def run_check(directory):
    done = subprocess.run([sys.executable, TOOL, directory], capture_output=True, text=True, timeout=120)
    return done.returncode, done.stdout


class ImportCheckTests(unittest.TestCase):
    def test_versions_that_import_are_ok(self):
        with tempfile.TemporaryDirectory() as d:
            for v in ("site608", "site61b2", "sitemaster"):
                fake_gramps(os.path.join(d, v))
            code, out = run_check(d)
        self.assertEqual(code, 0, out)
        for v in ("site608", "site61b2", "sitemaster"):
            self.assertIn("%s: ok" % v, out)

    def test_a_missing_package_is_named_with_the_command_that_installs_it(self):
        with tempfile.TemporaryDirectory() as d:
            fake_gramps(os.path.join(d, "site608"))
            fake_gramps(os.path.join(d, "site61b2"), "import pc_no_such_package_xyz\n")
            fake_gramps(os.path.join(d, "sitemaster"))
            code, out = run_check(d)
        self.assertEqual(code, 1, out)
        self.assertIn("site608: ok", out)
        self.assertIn("site61b2: missing Python package 'pc_no_such_package_xyz'", out)
        self.assertIn("pip install --break-system-packages pc_no_such_package_xyz", out)
        self.assertIn("sitemaster: ok", out)

    def test_another_error_is_told_as_it_is(self):
        with tempfile.TemporaryDirectory() as d:
            for v in ("site608", "site61b2"):
                fake_gramps(os.path.join(d, v))
            fake_gramps(os.path.join(d, "sitemaster"), "raise RuntimeError('broken on purpose')\n")
            code, out = run_check(d)
        self.assertEqual(code, 1, out)
        self.assertIn("sitemaster: FAILED RuntimeError: broken on purpose", out)

    def test_a_missing_folder_is_told_and_fails(self):
        with tempfile.TemporaryDirectory() as d:
            fake_gramps(os.path.join(d, "site608"))
            code, out = run_check(d)
        self.assertEqual(code, 1, out)
        self.assertIn("site61b2: the folder is missing", out)

    def test_the_check_does_not_use_the_home_folder_of_the_user(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as fake_home:
            for v in ("site608", "site61b2", "sitemaster"):
                fake_gramps(os.path.join(d, v), "import os\nopen(os.path.join(os.environ['GRAMPSHOME'], 'seen.txt'), 'w').close()\n")
            env = dict(os.environ, GRAMPSHOME=fake_home)
            done = subprocess.run([sys.executable, TOOL, d], capture_output=True, text=True, timeout=120, env=env)
            self.assertEqual(done.returncode, 0, done.stdout)
            self.assertEqual(os.listdir(fake_home), [], "the check wrote into the GRAMPSHOME of the caller")


class RoutineTests(unittest.TestCase):
    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
            return fh.read()

    def test_the_script_installs_orjson_and_ends_with_the_check(self):
        text = self.read("tools", "setup_gramps_versions.sh")
        self.assertIn("pip install --break-system-packages orjson", text)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        self.assertIn("check_gramps_import.py", lines[-2], "the check comes just before the final line")
        self.assertTrue(lines[-1].startswith('echo "Ready'), "Ready is said only when the check passed (set -e)")
        self.assertIn("set -e", text)

    def test_the_script_is_valid_shell(self):
        done = subprocess.run(["sh", "-n", SCRIPT], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_routine_names_gettext_and_orjson(self):
        text = self.read("MAINTENANCE.md")
        self.assertIn("gettext", text)
        self.assertIn("orjson", text)


if __name__ == "__main__":
    unittest.main()
