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
"""deploy_addon.py: copies what Gramps needs, repeats safely, keeps what it replaces."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import deploy_addon                                                                             # noqa: E402


class DeployTests(unittest.TestCase):
    def target(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return os.path.join(tmp.name, "PlaceCompleter")

    def test_what_is_copied_is_what_gramps_needs_and_not_the_tests(self):
        files = deploy_addon.runtime_files()
        self.assertIn("PlaceCompleter.gpr.py", files)
        self.assertIn("placecompleter_tool.py", files)
        self.assertIn("placecompleter_gramplet.py", files)
        self.assertIn("placecompleter/grampslink.py", files)
        self.assertIn("placecompleter/session.py", files)
        self.assertIn("placecompleter/engines.py", files)
        self.assertIn("packs/hu-habsburg.json", files)
        self.assertIn("data/type-conventions.json", files)                                       # what depends on the language of a tree
        self.assertIn("data/no-answer-phrases.json", files)
        self.assertFalse([f for f in files if f.startswith(("tests", "agent"))])

    def test_the_first_run_writes_everything_and_the_second_changes_nothing(self):
        target = self.target()
        first = deploy_addon.deploy(target)
        self.assertEqual(first["same"], [])
        self.assertEqual(sorted(first["written"]), sorted(deploy_addon.runtime_files()))              # no translation: the interface is English
        self.assertFalse(os.path.exists(os.path.join(target, "locale")))
        for rel in first["written"]:
            self.assertTrue(os.path.exists(os.path.join(target, rel)), rel)
        second = deploy_addon.deploy(target)
        self.assertEqual((second["written"], second["backed_up"]), ([], []))
        self.assertEqual(len(second["same"]), len(first["written"]))

    def test_the_translation_is_shipped_only_when_asked_for(self):
        target = self.target()
        report = deploy_addon.deploy(target, translations=True)
        translation = os.path.join("locale", "he", "LC_MESSAGES", "addon.mo")                          # made from po/he-local.po
        self.assertEqual(sorted(report["written"]), sorted(deploy_addon.runtime_files() + [translation]))
        self.assertTrue(os.path.exists(os.path.join(target, translation)))

    def test_a_translation_left_by_an_earlier_deployment_is_parked_so_that_gramps_does_not_load_it(self):
        target = self.target()
        deploy_addon.deploy(target, translations=True)
        mo = os.path.join(target, "locale", "he", "LC_MESSAGES", "addon.mo")
        self.assertTrue(os.path.exists(mo))
        report = deploy_addon.deploy(target)                                                           # the default: English
        self.assertEqual(report["parked"], ["locale -> locale.off"])
        self.assertFalse(os.path.exists(os.path.join(target, "locale")))                               # Gramps looks for this folder
        self.assertTrue(os.path.exists(os.path.join(target, "locale.off", "he", "LC_MESSAGES", "addon.mo")))     # nothing is deleted
        self.assertEqual(deploy_addon.deploy(target)["parked"], [])                                    # and the next run has nothing to park

    def test_the_translation_comes_back_with_the_option(self):
        target = self.target()
        deploy_addon.deploy(target, translations=True)
        deploy_addon.deploy(target)
        report = deploy_addon.deploy(target, translations=True)
        self.assertTrue(os.path.exists(os.path.join(target, "locale", "he", "LC_MESSAGES", "addon.mo")))
        self.assertEqual(report["parked"], [])

    def test_a_dry_run_parks_nothing_but_says_it_would(self):
        target = self.target()
        deploy_addon.deploy(target, translations=True)
        report = deploy_addon.deploy(target, dry_run=True)
        self.assertEqual(report["parked"], ["locale -> locale.off"])
        self.assertTrue(os.path.isdir(os.path.join(target, "locale")))

    def test_a_changed_file_is_replaced_after_its_old_version_is_kept_once(self):
        target = self.target()
        deploy_addon.deploy(target)
        path = os.path.join(target, "placecompleter", "engines.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# an old version\n")
        report = deploy_addon.deploy(target)
        self.assertEqual(report["written"], ["placecompleter/engines.py"])
        self.assertEqual(report["backed_up"], ["placecompleter/engines.py"])
        with open(path + ".bak", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# an old version\n")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("# an even older one\n")
        deploy_addon.deploy(target)
        with open(path + ".bak", encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# an old version\n")          # the first backup is not overwritten

    def test_a_dry_run_writes_nothing(self):
        target = self.target()
        report = deploy_addon.deploy(target, dry_run=True)
        self.assertTrue(report["written"])
        self.assertFalse(os.path.exists(target))

    def test_nothing_else_in_the_folder_is_touched(self):
        target = self.target()
        os.makedirs(target)
        mine = os.path.join(target, "my_notes.txt")
        with open(mine, "w") as fh:
            fh.write("keep me")
        deploy_addon.deploy(target)
        with open(mine) as fh:
            self.assertEqual(fh.read(), "keep me")

    def test_the_deployed_copy_works_by_itself(self):
        target = self.target()
        deploy_addon.deploy(target)
        code = ("import sys; sys.path.insert(0, %r); import placecompleter.session, placecompleter.engines, placecompleter.ingest; "
                "from placecompleter import prompts; print(prompts.build_prompt('X', '1900').splitlines()[0])" % target)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=tempfile.gettempdir())
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Place: X. Date: 1900.", out.stdout)

    def test_the_command_line_with_a_folder(self):
        target = self.target()
        out = subprocess.run([sys.executable, os.path.join(ROOT, "deploy_addon.py"), "--dir", target], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("DONE:", out.stdout)
        self.assertIn("Restart Gramps", out.stdout)



class VersionFolderTests(unittest.TestCase):
    """Each Gramps version reads its own plugins folder (gramps60/plugins, gramps61/plugins): a copy made by the python of Gramps 6.0 is invisible to
    Gramps 6.1. The command can deploy for a chosen version, or for every tested version that was started on the computer."""
    def root(self, *started):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for name in started:
            os.makedirs(os.path.join(tmp.name, name))
        return tmp.name

    def run_main(self, *argv):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = deploy_addon.main(list(argv))
        return code, buf.getvalue()

    def test_the_folder_of_a_version_is_named_by_major_and_minor(self):
        self.assertEqual(deploy_addon.version_name("6.1"), "gramps61")
        self.assertEqual(deploy_addon.version_name("6.0.8"), "gramps60")
        self.assertEqual(deploy_addon.version_folder("6.1", "/x/gramps"), "/x/gramps/gramps61/plugins/PlaceCompleter")

    def test_a_chosen_version_gets_the_copy_in_its_own_folder_and_no_other_does(self):
        root = self.root("gramps60", "gramps61")
        code, out = self.run_main("--gramps-version", "6.1", "--data-root", root)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(root, "gramps61", "plugins", "PlaceCompleter", "PlaceCompleter.gpr.py")))
        self.assertFalse(os.path.exists(os.path.join(root, "gramps60", "plugins")))
        self.assertIn("(Gramps 6.1)", out)

    def test_a_version_that_was_never_started_still_gets_its_folder_when_asked_for(self):
        root = self.root()
        self.run_main("--gramps-version", "6.1", "--data-root", root)
        self.assertTrue(os.path.exists(os.path.join(root, "gramps61", "plugins", "PlaceCompleter", "placecompleter_tool.py")))

    def test_all_deploys_to_every_tested_version_that_was_started(self):
        root = self.root("gramps60", "gramps61", "gramps52")
        code, out = self.run_main("--all", "--data-root", root)
        for name in ("gramps60", "gramps61"):
            self.assertTrue(os.path.exists(os.path.join(root, name, "plugins", "PlaceCompleter", "PlaceCompleter.gpr.py")), name)
        self.assertFalse(os.path.exists(os.path.join(root, "gramps52", "plugins")))                  # not a tested version
        self.assertIn("(Gramps 6.0)", out)
        self.assertIn("(Gramps 6.1)", out)

    def test_all_says_so_when_no_tested_version_was_started(self):
        root = self.root("gramps52")
        with self.assertRaises(SystemExit) as ctx:
            self.run_main("--all", "--data-root", root)
        self.assertIn("No tested Gramps version", str(ctx.exception))

    def test_a_dry_run_for_a_version_writes_nothing(self):
        root = self.root("gramps61")
        code, out = self.run_main("--gramps-version", "6.1", "--data-root", root, "--dry-run")
        self.assertFalse(os.path.exists(os.path.join(root, "gramps61", "plugins")))
        self.assertIn("DRY RUN (Gramps 6.1)", out)

    def test_a_gramps_that_runs_with_its_own_grampshome_gets_the_copy_there(self):
        """A Gramps 6.1 started with its own GRAMPSHOME: its plugins are in <GRAMPSHOME>/gramps/gramps61/plugins."""
        home = self.root()
        code, out = self.run_main("--gramps-version", "6.1", "--grampshome", home)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(os.path.join(home, "gramps", "gramps61", "plugins", "PlaceCompleter", "PlaceCompleter.gpr.py")))
        self.assertIn(os.path.join(home, "gramps", "gramps61", "plugins", "PlaceCompleter"), out)

    def test_all_follows_the_grampshome_too(self):
        home = self.root()
        os.makedirs(os.path.join(home, "gramps", "gramps61"))
        self.run_main("--all", "--grampshome", home)
        self.assertTrue(os.path.exists(os.path.join(home, "gramps", "gramps61", "plugins", "PlaceCompleter", "placecompleter_tool.py")))
        self.assertFalse(os.path.exists(os.path.join(home, "gramps", "gramps60")))

    def test_the_started_versions_are_found_in_order(self):
        self.assertEqual(deploy_addon.started_versions(self.root("gramps61", "gramps60", "gramps52")), ["6.0", "6.1"])


class GrampsFindsItTests(unittest.TestCase):
    """The real plugin manager of the Gramps that runs the tests (6.0 or 6.1) reads the deployed copy and registers all of it: the tool, the two
    gramplets and the right-click entry. (A copy in the folder of another version is not seen at all: that is the folder test above.)"""
    SCRIPT = """
import os, sys, tempfile
sys.path.insert(0, sys.argv[1])
import deploy_addon
from gramps.gen.plug import BasePluginManager, PluginRegister
from gramps.gen.plug._pluginreg import TOOL, GRAMPLET, QUICKREPORT
root = tempfile.mkdtemp()
deploy_addon.deploy(os.path.join(root, "plugins", "PlaceCompleter"))
BasePluginManager.get_instance().reg_plugins(os.path.join(root, "plugins"), None, None, load_on_reg=False)
reg = PluginRegister.get_instance()
found = lambda kind: sorted(p.id for p in reg.type_plugins(kind) if p.id.startswith("placecompleter"))
print("FOUND", found(TOOL), found(GRAMPLET), found(QUICKREPORT))
"""

    def test_the_tool_the_gramplets_and_the_quickview_are_registered(self):
        try:
            import gramps.version                                                           # noqa: F401
        except ImportError:
            self.skipTest("Gramps cannot be imported here")
        done = subprocess.run([sys.executable, "-c", self.SCRIPT, ROOT], capture_output=True, text=True, env=dict(os.environ))
        self.assertIn("FOUND ['placecompleter'] ['placecompleter-gramplet', 'placecompleter-place-gramplet'] ['placecompleter-quickview']",
                      done.stdout, done.stderr[-600:])


class SlimScrollbarsTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.dir, ignore_errors=True))
        self.css = os.path.join(self.dir, "gtk-3.0", "gtk.css")

    def read(self):
        return open(self.css, encoding="utf-8").read()

    def test_the_block_is_added_to_a_file_that_does_not_exist_yet(self):
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css), "added")
        text = self.read()
        self.assertTrue(text.startswith(deploy_addon.SLIM_BEGIN))
        self.assertIn("scrollbar button { min-width: 0;", text)
        self.assertTrue(text.rstrip().endswith(deploy_addon.SLIM_END))

    def test_it_is_added_after_what_the_user_has_and_what_they_have_is_kept(self):
        os.makedirs(os.path.dirname(self.css))
        open(self.css, "w", encoding="utf-8").write("@define-color my_blue #00f;\n\nbutton { color: red; }\n")
        deploy_addon.set_slim_scrollbars(self.css)
        text = self.read()
        self.assertTrue(text.startswith("@define-color my_blue #00f;"))
        self.assertIn("button { color: red; }", text)
        self.assertEqual(open(self.css + ".bak", encoding="utf-8").read(), "@define-color my_blue #00f;\n\nbutton { color: red; }\n")

    def test_it_is_safe_to_repeat(self):
        deploy_addon.set_slim_scrollbars(self.css)
        first = self.read()
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css), "same")
        self.assertEqual(self.read(), first)
        self.assertEqual(first.count(deploy_addon.SLIM_BEGIN), 1)

    def test_taking_it_out_leaves_the_rest_exactly(self):
        os.makedirs(os.path.dirname(self.css))
        original = "@define-color my_blue #00f;\n\nbutton { color: red; }\n"
        open(self.css, "w", encoding="utf-8").write(original)
        deploy_addon.set_slim_scrollbars(self.css)
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css, on=False), "removed")
        self.assertEqual(self.read().strip(), original.strip())
        self.assertNotIn("PlaceCompleter", self.read())

    def test_taking_it_out_when_it_is_not_there_changes_nothing(self):
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css, on=False), "absent")
        self.assertFalse(os.path.exists(self.css))

    def test_a_block_of_an_older_version_is_updated_in_place(self):
        deploy_addon.set_slim_scrollbars(self.css)
        old = self.read().replace("min-width: 8px", "min-width: 99px")
        open(self.css, "w", encoding="utf-8").write("a { b: c; }\n" + old + "d { e: f; }\n")
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css), "updated")
        text = self.read()
        self.assertNotIn("99px", text)
        self.assertTrue(text.startswith("a { b: c; }") and text.rstrip().endswith("d { e: f; }"))

    def test_a_dry_run_writes_nothing(self):
        self.assertEqual(deploy_addon.set_slim_scrollbars(self.css, dry_run=True), "added")
        self.assertFalse(os.path.exists(self.css))

    def test_the_command_line_does_it_and_does_not_deploy_the_plugin_then(self):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = deploy_addon.main(["--slim-scrollbars", "--gtk-css", self.css])
        self.assertEqual(code, 0)
        self.assertIn("slim scrollbars added", out.getvalue())
        self.assertIn(deploy_addon.SLIM_BEGIN, self.read())

if __name__ == "__main__":
    unittest.main(verbosity=2)


class CleanTests(unittest.TestCase):
    """--clean: the old folder of the addon is moved out of the plugins folder (never deleted, never left inside it), then the addon is deployed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = tmp.name
        self.target = os.path.join(self.root, "plugins", "PlaceCompleter")
        self.backups = os.path.join(self.root, "backups")
        os.makedirs(os.path.join(self.target, "placecompleter"))
        for name, text in (("PlaceCompleter.gpr.py", "old"), ("stale.py", "x"), ("placecompleter/old.bak", "y")):
            with open(os.path.join(self.target, name), "w", encoding="utf-8") as fh:
                fh.write(text)

    def run_main(self, *extra):
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()) as out:
            deploy_addon.main(["--dir", self.target, "--backup-dir", self.backups] + list(extra))
        return out.getvalue()

    def test_the_old_folder_is_moved_aside_and_the_new_one_has_only_what_gramps_needs(self):
        out = self.run_main("--clean")
        self.assertFalse(os.path.exists(os.path.join(self.target, "stale.py")))
        self.assertFalse(os.path.exists(os.path.join(self.target, "placecompleter", "old.bak")))
        moved = os.listdir(self.backups)
        self.assertEqual(len(moved), 1)
        self.assertTrue(moved[0].startswith("PlaceCompleter-plugins-"))
        self.assertTrue(os.path.exists(os.path.join(self.backups, moved[0], "stale.py")))             # nothing was lost
        found = sorted(os.path.relpath(os.path.join(r, f), self.target) for r, _d, fs in os.walk(self.target) for f in fs)
        self.assertEqual(found, sorted(deploy_addon.runtime_files()))
        self.assertIn("moved", out)

    def test_the_old_folder_is_never_left_under_the_plugins_folder(self):
        """Gramps reads every folder under plugins: a copy there would register the addon twice."""
        self.run_main("--clean")
        plugins = os.path.join(self.root, "plugins")
        self.assertEqual(os.listdir(plugins), ["PlaceCompleter"])

    def test_a_dry_run_moves_nothing(self):
        out = self.run_main("--clean", "--dry-run")
        self.assertTrue(os.path.exists(os.path.join(self.target, "stale.py")))
        self.assertFalse(os.path.exists(self.backups))
        self.assertIn("would move", out)

    def test_a_folder_that_is_not_the_addon_is_not_moved(self):
        os.remove(os.path.join(self.target, "PlaceCompleter.gpr.py"))
        with self.assertRaises(SystemExit):
            self.run_main("--clean")
        self.assertTrue(os.path.exists(os.path.join(self.target, "stale.py")))
        self.assertFalse(os.path.exists(self.backups))

    def test_a_place_for_the_old_folder_inside_the_folder_is_refused(self):
        with self.assertRaises(SystemExit):
            deploy_addon.main(["--dir", self.target, "--clean", "--backup-dir", os.path.join(self.target, "backups")])
        self.assertTrue(os.path.exists(os.path.join(self.target, "stale.py")))

    def test_without_an_old_folder_it_just_installs(self):
        shutil.rmtree(self.target)
        self.run_main("--clean")
        self.assertTrue(os.path.exists(os.path.join(self.target, "PlaceCompleter.gpr.py")))
        self.assertFalse(os.path.exists(self.backups))

    def test_two_cleans_in_the_same_second_do_not_meet(self):
        import datetime
        now = datetime.datetime(2026, 10, 29, 12, 0, 0)
        first = deploy_addon.clean_target(self.target, self.backups, "gramps60", now=now)
        os.makedirs(self.target)
        with open(os.path.join(self.target, "PlaceCompleter.gpr.py"), "w", encoding="utf-8") as fh:
            fh.write("again")
        second = deploy_addon.clean_target(self.target, self.backups, "gramps60", now=now)
        self.assertNotEqual(first, second)
        self.assertTrue(os.path.isdir(first) and os.path.isdir(second))
