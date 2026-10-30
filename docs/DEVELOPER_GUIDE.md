# Developer guide (the engine, the tools, the tests)

*This was the README while the addon was developed; the README for users is `README.md`.*

## The engine (step 1)

Pure-Python engine that finds where the place chains of a Gramps tree break and
simulates fixes, using Gramps' own place display rules (checked against Gramps
6.0.8 on tens of thousands of random events). No GTK, no Gramps import.

    cd gramps-place-completer                 # (the folder of the repository)
    python3 -m placecompleter.cli report                      # AI snapshot, read-only
    python3 -m placecompleter.cli report PATH/sqlite.db --csv out.csv
    python3 -m unittest discover -s tests -v                  # engine tests
    # with the Gramps python (GRAMPS_RESOURCES set), the same command also runs
    # the comparison against Gramps' own display (tests/test_vs_gramps.py)

    python3 -m placecompleter.cli report --pack packs/hu-habsburg.json   # (default: every file in packs/)

A regional pack (packs/*.json, schema placecompleter.pack.v1) lists places and dated
parent links with evidence. A proposal is made only when both ends match exactly one
place of the tree and the link fixes events in this tree (checked by simulation).

    python3 -m placecompleter.cli agent-request [--max-tasks 6]   # writes a request and a task file for the agent
    python3 -m placecompleter.cli agent-validate RESPONSE.json --request REQUEST.json

The agent loop: agent-request lists the places that still have a gap after the
engine's own fixes and the packs; the agent (agent/prompt.md) answers with names and
links that carry evidence; agent-validate rejects every item without valid dates and
evidence, turns the rest into a pack and shows the simulation. Nothing is written
to a tree by these commands.

    python3 -m placecompleter.cli wikidata-pack [--online] [--max-places 8] [--seed FILE]

wikidata-pack looks the places that still have a gap up in Wikidata (answers are cached in
~/.cache/placecompleter_wikidata.json; without --online only the cache and --seed files
are used). It offers dated parent links (P131, deprecated ignored) between places that
resolve to places of the tree, dated official names (P1448), and name periods taken from
an entity's lifetime (P571/P576). A tree place is tied to an entity only when the match is
unambiguous (equal name, and within 50 km when the tree has coordinates).

    python3 -m placecompleter.cli plan [--wikidata] [--out plan.json]    # proposals, numbered, by basis
    python3 -m placecompleter.cli apply --plan plan.json --tree-dir COPY --basis tree,evidence [--yes]

A plan is the list of proposals of one analysis. Each has a basis: "tree" (the tree's own
data), "evidence" (a dated statement in a source) or "assumption" (for example: the same
name for the whole lifetime of a place). apply is a dry run unless --yes is given; it
refuses a tree inside ~/Dropbox or one that is locked, writes everything in ONE Gramps
transaction (one Undo step), and skips any proposal whose target changed since the analysis.

A place that ceased to exist (a district abolished in 1920) is described by its lifetime in a
pack (or by Wikidata's dissolution date, or by the agent): the links to it end then, and the
engine judges that together with the link to the place that took over (pairs are evaluated
leave-one-out, so neither half is rejected alone). Street addresses (by their name and by being a leaf, never by the type alone) are not looked up in Wikidata; a type that contradicts the
place's behaviour is reported as TYPE CHECK.

A place the tree lacks (for example the Kingdom of Yugoslavia as the parent of a village after 1929) is
offered as a new place together with its link, as one bundle: both are judged, selected and written
together (the writer creates the place first, reuses a place that already carries the same Wikidata
link, and one Undo removes the place and the link). Wikidata offers at most 6 new parents per run.

    python3 -m placecompleter.cli complete-place "Subotica City" --date 1950 [--region Serbia] [--pick Q1041949] [--online]

complete-place takes a place name and the date of an event and prints one control screen: the identity
in Wikidata (candidates when the name is ambiguous, never a guess), coordinates, the name in the language
of the state on that date (the state at the top of the dated chain decides), the dated hierarchy up to the
first place the tree already has, places already in the tree that look the same (check before creating),
and what Gramps would display for an event on that date. The proposals go into a plan for apply.

    python3 -m placecompleter.cli ai-complete Bajmok --date 1850 [--skip 2]
    python3 -m placecompleter.cli search-ai Bajmok --date 1850 [--short] [--no-open]
    python3 -m placecompleter.cli ingest-text ANSWER.txt --date 1850 [--skip 2]

If the answer is AMBIGUOUS (several places with that name), ai-complete lists the candidates here, numbered, with what your tree
says about each (a place named like its region, the nearest place with coordinates), you choose, and a second question is sent
with the place described exactly ("Johnston, Iowa, United States (coordinates 41.673, -93.6977)"): clicking a candidate in
Google loses the question. --hint "Iowa" adds a word to the name from the start and usually avoids the question.

The AI sometimes gives the same text for different dates (it did for Johnston, Iowa, 1950 and 1995). ai-complete keeps every
answer in ~/gramps-place-work/answers/ and warns when this answer is identical to one saved for another date. A new place's
own name starts when the last former name listed in the answer ended (Johnston: from 1970, because "Johnston Station" ends in
1969), so the same text gives "Johnston Station" in 1950 and "Johnston" in 1995.

If Google AI mode answers "no answer for this search", compare the forms of the question: --form classic (the first template, which
was answered), long (asks that the date matters) and short; search-ai --show prints the question to paste into any chatbot.

Google sometimes wraps names in links ("[Iowa](https://www.google.com/search?kgmid=...)"): the reader keeps the text. "Unincorporated
community" becomes the Gramps type Locality; a township or other unit whose type is not in the user's convention is left
unknown for the user to choose.

Google AI mode sometimes answers "no answer for this search" (also to a question it answered a minute before). ai-complete
recognises that message (Hebrew or English) and tries the next form of the question (classic, short, dated, long) by itself;
--form one_of_them asks only that form. Google AI mode answered classic and short each time and refused long twice. --engine chatgpt or gemini opens the same question there (a ChatGPT link with web search
on; Gemini's link is experimental); the answer is read from the clipboard the same way.

Answers vary with the form of the question and the engine: a short answer may have pipes in the coordinates, a county called
"Polk" and no country. The reader tolerates those (coordinates separated by | or ;, a repeated type, "Polk" created as
"Polk County") and points out a chain that stops at a state. The fullest answers come from the long form.

The same place asked again (another form, another engine, another day) gives a different answer. ai-complete and ingest-text
compare the answer with every saved answer about the same place (same coordinates within 3 km, or a shared name) and print
"DISAGREES WITH A SAVED ANSWER: ..." for facts that differ: the start of a unit, the end of a former name, coordinates more than
1 km apart, and (for the same year) the name and the type. A disagreement is where to look first. --compare-dir chooses the folder.

THE WINDOW (Tools > Family Tree Processing > Place Completer in Gramps)
  python3 deploy_addon.py --dry-run     # then without --dry-run: copies the files Gramps needs into its user plugins folder
  python3 deploy_addon.py --translations --clean   # with the Hebrew; --clean first moves the old folder to ~/gramps-place-work/backups
                                                  # (outside the plugins folder, which Gramps reads whole; nothing is deleted)
  Restart Gramps. Type a place and a date (and, if the name is common, a region word), choose the AI, press Ask. For a browser or
  "manual" engine copy the answer into the window and press Analyze; an API engine answers by itself. Then: the levels of the answer
  (uncheck a doubtful one), the CHANGES (one check box each; NOTHING is checked for you; under each change the steps it is made of, which
  have no box because they cannot be chosen apart: a new place and its links, or a level put in between with the cut of the old direct
  link, because Gramps uses the first link that fits the date: either step alone does nothing or loses the connection; a proposal that
  stands alone, like a former name, is a change by itself; "changes a link" marks a change that edits a link already in the tree, and
  CONFLICT a real contradiction with the tree),
  what Gramps would display for an event on that date for what is checked now, and what to check first (warnings in red).
  "Write the checked proposals" is in the row of buttons at the bottom (next to Close) and writes in ONE step: Edit > Undo takes it all back.
  Scrolling: every scrolled window has a classic slim bar that takes its own room (an overlay bar floats over the text at the edge, which in
  a right-to-left Gramps is the left edge), the content scrolls sideways instead of being cut off if something is wider than the window, and
  long words (an address) break instead of making the window wider. The slim-bar CSS is given to this window only, never to all of Gramps.
  The window fits any screen: its size starts from the usable area of the monitor, whatever size or place Gramps remembered is brought back
  inside the screen, the content scrolls, and the parts that need an answer (levels, proposals, notes) appear only when there is one.
  THE GRAMPLET (Events view): Place Completer is also a gramplet. In the Events view open the sidebar or the bottombar (View menu),
  right-click on it, "Add a gramplet", choose "Place Completer". It shows the active event (its date, its place, what Gramps displays
  for it, and a note when names are missing: a "?") and one button, "Complete the place...", which opens the window with that place and
  that date already filled in. It is registered for the Events view only; a gramplet is listed only in the views of its own type.
  The date is read as Gregorian text YYYY[-MM[-DD]] (a Julian date is converted; the first date of a range or a span is used; a date that
  is only text gives no date and the window asks for the year). Nothing is asked and nothing is written from the gramplet itself.
  FILLING EMPTY FIELDS. When the place already exists, what it lacks and the answer can give is proposed as a change of its own (one box each,
  flag "fills an empty field"): its coordinates (when it has neither), the language of its name (when the name is the one of the answer and
  has no language), its type (when it is Unknown). A field that already has a value is never replaced; and at the moment of writing a field
  that somebody filled in the meantime is skipped, not overwritten. The coordinates of an AI answer can be off by some kilometres (two answers
  about the same place were 1.4 and 2.9 km apart): check them. A new place gets its coordinates and type when it is created.
  NAMES. A SETTLEMENT's name does not repeat its type: "City of Johnston" of type City is "Johnston" (also Town, Village, Hamlet, Borough,
  Municipality). Only the English form "<type word> of <name>" is simplified, and only when the type of the place is that word (never "Bay
  of Pigs"; "City of London" is kept, it is another place). Administrative units KEEP their word, consistent with the Hungarian ones
  ("Bács-Bodrog vármegye", "Zombori járás"): "Polk County", "State of Iowa", "Kingdom of Hungary" are left as they are. A new settlement is
  created with the simple name; a settlement that exists with the long name gets a change of its own to choose, "Rename «City of Johnston»
  to «Johnston»", and its old name stays as an alternative name with its language and period. The answer "Johnston" finds the place "City
  of Johnston" and the reverse.
  A LEVEL PUT IN BETWEEN. When the place is linked directly to Iowa and the answer says Polk County lies in between, the new link is written
  BEFORE the old direct one and nothing of the old one is edited: Gramps uses the first link that fits the date, so Polk County is used
  from 1846 and the old link to Iowa stays, untouched, for the years before.
  THE SAME PLACE TWICE. When the answer lists a municipality ("City of Johnston, municipal corporation") as a container of the place
  ("Johnston", a city), it is the same place: it is not made a separate place inside itself.
  NO NEW PLACE WHILE ONE THAT EXISTS MAY BE IT. When a level of the answer has the same name as several places of the tree, or as one that
  is not clearly it, the window asks which ("Which place is it?": each candidate, a new place, or leave the level out) and nothing is created
  for it until you have chosen. A partial name hit does not trigger the question.
  TYPES AND LANGUAGES OF NEW LEVELS. A new level gets its type from the answer when it is a city, town, village, hamlet, borough,
  municipality, parish, country, state or county (a township, a district or a region is left open, as in your convention). The names of the
  levels get the language "en" for an English answer (new ones when created, existing ones without a language as a change of their own to
  choose); for an answer in another language nothing is assumed, because the language of the names of the units cannot be told.
  COORDINATES FROM WIKIDATA. After the answer is read, and in the background, the names of the place and of the places of its chain that
  lack coordinates are looked up on Wikidata (only the names are sent; the checkbox "Look up coordinates on Wikidata" turns it off; the
  answers are kept in ~/.cache/placecompleter_wikidata.json). A coordinate of Wikidata (property P625, deprecated statements dropped) is
  used when ONE place of that name is found where the answer puts it (within 50 km; two near places of the same name are not chosen
  between). It replaces the coordinates of the answer, its basis is "evidence" and its source is the Wikidata statement; what Wikidata
  could not settle keeps the coordinates of the answer, and the window says so. A place that exists, has no coordinates and the answer
  gave none gets a proposal of its own. The numbers of the proposals and what you had checked are kept while this happens.
  CITATIONS. Each place that is written (new, or changed) also gets a Citation to a Source for each web page the answer lists for the fields
  that change is about (and for a Wikidata statement): the Source has the page's title and its address (in the publication information and as
  a source attribute "URL", which is how it is found again); the Citation says what it is cited for, the day it was fetched, confidence Low
  (found by an AI) or Normal (Wikidata); its note says which AI found it, the question, where the saved answer is, and what the answer was
  unsure of. One page is one Source however many places cite it; the very same statement is never cited twice; it is all one Undo.
  NAME PERIODS. A name that has no period gets the period of its unit in the answer, as a choice of its own, with the warning that an event
  before that date would show "?" instead of the name.
  WHERE TO FIND IT. Tools menu: Family Tree Processing > Place Completer. Gramplets: the Events view and the Places view each have one
  ("Add a gramplet" in the sidebar or bottombar). Right-click menu without touching Gramps: in the Places view, right-click a place > Quick
  View > Place Completer (Gramps shows a small Quick View window together with the window of the addon).
  HEBREW. po/he-local.po is compiled by deploy_addon.py into locale/he/LC_MESSAGES/addon.mo next to the plugin, where Gramps reads the
  translation of an addon; Gramps in Hebrew shows the addon in Hebrew. The texts of the engine are made translatable by _() and tr(); the
  English is kept for what the code and the tests read (the importance of a note is read from its English). After adding a text, run
  tools/extract_strings.py and add its translation to po/he-local.po: tests/test_i18n.py fails when one is missing or when a placeholder differs.
  SCROLLBARS. The windows of the addon have slim scrollbars without arrow buttons (a style that applies only to them). For ALL Gramps
  windows: python3 deploy_addon.py --slim-scrollbars (a marked block in ~/.config/gtk-3.0/gtk.css, which styles every GTK3 program of
  yours); --no-slim-scrollbars takes it out. An addon cannot style the windows of Gramps itself.
  Gramps versions: tested with 6.0 (6.0.8) and 6.1 (master, 6.1.0): the whole suite passes against both. Gramps loads a plugin only
  if it names the running major.minor, so the gpr names the running version when it is 6.0 or 6.1 and declines any other on purpose.
  The plugins folder is per version (gramps60, gramps61): run deploy_addon.py with the python of each Gramps (or give --dir).
  The window is a thin layer over placecompleter/session.py, which is tested without a screen. What the window remembers (AI and
  question form; NOT the region hint, which belongs to one question: it shows only as grey text in the empty field, and a hint typed for one
  place is cleared when another place is typed) is kept in ~/gramps-place-work/window.json; answers in ~/gramps-place-work/answers/.

WHICH AI ANSWERS is the user's choice, whatever search engine they use (python3 -m placecompleter.cli engines lists them):
  google, chatgpt, gemini   a link that opens the question in the browser; you copy the answer
  manual                    the question is copied; you paste it into any AI and copy the answer back
  anthropic                 the Claude API with its web search tool, asked by the program itself with your own key
  openai, ollama            any OpenAI-compatible endpoint (OpenAI, a local Ollama or LM Studio...). Without web access of
                            their own these answer from the model's memory: expect more errors, and rely on the checks
Add or change engines in ~/.config/placecompleter/engines.json (or the file named by $PLACECOMPLETER_ENGINES):
  {"engines": {"perplexity": {"kind": "browser", "label": "Perplexity", "url": "https://www.perplexity.ai/search?q={q}"},
               "anthropic": {"model": "the-model-you-pay-for"}}}
KEYS. Press "Key…" in the window (or let it open by itself when only a key is missing): a small window with a hidden field, and Test
(asks the service whether it accepts the key and knows the model, spending nothing: the models list of the service), Save and Remove.
The key is kept in the SYSTEM KEYRING (GNOME Keyring, KWallet...: encrypted, opened by your login), through libsecret or the secret-tool
command; with no keyring it is kept in a file only you can read (mode 600 in a folder of mode 700), NOT encrypted, and the window says so.
It is never put on a command line, in a log, in the Gramps database, in window.json or in any text of the window (only its public prefix,
its last four characters and its length, to recognise it), and it is sent only to the service itself. From the terminal:
  python3 -m placecompleter.cli keys anthropic --set | --test | --remove
When a service refuses a key (HTTP 401) the message names the server it was sent to and shows how to recognise the key (its public prefix, its
last four characters and its length, as the console of the service does), so that it can be compared with the key there; a key of the wrong
service (a Claude key given to OpenAI) is caught by its shape before anything is sent and is not kept. An AI that cannot work yet is never
remembered as the one the window opens with.
Order of lookup: the environment variable the engine names (for scripts), what the window saved, then a key_file of engines.json
(the file must be readable by you only). PLACECOMPLETER_KEYSTORE=none|file|keyring forces one place.
In the window every engine is marked: those that can
work come first; one that cannot (no key, no model name) says what to add and where, before anything is asked.
The engines command reports the state of each key without showing it (set or missing, its length, and what pasting may have
broken: spaces, quotes, a direction mark, a key that does not start with sk-ant-); a key refused with HTTP 401 gets a hint.
The API engines also send a strict system message (a reply of labelled lines only, remarks on a final NOTES: line, UNKNOWN only as
a whole value). The reader does not trust it: a remark in brackets is kept apart from a name, a unit written in the wrong column is
read from there, a unit called UNKNOWN is left out (the word UNKNOWN is never matched to a place of the tree), and a name given
without a period is not taken as valid for ever.
Calibrated on the real answer of the Claude API: the first column of a container line may hold a number, a code (19153) or UNKNOWN
(it is dropped); a period may have an unknown start or end ("UNKNOWN-1969"); the NOT_SURE line may be a paragraph of doubts, which is
shown in full ("the answer's own doubts").
Only the place name and the date are sent. Next to every saved answer a .meta.json records the engine, the model the service
reported (or "not disclosed"), the form of the question, a hash of the question and the time.

ai-complete opens Google in AI mode (the link carries udm=50, which a normal search page ignores) with the question
already asked, waits while you copy the answer, reads the clipboard (xclip, xsel or wl-paste) and prints the control
screen; the answer is kept in ~/gramps-place-work/answers/. search-ai only opens the link. The link of the long
question is about 1900 characters; use --short for long place names.

ingest-text reads an answer in the fixed template (agent/search_prompt.md) that you saved as a text file, matches every
administrative unit in it to the places of the tree, and prints the same control screen as complete-place: what
Gramps would display on that date, the units found or missing, what the answer contradicts in the tree (CONFLICT),
and what the answer itself is not sure about. A link in the tree that overlaps the answer's period is split, so that
other years keep their chain. Everything from a pasted answer has the basis "assumption". The regional packs (packs/*.json) serve as a dictionary: they
tell the reader that "Kingdom of Hungary" is the tree's "Magyarország". Text the page adds after the answer is ignored;
a name spelled like one the place already has is reported, not added; the name and link periods of matched units are
widened when the answer gives them more years. Checks on the answer itself: a place linked to itself is never proposed; an
answer that names the place one way but lists another name for that very date is called out; several names with the same
period are flagged; an answer whose sources have no full link is flagged as unverifiable. packs/world-basics.json holds
the names of countries in the languages of the tree (English, local, Hebrew), so that "United States" finds "USA".

Gaps: LINK gaps (no parent link covers the event date), NAME gaps ("?" shown
because no name covers the date). Proposals that need no outside source are
derived from the tree itself (a link that outlives its parent). The rest is a
list of what an outside source (Wikidata, a regional pack, an agent) must supply.

This folder is not yet a Gramps addon: the .gpr.py, the review window and the
Hebrew translation come in later steps.
