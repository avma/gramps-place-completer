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
"""PlaceCompleter engine: pure-Python place hierarchy analysis for Gramps trees.

The engine has no GTK and no Gramps import. It works on the JSON form Gramps
stores in its SQLite database, and reproduces Gramps' own place display rules.
"""

HOMEPAGE = "https://github.com/avma/gramps-place-completer"      # where it lives (the User-Agent that Wikimedia asks for says it)
__version__ = "0.1.1"                       # the registration file (PlaceCompleter.gpr.py) says the same: a test sees to it
