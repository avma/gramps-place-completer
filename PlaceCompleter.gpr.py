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
# Registration of Place Completer in Gramps: a tool (Tools > Family Tree Processing), a gramplet of the Events view, a gramplet of the Places
# view, and an entry in the right-click menu of the Places view (Quick View > Place Completer).
# The names register, TOOL, GRAMPLET, QUICKREPORT, CATEGORY_QR_PLACE, TOOL_DBPROC, TOOL_MODE_GUI, EXPERIMENTAL are provided by Gramps when it reads this file.
from gramps.version import major_version

# Gramps runs this file with its own _ : the texts of Gramps first, then the translation of the addon (locale/<language>/LC_MESSAGES/addon.mo next to this
# file, made by deploy_addon.py --translations). Only when the file is run by hand or by the tests (no _ given) the gettext of Gramps alone is used.
if "_" not in globals():
    from gramps.gen.const import GRAMPS_LOCALE as glocale
    _ = glocale.translation.gettext

# Gramps loads a plugin only if the version it names is the running major.minor (6.0 does not load in 6.1).
# This tool was tested with Gramps 6.0 (6.0.8) and 6.1 (the master branch, 6.1.0): it names the running version when that is one of
# these, and names 6.0 otherwise, so that any other Gramps declines it on purpose instead of running it untested.
TESTED_WITH = ("6.0", "6.1")

HELP_URL = "https://github.com/avma/gramps-place-completer"          # the Help button of the addon manager opens it (the same as placecompleter.HOMEPAGE)

register(
    TOOL,
    id="placecompleter",
    name=_("Place Completer"),
    description=_(
        "Completes the historical hierarchy of a place on a date: an AI answers, the program matches it to your "
        "places, shows what Gramps would display, and writes only what you check (one Undo)."
    ),
    version="0.1.1",
    gramps_target_version=major_version if major_version in TESTED_WITH else "6.0",
    status=EXPERIMENTAL,
    help_url=HELP_URL,
    fname="placecompleter_tool.py",
    authors=["Avi Markovitz"],
    authors_email=[""],
    category=TOOL_DBPROC,
    toolclass="PlaceCompleterTool",
    optionclass="PlaceCompleterOptions",
    tool_modes=[TOOL_MODE_GUI],
)

register(
    GRAMPLET,
    id="placecompleter-gramplet",
    name=_("Place Completer"),
    description=_("Shows the active event's place and date and opens the Place Completer window with them filled in."),
    version="0.1.1",
    gramps_target_version=major_version if major_version in TESTED_WITH else "6.0",
    status=EXPERIMENTAL,
    help_url=HELP_URL,
    fname="placecompleter_gramplet.py",
    height=150,
    expand=False,
    gramplet="PlaceCompleterGramplet",
    gramplet_title=_("Place Completer"),
    navtypes=["Event"],
)

register(
    GRAMPLET,
    id="placecompleter-place-gramplet",
    name=_("Place Completer (places)"),
    description=_("Shows the active place and what it lacks, and opens the Place Completer window with its name."),
    version="0.1.1",
    gramps_target_version=major_version if major_version in TESTED_WITH else "6.0",
    status=EXPERIMENTAL,
    help_url=HELP_URL,
    fname="placecompleter_gramplet.py",
    height=150,
    expand=False,
    gramplet="PlaceCompleterPlaceGramplet",
    gramplet_title=_("Place Completer"),
    navtypes=["Place"],
)

register(
    QUICKREPORT,
    id="placecompleter-quickview",
    name=_("Place Completer"),
    description=_("Open the Place Completer window for this place."),
    version="0.1.1",
    gramps_target_version=major_version if major_version in TESTED_WITH else "6.0",
    status=EXPERIMENTAL,
    help_url=HELP_URL,
    fname="placecompleter_quickview.py",
    authors=["Avi Markovitz"],
    authors_email=[""],
    category=CATEGORY_QR_PLACE,
    runfunc="run",
)
