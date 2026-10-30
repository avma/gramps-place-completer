# Search prompt for the pasted-answer route

Observed with Google AI mode (October 2026): the classic form and the short form were answered every time; the long form
(classic + a sentence that the date matters + a DIFFERS_FROM_TODAY line) was answered "no answer for this search" both times it
was sent. The default is therefore classic; "dated" (classic + the sentence only) is there to find which part is refused.

The program (or you) fills in PLACE and DATE and sends this to Google (AI mode) or to a chatbot. The answer is
saved as a text file and read by `ingest-text`. Short form, tested with Google AI mode on Bajmok 1850:

    PLACE in DATE. Reply with exactly these labelled lines and nothing else, UNKNOWN if not sure. NAME: official name then, with language code. TYPE: settlement type then, local term. COORDINATES: decimal. HIERARCHY: one line per level, smallest to largest, as unit | type | years | state. SOURCES: URLs.

The long form below produced a perfectly parsable answer in Google AI mode (the labels of the template are
what the reader looks for). It insists that name, type and containers are those of the date, and asks DIFFERS_FROM_TODAY:
Google once returned the very same text for 1950 and for 1995, so an answer that does not depend on the date is a warning. For a chatbot use the long form; for Google use whichever fits the search box.

    Administrative history lookup. Place: PLACE. Date: DATE.
    Answer ONLY with the block below, in plain text: no introduction, no summary, no questions, no markdown, no bullets. Write UNKNOWN for anything you cannot verify; do not guess. Periods: YYYY-YYYY or YYYY-present. Name, type and containers must be those valid on DATE, not today's.

    PLACE_NAME_ON_DATE: <name in the language of the ruling state on that date>
    LANGUAGE: <code, e.g. hu, de, ro, sr>
    OTHER_NAMES: <code>: <name> (<from>-<to>), one per line
    SETTLEMENT_TYPE_ON_DATE: <hamlet / village / market town / town / city, plus the local historical term>
    COORDINATES: <latitude>, <longitude> (decimal degrees)
    CONTAINERS: one line per level, smallest unit first, up to the state, each as:
    <number> | <unit name as used then> | <unit type: local term and English> | <from>-<to> | <state>
    STATE_ON_DATE: <state or empire> | <from>-<to>
    DIFFERS_FROM_TODAY: <yes or no; if yes, what differs (name, type, containers)>
    SOURCES: one per line, at most 5: <full URL> | <what it supports>
    NOT_SURE: <uncertain items above>

    Every container must be valid on DATE. If the name is ambiguous, write AMBIGUOUS: followed by the candidates (name, country, coordinates) and stop.

What the program does with the answer: everything is an assumption until a source or you confirm it; each unit
is matched to a place of the tree (by name, with tolerance for spelling, and by whether its names are valid on the
date); what contradicts the tree is shown as a conflict and never selected automatically.
