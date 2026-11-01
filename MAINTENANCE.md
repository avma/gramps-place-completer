# Maintaining Place Completer

Written while everything is fresh, so that nothing has to be remembered later. Short on purpose.

## The promise (what is said to anybody)

> Place Completer is written for my own use and is shared as it is, under the GPL. It has no support and no promised updates. It is tested on the versions of Gramps
> named at the top of `README.md`; on any other version it may or may not work.

Nothing in this file is a promise to anybody. It is a plan for the owner, to keep the addon from becoming a burden.

## The time budget

- **For a new version of Gramps: 30 minutes.** If it is not green after 30 minutes, stop, write "not tested on version X" at the top of `README.md`, and leave it until there is a wish to
  go on. An addon that says honestly what it was tested on is not neglected.
- **Once a year (or when a service stops answering): 1 hour** for the AI services and the web links (below).
- **Nothing else is scheduled.** No questions are answered unless the owner wants to answer.

## A new version of Gramps (the routine)

1. Add the version to `tools/setup_gramps_versions.sh` (a line with the version or tag) and run it: `sh tools/setup_gramps_versions.sh` (needs the network once, and `msgfmt` from the package `gettext`: `sudo apt install gettext`). It also installs `orjson`, which Gramps needs and the `--no-deps` install leaves out, and ends by importing each version: a missing Python package is named in the last lines.
2. Run all the versions: `sh tools/check_all.sh`. The last line says `ALL VERSIONS OK` or `SOME VERSION NOT OK`; each module that fails is named.
3. **Green:** add the new version to the sentence "Tested with Gramps ..." at the top of `README.md`. Done.
4. **Red:** read the first failing test; it names the part of Gramps that changed. Most likely one of the parts in the next section. Fix if it is small, else write
   "not tested on version X" in `README.md` and stop.
5. Try the window once by hand, because the tests do not open a real window: `python3 deploy_addon.py --gramps-version X --grampshome DIR --translations --clean`, then ask for one place
   (Blagnac, 1999 is a good one) and apply it on a copy of the tree.

## What is most likely to break

**1. The AI services (the most likely, and not Gramps at all).** Model names, addresses and the rules of each service change. They are in one place, `BUILTIN` in
`placecompleter/engines.py`, and in the default model of each engine. If an engine fails: `python3 tools/collect_answers.py --check` shows which one. **Keep few engines:** every
engine that is kept is one more thing that stops working. Remove the ones that are not used.

**2. The web links** in the answers and in the documents: `python3 tools/check_urls.py` (polite, with pauses). A page that moved is a line to change, not a failure.

**3. The parts of Gramps that the addon touches** (found with `grep -h "from gramps" placecompleter/*.py placecompleter_*.py`):

| Part | Used for | How likely to change |
|---|---|---|
| `gramps.gen.lib`: `Place`, `PlaceName`, `PlaceRef`, `PlaceType`, `Date`, `Url`, `Citation`, `Source`, `Note`, `Repository` | the data of a place | low: the data model of places has been stable since 5.0 |
| `gramps.gen.db.DbTxn` | one step that Edit > Undo takes back | low |
| `gramps.gen.display.place.displayer`, `gramps.gen.utils.location.get_location_list` | how Gramps would show a place on a date | medium: this is where 6.1 may differ (the names and the periods) |
| `gramps.gui.plug.tool`, `managedwindow`, `dialog`, `gramps.gen.plug.Gramplet`, GTK | the window, the gramplet | medium: GTK and the plugin registration (`PlaceCompleter.gpr.py`) |
| `PlaceType` words and `glocale` | the names of the types in the interface (taken from Gramps itself by `kinds.type_name`) | none to maintain: they follow Gramps |

**4. The tests that read English texts.** A change of a text in the interface means a change of the tests that check it. `docs/TEXT_REVIEW.md` says how the texts are changed in Poedit
(`tools/po_exchange.py`) and why some texts are read by the program (the notes of the analysis are recognised through the registry in `placecompleter/rules.py`, not through
their words).

## Watch list: things outside the addon that could break it

**GEPS 045, Place Model Enhancements** (a proposed new place model: one list of names with no primary name, types that are a list with dates and groups, a hierarchy type
on each enclosure, attributes and events on places).
- **Status:** stalled (the wiki page says so; the pull request has been stalled since May 2025). None of it is in Gramps 6.0.8, 6.1 beta2 or master.
- **How to know it landed:** `tests/test_00_place_model.py` fails first (it says that the place model changed), or `Place` has `add_name` or `get_place_types`.
- **What happens then:** Gramps declines to load the addon, because the registration names only the tested versions (`TESTED_WITH`): no data is at risk.
- **What to adapt:** `writer.py` (names, types, links: about half of all the uses of the place model), `model.py` (reading), `grampslink.py` (display), `kinds.py`,
  `citations.py`. A new link must carry the administrative type of hierarchy, or it may not show in the title of the place. `set_type` would only replace the top of a
  list of types: to keep a type with its period the addon would add a dated type instead. The rules about the period of a name (NP) and the notes about `?` have to be
  thought again: nobody knows yet how the new displayer chooses a name for a date.
- **What would get simpler:** the list of settlement types of `kinds.py` (a group of types does it), and the workaround for one type per place.

## Making it smaller (before anything is shared)

The addon is the biggest in the official repository of addons (about 11,000 lines installed, 29,000 with the tests; the median addon is 470 lines). Cut **by what the trial
shows**, in this order, the safest first:

1. **The engines that are not used** (one or two engines are enough: delete the rest from `BUILTIN` and their tests).
2. **The old forms of the question** (`classic`, `short`, `dated`, `long`, in `prompts.py`), after one test of the table form on another AI. Note that `reader.parse_structured` stays:
   it is the second stage of the table form too (`table.convert()` turns the table, with `|` or tabs, into labelled lines, and `parse_structured` reads those). It can only go if
   `table.py` is changed to build the record itself, which is a rewrite and not a deletion.
3. **The rules that never fired in the trial** (`docs/ANALYZER_RULES.md` has the table; `tools/replay_answers.py --ablate` shows what a rule changes). Never remove a rule that
   guards the tree (P0, and the notes that explain a safety rule) without a case that shows it is not needed.
4. **The tools in `tools/`** are not installed in Gramps: they cost nothing in use and may stay.

## If the owner stops

- Say so in the first lines of `README.md` ("not maintained; tested on ...").
- The GPL headers are already on every file; anybody may fork. Nothing else has to be done.
- Keep the repository as it is (the tests are what makes it safe to leave).

## Where things are

| File | What |
|---|---|
| `README.md` | what the addon is, the versions it was tested with, the tools |
| `STATUS.md` | what is done, what is open |
| `TRIAL.md` | the cases of the trial (one row for each place that was asked) |
| `docs/MODULES.md` | what each module does |
| `docs/ANALYZER_RULES.md` | every rule of the analysis and what it guards |
| `docs/TEXT_REVIEW.md`, `docs/GLOSSARY_HE.md` | the texts, the Hebrew, how to change them |
| `tools/make_local_commits.py` | the local commits and the tags (`local-trial-N`); nothing is pushed |
