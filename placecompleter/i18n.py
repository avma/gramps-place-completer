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
"""The translation hook of the engine: its modules call _() on what the user reads; the window installs the translator of Gramps
(the addon's own locale folder). Without one, _() gives the text as it is, which is English: the tests and the command line need nothing."""
_translator = []


def set_translator(function):
    """function: gettext-like, text -> text. Pass None to go back to the plain text."""
    _translator[:] = [function] if function else []


def _(text):
    return _translator[0](text) if _translator else text


def install_from_gramps(filename):
    """The gettext of the addon in the language of Gramps (the file locale/<language>/LC_MESSAGES/addon.mo next to `filename`, made by
    deploy_addon.py from po/<language>-local.po), with the texts of Gramps itself first; installed for the whole engine. Returns it."""
    from gramps.gen.const import GRAMPS_LOCALE as glocale
    try:
        function = glocale.get_addon_translator(filename).gettext
    except Exception:                                               # no translation of the addon: the language of Gramps alone
        function = glocale.translation.gettext
    set_translator(function)
    return function
