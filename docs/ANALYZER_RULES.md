# Hierarchy Analysis Rules

These tables describe how the analysis handles the administrative hierarchy of a place. Every rule is written down so that it can be read, questioned and tested. Each table names the tests that check it.

**Terms.** In Gramps, a place that has other places inside it **encloses** them, and they are **enclosed by** it (these are the tabs *Encloses* and *Enclosed By* of a place). In these tables, the place that encloses another place is called its **parent**, and the place that it encloses is its **child**.

**Phase 1** (the hierarchy) is in the addon. **Phase 2** is partly done: the web links, the links from Wikidata and the citations (Tables 5, 6 and 7) are also in the addon. What is still to be done (place notes, changes to coordinates that already exist, and distance notes) is agreed but not yet written: see the last section.

## Principle P0: Changes to Existing Data

**Nothing is checked for you.** When the proposals appear, no change is checked. You check the changes you accept, one by one or with the **Select all** button.

| Change type | Example | Included by **Select all**? |
|---|---|---|
| An addition | A new place, a new link, an alternative name | Yes |
| Filling an empty field | Coordinates, the language of a name, a place type | Yes |
| **A change to data that already exists** | A link that is disconnected, a period that is changed, a place that is renamed | Yes, unless it conflicts with the tree or has a rival (see below). A change that is left out must be checked one by one, and it comes with an explanation. |

**Select all** is a deliberate action of the user. It is a single button that works as a toggle. It checks every change that can be checked without a decision from you, including changes to existing data, together with the steps that these changes depend on (a change made of several steps is always checked as a whole). It leaves three kinds of change for you to decide one by one:

1. a change that **conflicts** with the tree (for example, a change that would replace a different date);
2. a web link to a site of an unknown kind;
3. a change that has a **rival**.

When you press the button again (it then reads **Clear all**), it unchecks everything, including the changes that you checked by hand.

A **rival** is another proposal for the same field of the same place that gives a different value. Examples: two different periods for one name, two sets of coordinates, or two different place types. Only one of them can be selected, never both. When you check one by hand, the other is unchecked. The same decision proposed twice is not a rivalry.
Tests: `test_existing_data.py` (`SelectAllButtonTests`).

A disconnect always comes with the new link that replaces it. Checking the disconnect also checks the new link, and unchecking the new link also unchecks the disconnect.
Tests: `test_existing_data.py`.

## Table 1: The Level of a Place Type

| Level | Place types | Note |
|---|---|---|
| 1 | Country; the custom types of your tree for an empire and a monarchy | The highest level |
| 2 | State, County, Province, Region, Department, District; the custom types of your tree for a province, a district, a canton, a járás, and so on | |
| 3 | Municipality | Encloses settlements |
| 4 | City, Town, Village, Hamlet; the custom settlement types of your tree (kibbutz, moshav, and so on) | An open list. It comes from your conventions file (`~/.config/placecompleter/type-conventions.json`; see the developer guide) and from the custom types that your tree uses (`typelearn.py`). |
| 5 | Neighborhood, Borough | |
| 6 | Street | |
| 7 | Number, Building, Farm | |
| None | Parish, Locality, and any unknown or custom type that has no level | No rule applies (T5) |

Tests: `test_levels.py` (`LevelTests`).

## Table 2: What May Enclose What (for Every Link, Existing or Proposed)

| # | Rule | Exception |
|---|---|---|
| T1 | A place cannot enclose itself, and the links cannot form a loop. | |
| T2 | The parent must be on a higher level than the place. | A country may enclose another country (federations) |
| T3 | A place cannot be enclosed by a place of the same type (a city cannot enclose a city, and a province cannot enclose a province). | Countries |
| T4 | All settlements (level 4) are on the same level: no settlement encloses another settlement. | |
| T5 | A type that has no level is not subject to these rules. | |

An area of level 2 may be enclosed by another area of level 2 of a different type (for example, a state can enclose a county, and a province can enclose a district).
Tests: `test_levels.py` (`RuleTests`).

## Table 3: When a Link in the Tree Is Wrong

A link in the tree is **wrong** in either of these cases:

- it breaks rule T1, T2, T3 or T4;
- its parent is a settlement that has the same name as the area that the response means (for example, the city *Parma* instead of the province *Provincia di Parma*), **and** the response names a different parent. Such a link is wrong for every date.

A link that only differs from the response (for example, another historical province) is **not** wrong.
Tests: `test_real_answers.py` (`SissaMovedTests`).

## Table 4: What the Analysis Does with Links (Phase 1)

The last column says whether the action is an addition or a change to existing data (see P0).

| # | Situation | Action | Change type |
|---|---|---|---|
| C1 | The tree has no link to the parent. | The whole chain from the response is created and linked. | Addition |
| C2 | The existing link is exactly as the response says. | Nothing is done. The screen shows one line: *"These links already exist"*. | |
| C3 | The parent is the same, but the period of the existing link is inverted (it ends before it starts). | The period is replaced with the one in the response. | Change to existing data |
| C3b | The parent is the same, the period in the response is wider, and no other link claims the extra years. | The period is widened. | Change to existing data |
| C4 | The tree links the place to another parent, and that link is not wrong. | The link from the response is added **before** the old link. The old link is not touched. | Addition |
| C5 | The tree has a link that is wrong (Table 3). | A **disconnect** is proposed. It is a separate change, and it needs the new link. | Change to existing data |
| C6 | The place is also linked directly to a higher place of the chain, and the link from the response covers all the years of that direct link. | The direct link is disconnected. The note on the screen says whether it comes before or after the new link. | Change to existing data |
| C7 | Like C6, but the direct link also has years that the new link does not cover. | The direct link is cut down to those years. | Change to existing data |
| C8 | A level in the response breaks one of the rules T1 to T4. | The level is left out, a note explains why, and the next level is linked to the same place. | |
| C9 | You unchecked a level in the list of retrieved levels. | The place of that level is not touched. | |

Tests: `test_real_answers.py` (`MessyLinksTests`), `test_writer.py` (tests on a real database), `test_ingest.py`.

## Table 5: Web Links of a Place

A web link of a place is a statement about that place itself. The addresses in the `SOURCES` lines of the response are sorted by `placecompleter/links.py`. An address that does not become a link may still be used as a citation.

| # | Rule | Included by **Select all**? |
|---|---|---|
| LK1 | Wikipedia and Wikidata pages (any language, mobile or desktop form). | Yes (an addition) |
| LK2 | An address that looks like an official site (`.gov`, `comune.*`, `*.admin.ch`, an archive, and so on). | Yes, marked *"likely official"* |
| LK3 | Any other address. It is offered with the note *"choose it only if the site is official"*. | **No**: you decide |
| LK4 | Tourism, hiking, booking, advertising, shopping and social sites, and similar ones (found by the name of the site or by a word in the address). | Never a link (it may still be a citation) |
| LK5 | The limits, for each place (see below). | |

**LK5, the limits for each place.** A place can have at most:

- one Wikidata link;
- one Wikipedia article for each language you selected;
- two other sites.

The links that the place already has count toward these limits. Your languages are a setting: a list in order of preference. The default is the language of Gramps, then English. English is used only when none of your languages has an article. If the response has no article in one of your languages, the article is taken from the sitelinks of the Wikidata item (an address is never guessed). The same page in another form (http or https, `www`, a mobile address, a fragment, tracking parameters) counts as the same link.

When the limit is reached, the least important links are dropped first. From the most important to the least important, the order is: Wikidata, Wikipedia, likely official sites, other sites.
Tests: `test_links.py`.

## Table 6: Citations for What Is Written

| # | Rule |
|---|---|
| CT1 | Each place that is written (created or changed) gets a citation for each source of what was written to it. The citations are made in the same transaction, so one Undo removes them together with the changes. |
| CT2 | A place gets **at most 3 new citations in one run**. When more than three sources compete, the strongest are kept. A source is stronger than another according to these criteria, in this order: (1) its confidence is higher; (2) its kind ranks higher: Wikidata, then Wikipedia, then official sites, then other sites, then tourism or commercial sites; (3) it is cited for more fields; (4) it comes first in the response. The message shown after Apply says which sources were left out. |
| CT3 | A source that the tree already has is used again, even when the page is written in another form (http or https, `www`, mobile, a fragment). A place that already has a citation to that page with the same text gets no new citation, and this does not count toward the limit of three. |
| CT4 | A tourism, commercial or social site is still cited when the response relies on it, but its confidence is never higher than **Low**, and the note on the citation says why. |
| CT5 | **A citation goes to the place that its source is about.** If the title of a page is the name of a place that is written in the same run, the page is cited on that place only. For example, an article titled `Parma` is cited on Parma, and `Provincia di Parma` on Provincia di Parma. Text after a comma is a qualifier: `Johnston, Iowa` is Johnston. Names are compared without case, accents or punctuation. A page that is about none of these places is cited on the main place. A page about a place of the chain that this run does not change is cited nowhere. A statement from Wikidata stays on the place it was made for. When there is no main place (for example, a plan applied from the command line), the old rule applies: each place that is touched gets the sources of its own proposals. |

Tests: `test_citations.py`.

## Table 7: Web Links from Wikidata

When Wikidata is asked about the **main place** (because it has no coordinates), the addon offers the link to its Wikidata item and the Wikipedia articles that the item lists in your languages. The rules of Table 5 apply (the basis is `evidence`: independent data). The addresses come from the **sitelinks** of the Wikidata item and are never invented. No other place in the chain gets these links. As before, only place names are sent to Wikidata.
Tests: `test_geo.py` (`ArticleTests`, `LinksFromWikidataTests`).

## Table 8: The Type of the Place Itself (the Lowest Level)

The question asks for the **size class** of the settlement, as **one word** from a closed list. It keeps the legal status out of the answer.
Tests: `test_settlement_types.py`.

| # | Rule |
|---|---|
| ST1 | The closed list is `metropolis`, `city`, `town`, `village`, `hamlet`, `neighborhood`, `locality`. The five size classes follow the number of inhabitants of **the settlement itself**: metropolis, over about 500,000; city, about 30,000 to 500,000; town, about 2,000 to 30,000; village, about 100 to 2,000; hamlet, under about 100. The size is judged for the year of the question. For earlier centuries, the question tells the AI to judge by the settlements of that country and period. A *neighborhood* is a named part of a city or town. A *locality* is a named place that is not a settlement with residents (a station, an estate, a crossing). |
| ST2 | Gramps types: metropolis and city give City; town gives Town; village gives Village; hamlet gives Hamlet; neighborhood gives Neighborhood; locality gives Locality. A rule from your conventions file (`~/.config/placecompleter/type-conventions.json`, which matches whole words of the response) is applied first. With such a rule, a metropolis can get a type of its own, and so can a moshav or a kibbutz. |
| ST3 | A bare word from the list decides the type. What follows the bar (the local term) cannot change it. For example, `village \| commune` is a Village, whatever the commune is in law. |
| ST4 | The legal status (commune, municipality, comune, and so on) is not an answer to this question. Where it is wanted, it will be a note on the place (not written yet). |
| ST5 | A response in an older format (a longer text, or a word that is not in the list) is read as before, so that saved responses keep their types. |
| ST6 | A place that **already exists** keeps its type, except when all of these are true: the response gives one bare word from the list; the type in the tree is a built-in settlement type of Gramps (City, Locality, Borough, Municipality, Town, Village or Hamlet; never a type of your own, and never a province or another area); and the two types differ. In that case a **type change** is proposed. It is a change to existing data (P0): it is not checked at first, and you can check it one by one or with the **Select all** button. It has the confidence of the field. |

The levels above the place (the unit types in `CONTAINERS`) are a different question and are not covered here.

## Table 8b: A Place in the Tree That Is Not a Settlement (Note M51)

| # | Rule |
|---|---|
| ST6 (empty type) | **A place with no type is given the type from the response** (`set-type`). In Gramps, two kinds of type look like an empty field in the *Type* column: Unknown (value -1) and a custom type with empty text (value 0, Custom). `kinds.has_no_type` treats both as "no type" (for the type of the place, for the type of a level, in the safety check of the writer, and in the gramplets). Earlier versions of the addon counted only Unknown, so a place with a blank custom type (for example, one made by an import or by an older version) got no proposal, and the screen said nothing. |
| ST6 (note) | The response gives a settlement class (`town`, `city`, and so on), but the place in the tree has a type that is **neither a settlement nor unknown**. Examples: an area type of Gramps such as District or Province, a canton, or a custom type that is not in the `settlements` list of `type-conventions.json`. In this case the type is **not changed**, and the screen **says so**. The reason may be that the place is the canton or the province with the same name (another place), or that the town itself has the wrong type. Before this note, the screen said nothing and nothing was proposed. Switch: `M51`.<br>Tests: `test_type_notes.py`. |

## Table 8c: A Custom Type That Is New in the Tree (Note M52)

| # | Rule |
|---|---|
| M52 (note) | A proposal (a new place, a type for a place that has none, or a type change) gives a place a **custom type** (value 0, with a text), and **no place in your tree uses that type yet**. In this case the screen says so, once for each type, and names the places that get it (up to three, then `+N`). Types are compared by `typelearn.type_key`, so capital letters, spaces and dashes do not matter. In Gramps, a custom type exists only because places use it, so approving the place is what adds the type to the tree. The note is information only: it does not change anything that is proposed, and it does not check anything for you. A type of Gramps and a blank type are never new. The tree is read (`typelearn.census`) only when a proposal gives a custom type. Switch: `M52`.<br>Tests: `test_new_type_note.py`. |

## Table 9: Levels and Places That Share a Name

| # | Rule |
|---|---|
| LV1 | A structure that **overlaps** the levels without being enclosed by one of them (an intercommunality, a French métropole of the EPCI kind) is not a level of the chain. Its line is left out, and the screen says so. The question asks for divisions that nest: each one is enclosed by the one above it. A "metropolitan city" that is a real level (as in Italy) is kept. |
| LV2 | Two levels, or a level and the place itself, that have one name and different types (for example, a canton named like the commune that is its seat) are **two places**. Each gets its own key, and the screen says that the level has the name of the place. The same name with the same type is one place. |
| LV3 | When the response is about a settlement, an area in the tree with the same name (a canton, a province, a county, or a custom type of yours that is not a settlement) is **not a candidate** for the place in the question. When only one candidate is a settlement, the window does not ask which place you mean. |

Tests: `test_same_names.py`.

## Table 10: The `table` Form of the Question (TB1 to TB7)

The `table` form is a short question (about 2,000 characters) whose response is one table. The table is easy to read by eye and by the program.
Tests: `test_table.py`.

| # | Rule |
|---|---|
| TB1 | The `table` form is the **first** in the automatic order (table, classic, short, dated, long). The older forms stay as the way back when an AI does not answer or gives the question back. |
| TB2 | The question asks for two header lines (`Name \| Language \| From \| Source` and `Alternatives`) and a table with the columns `Category \| Value/Name \| Year Range \| Level Type \| Explanation \| Source`. The rows are: Place Type, Level 1 to Level N, Sovereign state, Latitude, Longitude. The type of the place is **one word** from the closed list (Table 8). The type of a level is a word from a closed list, or `other (the local term)`. The legal status is written only in the explanation column. |
| TB3 | The response is read as it was copied: separated by tabs, or by bars as in Markdown. The columns are found by the names in the header, and the rows by the first column. The table is turned into the labelled lines that the core reads, **so that everything after this step is the same for every form**. The response that is saved (in the `answers` folder) is the converted text. |
| TB4 | What the response gives but the addon does not write is **reported**. Examples: a source that is not the address of a page (it cannot be cited), a name "from" a year, other places with the same name (ask again with a region), a level without a type. None of this reaches the tree. |
| TB5 | Years are written the way the core reads them: `YYYY-present` and `YYYY-YYYY`. A range written backwards by a right-to-left page (`-1800 present`), or with a word in another language, is also read. No years means `UNKNOWN`. |
| TB6 | The type of a level is a generic word (`department`, `district`, and so on) or the local term in `other (...)` (for example `canton`). The rules in your conventions file turn the local term into a type of your own. |
| TB7 | The explanation is requested in the language of Gramps (its ISO code), and in English when that language is not known. |

## Table 11: A Place in the Tree That Is Not the Place in the Response (ID1), and the Rules That Are Off by Default

| # | Rule |
|---|---|
| ID1 | A place in the tree that has the name from the response **and coordinates**, and is more than 30 km from the coordinates in the response, is **another place with the same name**. For example, Johnston in Iowa and Johnston in Rhode Island are about 1,600 km apart. The place in the tree is not changed, the place from the response becomes a new place, and the screen says so. The names of the places above are **not** compared: one place has many names in different languages and periods (the Banat is an example), and a rule on them would reject the right place. A place without coordinates, or a response without coordinates, cannot be compared: it is handled as before. When two places have the name, the nearer one is taken without asking. |
| NP3, NP5, NL | **Off by default.** NP3: a name starts when the state that ruled at that time began. In Gramps, a name that has one period and no other name is shown as `?` for an earlier event, so no period is better. NP5 and NL: the period (NP5) and the language (NL) of an existing name of a **level** are not proposed. They made up about half of all the proposals for responses in the `table` form, and they are not part of the first idea (type, levels, coordinates). The name of the place itself keeps its language and its period. `PLACECOMPLETER_RULES_ON=NP3,NP5,NL` switches them on. |

Tests: `test_identity.py`, `test_defaults.py`.

## Table 12: Rules and Notes That Were Removed After the Review

The review replayed 55 responses (35 in older formats and 20 in the `table` form). As a result, three rules and fifteen notes were **removed from the code**. None of them was triggered by the 20 responses in the `table` form (the rules about names), or they were triggered by every response and changed nothing (noise).

| Removed | What it did | Why it was removed |
|---|---|---|
| NP2 | A name started on the day after the last former name in the response ended. | It needs a list of other names, which the table does not give. Names in other languages are "nice to have, not required". |
| NP4 | A name in the tree that started after the state began was offered an earlier start. | It was triggered by 0 of 55 responses. It only improved an optional detail of a name. |
| NP6 | The other names in the response were added to the place with their periods. | It is not part of the first idea (type, levels, coordinates). |
| M06, M07, M08, M44 | The remarks, notes, doubts and "not sure" statements of the AI. | The table has no field for them. |
| M09, M10, M11, M12, M13 | Notes about the other names, about a contradiction with them, and about a source without a link. | They depended on the other names. |
| M24, M27, M41, M26 | Notes of the removed rules, and the note about the plain name of a new place. | The rules were removed. They were triggered by 0 of 20 responses. |
| M20 ("the state is listed twice"), M45 ("sources listed by the response") | Noise: they appeared for every response and changed nothing. | The sources are already in the evidence of each proposal. |

**Kept, although the review proposed to remove them.** Each of these explains a rule that protects the tree, and a rule whose reason is not shown is a rule that people stop trusting:

- NP1: a name period is not ended by the years of the municipality with the same name. It protects the end date of a name.
- M15 and M17: a level that you left out.
- M16 and M19: the window asks which place you mean.
- M21: a level that is not valid on the date.
- M22: the same as LV2.
- M28: the same as C8.
- M30, M31, M33, M35, M37: the link rules.
- M23 and M40: the same as NP1.
- M43: the chain has no country.
- M46 and M47: the table.
- M02 to M04: the command line, until the old parser is removed.

**Not removed yet:** the parser for the older forms of the response and the older forms of the question (`classic`, `short`, `dated`, `long`). They will be removed when the `table` form has been tried with other AIs.

## What Is Still to Be Done (Agreed, Not Yet Written)

| What | Rule |
|---|---|
| Place notes | One note on the place for each run, with `DIFFERS_FROM_TODAY` and the notes of the response, without repeating. It is added when it is missing, without duplicates. |
| Coordinates that already exist | An empty coordinate field is already filled (Table 4 and the proposals *Set missing coordinates*). Still to do: a different position is a change to existing data (not checked at first). It is proposed when Wikidata matches the place with certainty, or when the response is certain. |
| Distance | A note when a place is far from its parent, compared with the other children of that parent. |
