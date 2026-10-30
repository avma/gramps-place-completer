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
"""What the steps of the analysis share: what it was asked, and what the steps found and made so far."""


class Analysis:
    """The state of one analysis. ingest() makes it from what it was asked (the tree, the answer, the date ...); each step reads what it needs and keeps
    what it made for the steps that follow (the place of the tree, the levels, the proposals ...)."""

    def __init__(self, **given):
        self.__dict__.update(given)

    def get(self, name, default=None):
        """A value that an earlier step may not have made (it is made only when a condition held)."""
        return self.__dict__.get(name, default)

    def keep(self, local_names, *names):
        """Keep the values of a step for the steps that follow: only the names that the step did assign (a name may be made only in a branch)."""
        for name in names:
            if name in local_names:
                setattr(self, name, local_names[name])
