# Review of the English texts (379 texts, one pass) and the state of the Hebrew

The texts are `po/template.pot` (made by `python3 tools/extract_strings.py`). All were read. What follows is what to change; nothing here has been changed in the code
yet except where it says **done**. The numbers are the order of the texts in the catalog at the time of the review.

## Done

| What | Why |
|---|---|
| The 20 names of the types of places (Town, Village ...) are **no longer texts of the addon**: the window shows the word that Gramps shows in the Type column (`kinds.type_name`) | 8 of the 20 differed from Gramps in Hebrew (Town: Gramps *ir'a*, the addon *ayarah*), and Gramps changes some of them between versions (State, Province: 6.0.8 and 6.1 differ), so a copy in the addon is right for one version and wrong for another |
| NP3 (the name of a place given a period from the start of its state) is **off by default** | in Gramps a name with one period and no other name shows `?` for an event that is earlier |

## Status after the approval

R1-R5 were approved with the wording of the owner (R1 *Analyze the response, then choose which changes to apply.*, R2 *Other changes (each box is a single change applied as a set)*,
R3 *(listed before/after the link to %s) ... it applies only to the years before this link takes effect*, R4 *conflicting change(s)*, R5 *depend on one of these*); R6-R10 as proposed.
All ten are **done**. The Hebrew is **complete**: `po/he-local.po` has the 378 texts of the catalog, none missing and none obsolete (the 72 obsolete were removed, the 120 new or changed
were translated with the words of `docs/GLOSSARY_HE.md`; one existing text that named the button was changed to the new name of the button). The check of completeness
(`PLACECOMPLETER_FINAL_TRANSLATION=1`) passes.

## The revision of the English by the owner (300 of the 378 texts)

Applied as written (`placecompleter-en-edit_revized.po`, read from the .po and the .mo: the same 300 changes, none fuzzy or empty), with these corrections that the program needed:

| What | Why |
|---|---|
| *no model could be chosen* (engines.py) | the new text put the values in another order than the arguments (the config path where the engine id belongs): the order is restored and the example of `engines.json` kept |
| *new link placed before the existing link* (session.py) | the new text said that Gramps *evaluates hierarchy links chronologically*: Gramps uses the first link in the list that fits the date. Corrected |
| *API key missing* (engines.py) | the new sentence did not join with the piece about the environment variable (`... or configure export environment variable X; or in /path`): reworded |
| the readiness of a key file (engines.py) | the program chose between two messages by looking for English words inside the other message: it looks for the command `chmod 600` now |
| warnings (red) in the window (session.py, rules.py) | they were recognised by the first English words of a note (`the chain ends`, `DISAGREES`): they come from the registry of the notes now (`rules.warning_starts()`), so a change of the English can no longer turn a warning into information; the note of a saved answer begins `CONFLICTS WITH SAVED RESPONSE` |

About 190 expectations in the tests (they check English texts) were changed to the new words. Hebrew: the entries were kept with their new English; three hints whose number of lines changed were translated again.

### Open points for the owner (nothing is lost: each is one change in the next round of the PO file)

1. **Explanations that the new English no longer gives** (the Hebrew still has them): *an event before that would show ? instead of this name* (the period given to a name); *Gramps uses the first link that fits the date* (moving a link); *the type already says what the longer name says* (renaming); *the answer says it is that* (change of a type); *rename it if you want* (a level made a place of its own); *nothing that exists is changed* (a second link kept); *it never shows the key / run the engines command* (a refused key); *a Hebrew keyboard or a direction mark* (a pasted key); *add them as links of the place if they are* (sites that may be official); the examples *Brooklyn -> New York* (Region hint) and *zh* (Wikipedia languages).
2. **Words that are not those of Gramps or of the rest of the interface:** *entity* (10 texts: *Select target entity*, *place entity*), *tier* (3), *query* and *prompt* (the rest of the interface says *question*), *hierarchy link*, *administrative place type* (Gramps says *type*), *homonymous*, *daemon*. The word of Gramps is *place*, *level*, *type*.
3. **Texts that read awkwardly when the program joins them:** *Key saved in system keyring (encrypted via system keyring)*; *Set missing coordinates for X: ... (from AI response: verify accuracy (coordinates may deviate slightly))* (two brackets); *rejected API key authentication sent (sk-ant-…, 25 characters)*; *Select target entity (excluded until resolved)*.
4. The Hebrew keeps the explanations of point 1; if the English stays short, the Hebrew can be shortened to match.

## How the English and the Hebrew are corrected in Poedit

`python3 tools/po_exchange.py make` writes two files: `placecompleter-he.po` (each English text and its Hebrew, edited in the translation box) and
`placecompleter-en-edit.po` (each English text and, in the translation box, the same English, which is changed there where the English is to be corrected).
Each text has the places where it is used and, where the code says it, what each `%s` stands for. `python3 tools/po_exchange.py check FILE ...` checks a file
that came back: a lost `%s`/`%d`, a lost line break, a space added or removed at an end, an empty or fuzzy text; for the English file it lists the texts that were
changed. The corrections are then carried to the code (the English), to `po/he-local.po` (the Hebrew, which follows its English text), and to the tests.

## To change (the English), for approval (kept for the record)

| # | Text (number) | Problem | Proposed text |
|---|---|---|---|
| R1 | the hint of the gramplet (104): *After the AI's answer is analyzed, the addon will complete or correct the data as needed.* | says the opposite of the rule of the project: nothing is written without the user's approval | *After the answer is analyzed, you choose which changes to apply.* |
| R2 | the title of the list (7): *Additional Changes (each box represents a change: steps are applied all together or not at all)* | Title Case in an interface of sentence case; long | *Other changes (each box is one change: its steps are applied together or not at all)* |
| R3 | the notes of the direct links (119-122): *... ahead of the link to X: it can be kept only for the years before* and *... after the link to X: it can be kept only for the years before* | *ahead of* and *after* are the order in the list of links, not time, and *after ... years before* reads as a contradiction | *... (listed before the link to X): it can be kept only for the years before that link starts* and *(listed after ...)*; in 121-122 *(listed before/after its link to X) and for all the years of that link* |
| R4 | the summary (55) and the hint (237): *change(s) that decide the same thing differently from another* | awkward | *change(s) that conflict with another change (check one or the other)* |
| R5 | the summary (56): *change(s) that need one of those* | unclear what *those* are | *change(s) that depend on one of those* (to be checked against the window) |
| R6 | the skipped steps (91): *%d will be skipped: %s* | what is skipped? | *%d change(s) will be skipped: %s* |
| R7 | (32) *Which place is it?* and (33) *Which place?* | two texts for one question | one text: *Which place is it?* |
| R8 | (332) *... off by some kilometres* | British spelling: the rest is American (analyze, neighborhood) | *kilometers* |
| R9 | (298) *Asking %s (%s) about «%s» on %s...* | three dots; the rest use the character … | `…` |
| R10 | 9 texts with `%r` (117, 204, 211, 257, 258, 259, 261, 280, 356) | the program shows Python quotes (`'Blagnac'`, or `"L'Aquila"`, or `'\u200f...'` for a name with a direction mark), the rest of the texts use «...» | `«%s»` (a change at the call site as well as in the text) |

## Not changed, and why

| What | Why |
|---|---|
| 25 texts that are pieces of a sentence joined by the code (the date words *before / after / from / to*, `; %d skipped`, ` and put it in the hierarchy` ...) | a translator must keep the space or the punctuation at their ends. They are listed for the translation. Rewriting them as whole sentences is worth doing only where the Hebrew breaks |
| 46 texts with three or more unnamed placeholders (`%s %s %s`) | Hebrew word order may need a different order. Python cannot reorder `%s`; only named placeholders (`%(name)s`) can be. During the translation, each text that cannot be written in the same order becomes a named one; the others stay |
| `->` in the notes of links | in a right-to-left sentence the mirrored `>` points the right way; the arrow character `→` would point the wrong way |

## The Hebrew

- The catalog: 379 texts. In `po/he-local.po`: 265 current, **114 new or changed** (to translate), **65 obsolete** (to remove).
- The words of Gramps (Place *makom*, Repository *ma'agar*, Citation *movaa*, Confidence *vada'ut*, Enclosed By *mukhal betokh* ...) are in `docs/GLOSSARY_HE.md`, read from the
  catalog of Gramps itself (6.0.8 and 6.1 agree on all of them).
- Order of the work: the approved changes of the English, the template made again, the 65 obsolete texts removed, the 114 translated with the glossary, then the check of completeness
  (`PLACECOMPLETER_FINAL_TRANSLATION=1`) and a look at the window in Hebrew.
