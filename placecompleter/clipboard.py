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
"""Read the system clipboard through whichever tool the desktop has (xclip, xsel, wl-paste)."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import shutil
import subprocess

TOOLS = (["xclip", "-selection", "clipboard", "-o"], ["xsel", "-ob"], ["wl-paste", "--no-newline"])


def read_clipboard():
    """The clipboard text, or None when no tool is installed or the clipboard is empty."""
    for cmd in TOOLS:
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
    return None


WRITE_TOOLS = (["xclip", "-selection", "clipboard"], ["xsel", "-ib"], ["wl-copy"])


def write_clipboard(text):
    """Put text on the clipboard through whichever tool the desktop has; False when there is none."""
    for cmd in WRITE_TOOLS:
        if shutil.which(cmd[0]):
            res = subprocess.run(cmd, input=text, text=True, capture_output=True)
            if res.returncode == 0:
                return True
    return False
