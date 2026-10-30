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
"""Setting Ollama up for the user. Ollama is a program on this computer that runs a language model (no key, no payment, no web access).

What is missing is one of four things, and each has a step that the program can take once the user has agreed to it:
  missing   Ollama is not installed: the official installer needs the administrator's password, so it is run in a terminal window that the
            program opens (the user types the password there, nothing is typed for them); the command is also shown and can be copied.
  stopped   it is installed but nothing answers: the program starts it (`ollama serve`, as the user, in the background).
  no-model  it answers but has no model: the program downloads one through Ollama's own API (POST /api/pull), with a progress report.
  ready     there is a model to ask.
Nothing here needs a configuration file: Ollama listens on this computer only (localhost:11434) with its defaults.
Every function that touches the system takes the thing it uses as a parameter, so that the tests need no Ollama.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import json
import os
import shlex
import shutil
import subprocess
import time
import urllib.error
import urllib.request

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import engines
from .i18n import _ as tr

INSTALL_COMMAND = "curl -fsSL https://ollama.com/install.sh | sh"
HOST, PORT = "localhost", 11434
BASE = "http://%s:%d" % (HOST, PORT)
DEFAULT_MODEL = "llama3.2"
# (name, a short note) of the models the user can choose from; any other name of ollama.com/library can be typed.
SUGGESTED = (
    ("llama3.2", tr("small and fast (~2 GB, recommended)")),
    ("llama3.2:1b", tr("ultra-compact: faster response, reduced accuracy")),
    ("gemma3:4b", tr("Google model family (~a few GB)")),
    ("mistral", tr("general-purpose model (~a few GB)")),
)
KNOWN_PLACES = ("/usr/local/bin/ollama", "/usr/bin/ollama", "/opt/ollama/bin/ollama")
TERMINALS = ("gnome-terminal", "x-terminal-emulator", "mate-terminal", "xfce4-terminal", "konsole", "xterm")
PULL_TIMEOUT = 60                                    # seconds without a line from the server while a model is downloaded


def binary(which=shutil.which, exists=os.path.exists):
    """The path of the ollama program, or '' when it is not installed."""
    found = which("ollama")
    if found:
        return found
    return next((p for p in KNOWN_PLACES if exists(p)), "")


def installed_models(http_get=None):
    """The models the running server has (without those made for embeddings, which cannot answer a question)."""
    listing = (http_get or engines.get_json)(BASE + "/v1/models", {})
    rows = [str(m["id"]) for m in (listing.get("data") or []) if isinstance(m, dict) and m.get("id")] if isinstance(listing, dict) else []
    return [r for r in rows if "embed" not in r.lower()]


def state(listening=engines._listening, which=shutil.which, exists=os.path.exists, http_get=None):
    """'missing', 'stopped', 'no-model' or 'ready'."""
    if not listening(HOST, PORT):
        return "stopped" if binary(which, exists) else "missing"
    try:
        names = installed_models(http_get)
    except engines.EngineError:
        names = []
    return "ready" if names else "no-model"


def start_server(popen=subprocess.Popen, listening=engines._listening, sleep=time.sleep, now=time.monotonic, wait=20, log_path="",
                 which=shutil.which, exists=os.path.exists):
    """Start `ollama serve` in the background, detached from the window (it goes on if the window is closed), and wait until it answers.
    Returns (ok, message)."""
    path = binary(which, exists)
    if not path:
        return False, tr("Ollama is not installed")
    log_path = log_path or os.path.join(engines.work_dir(), "ollama-serve.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "ab") as log:                              # (the server keeps its own copy of the file: this one is closed here)
            popen([path, "serve"], stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    except OSError as exc:
        return False, tr("Failed to launch Ollama: %s") % exc
    deadline = now() + wait
    while now() < deadline:
        if listening(HOST, PORT):
            return True, ""
        sleep(0.5)
    return False, tr("Ollama launched but is not responding yet; check logs in %s") % log_path


def pull(model, progress, opener=urllib.request.urlopen, cancelled=lambda: False):
    """Download a model through the server's own API and report (status, done, total) to progress. Returns (ok, message)."""
    body = json.dumps({"model": model, "name": model, "stream": True}).encode("utf-8")
    request = urllib.request.Request(BASE + "/api/pull", data=body, headers={"content-type": "application/json"})
    try:
        response = opener(request, timeout=PULL_TIMEOUT)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("error") or ""
        except (ValueError, OSError, AttributeError):
            detail = ""
        return False, tr("service returned HTTP error %s: %s") % (exc.code, detail or exc.reason)
    except (urllib.error.URLError, OSError) as exc:
        return False, engines._cannot_reach(BASE + "/api/pull", getattr(exc, "reason", exc))
    try:
        for raw in response:
            if cancelled():
                return False, tr("download cancelled")
            line = raw.decode("utf-8", "replace").strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if data.get("error"):
                return False, str(data["error"])
            progress(str(data.get("status") or ""), int(data.get("completed") or 0), int(data.get("total") or 0))
            if data.get("status") == "success":
                return True, ""
    except OSError as exc:
        return False, tr("download process interrupted: %s") % exc
    finally:
        close = getattr(response, "close", None)
        if close:
            close()
    return False, tr("download terminated prematurely")


def terminal_argv(script, which=shutil.which):
    """The command that opens a terminal window running the script and waiting for a key at the end, or None when no terminal is found."""
    wrapped = script + "; echo; read -r -p 'Press Enter to close this window. ' _"
    for name in TERMINALS:
        path = which(name)
        if not path:
            continue
        if name == "gnome-terminal":
            return [path, "--", "bash", "-c", wrapped]
        if name == "mate-terminal":
            return [path, "-x", "bash", "-c", wrapped]
        if name == "xfce4-terminal":
            return [path, "-e", "bash -c " + shlex.quote(wrapped)]
        return [path, "-e", "bash", "-c", wrapped]                          # konsole, x-terminal-emulator, xterm
    return None


def open_installer_terminal(popen=subprocess.Popen, which=shutil.which):
    """Open a terminal that runs the official installer; (ok, message). The program types no password and sees none."""
    argv = terminal_argv(INSTALL_COMMAND, which)
    if not argv:
        return False, tr("Terminal application not detected. Copy command and execute manually in system terminal.")
    try:
        popen(argv, stdin=subprocess.DEVNULL, start_new_session=True)
    except OSError as exc:
        return False, tr("Could not launch terminal application: %s") % exc
    return True, ""


def percent(done, total):
    """A whole number 0-100, or None when the size is not known yet."""
    return None if not total else max(0, min(100, int(done * 100 / total)))


def human_size(count):
    """'1.2 GB' or '340 MB' (decimal, as the download sizes of the models are given)."""
    return "%.1f GB" % (count / 1e9) if count >= 1e9 else "%d MB" % (count / 1e6)
