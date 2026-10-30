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
"""Place Completer in the right-click menu of the Places view: Quick View > Place Completer.

A quick view is how an addon gets into the context menu without touching Gramps: choosing it runs `run`, which opens the Place Completer
window with the place's name and writes a few lines about the place into the small Quick View window that Gramps always shows.
"""

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

# -------------------------------------------------------------------------
#
# Gramps modules
#
# -------------------------------------------------------------------------
from gramps.gen.simple import SimpleDoc

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from placecompleter import i18n                                             # first: the engine's texts are made when it is imported
_ = i18n.install_from_gramps(__file__)

from placecompleter import grampslink                                       # noqa: E402
from placecompleter_open import open_window                                 # noqa: E402


def run(database, document, place):
    summary = grampslink.place_summary(database, place)
    opened = open_window(document.dbstate, document.uistate, summary["place_name"], "", summary.get("top_name", ""))
    sdoc = SimpleDoc(document)
    sdoc.title("%s [%s]" % (summary["place_name"] or _("(no name)"), summary["gramps_id"]))
    sdoc.paragraph(_("Gramps currently displays: %s") % summary["shown"])
    sdoc.paragraph(_("Missing data: %s") % ", ".join(summary["missing"]) if summary["missing"] else _("Analyze the response, then choose which changes to apply."))
    sdoc.paragraph(_("Place Completer opened for this place: specify a date and click Ask.") if opened
                   else _("Place Completer window is already open."))
