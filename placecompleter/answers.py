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
"""Saved answers: the text, and next to it who answered (engine, model, form, time)."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import glob
import json
import os
import re


def safe_name(place, date):
    return "".join(ch if ch.isalnum() else "_" for ch in "%s_%s" % (place, date))


def save_answer(folder, place, date, text, meta=None):
    """Write the answer as text (and its provenance as .meta.json beside it); return the path of the text."""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, safe_name(place, date) + ".txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if meta:
        with open(path[:-4] + ".meta.json", "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
    return path


def same_answer_elsewhere(folder, place, date, text):
    """Dates of saved answers for the same place whose text is identical to this one."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in place)
    same = []
    for path in sorted(glob.glob(os.path.join(folder, safe + "_*.txt"))):
        other = re.sub(r".*_(\w+)\.txt$", r"\1", os.path.basename(path))
        if other != str(date).replace("-", "_"):
            with open(path, encoding="utf-8") as fh:
                if " ".join(fh.read().split()) == " ".join(text.split()):
                    same.append(other)
    return same
