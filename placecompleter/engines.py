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
"""Which AI answers the question: any of them, whatever search engine the user has.

Three kinds of engine, all behind the same two steps (ask, get the answer text):

  browser  a link template with {q}: the browser opens the question, the user copies the answer (Google AI mode, ChatGPT,
           Gemini, Perplexity, Copilot... anything that takes a question in its address)
  manual   the question is copied to the clipboard; the user pastes it into any AI and copies the answer back
  api      the program asks by itself with the user's own key: "anthropic" (Claude API with its web search tool) and
           "openai" (any OpenAI-compatible endpoint: OpenAI, a local Ollama or LM Studio, ...). The model is known and
           written down next to the answer.

Users add or change engines in ~/.config/placecompleter/engines.json. A key is found, in this order, in the environment variable
the engine names (for scripts), in what the window saved (the system keyring, see keystore.py), or in a key_file the user made.
"""

# -------------------------------------------------------------------------
#
# Standard python modules
#
# -------------------------------------------------------------------------
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request

# -------------------------------------------------------------------------
#
# Place Completer modules
#
# -------------------------------------------------------------------------
from . import keystore
from .i18n import _ as tr

CONFIG = os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "engines.json")
MODELS = os.path.join(os.path.expanduser("~"), ".config", "placecompleter", "models.json")     # what the program chose by itself (no secret in it)

BUILTIN = {
    "google": {"kind": "browser", "label": tr("Google AI mode"), "url": "https://www.google.com/search?udm=50&q={q}"},
    "chatgpt": {"kind": "browser", "label": tr("ChatGPT (web search enabled)"), "url": "https://chatgpt.com/?hints=search&q={q}"},
    # Gemini ignores a question put in its address (the page opens empty and the question stays in the address bar): the question is
    # copied instead, and the page is opened for it to be pasted ("copy": True).
    "gemini": {"kind": "browser", "label": tr("Gemini (query copied to clipboard: paste into the browser prompt)"), "url": "https://gemini.google.com/app",
               "copy": True},
    "manual": {"kind": "manual", "label": tr("Custom AI: query is copied; paste into your AI tool and paste the response back here")},
    "anthropic": {"kind": "api", "api": "anthropic", "label": tr("Claude API with web search"), "model": "claude-sonnet-5-5",
                  "key_env": "ANTHROPIC_API_KEY", "web_search": True, "max_uses": 5, "tool": "web_search_20250305"},
    "openai": {"kind": "api", "api": "openai", "label": tr("OpenAI-compatible endpoint (without internal web search)"),
               "base_url": "https://api.openai.com/v1", "model": "", "key_env": "OPENAI_API_KEY"},
    "ollama": {"kind": "api", "api": "openai", "label": tr("Local Ollama instance (no internet access)"),
               "base_url": "http://localhost:11434/v1", "model": "", "key_env": ""},
}


SYSTEM = ("You answer a data request for a genealogy program, which reads your reply by machine. Reply with the requested block "
          "of labelled lines and nothing else. Each field holds one plain value: no remark in brackets inside a field, except the "
          "period of a name. Put every remark, doubt or detail in one final line that starts with NOTES: . Write UNKNOWN only as the "
          "whole value of a field; if a container is unknown, leave that line out. If you do not know when a name was used, write the "
          "name without a period.")


class EngineError(Exception):
    pass



class NeedsSetup(EngineError):
    """The engine needs something done on this computer before it can be asked (Ollama with no model): the window offers to do it."""

def work_dir():
    """The folder where the work of the user is kept (the answers, what the window remembers, the log of Ollama): $PLACECOMPLETER_WORK, or ~/gramps-place-work."""
    return os.path.expanduser(os.environ.get("PLACECOMPLETER_WORK") or "~/gramps-place-work")


def config_path():
    """The file of the user's engines: $PLACECOMPLETER_ENGINES, or ~/.config/placecompleter/engines.json."""
    return os.environ.get("PLACECOMPLETER_ENGINES") or CONFIG


def load_engines(path=None):
    """The built-in engines plus whatever the user's file adds or changes."""
    engines = {k: dict(v) for k, v in BUILTIN.items()}
    path = path or config_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise EngineError("cannot read %s: %s" % (path, exc))
        for name, cfg in (data.get("engines") or {}).items():
            engines[name] = {**engines.get(name, {}), **cfg}
    return engines


def models_path():
    return os.environ.get("PLACECOMPLETER_MODELS") or MODELS


def remembered_model(engine_id):
    """The model the program chose for this engine earlier ('' if none)."""
    try:
        with open(models_path(), encoding="utf-8") as fh:
            return str((json.load(fh) or {}).get(engine_id) or "")
    except (OSError, ValueError, AttributeError):
        return ""


def remember_model(engine_id, model):
    """Keep the choice (an empty model forgets it). Written whole and replaced at once: a half-written file is never read."""
    try:
        with open(models_path(), encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    if model:
        data[engine_id] = model
    else:
        data.pop(engine_id, None)
    path = models_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


_NOT_FOR_TEXT = ("audio", "realtime", "image", "tts", "transcribe", "search", "embedding", "instruct", "moderation", "codex", "whisper",
                 "dall", "vision", "preview", "research", "diariz", "-pro", "computer-use")


def choose_model(listing, host=""):
    """The model to ask, chosen from what the service lists (GET /models), or '' when it cannot be told.

    OpenAI: the newest general text model of the gpt family: not a snapshot with a date in its name when the plain name exists, not a
    mini or nano one when a full one exists, and none made for audio, images, search, embeddings or only for the newer API. Another
    service: the model it lists when it lists only one; with several there is nothing to go by, and the user names one."""
    rows = []
    for m in (listing.get("data") or []) if isinstance(listing, dict) else []:
        if isinstance(m, dict) and m.get("id"):
            rows.append((str(m["id"]), m.get("created") if isinstance(m.get("created"), (int, float)) else 0))
    if not rows:
        return ""
    if host.split(":")[0] in ("localhost", "127.0.0.1", "::1"):
        # a server on this very computer (Ollama ...) lists what was installed: the newest model that is not made for embeddings
        text = [(i, c) for i, c in rows if "embed" not in i.lower()]
        return max(text, key=lambda r: (r[1], r[0]))[0] if text else ""
    if not host.endswith("openai.com"):
        return rows[0][0] if len(rows) == 1 else ""
    import re
    good = [(i, c) for i, c in rows if re.match(r"^gpt-\d", i) and not any(w in i for w in _NOT_FOR_TEXT)]
    for dated in (False, True):
        pool = [(i, c) for i, c in good if bool(re.search(r"-\d{4}-\d{2}-\d{2}$|-\d{4}$", i)) == dated]
        for small in (False, True):
            tier = [(i, c) for i, c in pool if bool(re.search(r"mini|nano", i)) == small]
            if tier:
                return max(tier, key=lambda r: (r[1], r[0]))[0]
    return ""


def known_model(cfg):
    """The model this engine will use, as far as it is known without asking the service ('' if it is not decided yet)."""
    return cfg.get("model") or (remembered_model(cfg.get("id", "")) if cfg.get("api") == "openai" else "")


def settle_model(cfg, http_get=None):
    """(model, how) for an engine that wants one: what engines.json says, else what was chosen before, else the service is asked what
    it has (the list of models: nothing is spent) and the choice is kept. how: 'settings', 'remembered' or 'chosen'. EngineError if none."""
    if cfg.get("model"):
        return cfg["model"], "settings"
    if cfg.get("api") != "openai":
        raise EngineError(tr("this engine requires a model specification. Define it in %s, e.g.: {\"engines\": {\"%s\": {\"model\": "
                             "\"model-name\"}}}") % (
            config_path(), cfg.get("id", "")))
    saved = remembered_model(cfg.get("id", ""))
    if saved:
        return saved, "remembered"
    headers = {}
    key = _key(cfg)
    if key:
        headers["authorization"] = "Bearer " + key
    url = cfg["base_url"].rstrip("/") + "/models"
    listing = (http_get or get_json)(url, headers)
    model = choose_model(listing, service_host(cfg) or "")
    if not model and cfg.get("id") == "ollama" and not (isinstance(listing, dict) and listing.get("data")):
        raise NeedsSetup(tr("Ollama service is active but has no models installed. Run 'ollama pull llama3.2' in terminal and try again"))
    if not model:
        names = [str(m.get("id")) for m in (listing.get("data") or []) if isinstance(m, dict) and m.get("id")] if isinstance(listing, dict) else []
        raise EngineError(tr("could not select a model from %s (%s). Specify a target model in %s, e.g.: {\"engines\": {\"%s\": {\"model\": "
                             "\"model-name\"}}}") % (
            service_host(cfg) or url, ", ".join(names[:8]) + (", ..." if len(names) > 8 else "") if names else tr("none"), config_path(), cfg.get("id", "")))
    remember_model(cfg.get("id", ""), model)
    return model, "chosen"


def pick(name, path=None):
    engines = load_engines(path)
    if name not in engines:
        raise EngineError("no engine called %r. Available: %s" % (name, ", ".join(sorted(engines))))
    cfg = dict(engines[name])
    cfg["id"] = name
    return cfg


def browser_url(cfg, prompt):
    return cfg["url"].replace("{q}", urllib.parse.quote(prompt, safe=""))


def _cannot_reach(url, reason):
    """The message for a service that cannot be reached; for this computer's own address it says what that means."""
    text = tr("cannot connect to %s: %s") % (url, reason)
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1"):
        text += tr(". Destination unreachable: the local model server (e.g. Ollama) is either not installed or not currently "
                   "running")
    return text


def require_http(url):
    """The address of a service comes from the settings of the user: only http and https are opened (not file:, not ftp:, not anything else)."""
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise EngineError(tr("only http and https addresses are allowed: %s") % url)


ASK_TIMEOUT = 120                     # seconds that an AI may take to answer a question (a search of the web makes it slow)
LOOKUP_TIMEOUT = 20                   # seconds for a short question to a service (the list of its models, a test of a key)


def post_json(url, headers, body, timeout=ASK_TIMEOUT):
    require_http(url)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:                 # nosec B310 (require_http was called)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise EngineError(tr("service returned HTTP error %s: %s") % (exc.code, detail))
    except (urllib.error.URLError, OSError) as exc:
        raise EngineError(_cannot_reach(url, getattr(exc, "reason", exc)))


def get_json(url, headers, timeout=LOOKUP_TIMEOUT):
    require_http(url)
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:                 # nosec B310 (require_http was called)
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise EngineError(tr("service returned HTTP error %s: %s") % (exc.code, exc.read().decode("utf-8", "replace")[:300]))
    except (urllib.error.URLError, OSError) as exc:
        raise EngineError(_cannot_reach(url, getattr(exc, "reason", exc)))


# ---------------------------------------------------------------------------------------------------- keys
def _clean(raw):
    return (raw or "").strip().strip("\"'").strip()                      # pasting can add a newline, a space or quotes


def _key_from_file(cfg):
    """(key, problem) from the file named by key_file: it must be readable by its owner only."""
    path = os.path.expanduser(cfg.get("key_file") or "")
    if not path or not os.path.isfile(path):
        return "", None
    if os.stat(path).st_mode & 0o077:
        return "", tr("key file %s has insecure permissions (readable by others). Execute: chmod 600 %s") % (path, path)
    with open(path, encoding="utf-8") as fh:
        return _clean(fh.read()), None


def needs_key(cfg):
    return bool(cfg.get("key_env") or cfg.get("key_file"))


def key_account(cfg):
    """The name under which the window keeps this engine's key."""
    return cfg.get("key_account") or cfg.get("id") or ""


def _find_key(cfg):
    """(key, where, problem): the environment variable first (for scripts), then what the window saved (system keyring or a
    private file), then the key_file named in engines.json."""
    env = cfg.get("key_env")
    if env and _clean(os.environ.get(env, "")):
        return _clean(os.environ[env]), "$%s" % env, None
    account = key_account(cfg)
    if account:
        store = keystore.get_store()
        try:
            stored = _clean(store.get(account))
        except keystore.StoreError as exc:
            return "", None, str(exc)
        if stored:
            return stored, store.name, None
    if cfg.get("key_file"):
        key, problem = _key_from_file(cfg)
        if problem:
            return "", None, problem
        if key:
            return key, "file %s" % cfg["key_file"], None
    return "", None, None


def _key(cfg):
    if not needs_key(cfg):
        return ""
    key, where, problem = _find_key(cfg)
    if problem:
        raise EngineError(problem)
    if not key:
        env = cfg.get("key_env")
        env_part = tr("export environment variable %s (requires starting Gramps from the matching terminal session); or") % env if env else ""
        raise EngineError((tr("API key missing. Enter it via the Key button (stored securely in keyring or restricted user file), or "
                              "%s specify key_file in %s.") % (env_part, config_path())).replace("  ", " "))
    return key


def _local_address(cfg):
    """(host, port) when the engine is a server on this very computer (Ollama, LM Studio...), else None."""
    if cfg.get("kind") != "api" or cfg.get("api") != "openai":
        return None
    parts = urllib.parse.urlsplit(cfg.get("base_url") or "")
    if (parts.hostname or "") not in ("localhost", "127.0.0.1", "::1"):
        return None
    return parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def _listening(host, port, timeout=0.5):
    """Does anything answer at this address of this computer? (A refused connection is immediate: nothing waits.)"""
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def readiness(cfg):
    """(ready, problems, how to fix) for an engine: whether asking it can work at all."""
    if cfg.get("kind") != "api":
        return True, [], ""
    problems, fixes = [], []
    local = _local_address(cfg)
    if local and not _listening(*local):
        problems.append(tr("no response from host %s:%d") % local)
        if cfg.get("id") == "ollama":
            fixes.append(tr("Ollama is not active locally. Click Ask to run guided setup. Manual steps: 1) Install from ollama.com; 2) "
                            "Start service with 'ollama serve'; 3) Download model using 'ollama pull llama3.2'."))
        else:
            fixes.append(tr("start the local model server daemon, or update base_url in %s") % config_path())
    if needs_key(cfg):
        key, _where, problem = _find_key(cfg)
        if problem:
            problems.append(tr("key file permissions are insecure (readable by others)") if "chmod 600" in problem else tr("unable to read key file"))
            fixes.append(problem)
        elif not key:
            problems.append("no key")
            env = cfg.get("key_env")
            fixes.append(tr("use the Key button to store your credential%s, or specify key_file in %s") % (
                tr(", or set environment variable $%s before launching Gramps") % env if env else "", config_path()))
    return (not problems), problems, "; ".join(fixes)


def key_report(cfg):
    """What can be said about the key without showing it: is it set, where from, how long, does it look like this service's
    keys, what pasting may have broken. Never returns a character of the key."""
    if not needs_key(cfg):
        return {"needed": False, "problems": []}
    key, where, problem = _find_key(cfg)
    if problem:
        return {"needed": True, "set": False, "problems": [problem]}
    if not key:
        return {"needed": True, "set": False, "problems": ["not set"]}
    env = cfg.get("key_env")
    raw = os.environ.get(env, "") if where == "$%s" % env else key
    problems = []
    if raw != raw.strip():
        problems.append(tr("contains leading/trailing whitespace or line breaks (automatically trimmed)"))
    core = raw.strip()
    if core[:1] in "\"'" or core[-1:] in "\"'":
        problems.append(tr("enclosed in quotation marks (automatically stripped)"))
    core = core.strip("\"'").strip()
    if any(ch.isspace() for ch in core):
        problems.append(tr("contains internal spaces or line breaks: clipboard data might be corrupted"))
    if any(ord(ch) > 126 or ord(ch) < 33 for ch in core if not ch.isspace()):
        problems.append(tr("contains non-ASCII characters (check for formatting marks or localized keyboard input)"))
    if cfg.get("api") == "anthropic" and not core.startswith("sk-ant-"):
        problems.append(tr("invalid Anthropic API key format (must begin with 'sk-ant-')"))
    return {"needed": True, "set": True, "length": len(core), "where": where, "problems": problems}


def key_hint(cfg):
    """How to recognise the saved key (its public prefix, its last four characters, its length): for the key window only, never
    for logs or reports."""
    key, _where, _problem = _find_key(cfg)
    return keystore.describe_key(key) if key else ""


def service_host(cfg):
    """The server a key of this engine is sent to."""
    if cfg.get("api") == "anthropic":
        return "api.anthropic.com"
    if cfg.get("api") == "openai":
        return urllib.parse.urlparse(cfg.get("base_url", "")).netloc or "?"
    return ""


def key_mismatch(cfg, key):
    """A message when the key is plainly not of the service it would be sent to (a Claude key given to OpenAI, or the reverse), else ''."""
    key = _clean(key)
    host = service_host(cfg)
    if not key or not host:
        return ""
    if cfg.get("api") == "openai" and host.endswith("openai.com") and key.startswith("sk-ant-"):
        return (tr("This is an Anthropic Claude key, but the engine sends requests to %s. Please select 'Claude API with web "
                   "search' from the engine list.") % host)
    if cfg.get("api") == "anthropic" and not key.startswith("sk-ant-"):
        return (tr("Anthropic API keys must start with 'sk-ant-'. The provided key appears invalid or belongs to a different "
                   "provider. It will be sent to %s.") % host)
    return ""


def key_status(cfg):
    if not needs_key(cfg):
        return tr("no key required")
    rep = key_report(cfg)
    if not rep.get("set"):
        env = cfg.get("key_env")
        where = "$%s" % env if env else "file %s" % cfg.get("key_file")
        return tr("API key in %s: MISSING%s") % (where, "" if rep["problems"] == ["not set"] else " (%s)" % "; ".join(rep["problems"]))
    state = tr("configured, %d characters") % rep["length"]
    if rep["problems"]:
        state += "; CHECK: " + "; ".join(rep["problems"])
    return "key in %s: %s" % (rep["where"], state)


def check_key(cfg, key=None, http_get=get_json):
    """Ask the service whether it accepts the key (and knows the model), without spending a token: the models list of the service.
    `key` is a key typed in the window and not saved yet. Returns {'ok', 'message'}."""
    import re
    try:
        key = _clean(key) if key is not None else _key(cfg)
    except EngineError as exc:
        return {"ok": False, "message": str(exc)}
    if not key:
        return {"ok": False, "message": tr("No API key available to test.")}
    wrong = key_mismatch(cfg, key)
    if wrong:
        return {"ok": False, "message": wrong}                           # no need to ask a service that cannot know this key
    model = cfg.get("model")
    if cfg.get("api") == "anthropic":
        url = "https://api.anthropic.com/v1/models/%s" % urllib.parse.quote(model) if model else "https://api.anthropic.com/v1/models?limit=1"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    elif cfg.get("api") == "openai":
        url = cfg["base_url"].rstrip("/") + ("/models/%s" % urllib.parse.quote(model) if model else "/models")
        headers = {"authorization": "Bearer " + key}
    else:
        return {"ok": False, "message": tr("This engine does not use an API key.")}
    try:
        resp = http_get(url, headers)
    except EngineError as exc:
        code = re.search(r"HTTP (\d+)", str(exc))
        code = int(code.group(1)) if code else None
        if code in (401, 403):
            return {"ok": False, "message": tr("Service %s rejected the API key (HTTP %d). Sent key suffix: %s. Verify key validity, quota limits, and "
                                               "provider matching.") % (
                                                service_host(cfg), code, keystore.describe_key(key))}
        if code == 404 and model:
            return {"ok": True, "message": tr("API key validated, but model «%s» is unrecognized by host. Select another model in %s.") % (model, config_path())}
        return {"ok": False, "message": str(exc)}
    name = (resp.get("display_name") or resp.get("id") or model) if isinstance(resp, dict) else model
    return {"ok": True, "message": tr("API key validated successfully%s.") % (tr("; model %s is active") % name if model else "")}


def ask_anthropic(cfg, prompt, http=post_json):
    body = {"model": cfg["model"], "max_tokens": cfg.get("max_tokens", 2500), "system": cfg.get("system", SYSTEM),
            "messages": [{"role": "user", "content": prompt}]}
    if cfg.get("web_search", True):
        body["tools"] = [{"type": cfg.get("tool", "web_search_20250305"), "name": "web_search", "max_uses": cfg.get("max_uses", 5)}]
    resp = http("https://api.anthropic.com/v1/messages",
                {"x-api-key": _key(cfg), "anthropic-version": "2023-06-01", "content-type": "application/json"}, body)
    # while it searches the model may write a line ("I'll look that up"): the answer is the text after the last tool block
    final, every = [], []
    for block in resp.get("content", []):
        if block.get("type") == "text":
            final.append(block.get("text", ""))
            every.append(block.get("text", ""))
        else:
            final = []
    text = "\n".join(final).strip() or "\n".join(every).strip()
    if not text:
        raise EngineError(tr("response returned empty content (stop reason: %s)") % resp.get("stop_reason"))
    return {"text": text, "model": resp.get("model") or cfg["model"]}


def ask_openai(cfg, prompt, http=post_json, http_get=None):
    model, how = settle_model(cfg, http_get)
    cfg = {**cfg, "model": model}
    headers = {"content-type": "application/json"}
    key = _key(cfg)
    if key:
        headers["authorization"] = "Bearer " + key
    body = {"model": model, "temperature": 0,
            "messages": [{"role": "system", "content": cfg.get("system", SYSTEM)}, {"role": "user", "content": prompt}]}
    url = cfg["base_url"].rstrip("/") + "/chat/completions"
    try:
        try:
            resp = http(url, headers, body)
        except EngineError as exc:
            if "HTTP 400" not in str(exc) or "temperature" not in str(exc):
                raise
            body.pop("temperature")                                    # the newer models accept only their own temperature: ask without one
            resp = http(url, headers, body)
    except EngineError as exc:
        if how == "settings" and "HTTP 404" in str(exc) and _local_address(cfg):
            raise EngineError(str(exc) + tr(". Target model missing: download using 'ollama pull %s'") % model)
        if how != "settings" and ("HTTP 404" in str(exc) or "model_not_found" in str(exc)):
            remember_model(cfg.get("id", ""), "")                      # the service no longer has the model chosen: the next call chooses again
            raise EngineError(tr("model %s is no longer offered by host (%s); model choice will re-evaluate on next request") % (model, exc))
        raise
    try:
        text = (resp["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError):
        raise EngineError(tr("response structure is invalid or unrecognized"))
    if not text:
        raise EngineError(tr("the response is empty"))
    return {"text": text, "model": resp.get("model") or cfg["model"]}


def ask(cfg, prompt, http=post_json, http_get=None):
    """{'text', 'model'} from an api engine."""
    try:
        if cfg.get("api") == "anthropic":
            return ask_anthropic(cfg, prompt, http)
        if cfg.get("api") == "openai":
            return ask_openai(cfg, prompt, http, http_get)
    except EngineError as exc:
        if "HTTP 401" in str(exc):
            hint = key_hint(cfg)
            raise EngineError(tr("%s\n  Service %s rejected API key authentication%s. Verify key active status in provider dashboard and "
                                 "re-enter using Key button.") % (
                                  exc, service_host(cfg) or "", tr(" sent (%s)") % hint if hint else ""))
        raise
    raise EngineError("unknown api %r" % cfg.get("api"))


def provenance(cfg, form, place, date, prompt, model=None, url=None, when=None):
    """What to keep next to a saved answer: who answered, how it was asked, when."""
    import datetime
    return {"engine": cfg["id"], "engine_label": cfg.get("label"), "kind": cfg.get("kind"),
            "model": model or ("not disclosed by the service" if cfg.get("kind") != "manual" else "unknown (pasted by the user)"),
            "form": form, "place": place, "date": str(date), "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "asked_at": when or datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "url": url}
