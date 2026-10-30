# Rules of the analysis of the hierarchy

What the analysis does with the administrative hierarchy of a place, in tables, so that every rule can be read, criticised and tested.
Each row names the test that proves it. **Phase 1** is in the addon; **phase 2** (the completion of data, the distance and coordinates rules) is not yet.

## Principle P0: changes to what exists

| Kind of change | Example | Chosen by itself? |
|---|---|---|
| An addition | a new place, a new link, an alternative name | yes |
| The filling of an empty field | coordinates, language of a name, type | yes |
| **A change to data that exists** | a link disconnected, a period changed, a place renamed | **no: one by one**, with an explanation |
| The button "Select all" | | an act of the user, one button that toggles: it chooses **everything that can be chosen, changes to what exists too** (with the steps that these need, a bundle whole); left for the user: a change in CONFLICT with the tree, a web link of a site of unknown kind, and a change that has a **rival**; pressed again ("Clear all") it unchecks everything, what was checked by hand too |

A **rival** is another proposal that decides the same field of the same place in a different way (two periods for one name, two coordinates, two types): one or the other, never both. Checking one by hand unchecks the other. The same decision twice is not a rivalry. Tests: `test_existing_data.py` (SelectAllButtonTests).

A disconnect needs the new link that replaces it: choosing the disconnect chooses the new link; unchoosing the new link unchooses the disconnect.
Tests: `test_existing_data.py`.

## Table 1: the level of a type

| Level | Types | Note |
|---|---|---|
| 1 | Country; the custom empire and monarchy of the tree | |
| 2 | State, County, Province, Region, Department, District; the custom province, district, canton, járás ... of the tree | |
| 3 | Municipality | contains settlements |
| 4 | City, Town, Village, Hamlet; the custom `settlements` of the tree (kibbutz, moshav ...) | an open list: the conventions of the tree (`~/.config/placecompleter/type-conventions.json`, see the developer guide) |
| 5 | Neighborhood, Borough | |
| 6 | Street | |
| 7 | Number, Building, Farm | |
| none | Parish, Locality, an unknown or custom type with no level | no rule applies (T5) |

Tests: `test_levels.py` (LevelTests).

## Table 2: what may be inside what (every link: existing or proposed)

| # | Rule | Exception |
|---|---|---|
| T1 | a place is not inside itself, and there is no loop | |
| T2 | the parent is on a higher level than the place | a country inside a country (federations) |
| T3 | a place is not inside a place of its own type (a city in a city, a province in a province) | countries |
| T4 | settlements (level 4) are on one level: none is inside another | |
| T5 | a type with no level has no rule | |

An area of level 2 may be inside another area of a different type (a county in a state, a district in a province).
Tests: `test_levels.py` (RuleTests).

## Table 3: a link in the tree is wrong

A link is **wrong** when it breaks T1-T4, or when its parent is a settlement with the same name as the area that the answer means (Parma the city, Provincia di Parma),
**at any time**, and the answer names another parent. A link that is only different (another province) is **not** wrong.
Tests: `test_real_answers.py` (SissaMovedTests).

## Table 4: what is done (phase 1)

| # | Situation | Action | Chosen? |
|---|---|---|---|
| C1 | no link to the parent | the chain of the answer is made and linked | yes |
| C2 | the link is as the answer says | nothing (one line: "These links already exist") | |
| C3 | the same parent, a period that ends before it starts | a change of the period to the answer's | no |
| C3b | the same parent, the answer is wider and nothing else claims the years | the period is widened | no |
| C4 | a link to another parent that is not wrong | the link of the answer is added **before** it; the old is not touched | yes |
| C5 | a link that is wrong | a **disconnect** (a separate change; needs the new link) | no |
| C6 | a direct link to a higher place of the chain, standing first, all its years covered | a disconnect | no |
| C7 | the same, with years of its own | a cut to those years | no |
| C8 | a level of the answer that breaks T1-T4 | the level is left out, a note, the next level is linked to the same place | |
| C9 | a level that the user unchecked | its place is not touched | |

Tests: `test_real_answers.py` (MessyLinksTests), `test_writer.py` (real database), `test_ingest.py`.

## Table 5: the web links of a place (phase 2, the module is written, not yet joined to the window)

A link of a place is a statement about the place itself. The addresses of the `SOURCES` lines are sorted by `placecompleter/links.py`; whatever is not a link may still be cited.

| # | Rule | Chosen? |
|---|---|---|
| LK1 | Wikipedia and Wikidata (any language, mobile or desktop form) | yes (an addition) |
| LK2 | an address of the shape of an official site (`.gov`, `comune.*`, `*.admin.ch`, an archive ...) | yes, marked "likely official" |
| LK3 | any other address: offered with the note "choose it only if the site is official" | **no**: the user decides |
| LK4 | tourism, hiking, booking, advertising, shops, social sites and the like (by the name of the site or a word in the address) | never a link (it may be a citation) |
| LK5 | the limits: 1 Wikidata; **1 Wikipedia article per language that the user chose** (a setting: a list in the order of preference, default the language of Gramps and then English); English only when none of the chosen languages has an article; 2 other sites; the total is the sum, **the links that exist count**. The article of a chosen language is taken from the sitelinks of the Wikidata entity when the answer has none (an address is never guessed). The same page in another form (http/https, www, mobile, a fragment, tracking) is the same link | |

When the total is full, the less important is left out: Wikidata, Wikipedia, likely official, other.
Tests: `test_links.py`.

## Table 6: the citations of what is written (phase 2)

| # | Rule |
|---|---|
| CT1 | each place that is written gets a citation to each source of what was written to it, in the same transaction (one Undo) |
| CT2 | at most **3 new citations per place in one run**, the strongest first: the higher confidence; then Wikidata, Wikipedia, an official site, any other site, a tourism or commercial site; then the page cited for more fields. What the limit leaves out is said in the message after Apply |
| CT3 | a source that the tree has is used again, **the same page in another form** (http/https, www, mobile, a fragment) included; a place that has a citation to that page with that text gets none, and it does not count for the limit |
| CT5 | **a citation goes to the place that its source is about**: a page whose title is the name of a place written in the same run (an article `Parma` -> Parma, `Provincia di Parma` -> Provincia di Parma; after a comma is a qualifier: `Johnston, Iowa` is Johnston; names are compared without case, accents or punctuation) is cited on that place only. A page about none of them is cited on the main place. A page about a place of the chain that this run does not change is cited nowhere. A statement of Wikidata stays on the place it was made for. Without the main place (a plan applied from the command line) the old rule holds: every place touched gets the sources of its own proposals |
| CT4 | a tourism, commercial or social site is still cited when the answer rests on it, but its confidence is never above **Low**, and the note says why |

Tests: `test_citations.py`.

## Table 7: the web links that Wikidata gives (phase 2)

When Wikidata is asked about the **main place** (it lacks coordinates), the link to its Wikidata item and the Wikipedia articles that the item lists in the languages of the user are offered by the rules of Table 5 (the basis is `evidence`: independent data). An address is taken from the sitelinks of the item, never made up. No other place of the chain gets links. Only the names of places are sent to Wikidata, as before.
Tests: `test_geo.py` (ArticleTests, LinksFromWikidataTests).

## Table 8: the type of the place itself (the lowest level)

The question asks for the SIZE CLASS of the settlement, as ONE word of a closed list, and keeps the legal status out of it. Tests: `test_settlement_types.py`.

| # | Rule |
|---|---|
| ST1 | the list is `metropolis`, `city`, `town`, `village`, `hamlet`, `neighborhood`, `locality`, with anchors in inhabitants of the settlement itself (over about 500,000; 30,000-500,000; 2,000-30,000; 100-2,000; under 100), judged IN the year of the question, relative to the country and period in earlier centuries |
| ST2 | the types of Gramps: metropolis and city = City, town = Town, village = Village, hamlet = Hamlet, neighborhood = Neighborhood, locality = Locality. A rule of the tree (the conventions file of the tree: `~/.config/placecompleter/type-conventions.json`, whole words of the whole answer) comes first: a metropolis can be given a type of its own, and so can a moshav or a kibbutz |
| ST3 | a bare word of the list decides; what follows the bar (the local term) cannot change it: `village | commune` is a Village, whatever the commune is in law |
| ST4 | the legal status (commune, municipality, comune ...) is not an answer to this question; where it is wanted it is a note of the place (not written yet) |
| ST6 | a place that **exists** keeps its type, except when all of these hold: the answer is one bare word of the list; the type of the tree is a built-in settlement type (City, Locality, Borough, Municipality, Town, Village, Hamlet; never a type of the user's own, never a province or another area); and it differs. Then a **change of type** is proposed: a change to data that exists (P0), not chosen by itself, chosen by the "Select all" button or one by one, with the confidence of the field |
| ST5 | an answer of the old kind (a longer text, a word that is not in the list) is read as before, so that saved answers keep their types |

The levels above the place (the unit types of `CONTAINERS`) are a different question, not covered here.

## Table 9: levels and places that share a name

| # | Rule |
|---|---|
| LV1 | a structure that **overlaps** the levels without being inside one (an intercommunality, a French métropole of the EPCI kind) is not a level of the chain: its line is left out and the screen says so. The question asks for divisions that nest. A "metropolitan city" that is a real level (Italy) is kept |
| LV2 | two levels, or a level and the place itself, with one name and different types (a canton named like the commune that is its seat) are **two places**, each with a key of its own; the screen says that the level has the name of the place. The same name with the same type is one place |
| LV3 | when the answer is a settlement, an area of the tree with the same name (a canton, a province, a county, a type of the user's own that is not a settlement) is **not a candidate** for the place of the question: the window does not ask which one when only one candidate is a settlement |

Tests: `test_same_names.py`.

## Table 10: the form "table" of the question (TB1-TB7)

A short question (about 2,000 characters) whose answer is one table, easy to read by eye and by the program. Tests: `test_table.py`.

| # | Rule |
|---|---|
| TB1 | the form `table` is the **first** of the automatic order (table, classic, short, dated, long): the older forms stay as the way back when an AI does not answer or gives the question back |
| TB2 | the question asks for two lines (`Name | Language | From | Source`, `Alternatives`) and a table `Category | Value/Name | Year Range | Level Type | Explanation | Source` with the rows Place Type, Level 1 ... N, Sovereign state, Latitude, Longitude. The type of the place is ONE word of the closed list with anchors (Table 8); the type of a level is a word of a closed list, or `other (the local term)`; the legal status is written only in the explanation |
| TB3 | the answer is read as it is copied: tab separated, or with bars as in Markdown; the columns are found by the names in the header, the rows by the first column. It is turned into the labelled lines of the core, **so that everything after it is the same for every form**; the answer that is saved is the converted text |
| TB4 | what the answer gives and is not written is **said**: a site that is not the address of a page (it cannot be cited), a name "from" a year, other places of the same name (ask again with the region), a level without a type. Nothing of it reaches the tree |
| TB5 | the years are written as the core reads them: `YYYY-present`, `YYYY-YYYY`; a range written backwards by a right-to-left page (`-1800 present`) or with a word in another language is read; no years is `UNKNOWN` |
| TB6 | the type of a level is the generic word (`department`, `district` ...) or the local term of `other (...)` (`canton`), which the rules of the tree turn into a type of its own |
| TB7 | the explanation is asked in the language of Gramps (its ISO code), in English when it is not known |

## Table 8b: a place of the tree that is not a settlement (note M51)

| # | Rule |
|---|---|
| ST6 (empty type) | **a place with no type is given the type of the answer** (`set-type`). In Gramps two types show as an empty field in the Type column: Unknown (value -1) and a type of the user's own with an empty text (value 0, CUSTOM): `kinds.has_no_type` says yes to both (the type of the place, of a level, the guard of the writer, the gramplet). The addon had counted only Unknown, so a place with the blank custom type (for example one made by an import or by an older version) got no proposal and the screen said nothing |
| ST6 (note) | when the answer gives a settlement class (`town`, `city` ...) and the place of the tree has a type that is **not a settlement and not unknown** (an area of Gramps such as District or Province, a canton, or a type of the user's own that is not in the list `settlements` of `type-conventions.json`), the type is **not changed** and the screen **says so**: the place may be the canton or the province of the same name (another place), or the town itself typed wrongly. Before this note the screen was silent and nothing was proposed. Switch: `M51`. Tests: `test_type_notes.py` |

## Table 11: the place of the tree that is not the place of the answer (ID1) and the rules that are off by default

| # | Rule |
|---|---|
| ID1 | a place of the tree with the name of the answer **and coordinates** that is more than 30 km from the coordinates of the answer is **another place with the same name** (Johnston in Iowa and Johnston in Rhode Island, 1,600 km apart): it is not changed, the place of the answer is a new place, and the screen says so. The names of the places above are NOT compared: one place has many names in the languages and the periods of the Banat, and a rule on them would refuse the right place. A place with no coordinates, or an answer with none, cannot be compared: it is taken as before. Of two places of the name, the near one is taken without asking |
| NP5, NL | **off by default**: the period (NP5) and the language (NL) of an existing name of a LEVEL are not offered. They were half of all the proposals on the answers of the form `table` and are not part of the first idea (type, levels, coordinates). The name of the place itself keeps its language and its period. `PLACECOMPLETER_RULES_ON=NP5,NL` switches them on |

Tests: `test_identity.py`, `test_defaults.py`.

## Table 12: what the review removed (from the 55 answers of the replay: 35 of the older forms, 20 of the form `table`)

Removed: three rules, and fifteen notes. The data: none of them fired on the 20 answers of the form `table` (the rules of the names), or they fired on every answer and changed nothing (the noise).

| Removed | What it did | Why |
|---|---|---|
| NP2 | a name starts the day after the last former name in the answer ended | needs a list of other names, which the table does not give; names in other languages are "nice, not required" |
| NP4 | a name of the tree that starts after the state began is offered an earlier start | 0 of 55 answers; an optional improvement of a name |
| NP6 | the other names of the answer are added to the place with their periods | not part of the first idea (type, levels, coordinates) |
| M06, M07, M08, M44 | the remarks, the notes, the doubts and the "not sure" of the AI | the table has no field for them |
| M09, M10, M11, M12, M13 | notes about the other names, about a contradiction with them, about a source without a link | they depended on the other names |
| M24, M27, M41, M26 | notes of the removed rules, and the note of the plain name of a new place | the removed rules; 0 of 20 |
| M20 ("the state is listed twice"), M45 ("sources listed by the answer") | noise: on every answer, changed nothing | the sources are in the evidence of each proposal |

**Kept although the review proposed them**, because each explains a rule that protects the tree, and a rule whose reason is not said is a rule that is distrusted: NP1 (a name period is not ended by the years of the municipality of the same name: it protects the end date of a name), the notes M15 and M17 (a level that the user left out), M16 and M19 (the window asks which place), M21 (a level that is not valid on the date), M22 (LV2), M28 (C8), M30, M31, M33, M35, M37 (links), M23 and M40 (NP1), M43 (the chain has no country), M46 and M47 (the table), M02-M04 (the command line, until the old parser goes).

Not removed yet: the parser of the older forms of the answer and the older forms of the question (`classic`, `short`, `dated`, `long`): they go when the form `table` has been tried on other AIs.

## Phase 2 (agreed, not yet written)

| What | Rule |
|---|---|
| Completion | web links (Table 5), at most 3 citations per place and run (the strongest first, an existing source is reused), one place note per run (DIFFERS_FROM_TODAY and the answer's notes, not repeated): added when missing, without duplicates |
| Coordinates | an empty field is filled; a different position is a change to what exists (not chosen) when Wikidata matches the place with certainty, or the answer is certain |
| Distance | a place far from its parent compared with the other children of that parent: a note |
