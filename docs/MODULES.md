# The modules of Place Completer

The engine (`placecompleter/`) does not import Gtk or Gramps at the top of any file, so that it runs from the command line and in the tests without a
screen. The window and the other entry points of Gramps are the files `placecompleter_*.py` and `PlaceCompleter.gpr.py` next to the folder.

Every Python file begins with the license header of Gramps (GNU General Public License, version 2 or later) and has, above its imports, the banners that
Gramps uses: *Standard python modules*, *GTK/Gnome modules*, *Gramps modules*, *Place Completer modules*. `tools/add_headers.py` writes them (and
`tests/test_headers.py` checks them).

## The analysis of an answer

`ingest.ingest(tree, rec, date_text, ...)` makes the control screen of an answer. It is a list of **steps**; each step reads what it needs from an
`Analysis` (`analysis.py`) and keeps what it made for the steps that follow.

| Step | Module | What it does |
|---|---|---|
| `find_place` | `findplace.py` | the place of the tree that has the name of the answer (ID1: not one that is far away; LV3: not an area); the web links offered for it |
| `check_levels` | `resolve.py` | the remarks of the reader; the levels that the country has on that date and the answer lacks |
| `prepare_levels` | `resolve.py` | what the user chose; how a level is matched to a place of the tree; the language of a level |
| `read_levels` | `resolve.py` | each level made into a unit: a place of the tree or a new one; the state; the chain of the units |
| `new_place` | `makeplaces.py` | the new place of the question, with its names, type and coordinates |
| `fix_levels` | `makeplaces.py` | the plain name, the language and the type of the levels that exist |
| `existing_place` | `chainlinks.py` | what the answer adds to the place that the tree has; the checks of a link |
| `link_chain` | `chainlinks.py` | the links of the chain, level by level (C1-C8, T1, T2) |
| `chain_notes` | `chainlinks.py` | the note of the links that already exist; the levels that the user chose as places |
| `names_and_links` | `namefixes.py` | the periods of the names (NP1, NP3, NP5, NL); the web links |
| `finish` | `screen.py` | the proposals made into the screen, with the preview |

The topics that the steps use, in the order of their dependencies (a module imports only from those above it):

| Module | What it holds |
|---|---|
| `words.py` | the folding of names, the lists of generic words, the tests of an unknown value |
| `kinds.py` | the types of places: the size classes, the custom types of the tree, the type of a level from a word |
| `typelearn.py` | the custom types that a tree uses, read from the tree: the ways of writing one type joined (`type_key`), the role of each by a vocabulary (`data/type-vocabulary.json`), merged with the file of the user, which comes first |
| `periods.py` | the date of a period and the arithmetic on periods |
| `reader.py` | `parse_structured`: the labelled lines of the template made into one record |
| `matching.py` | the names of a place by the packs; the place of the tree that a level is; what covers a date |
| `evidence.py` | the sources of an answer and the fields that each supports; the proposal of a web link |
| `screen.py` | the notes, the label of a place, the preview, the last step |
| `compare.py` | two answers, an answer and the saved answers |

`ingest.py` imports all of them and **re-exports their names**, so that `ingest.parse_structured`, `ingest.TREE_TYPES` and the rest are read there as
they always were. The rules (`rules.py`) have an id and a switch each; see `RULES_REVIEW.md`.

## What is still long

`link_chain` (about 136 lines) is one loop over the levels with the nested functions `disconnect_notes`, `duplicate_notes` and `offer_shortcuts`. It is the
next candidate to split: the loop body, a level at a time, into the checks of C3, C4, C5, C6 and C8.
