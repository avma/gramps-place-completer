# Place Completer: User Guide

This guide accompanies the [README](../README.md). The README gives a high-level overview of the addon; this guide explains, step by step, how to use it. All field names, buttons and menu options are those shown by the application (in English; the Hebrew interface has the matching terms).

**Contents:** [Quick Start](#quick-start) · [The Main Window](#the-main-window) · [Interpreting Proposals](#interpreting-proposals) · [Applying and Undoing Changes](#applying-and-undoing-changes) · [What Is Written to the Database](#what-is-written-to-the-database) · [Selecting an AI Engine](#selecting-an-ai-engine) · [API Key Management](#api-key-management) · [Gramplets and Quick View](#gramplets-and-quick-view) · [Configuration and Files](#configuration-and-files) · [Custom Place Types](#custom-place-types) · [Privacy and Data Security](#privacy-and-data-security) · [Troubleshooting](#troubleshooting) · [Uninstallation](#uninstallation)

---

## Quick Start

Before you begin, try the addon on a **copy of your family tree**, or make a full backup first (*Family Trees > Make Backup*). An AI engine that runs in your browser needs no API key.

**Where to start.** You can open the window in three ways:

- **From the Events view (the most convenient).** With the *Place Completer* gramplet on the Events view, select an event and click **Complete place data…**. The window opens with the **place and the date of the event** already filled in.
- **From the Places view.** With the *Place Completer (places)* gramplet, or the Quick View (right-click a place), the window opens with the **name of the active place**; you enter the date.
- **From the menu:** *Tools > Family Tree Processing > Place Completer*. You enter both the place and the date.

The date to enter is usually the date of the event whose place details you want to complete: a birth in 1899 needs the place as it was in 1899. (Adding a gramplet is described in [Gramplets and Quick View](#gramplets-and-quick-view).)

1. **Open the window** in one of the ways above.

   ![Tools, Family Tree Processing, Place Completer](screenshots/tool-menu.png)

   *Opening the tool from the menu: Tools > Family Tree Processing > Place Completer…*
2. **Confirm the place and the date.** Enter the place as you normally write it (for example *Blagnac*) and the date of interest (*1999*, *1999-05* or *1999-05-17*).
3. **Select an AI engine** (*Google AI mode*, *ChatGPT* or *Gemini*) and click **Ask**. Your browser opens with the question already entered. (For *Gemini*, the question is copied to the clipboard: paste it with `Ctrl+V`.)
4. **Bring the response back.** Copy the whole response of the AI, click **Paste from clipboard** (or paste it into the *Response* box) and click **Analyze**.

   ![The response of Google AI mode in the browser](screenshots/ai-response.png)

   *The response of the AI in the browser: copy all of it.*

   ![The window with the response pasted](screenshots/pasted-response.png)

   *The window after **Paste from clipboard**: the response is in the box, ready to **Analyze**.*
5. **Review the proposals.** When the analysis finishes, **no change is checked**; only the retrieved levels are (uncheck any level that you doubt). Check the changes that you accept, or click **Select all** and then uncheck any that you doubt.

   ![The proposals](screenshots/proposals.png)

   *The proposals. Each change has a check box, a confidence level and, when it needs care, a flag. The **Issues to review** are listed below; a red line is a warning.*
6. **Apply.** Click **Apply checked changes** and confirm. **Edit > Undo** reverses the changes (see [Applying and Undoing Changes](#applying-and-undoing-changes)).

   ![The confirmation](screenshots/apply-confirmation.png)

   *The confirmation: all the checked changes are applied together, in one step.*

Three optional settings are described in [The Main Window](#the-main-window): the form of the question (**Question**, left on `auto`), the **Wikipedia languages**, and the **Look up coordinates on Wikidata** checkbox (checked by default).

---

## The Main Window

![The main window after Analyze](screenshots/place-completer-window.png)

*The main window after **Analyze** (the example is Bojabirz in 1865): the fields at the top, the response, the retrieved levels, the changes (the grouped change is applied as a set) and the issues to review.*

| Field / Control | Description |
|---|---|
| **Place** | The place to look up, written as you normally would: *Parma*, *Sissa*, *Johnston*. |
| **Date** | The year for which you want the place names and administrative levels, for example `1850`. A month or a day is also allowed (`1990-05`, `1990-05-17`). |
| **Region hint** | *Optional.* A word that distinguishes this place from others with the same name: a county, a state or a country (*Parma* with *Italy*, *Johnston* with *Iowa*). If you give a country, the question also asks for the administrative levels that the country had in that year. |
| **Question** | The form of the question that is sent. Leave it on `auto`: it tries `table` first, then `classic`, `short`, `dated` and `long`, until the AI gives a response that can be read (at most five questions). `table` asks for a short response in a table that is easy to check; `classic` is the full question, with an explanation of every field; `short` has the same fields in one paragraph, for services that refuse a long question; `dated` adds that the name, the type and the containers must be those of the given date, not of today; `long` is the longest, and asks whether the name, the type or the containers differ from today's. |
| **AI** | The AI that you ask. A check mark means that it is ready; a cross says what is missing (usually a key). See [Selecting an AI Engine](#selecting-an-ai-engine). |
| **Ask** | Sends the question to the selected AI. An AI that has a key responds by itself, and its response appears in the *Response* box; a browser engine opens your browser. **Nothing in the tree changes at this stage.** |
| **Key…** | Opens the window in which you enter the API key of the selected AI (once). See [API Key Management](#api-key-management). |
| **Wikipedia languages** | The languages of the Wikipedia articles that are attached to places as web links, in order of preference (`he, en`). See [Wikipedia languages in detail](#wikipedia-languages-in-detail) below. |
| **Look up coordinates on Wikidata** | A checkbox, **checked by default**. After the analysis, the addon looks up in Wikidata the coordinates of places that have none (and, for the main place, the Wikipedia articles in your languages). Only the names of places are sent. Uncheck it to send nothing to Wikidata. |
| **Response** | The response of the AI. When the AI responded by itself, it appears here; when you used a browser, paste the whole response here. |
| **Paste from clipboard** | Puts the text of the clipboard in the *Response* box. |
| **Analyze** | Reads the response and shows what it would change in the tree. **Nothing changes yet.** |
| **Retrieved administrative levels** | The levels that the response lists, starting from the smallest. **They start checked:** uncheck a level that you doubt, and it is left out of the changes. |
| **Proposed changes** | The changes, each with a check box, its *Confidence* and a description of what it does. |
| **Other changes** | Changes made of several steps, applied as a set. Each box is one change, and its steps are applied together or not at all. |
| **Select all** / **Clear all** | One toggle button: it checks every change that can be checked without a decision from you, or clears all the check boxes. |
| **Issues to review** | The notes and warnings of the analysis (warnings are in red). Read them before you apply. |
| **Apply checked changes** | Writes the checked changes, in one step. |
| **Help** | Opens this guide in your web browser (the window stays open). The *Help* button of the gramplets opens it too. |

The line *Gramps display format for an event on this date* shows how Gramps would display the place on that date, and it updates as you check and uncheck changes.

### Wikipedia languages in detail

The field holds a list of Wikipedia language codes in order of preference, separated by commas: `he, en` or `fr, es`. It decides **which Wikipedia articles are added to a place as web links**. It does **not** change the language in which the AI responds (the question is always in English).

- **One article per language.** A place receives at most one Wikipedia article for each language in your list, one Wikidata link, and at most two other sites (those whose address looks official). The links that the place already has count toward these limits, and the same page in another form (`http` or `https`, `www`, mobile, a fragment) is the same link.
- **Where the articles come from.** They come from the pages that the AI cites (in any language) and, for the **main place** (the one you asked about), from its Wikidata item when *Look up coordinates on Wikidata* is checked. Wikidata lists the articles that exist in each language, so the addon can offer the article in your language even when the AI cited only the English one. An address is never guessed.
- **English is the fallback**: it is used only when none of your languages has an article.
- **The default** is the language of Gramps and then English (only English when Gramps is in English). Only language codes are accepted (`he`, `en`, `fr` …). The list is kept in `~/.config/placecompleter/settings.json`.

---

## Interpreting Proposals

Each proposal states what it does, in plain words:

| Display text | Meaning |
|---|---|
| *Create place «X» (Town); primary name: from [date]* | A place that is not in the tree, with its type and the period of its name. The type is determined as described in [Place types](#place-types). |
| *Enclose X inside Y: from [date]* | Links X into Y **with a date range**. |
| *Insert X between Y and Z* | A level that is missing between two places that are directly linked. |
| *Move X from Y to Z*, *Prioritize link of X inside Y over link inside Z* | The order of the links matters: **Gramps uses the first link in the list that fits the date.** |
| *Disconnect X from Y* | Removes a link (both places remain). |
| *Update hierarchy link date range…* | An existing link is given a different period. |
| *Change administrative place type of X from A to B*, *Set administrative place type of X to B* | The type of the place. |
| *Set missing coordinates for X…* | Fills empty coordinates, from the response or from Wikidata. |
| *Assign date period to name…*, *Set language tag for name…*, *Add place name…* | Names, with their periods and languages. |
| *Attach web link… to X* | A link to a page that the AI cited, or a Wikipedia or Wikidata link. |

### Confidence

Each change has a confidence level. A change made of several steps has the level of its least certain step.

- **Confirmed**: independent data agrees (Wikidata, a regional pack, or the tree itself).
- **Reported**: the response states it and cites a page that supports it.
- **Inferred**: worked out by the program from other data; check it.
- **Unsure**: the response says that it is not sure, contradicts itself, or cites no page.

### Flags

A small label on a change tells you what kind of care it needs: *modifies existing tree data*, *disconnects place link*, *modifies hierarchy link*, *inserts intermediate level*, *renames place*, *modifies place type*, *verify official status of web source* (a site of an unknown kind: is it official?), and *populates unassigned field* (fills something that was empty).

### What is checked, and what Select all does

**When the proposals appear, no change is checked.** Only the retrieved levels are, because with them you uncheck what you doubt. A change to existing data is marked as such. **Select all** checks everything that can be checked without a decision from you, **including changes to existing data that are not in conflict** (read their flags first). It leaves these for you to decide one by one: a **CONFLICT** with the tree (for example, a link that the response says is wrong), a web link of an unknown kind, and changes that cannot be made together (check one or the other). Read *Issues to review* before you apply.

### Place types

The type of a place is taken from the types of Gramps itself:

- **A settlement** (the question asks for its size class): *metropolis* and *city* become **City**, *town* becomes **Town**, *village* becomes **Village**, *hamlet* becomes **Hamlet**, and *neighborhood* and *locality* map to their own types. The legal status (commune, municipality …) is not part of the response.
- **An administrative level** (country, state, province, county, district …) gets the Gramps type that fits the word the AI used. If Gramps has no such type (a *canton*, for example), the **word used in the response becomes a custom type** (`Canton`).
- **A place that already exists keeps its type.** The type is changed only when the tree has a Gramps settlement type (City, Town, Village …) and the response gives a different size class. The change is then proposed, flagged *modifies place type*, for you to decide. When the type of the place is not a settlement (a District, a Province, a custom type), the type is not changed and *Issues to review* says so: the place may be the canton or the province of the same name, or the town itself with the wrong type. A place with **no type** is given the type from the response.
- **Custom types** (types that you made up, in the language of your tree) are **learned from the tree** when a question is asked: the addon reads the custom types that places use, and treats the different ways of writing one type as one. What you describe in the file `type-conventions.json` always comes first: see [Custom Place Types](#custom-place-types).

---

## Applying and Undoing Changes

Clicking **Apply checked changes** asks for a final confirmation, and then writes all the checked changes in **one single step**. A message tells you how many were applied.

**Undo is a built-in feature of Gramps**: *Edit > Undo* restores the tree to its state before the changes, all of them together. Gramps keeps the undo history only while the tree is open, so check the result before you close the tree. A backup is the safe way back.

Each place that changed also receives **citations** for the pages that the AI cited (see [What Is Written to the Database](#what-is-written-to-the-database)). The response is also saved in a file (see [Configuration and Files](#configuration-and-files)). If you ask for the same place on another date and the response is identical to the one saved for the first date, the addon warns you: the AI probably returned a fixed text for different dates.

---

## What Is Written to the Database

Only the places that you check are touched, and nothing else in the tree.

| What | How it is written |
|---|---|
| **New places** | A place with its name (and the language of the name), its type, its place in the hierarchy and, when known, coordinates and web links. |
| **Names** | The primary name of a place keeps its language and the period when the name was used. When the name changes, the old name stays as an **alternative name**, with its language and its period. |
| **Type** | Set for a new place or for one with no type. Changed only as described in [Place types](#place-types). |
| **Hierarchy (enclosure) links** | A link to the place that encloses it, **with a date range**, placed so that the first link that fits a date is the right one. *Disconnect* removes a link, never a place. |
| **Coordinates** | Latitude and longitude, only where they are empty (from the response or from Wikidata). |
| **Web links** | In the *Internet* tab of the place: the Wikipedia articles in your languages, a Wikidata link, and at most two other sites (see [Wikipedia languages in detail](#wikipedia-languages-in-detail)). |
| **Citations** | The chain **Place → Citation → Source → Repository**, described below. |

**The chain of a citation.**

- **Repository**: the web site that the page belongs to (Wikipedia, Wikidata …). The repository that the tree already has is used; a new one is created only when there is none.
- **Source**: one for each web page. Its title is the title of the page, and the address is kept in the publication information and as a source attribute named `URL`, which is how the addon finds it again. A source that the tree already has (the same page in another form) is reused, not duplicated.
- **Citation**: its *page* text says **what the page is cited for**; its date is the **day the information was retrieved**; and its confidence is *Normal*, *Low* or *Very Low*. (For a Wikidata statement the confidence is *Normal*. For an AI response it follows how sure the response was, and is one level lower when the analysis found that the response contradicts itself or a response saved for another date. A tourism, commercial or social site is never above *Low*.)
- **Note** (of the type *Place*, attached to the **citation**, not to the place): **how the information was found**: which AI and model, on what day, in response to which question and form, where the response is saved, and what the response was unsure about.

A place receives **at most three new citations in one run** (the strongest first: higher confidence, then Wikidata, Wikipedia, official sites, other sites), and a citation that already exists is not added again. A citation goes to the place that its page is **about**; a page about none of the places is cited on the main place. What the limit left out is reported after the changes are applied.

**What is never written:** events, people, merged places, or the deletion of a place.

---

## Selecting an AI Engine

All the engines appear in the **AI** list; a check mark means that the engine is ready.

| Engine | Requirements | Notes |
|---|---|---|
| **Claude API with web search** | An Anthropic API key | Responds by itself, and can cite pages. |
| **OpenAI-compatible** | An API key and a model | Responds by itself; no web search of its own. |
| **Ollama** | Ollama on your computer | Free; the question never leaves your computer; no web access, so less reliable. Installing Ollama and downloading a model need the network. |
| **Google AI mode**, **ChatGPT** | Nothing | The browser opens with the question already in its address; you paste the response back. |
| **Gemini**, **any other AI** | Nothing | The question is copied: paste it (`Ctrl+V`) into the AI, then copy the response back. |

**Claude API.** Click **Key…**, paste the key and click **Save**; **Test** tells you whether the service accepts it. The addon selects the model.

**OpenAI-compatible.** Save the key in the same way. The addon asks the service for its list of models and selects one. If it cannot, write the model name in `~/.config/placecompleter/engines.json`:

    {"engines": {"openai": {"model": "the-name-of-the-model"}}}

Another service that uses the same API (a local one, for example) is added in the same way, with its `base_url`.

**Ollama.** Select *Ollama* and click **Ask**. If Ollama is not installed, the window offers to open a terminal with the installer (it asks for your administrator password **in the terminal**, not in the window). If it is installed but not running, the window offers to start it (it then runs in the background). If it has no model, **Download a model** offers a small one (about 2 GB, recommended) or any name from ollama.com/library. The download can be cancelled.

**A browser engine** can be added in `engines.json` for any AI that accepts a question in its web address (the question goes where `{q}` is):

    {"engines": {"perplexity": {"kind": "browser", "label": "Perplexity", "url": "https://www.perplexity.ai/search?q={q}"}}}

---

## API Key Management

*Optional.* A key is needed only for the engines that respond by themselves and are paid for by use (**Claude API**, **OpenAI-compatible**): the service provider charges according to its own price list. The browser engines and Ollama need no key. Every **Ask** sends one question; with `auto`, a response that cannot be read may be followed by up to five questions in all.

An API key is kept, in this order of preference: in the **keyring of your system** (through libsecret, or the `secret-tool` command), otherwise in a **private file** under `~/.config/placecompleter/keys/` (mode 600: readable by you alone). It is never put on a command line, in a log, in the Gramps database or in the settings of the window, and the window shows only a masked hint (`sk-ant-…wXyZ`, and the number of characters). **Remove** (in the key window) deletes it.

For scripts, an environment variable named in `engines.json` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) takes precedence over everything else. `PLACECOMPLETER_KEYSTORE=none` keeps no key at all; `file` or `keyring` forces one of the two places.

---

## Gramplets and Quick View

The addon has three places to start from (besides the menu):

- **Place Completer**, a gramplet of the *Events* view: shows the type and the date of the active event, and **how Gramps displays its place on that date**. When the place has names but none for that date, it says so: *Names are missing for this date (place displayed with «?»)*. **Complete place data…** opens the window with the place and the date of the event.
- **Place Completer (places)**, a gramplet of the *Places* view (its title in the sidebar is *Place Completer*): shows the active place, how Gramps displays it, and **what it lacks** (coordinates, type, language of the name, a cited source). **Complete place data…** opens the window with the name of the place; enter the date and click **Ask**.
- **Quick View**, from the context menu of a place (right-click): the same as the gramplet of the Places view.

![The gramplet in the sidebar of the Places view](screenshots/side-bar-gramplet.png)

*The gramplet in the sidebar of the Places view: how Gramps displays the active place, and the button that opens the window.*

To add a gramplet, which is a **standard feature of Gramps**, right-click the bar of the sidebar or of the bottom bar of the view and select *Add a gramplet*.

---

## Configuration and Files

| What | Where |
|---|---|
| The addon | The plugins folder of your Gramps (`~/.local/share/gramps/gramps60/plugins/PlaceCompleter`; `gramps61` for 6.1) |
| The responses received | `~/gramps-place-work/answers/<place>_<date>.txt` |
| What the window remembers (the AI, the form, the Wikidata box) | `~/gramps-place-work/window.json` |
| The log of `ollama serve`, when the addon started it | `~/gramps-place-work/ollama-serve.log` |
| Older copies of the addon (`deploy_addon.py --clean`) | `~/gramps-place-work/backups/` |
| Your engines | `~/.config/placecompleter/engines.json` |
| The model that the addon selected by itself (no secret in it) | `~/.config/placecompleter/models.json` |
| Your Wikipedia languages | `~/.config/placecompleter/settings.json` |
| Your keys, when there is no keyring | `~/.config/placecompleter/keys/` |
| Your type conventions (the types of your tree) | `~/.config/placecompleter/type-conventions.json` |
| Your type vocabulary (the words that tell what a custom type of your tree is) | `~/.config/placecompleter/type-vocabulary.json` |

| Environment variable | What it does |
|---|---|
| `PLACECOMPLETER_WORK` | The folder of the responses, of what the window remembers and of the backups (default `~/gramps-place-work`) |
| `PLACECOMPLETER_KEYSTORE` | `none`, `file` or `keyring`: where keys are kept |
| `PLACECOMPLETER_ENGINES`, `PLACECOMPLETER_MODELS`, `PLACECOMPLETER_SETTINGS` | Another file in place of `engines.json`, `models.json`, `settings.json` |
| `PLACECOMPLETER_CONVENTIONS`, `PLACECOMPLETER_VOCABULARY` | Another file in place of `type-conventions.json`, `type-vocabulary.json` |
| `PLACECOMPLETER_TREE`, `PLACECOMPLETER_CACHE`, `PLACECOMPLETER_LIVE_DIRS` | For the command line (`placecompleter/cli.py`): the tree to read, the file of what Wikidata responded, and the folders that hold live data and are refused |
| `PLACECOMPLETER_RULES_OFF`, `PLACECOMPLETER_RULES_ON` | Switch analysis rules off or on, by their ids (`docs/ANALYZER_RULES.md`). For the curious; the defaults are the tested ones |

---

## Custom Place Types

If your tree uses custom place types for administrative units (a canton, a district, in any language), copy `data/type-conventions.json` to `~/.config/placecompleter/type-conventions.json` and describe your types in it (see `data/type-conventions.example-he.json`, the types of a tree in Hebrew). The file says which of your types is a province, an empire, a district or a settlement, and it gives rules of the form *when the response calls a level by one of these words, give it this type*. An update of the addon does not touch that copy. Without the file, and when the tree has no custom type, the types of Gramps itself are used, and a unit for which Gramps has no type (a canton, for example) is given the word used in the response as a custom type.

**The tree is read as well.** When a question is asked in the window, the addon reads the custom place types that the places of the tree use. A type that no place uses any more is not read, and reading never changes anything in the tree.

- **One type, one way of writing.** The same type is often written in more than one way: with a space before or after it, with a no-break space, with an invisible direction mark, in capital or small letters, with a dash or a space between two words, with different quotation marks, with or without vowel points or accents. These are not different types: the addon treats them as one. A place that already has a type keeps the writing it has. The writing used for a *new* place is the tidy one (no space before or after) that most places use. When the tree has no tidy writing at all, the one it has is used, so that no second type is created.
- **What each type is.** A type is recognized by a vocabulary of synonyms in several languages (`data/type-vocabulary.json`, starter data to be reviewed): a province, an empire, a monarchy, a district, a canton or a settlement. A custom type that is not known as a settlement is treated as an administrative area, so the settlement words of your language matter most. To add words of your own language, write groups of the same shape in `~/.config/placecompleter/type-vocabulary.json` (or in the file that `PLACECOMPLETER_VOCABULARY` names): they are added to the starter ones.
- **Distinctions are not guessed.** Words that name different units (the Hungarian *járás* and *kerület*, for example) are in groups of their own and are never joined. When two types of your tree fit one group, no rule is made for it: describe it in `type-conventions.json`. A rule is also not made from a custom type that the tree uses less than the Gramps type that it would replace (one custom *District* among forty Gramps *District* places does not turn every new district into a custom one).
- **A new type is reported.** When a proposal gives a place a custom type that no place in the tree uses yet (a canton, or a type that your file gives), the screen says so in a note, once for each type. In Gramps a custom type exists only because places use it, so approving the place is what adds the type. Nothing is selected for you, and the note disappears once a place in the tree has the type.
- **Your file comes first.** What `type-conventions.json` says for a province, an empire or a monarchy is kept. What it leaves empty is filled from the tree, and the types of the tree are added to its lists.

To see what was learned from a tree, run the command `types` of `placecompleter/cli.py` on a copy of the tree (never the live one). It lists each type, its role, the writings that were joined and how many places use each, the rules that were left out, and the **possible duplicates**: types that are one letter apart (*Cemetery* and *Cemetary*). These are only reported, never joined: if they are one type, correct them in Gramps.

### Describing a type yourself

The addon cannot know every type of every tree. When the command `types` shows `-` as the role of a type that is a settlement or an administrative unit, or gives a type the wrong role, describe it in your own files in `~/.config/placecompleter/`. There are two; an update of the addon does not touch them, and what they say always comes first:

| File | Use it to say | When it is read |
|---|---|---|
| `type-conventions.json` | *this type of my tree is a settlement, a district, the province ...*, and *when a response calls a level by this word, give it this type* | when Gramps starts: restart Gramps after a change |
| `type-vocabulary.json` | *these words mean a settlement, a district ...* (any language; for several types at once, or for a word that the addon does not know) | at every question: no restart |

Start with `type-conventions.json`: it names the types of your tree exactly.

**1. Create the file** (once). The folder may not exist yet. For Gramps 6.1 write `gramps61` in place of `gramps60`:

```
mkdir -p ~/.config/placecompleter
cp ~/.local/share/gramps/gramps60/plugins/PlaceCompleter/data/type-conventions.json ~/.config/placecompleter/
```

Open the copy in a text editor. It has one line for each thing that can be said (the order of the lines does not matter, and a line that you do not need can stay as it is). The first line, `description`, is a long text: leave it. Here it is shortened to `...`:

<!-- json-file:conventions -->
```json
{
  "description": "...",
  "province": "",
  "empire": "",
  "monarchy": "",
  "district": [],
  "rules": [],
  "settlements": []
}
```

**2. A type of settlement that the addon does not recognise.** Write its name between the square brackets of the line `"settlements"`, as the Type column of Gramps shows it, in quotation marks; a second name after a comma. Capital letters, spaces before or after the name and a dash in place of a space do not matter. Change the line

`"settlements": [],`

to

<!-- json-line:conventions -->
```json
"settlements": ["Homestead", "Outstation"],
```

**3. A type of district.** The same in the line `"district"`. If the response should also give a new place that type when it calls a level by a word (here *okres*), add a *rule* in the brackets of `"rules"`: `words` are the words as the response writes them, in any language (capital letters and accents do not matter), `value` is always `0` (a type of your own), and `string` is the name of the type.

<!-- json-line:conventions -->
```json
"district": ["Okres"],
```

<!-- json-line:conventions -->
```json
"rules": [{"words": ["okres"], "value": 0, "string": "Okres"}],
```

A second rule goes after the first, with a comma between them (and no comma after the last):

<!-- json-line:conventions -->
```json
"rules": [
  {"words": ["okres"], "value": 0, "string": "Okres"},
  {"words": ["canton", "kanton"], "value": 0, "string": "Kanton"}
],
```

**4. A province, an empire or a monarchy** has one name, between the quotation marks of its line:

<!-- json-line:conventions -->
```json
"province": "Kronland",
```

All together, the file looks like this:

<!-- json-file:conventions -->
```json
{
  "description": "...",
  "province": "Kronland",
  "empire": "",
  "monarchy": "",
  "district": ["Okres"],
  "rules": [
    {"words": ["okres"], "value": 0, "string": "Okres"},
    {"words": ["canton", "kanton"], "value": 0, "string": "Kanton"}
  ],
  "settlements": ["Homestead", "Outstation"]
}
```

**5. By words: `type-vocabulary.json`.** This file has no copy to start from: create it in the same folder with a text editor. It holds groups of words, and each group has a `role`: `settlement`, `district`, `canton`, `province`, `empire` or `monarchy`. A type of your tree whose name is one of the words gets that role. Words that name different units belong in groups of their own. Its groups are added to the ones that come with the addon:

<!-- json-file:vocabulary -->
```json
{
  "groups": [
    {"role": "settlement", "words": ["homestead", "outstation"]},
    {"role": "district", "words": ["okres"]}
  ]
}
```

**6. Check it.** After a change in `type-conventions.json` restart Gramps; then run the command `types` on a copy of the tree. A star after a role (`settlement*`) means that your file `type-conventions.json` says it; a role without a star comes from the vocabulary; `-` means that the type is not known yet. The lines under `conventions in use` show what the engine works with.

**Take care of the file itself.** The file must be valid JSON: quotation marks like `"` (not curly ones), a comma between two items and **no** comma after the last one in a list or a file. **A file with a mistake is ignored as a whole, without a message**, and the addon then behaves as if the file were not there. To check a file, run `python3 -m json.tool ~/.config/placecompleter/type-conventions.json`: it prints the file when it is valid and names the line of the mistake when it is not.

---

## Privacy and Data Security

- **Sent to the AI that you select:** the name of the place, the date, the optional region hint and the text of the question. **Your tree, your people and your events are never sent.** With *Google AI mode* and *ChatGPT*, the question is in the address that the browser opens.
- **Sent to Wikidata**, when *Look up coordinates on Wikidata* is checked: the names of the places that need coordinates, one request at a time.
- **Nothing else** leaves your computer: no telemetry, no tracking, no remote analytics, and no server of the author.

---

## Troubleshooting

| What you see | What it means, and what to do |
|---|---|
| *No API key saved for this AI engine yet* | Click **Key…** |
| *…rejected API key authentication (HTTP 401)* | The service does not accept the key. Check in the provider's dashboard that the key is active and has credit, and enter it again. |
| *…does not recognize the model «X»* | Select another model in `engines.json` (see [Selecting an AI Engine](#selecting-an-ai-engine)). |
| *key file … has insecure permissions* | Run `chmod 600` on that file. |
| *Ollama is not active locally* | Click **Ask** for the guided steps, or run `ollama serve`. |
| *Ollama is running but no model is installed* | Click **Download a model**. |
| *Could not launch web browser. Please open this URL manually* | Copy the address that follows and open it yourself. |
| *Text does not conform to the expected response template* | The response is not in the form that was requested. Paste the **whole** response, or try another AI or another *Question* form. |
| *AI returned unfulfilled prompt* | The AI returned the question to you. Add a *Region hint* (a county, for example) or use another AI. |
| *This name matches multiple places. Which one did you mean?* | The tree has several places with this name. Select one (nothing is created until you do). |
| *Names are missing for this date (place displayed with «?»)* | The place has names, but none that is valid for that date. The addon proposes the missing name. |
| *…has leading/trailing whitespace*, *enclosed in quotation marks* | The addon removes spaces and line breaks at the ends of a key, and quotation marks around it, by itself. |
| *…contains internal spaces or line breaks* | Spaces or line breaks **inside** the key mean that the copy is damaged: copy it again. |
| The Hebrew text looks reversed around a command or an address | Please report it. Those are wrapped in direction marks, and a case that slipped through is a bug. |
| Nothing is proposed | Read *Issues to review*: usually the response has no name for the place. |

If a question to an AI fails five times, the window says so. Try again later, add a region word, or select another engine.

---

## Uninstallation

Delete the folder `PlaceCompleter` from the plugins folder of your Gramps and restart Gramps. To remove everything that the addon left behind, first click **Remove** in the key window of each AI (so that the key leaves the keyring), and then delete `~/.config/placecompleter` and `~/gramps-place-work`. Nothing was ever written to your tree except the changes that you applied.
