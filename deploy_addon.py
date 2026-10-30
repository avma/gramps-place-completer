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
"""Copy the files Gramps needs to run Place Completer into its user plugins folder.

    python3 deploy_addon.py                      # into the plugins folder of the Gramps this python runs (found through Gramps itself)
    python3 deploy_addon.py --gramps-version 6.1 # into the plugins folder of Gramps 6.1 (each version has its own: gramps60, gramps61)
    python3 deploy_addon.py --all                # into the folder of every tested Gramps version that has been started on this computer
    python3 deploy_addon.py --gramps-version 6.1 --grampshome DIR   # a Gramps that runs with its own GRAMPSHOME
    python3 deploy_addon.py --dir DIR            # into another folder
    python3 deploy_addon.py --dry-run            # only say what would change
    python3 deploy_addon.py --clean              # first move the old folder of the addon out of the plugins folder (nothing is deleted), then deploy
    python3 deploy_addon.py --translations       # also the translation (po/*-local.po): off by default, the interface is English

    python3 deploy_addon.py --slim-scrollbars      # also: slim scrollbars in ALL Gramps windows (a block in ~/.config/gtk-3.0/gtk.css)
    python3 deploy_addon.py --no-slim-scrollbars   # takes that block out again

Safe to repeat: a file that is already the same is left alone; a file that differs is replaced after its old version is
kept once as NAME.bak. Nothing is ever deleted, and nothing outside the target folder is touched (--clean moves the whole old folder, to a place of
your choice outside the plugins folder: Gramps reads every folder under plugins, so a copy left there would register the addon twice).
"""
import argparse
import datetime
import glob
import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNTIME = ["PlaceCompleter.gpr.py", "placecompleter_tool.py", "placecompleter_gramplet.py", "placecompleter_quickview.py", "placecompleter_open.py",
           "placecompleter/*.py", "packs/*.json", "data/*.json"]


def runtime_files():
    out = []
    for pattern in RUNTIME:
        out += sorted(os.path.relpath(p, HERE) for p in glob.glob(os.path.join(HERE, pattern)))
    return out


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


TESTED = ("6.0", "6.1")                    # the Gramps versions this addon was tested with (the same as in PlaceCompleter.gpr.py)


def data_root(arg=""):
    """The folder that holds the user data of every Gramps version (…/gramps), found through Gramps when this python can import it."""
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    try:
        from gramps.gen.const import USER_DATA                  # (it follows GRAMPSHOME when that is set, as Gramps does)
        return USER_DATA
    except ImportError:
        if os.environ.get("GRAMPSHOME"):
            return os.path.join(os.path.expanduser(os.environ["GRAMPSHOME"]), "gramps")
        return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "gramps")


def version_name(version):
    major, minor = (version.strip().split(".") + ["0"])[:2]
    return "gramps%s%s" % (major, minor)


def version_folder(version, root=""):
    """The user plugins folder of Gramps X.Y for this addon: <data root>/gramps<XY>/plugins/PlaceCompleter."""
    return os.path.join(data_root(root), version_name(version), "plugins", "PlaceCompleter")


def started_versions(root=""):
    """The tested versions whose user folder exists, that is, that were started on this computer."""
    return [v for v in TESTED if os.path.isdir(os.path.join(data_root(root), version_name(v)))]


def target_folder(arg):
    if arg:
        return os.path.abspath(os.path.expanduser(arg))
    try:
        from gramps.gen.const import USER_PLUGINS
    except ImportError:
        sys.exit("Gramps cannot be imported by this python: run this with the python that Gramps uses, or give --dir.")
    return os.path.join(USER_PLUGINS, "PlaceCompleter")


def compile_translations(target, report, dry_run=False):
    """po/<language>-local.po -> <target>/locale/<language>/LC_MESSAGES/addon.mo, where Gramps looks for the translation of an addon."""
    sys.path.insert(0, HERE)
    from placecompleter import msgfmt
    for po in sorted(glob.glob(os.path.join(HERE, "po", "*-local.po"))):
        language = os.path.basename(po).split("-")[0]
        rel = os.path.join("locale", language, "LC_MESSAGES", "addon.mo")
        with open(po, encoding="utf-8") as fh:
            data = msgfmt.compile_mo(msgfmt.parse_po(fh.read()))
        dst = os.path.join(target, rel)
        if os.path.exists(dst) and open(dst, "rb").read() == data:
            report["same"].append(rel)
            continue
        if not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(data)
        report["written"].append(rel)


def park_translations(target, report, dry_run=False):
    """The interface is English until the translation is finished: a locale folder that an earlier deployment left in the target would still be
    loaded by Gramps, so it is moved to locale.off (nothing is deleted; --translations brings the translation back, made again from po/)."""
    folder, parked = os.path.join(target, "locale"), os.path.join(target, "locale.off")
    if not os.path.isdir(folder):
        return
    if not dry_run:
        if os.path.exists(parked):
            shutil.rmtree(parked)                          # only what an earlier parking left: the files are made again from po/
        shutil.move(folder, parked)
    report["parked"].append("locale -> locale.off")


def deploy(target, dry_run=False, translations=False):
    """Returns {'written': [...], 'same': [...], 'backed_up': [...], 'parked': [...]} (names relative to the target)."""
    report = {"written": [], "same": [], "backed_up": [], "parked": []}
    for rel in runtime_files():
        src, dst = os.path.join(HERE, rel), os.path.join(target, rel)
        if os.path.exists(dst) and sha(src) == sha(dst):
            report["same"].append(rel)
            continue
        if not dry_run:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if os.path.exists(dst) and not os.path.exists(dst + ".bak"):
                shutil.copy2(dst, dst + ".bak")
                report["backed_up"].append(rel)
            shutil.copy2(src, dst)
        report["written"].append(rel)
    if translations:
        compile_translations(target, report, dry_run)
    else:
        park_translations(target, report, dry_run)
    return report


BACKUP_ROOT = os.path.join(os.path.expanduser(os.environ.get("PLACECOMPLETER_WORK") or "~/gramps-place-work"), "backups")      # (the same as engines.work_dir())


def inside(path, folder):
    """True when `path` is `folder` or lies under it."""
    path, folder = os.path.realpath(path), os.path.realpath(folder)
    return path == folder or path.startswith(folder + os.sep)


def clean_target(target, backup_root, label="", dry_run=False, now=None):
    """Move the old folder of the addon out of the plugins folder (nothing is deleted). Returns the new place of the old folder, or "" when there is no
    old folder. Refuses a folder that is not a folder of Place Completer, and a backup place inside the folder that is moved."""
    if not os.path.isdir(target):
        return ""
    if not os.path.exists(os.path.join(target, "PlaceCompleter.gpr.py")):
        sys.exit("%s is not a folder of Place Completer (no PlaceCompleter.gpr.py in it): nothing was moved." % target)
    if inside(backup_root, target):
        sys.exit("The place for the old folder (%s) is inside the folder that would be moved (%s): choose another with --backup-dir." % (backup_root, target))
    stamp = (now or datetime.datetime.now()).strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(backup_root, "PlaceCompleter-%s-%s" % (label or "plugins", stamp))
    n = 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(backup_root, "PlaceCompleter-%s-%s-%d" % (label or "plugins", stamp, n))
    if not dry_run:
        os.makedirs(backup_root, exist_ok=True)
        shutil.move(target, dest)
    return dest


SLIM_BEGIN = "/* >>> PlaceCompleter slim scrollbars (take out with: deploy_addon.py --no-slim-scrollbars) */"
SLIM_END = "/* <<< PlaceCompleter slim scrollbars */"
SLIM_BLOCK = """scrollbar.vertical { min-width: 8px; }
scrollbar.vertical slider { min-width: 5px; }
scrollbar.horizontal { min-height: 8px; }
scrollbar.horizontal slider { min-height: 5px; }
scrollbar button { min-width: 0; min-height: 0; padding: 0; margin: 0; border: none; background: none; -gtk-icon-source: none; }"""


def gtk_css_path(arg=""):
    return os.path.abspath(os.path.expanduser(arg or "~/.config/gtk-3.0/gtk.css"))


def set_slim_scrollbars(path, on=True, dry_run=False):
    """Put the block of slim scrollbars into the user's GTK style file (it styles every GTK3 program of the user, Gramps included), or take
    it out. Only the block between the two marks is ever touched; the old file is kept once as gtk.css.bak. Returns what was done:
    'added', 'updated', 'same', 'removed' or 'absent'."""
    text = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    start, end = text.find(SLIM_BEGIN), text.find(SLIM_END)
    has = start != -1 and end > start
    block = "%s\n%s\n%s\n" % (SLIM_BEGIN, SLIM_BLOCK, SLIM_END)
    if has:
        stop = end + len(SLIM_END)
        stop += 1 if text[stop:stop + 1] == "\n" else 0
        current = text[start:stop]
        rest_before, rest_after = text[:start], text[stop:]
        if on:
            done, new = ("same", text) if current == block else ("updated", rest_before + block + rest_after)
        else:
            done, new = "removed", (rest_before.rstrip("\n") + ("\n" if rest_before.strip() and rest_after.strip() else "") + rest_after.lstrip("\n")
                                    if (rest_before + rest_after).strip() else "")
    elif on:
        done, new = "added", text + ("\n" if text and not text.endswith("\n\n") else "") + block
    else:
        return "absent"
    if done != "same" and not dry_run:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path) and not os.path.exists(path + ".bak"):
            shutil.copy2(path, path + ".bak")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(new)
    return done


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default="")
    ap.add_argument("--gramps-version", default="", metavar="X.Y", help="deploy for this Gramps version (e.g. 6.1) whatever python runs this")
    ap.add_argument("--all", action="store_true", help="deploy for every tested Gramps version that was started on this computer")
    ap.add_argument("--data-root", default="", help="the folder that holds the user data of the Gramps versions (…/.local/share/gramps)")
    ap.add_argument("--grampshome", default="", metavar="DIR",
                    help="the GRAMPSHOME a Gramps is started with (its user data is DIR/gramps): for an isolated test environment")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--clean", action="store_true", help="first move the old folder of the addon out of the plugins folder (to --backup-dir; nothing is deleted)")
    ap.add_argument("--backup-dir", default=BACKUP_ROOT, metavar="DIR", help="where --clean puts the old folder (default ~/gramps-place-work/backups: outside Dropbox)")
    ap.add_argument("--translations", action="store_true", help="also ship the translation (po/*-local.po); off by default: the interface is English")
    ap.add_argument("--slim-scrollbars", action="store_true", help="put slim scrollbars in ALL Gramps windows (GTK style file of the user)")
    ap.add_argument("--no-slim-scrollbars", action="store_true", help="take that block out again")
    ap.add_argument("--gtk-css", default="", help="another GTK style file than ~/.config/gtk-3.0/gtk.css")
    args = ap.parse_args(argv)
    if args.grampshome and not args.data_root:
        args.data_root = os.path.join(os.path.abspath(os.path.expanduser(args.grampshome)), "gramps")
    if args.slim_scrollbars or args.no_slim_scrollbars:
        path = gtk_css_path(args.gtk_css)
        done = set_slim_scrollbars(path, on=args.slim_scrollbars, dry_run=args.dry_run)
        print("%s%s in %s" % ("DRY RUN: " if args.dry_run else "", {"added": "slim scrollbars added", "updated": "slim scrollbars updated",
              "same": "slim scrollbars already there", "removed": "slim scrollbars taken out", "absent": "no slim scrollbars block there"}[done], path))
        print("Restart Gramps to see it. It styles every GTK3 program of yours; to undo: deploy_addon.py --no-slim-scrollbars.")
        return 0
    if args.dir:
        targets = [("", target_folder(args.dir))]
    elif args.all:
        versions = started_versions(args.data_root)
        if not versions:
            sys.exit("No tested Gramps version (%s) was started on this computer under %s: start it once, or give --gramps-version or --dir."
                     % (", ".join(TESTED), data_root(args.data_root)))
        targets = [(v, version_folder(v, args.data_root)) for v in versions]
    elif args.gramps_version:
        targets = [(args.gramps_version, version_folder(args.gramps_version, args.data_root))]
    else:
        targets = [("", target_folder(""))]
    for version, target in targets:
        if args.clean:
            moved = clean_target(target, os.path.abspath(os.path.expanduser(args.backup_dir)), version_name(version) if version else "", args.dry_run)
            if moved:
                print("%s%s  ->  %s" % ("would move   " if args.dry_run else "moved        ", target, moved))
        report = deploy(target, args.dry_run, args.translations)
        for rel in report["written"]:
            print(("would write  " if args.dry_run else "write        ") + rel)
        for rel in report["parked"]:
            print(("would move   " if args.dry_run else "moved        ") + rel + "   (the interface is English; --translations brings it back)")
        for rel in report["backed_up"]:
            print("backed up    %s.bak" % rel)
        print("%s%s: %d written, %d identical. Folder: %s" % ("DRY RUN" if args.dry_run else "DONE", " (Gramps %s)" % version if version else "",
                                                             len(report["written"]), len(report["same"]), target))
    if not args.dir and not args.all and not args.gramps_version:
        others = [v for v in started_versions(args.data_root) if version_name(v) not in targets[0][1]]
        try:
            from gramps.version import VERSION
            print("This python runs Gramps %s, and the plugins folder is per version (gramps60, gramps61)." % VERSION)
        except ImportError:
            pass
        if others:
            print("Place Completer is NOT in the folder of Gramps %s, which was also started here: run this with --all (or --gramps-version %s)." % (
                ", ".join(others), others[0]))
    if not args.dry_run:
        print("Restart Gramps: Tools > Family Tree Processing > Place Completer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
