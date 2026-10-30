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
"""Where an API key is kept, so that the window can ask for it once and never again.

In order of preference (the first that works):
  1. the system keyring (Secret Service: GNOME Keyring, KWallet...), through libsecret: encrypted, opened by the login
  2. the same keyring through the `secret-tool` command, when the libsecret bindings are not installed
  3. a file that only its owner can read (mode 600 in a folder of mode 700): NOT encrypted, and the window says so

The key is never put on a command line, in a log, in the Gramps database or in the settings of the window. The environment
variable named in engines.json still wins over all of these (for scripts). PLACECOMPLETER_KEYSTORE=none|file|keyring forces one.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import os
import shutil
import subprocess

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from .i18n import _ as tr

SERVICE = "placecompleter"
FOLDER = os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "keys")


class StoreError(Exception):
    pass


class NullStore:
    name, secure = tr("key storage location unavailable (disabled)"), False

    def get(self, account):
        return ""

    def set(self, account, value):
        raise StoreError(tr("key persistence disabled (PLACECOMPLETER_KEYSTORE=none)"))

    def delete(self, account):
        return None


class SecretServiceStore:
    """libsecret through GObject introspection (the Secret typelib: gir1.2-secret-1)."""
    name, secure = tr("system keyring"), True

    def __init__(self, secret=None):
        if secret is None:
            import gi
            gi.require_version("Secret", "1")
            from gi.repository import Secret as secret
        self.secret = secret
        self.schema = secret.Schema.new("org.placecompleter.Key", secret.SchemaFlags.NONE,
                                        {"account": secret.SchemaAttributeType.STRING})

    def get(self, account):
        try:
            return self.secret.password_lookup_sync(self.schema, {"account": account}, None) or ""
        except Exception as exc:
            raise StoreError(tr("unable to read system keyring: %s") % exc)

    def set(self, account, value):
        try:
            ok = self.secret.password_store_sync(self.schema, {"account": account}, self.secret.COLLECTION_DEFAULT,
                                                 "PlaceCompleter key: %s" % account, value, None)
        except Exception as exc:
            raise StoreError(tr("system keyring rejected key: %s") % exc)
        if not ok:
            raise StoreError(tr("system keyring failed to store key"))

    def delete(self, account):
        try:
            self.secret.password_clear_sync(self.schema, {"account": account}, None)
        except Exception as exc:
            raise StoreError(tr("failed to remove key from system keyring: %s") % exc)


class SecretToolStore:
    """The `secret-tool` command (package libsecret-tools). The key goes through its standard input, never its arguments."""
    name, secure = tr("system keyring"), True

    def __init__(self, run=subprocess.run):
        self.run = run

    def _attrs(self, account):
        return ["service", SERVICE, "account", account]

    def get(self, account):
        res = self.run(["secret-tool", "lookup"] + self._attrs(account), capture_output=True, text=True)
        return res.stdout.strip() if res.returncode == 0 else ""

    def set(self, account, value):
        res = self.run(["secret-tool", "store", "--label=PlaceCompleter key: %s" % account] + self._attrs(account),
                       input=value, capture_output=True, text=True)
        if res.returncode != 0:
            raise StoreError(tr("secret-tool failed to save key: %s") % (res.stderr or "").strip()[:200])

    def delete(self, account):
        self.run(["secret-tool", "clear"] + self._attrs(account), capture_output=True, text=True)


class FileStore:
    name, secure = tr("unencrypted local file (restricted permissions)"), False

    def __init__(self, folder=None):
        self.folder = folder or FOLDER

    def path(self, account):
        return os.path.join(self.folder, "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in account) + ".key")

    def get(self, account):
        path = self.path(account)
        if not os.path.isfile(path):
            return ""
        if os.stat(path).st_mode & 0o077:
            raise StoreError(tr("key file %s has insecure permissions (readable by others). Execute: chmod 600 %s") % (path, path))
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()

    def set(self, account, value):
        os.makedirs(self.folder, mode=0o700, exist_ok=True)
        os.chmod(self.folder, 0o700)
        path = self.path(account)
        tmp = path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)            # mode 600 from the first byte
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        os.replace(tmp, path)

    def delete(self, account):
        try:
            os.remove(self.path(account))
        except FileNotFoundError:
            pass


def _keyring_works(store):
    try:
        store.get("__probe__")
        return True
    except Exception:
        return False


def choose_store(mode=None, folder=None, secret=None, run=subprocess.run, which=shutil.which):
    """The place to keep keys: see the module text. `secret` and `run` stand in for libsecret and subprocess in tests."""
    mode = (mode if mode is not None else os.environ.get("PLACECOMPLETER_KEYSTORE", "")).strip().lower()
    if mode == "none":
        return NullStore()
    if mode == "file":
        return FileStore(folder)
    if mode in ("", "auto", "keyring"):
        try:
            store = SecretServiceStore(secret)
            if _keyring_works(store):
                return store
        except Exception:
            pass
        if which("secret-tool"):
            probe = SecretToolStore(run)
            res = run(["secret-tool", "lookup", "service", SERVICE, "account", "__probe__"], capture_output=True, text=True)
            if res.returncode == 0 or (res.returncode == 1 and not (res.stderr or "").strip()):
                return probe
        if mode == "keyring":
            raise StoreError(tr("system keyring daemon/bindings unavailable (libsecret or secret-tool required)"))
    return FileStore(folder)


_STORE = None


def get_store():
    global _STORE
    if _STORE is None:
        _STORE = choose_store()
    return _STORE


def reset_store(store=None):
    """For tests, and after the settings changed: forget the choice (or set one)."""
    global _STORE
    _STORE = store


def describe_key(key):
    """A hint to recognise a key without revealing it: its public prefix, its last four characters, its length."""
    key = (key or "").strip()
    if len(key) < 12:
        return tr("%d characters") % len(key)
    prefix = key[:7] if key.startswith("sk-ant-") else ""
    return tr("%s…%s, %d characters") % (prefix, key[-4:], len(key))
