# Which rules do we really need? (a review after the form "table")

The first idea was small: ask an AI for the type of a place, its levels and its coordinates, and write them to Gramps instead of typing them.
The rules of `ANALYZER_RULES.md` grew around that idea because the answers of the AI were free text and the tree has data of the user.
The form `table` (Table 10) asks for a table; some of the rules may no longer be needed. This file says how we find out, not what to remove.

## The groups (a first sorting; the evidence decides)

| Group | Rules | What it protects | Decision |
|---|---|---|---|
| A. Safety of the tree | P0 (what exists is changed one by one), T1-T5 (no loop, no place inside a place of its own type), C1, C2, C4 (a link is added before an old one, nothing is touched), the stale checks of the writer, Undo, a type of the user's own is never changed | the data of the user | **keep**, whatever the evidence |
| B. Making up for a free-text answer | ST1-ST6 (the closed list for the type: the question says it now), LV1 (overlapping structures), TB5 (years written backwards), the word lists `SETTLEMENT_TYPES` and `CONTAINER_TYPES`, "listed twice as a level and as the state", "the chain ends at the state with no country above it", "the first level is the parent" (Sissa), the name periods that are inferred, "the answer contradicts itself", `compare_with_saved`, the echo test and the five forms | a bad or loose answer | **test** with the replay (below) |
| C. Correcting links that exist | C3, C5, C6, C7 (a period, a disconnect, a cut), `rename-place`, `set-name-language` | an untidy tree | **test**: they fire on the tree, not on the answer |
| D. More than the first idea | LK1-LK5 (web links), CT1-CT5 (citations and their routing), Table 7 (Wikidata links), the Wikidata look-up of coordinates, the languages of Wikipedia | extras | **the user decides** whether they stay |

## The method

1. **Collect answers of the form `table`**, about 20: by hand in the window with the engine `manual` (the answers are saved in
   `~/gramps-place-work/answers`, and the window overwrites an answer of the same place and year: move the old folder aside first), or with no
   one at the keyboard: `python3 tools/collect_answers.py` asks an engine with a key (Claude, OpenAI or Ollama) the table question for a list of
   places and keeps the answers in `~/gramps-place-work/answers-table`, without touching the old ones (`--check` says whether the engine is
   ready, `--dry-run` prints the questions, `--report --db SNAPSHOT` also writes the two reports of step 2). Places that are not alike: France (Aussonne 1997, Blagnac 2026, Toulouse, Paris 1980), Italy (Parma 1990,
   Sissa 1990), Hungary, Serbia, Romania (Bajmok 1877, Hadad 1900, Zombor 1850), Israel (Kfar Hess), the USA (Johnston 1950, which is ambiguous),
   a very small village, a very large city, a place whose name changed, a place whose state changed.
2. **Replay them, read-only**, against the snapshot (the rules about places that exist only fire with a tree):
   `python3 tools/replay_answers.py --db PATH-TO-THE-SNAPSHOT-SQLITE`
   It prints which proposals and which messages (each message is a rule) fired, in how many answers, and writes a table.
3. **Read the result with three questions for every rule of groups B, C and D:**
   - did it fire at all, and in how many of the answers?
   - when it fired, was what it did right?
   - what happens without it: **data lost or wrong data** (keep it), or only an extra note or a proposal nobody needed (it can go)?
4. **A rule is removed only when** it never fired, or fired in fewer than one answer in twenty, **and** its absence cannot damage the tree.
   A rule that protects the data stays even if it never fires: a rare danger is still a danger.
5. **What is removed goes in steps**, each a separate installer with the tests that go with it, so that any step can be undone.

## The switches (`placecompleter/rules.py`)

Every rule has an id and can be switched off, for an experiment only; nothing here is a setting of a user. With every rule on (the usual state)
nothing changes. The list is in `rules.py`:
- the behavior rules of the answer and the extras: ST3, ST6, LV1, LV2, LV3, LK, WL, CT2, CT4, CT5;
- the rules of the periods of names: NP1, NP3, NP5 (a name's years end it only when a later name is given; a name starts when the state began; a name
  of a level gets the answer's period, off by default). NP2, NP4 and NP6 were removed (Table 12 of ANALYZER_RULES.md);
- the rules of the nesting and of the links: T1, T2 (T2-T4), C3, C4, C5, C6 (C6 and C7), C8;
- ID1 (a place of the tree with the name but far from the answer is another place) and NL (the language of the names of levels);
- the rules that are OFF by default (`DEFAULT_OFF`: NP5 and NL): switched on with `PLACECOMPLETER_RULES_ON=NP5,NL`; `--ablate` tries them ON;
- the notes of the analysis, M01-M49, one rule each (a test checks that every note belongs to a rule);
- the rules that cannot be switched, listed so that the list is complete: P0 (what exists is changed one by one), C1-C2 (the chain is made and
  linked; a link as the answer says is left alone), C9 (a level the user unchecked is not touched).
A test shows each of the rules of the second and third lists through an existing test of the program: with the rule on the test passes, with the
rule off it fails.

- `python3 tools/replay_answers.py --db SNAPSHOT --ablate` switches the rules off one at a time over the saved answers and prints, for each, how many
  answers change in what would be proposed and in the notes. A rule that changes neither is a rule these answers never needed; a rule that changes
  only the notes is information (or noise), not data.
- `--without M20,LV1` switches rules off for a whole run of the normal report.
- `PLACECOMPLETER_RULES_OFF=M20,LV1` does the same for any run of the program.
- WL, CT2, CT4 and CT5 act on Wikidata and on the writing, so the replay cannot measure them: they are seen by writing to a database
  (`test_rules.py` shows each).

When the review decides to remove a rule, the switch is the first step (switched off, the tests and the answers say what changes), and the code
of the rule goes after that, in one installer for all of them.

## What the replay cannot tell

- It counts the rules that fire on the answers we have. A rule against a mistake that an AI makes once in a hundred answers will not show up in twenty.
- A rule that "never fired" may protect a case that is not in our answers. Group A is therefore never removed by this method.
- The AI of another day can answer differently: the review should be repeated after a few months of real use.
