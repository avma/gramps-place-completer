# Code review before sharing (2026-10-29)

What was looked at and how: static analysis (`pyflakes`, `flake8`), security (`bandit`), unused code (`vulture`), complexity (`radon`), scans of my own for
addresses, paths, numbers, timeouts and exceptions written in the code, a read of the threads and the waits of the window, and a **measurement** of the time and
the memory against a real Gramps database of 1,000 to 20,000 places. Every change has a test; the suite (1,333 tests) passes on Gramps 6.0.8, 6.1 beta2 and master.

## Fixed in this pass

| # | Finding | Why it mattered | What was done |
|---|---|---|---|
| 1 | **The analysis of one answer grew with the size of the tree: 1 second for every 1,000 places** (`matching.match_container` folded every name and compared every word with `difflib`, for every level of the answer, again and again) | a tree of 20,000 places took 19 seconds to analyse one answer | the folding and the splitting into words are kept (`functools.lru_cache`), the words of an alternative are made once, and the two cheap upper bounds of `difflib` are asked first. **1,008 places 1.06 s -> 0.10 s; 5,028 places 4.8 s -> 0.9 s; 20,103 places 19.4 s -> 3.7 s.** The result is **identical** (same tree, 3 different answers, every proposal and note compared) |
| 2 | **Paths of one computer in a public repository:** `cli.py` had the snapshot of the author's own tree (with its id) as the default tree, `/usr/local/lib/python3.12/dist-packages` as the place of Gramps, `~/Dropbox` as the live data; five test files had the same path | nobody else has them, and the path of a tree is personal | no default tree (`PLACECOMPLETER_TREE`, or give it); where Gramps keeps its data is found from the installed package (and in the tests, once, in `tests/__init__.py`); the folders that hold live data are `PLACECOMPLETER_LIVE_DIRS` (default `~/Dropbox`); `PLACECOMPLETER_WORK` and `PLACECOMPLETER_CACHE` |
| 3 | **The window froze for up to 20 seconds while Ollama was started** (a `sleep` loop in the thread of the window) | Gramps looks "not responding" | the wait handles the waiting events (`_pause_and_answer`, bounded) |
| 4 | **Wikidata `Retry-After`:** a date (a legal value) raised an error in the worker, and a server could make it wait for any time | a crash, or a hang | `retry_after()`: seconds or a date, never more than 60 seconds, never less than 0 |
| 5 | **The address of a service was opened whatever it was** (`file:`, `ftp:` ...) (bandit B310) | the address comes from the settings of the user | `engines.require_http`: only `http` and `https` |
| 6 | The log file of `ollama serve` was left open in the window | a handle for the life of Gramps | closed after the start |
| 7 | **The version** was `0.1.0` in the engine and `0.1.1` in the registration (four times) | the User-Agent said `0.1` | one `__version__`, the registration must agree (a test), the User-Agent names it |
| 8 | Unused code: `msgfmt.compile_file`, imports in `session`, `wikidata`, `cli`; re-exports of `ingest.py` were reported as errors | noise | removed or marked as meant |
| 9 | Timeouts and match scores were numbers in the middle of the code | hard to find and to change | `ASK_TIMEOUT`, `LOOKUP_TIMEOUT`, `FETCH_TIMEOUT`, `PULL_TIMEOUT`, `MAX_RETRY_WAIT`; `SCORE_*`, `SIMILAR_RATIO` |
| 10 | The Gramps place model could change (GEPS 045) | the writer would break in hard-to-read ways | an alarm test (`test_00_place_model.py`, the first of the suite) and the watch list of `MAINTENANCE.md` |

## Looked at, nothing to do

- `pyflakes` / `flake8`: no error (the names `register`, `TOOL` ... of the registration file are given by Gramps).
- `bandit`: no medium or high finding left; the low ones are the use of `subprocess` with a list of arguments (no shell), `saxutils.escape` used for the markup of a label
  (not for parsing XML), and four `except Exception: pass` that are cosmetic (a style of the window, the position of the window) or a probe (the keystore).
- **No secret in the repository**; the keys are kept in the keyring or in a file of the user with restricted rights (`keystore.py`, tested).
- **No `print()` in the engine** (only in the command line and the deploy tool).
- **Threads:** the questions to an AI, to Wikidata and the download of a model run in worker threads; the window is told the result with `GLib.idle_add`. The only
  waiting in the thread of the window is bounded (`_flush`, 50 events).
- **Memory:** the caches are bounded (262,144 entries); the load of the tree is 1.4 s and about 0 MB more for 20,000 places.
- **Exceptions:** 61 specific handlers, 17 broad ones (mostly at the border with Gramps or the network).
- **Numbers in the code:** 281 literals, most of them are tables (the types of places in `kinds.py`, the properties of Wikidata, the ids of the buttons); only the ones
  of item 9 were thresholds in the middle of the code.

## Left for the owner (not changed, on purpose)

| # | What | Why it was left | When to do it |
|---|---|---|---|
| a | **12 functions are very complex** (radon F: `propose_from_pack` 89, `link_chain` 76, `apply_proposals` 73, `parse_structured` 67, `complete_place` 57 ...); the average is B (7.4) | they work and are covered by tests; splitting them is a refactoring without a visible gain | when one of them has to change |
| b | **The matching still looks at every place for every level** (3.7 s at 20,000 places) | an index by name would make it near-instant, but it must keep the same results (the same method of proof as item 1) | if somebody has a tree of more than 20,000 places |
| c | **The `User-Agent`** does not give a way to be reached (Wikimedia asks for one) | there is no repository yet | when the repository has an address: add it to `USER_AGENT` |
| d | **The window has been run only against a stand-in for GTK** in the tests | a real window can be looked at only on a computer with Gramps | look at it in Gramps 6.0.8 and 6.1 before sharing (the Hebrew, the direction marks, the width of the buttons) |
| e | Before sharing: `LICENSE` (GPL v2 or later), `.gitignore`, a README for strangers, a repository with one first commit | not code | with the repository |
