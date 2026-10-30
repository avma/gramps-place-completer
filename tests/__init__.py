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
"""Each test is on its own: in English, in an empty home folder, without the keys and the settings of the user, and without the network (this computer excepted).

The tests must give the same answer on every computer. Without this they used what the user has: Gramps in Hebrew translates the words that it knows
(Place, Confidence, _Cancel ...), a model that the program chose for the user is remembered in a file, and a key in the environment is a real key.
This file is read first, before the tests import Gramps."""
import atexit
import os
import shutil
import socket
import tempfile

_HOME = tempfile.mkdtemp(prefix="placecompleter-tests-")
atexit.register(shutil.rmtree, _HOME, True)

os.environ.update({"HOME": _HOME, "XDG_DATA_HOME": os.path.join(_HOME, "data"), "XDG_CONFIG_HOME": os.path.join(_HOME, "config"),
                   "XDG_CACHE_HOME": os.path.join(_HOME, "cache"), "LANGUAGE": "en", "LANG": "C", "LC_ALL": "C",
                   "PLACECOMPLETER_KEYSTORE": "none", "PLACECOMPLETER_MODELS": os.path.join(_HOME, "models.json"),
                   "PLACECOMPLETER_ENGINES": os.path.join(_HOME, "engines.json"),
                   # the rules that are off by default (the periods and the languages of the names of the levels, NP5 and NL, and the period of the name of a place, NP3) are on in the tests, which
                   # show what they do; test_defaults.py shows that they are off when nobody asks for them
                   "PLACECOMPLETER_RULES_ON": "NP3,NP5,NL"})
os.environ["PLACECOMPLETER_CONVENTIONS"] = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "type-conventions.example-he.json")
if "GRAMPS_RESOURCES" not in os.environ:                                  # where this computer keeps Gramps (nothing is assumed about it)
    import importlib.util
    _spec = importlib.util.find_spec("gramps")
    if _spec and _spec.origin:
        os.environ["GRAMPS_RESOURCES"] = os.path.dirname(os.path.dirname(_spec.origin))
os.environ.pop("GRAMPSHOME", None)                                        # (the test environment of Gramps 6.1 sets it)
for _name in [n for n in os.environ if n.endswith("_API_KEY")]:
    del os.environ[_name]                                                 # the tests give their own keys

_THIS_COMPUTER = ("localhost", "127.0.0.1", "::1", "0.0.0.0", "", None)
_connect, _getaddrinfo = socket.socket.connect, socket.getaddrinfo


def _is_this_computer(host):
    return host in _THIS_COMPUTER or (isinstance(host, str) and host.startswith("127."))


def _connect_here_only(self, address):
    host = address[0] if isinstance(address, tuple) else None
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_this_computer(host):
        raise OSError("the network is closed in the tests: %r" % (host,))
    return _connect(self, address)


def _getaddrinfo_here_only(host, *args, **kwargs):
    if not _is_this_computer(host):
        raise socket.gaierror(socket.EAI_NONAME, "the network is closed in the tests: %r" % (host,))
    return _getaddrinfo(host, *args, **kwargs)


socket.socket.connect = _connect_here_only
socket.getaddrinfo = _getaddrinfo_here_only
