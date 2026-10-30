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
"""Open the Place Completer window with a place (and a date) already filled in. Used by the gramplets and by the entry in the right-click menu."""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


def open_window(dbstate, uistate, place="", date="", hint=""):
    """True when the window was opened, False when it is already open (use that one)."""
    from gramps.gen.errors import WindowActiveError
    from gramps.gui.user import User
    # Gramps puts the folder of a plugin on sys.path only while it imports the plugin and takes it off right after (import_plugin in
    # gramps/gen/plug/_manager.py), so by the time of a click the folder is no longer there: put it back for this import only.
    added = HERE not in sys.path
    if added:
        sys.path.insert(0, HERE)
    try:
        from placecompleter_tool import PlaceCompleterOptions, PlaceCompleterTool              # the module the Tools menu uses
    finally:
        if added and HERE in sys.path:
            sys.path.remove(HERE)
    try:
        PlaceCompleterTool(dbstate, User(uistate=uistate, dbstate=dbstate), PlaceCompleterOptions, "placecompleter",
                           prefill={"place": place, "date": date, "hint": hint})
    except WindowActiveError:
        return False
    return True
