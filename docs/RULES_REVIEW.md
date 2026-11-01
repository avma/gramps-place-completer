# Which Rules Do We Really Need? (A Review After the "Table" Format)

The initial concept was modest: prompt an AI for a place's type, administrative hierarchy levels, and geographic coordinates, and commit them directly to Gramps instead of entering them manually.

The rules detailed in `ANALYZER_RULES.md` evolved around this concept because early AI responses consisted of unstructured, free-form text, and existing user data in the family tree required strict protection.

With the introduction of the structured `table` format (Table 10), responses are returned in a standardized tabular format. Consequently, several legacy rules may no longer be necessary. This document defines the evaluation methodology used to determine candidate rules for removal, rather than declaring immediate deprecation.

---

## The Groups (An Initial Classification)

*The ultimate decision for each group depends on empirical evaluation.*

| Group | Rules Included | What It Protects | Decision Strategy |
|---|---|---|---|
| **A. Tree Data Integrity** | **P0** (existing data modified only with explicit individual approval), **T1–T5** (prohibitions against self-enclosure, circular loops, and identical-type nesting), **C1, C2, C4** (prepending new hierarchy links before existing ones without altering legacy records), stale-state writer checks, atomic Undo operations, and preservation of user-defined custom place types. | User data integrity | **Retain unconditionally**, regardless of empirical evidence. |
| **B. Unstructured Text Handling** | **ST1–ST6** (closed-vocabulary place type taxonomy), **LV1** (overlapping administrative structures), **TB5** (parsing reversed/RTL historical year ranges), standard term dictionaries (`SETTLEMENT_TYPES` and `CONTAINER_TYPES`), deduplication logic (co-named levels and sovereign states), top-of-chain rules (a chain that ends at a state with no country above it), the rule that the first level is the parent (*Sissa* case), inferred name active periods, self-contradiction detection, `compare_with_saved`, echo testing, and multi-prompt template fallbacks. | Formatting variations or ambiguous AI responses | **Evaluate empirically** using the replay benchmark. |
| **C. Existing Link Reconciliation** | **C3, C5, C6, C7** (date boundary adjustments, invalid link disconnections, link truncation), `rename-place`, `set-name-language`. | Existing database hierarchy accuracy | **Evaluate empirically**: triggered against database records, not raw AI responses. |
| **D. Extended Capabilities** | **LK1–LK5** (web link processing), **CT1–CT5** (citation routing and caps), **Table 7** (Wikidata entity links), automated Wikidata coordinate lookups, Wikipedia language prioritization. | Non-core functional enhancements | **User-configured**: retained or removed based on user preference. |

---

## The Evaluation Methodology

1. **Collect `table`-format AI Responses (~20 samples):**
   * *Manual Collection:* Use the addon interface set to `manual` engine mode (responses are saved to `~/gramps-place-work/answers`; move existing folders aside to avoid overwriting).
   * *Automated Collection:* Run `python3 tools/collect_answers.py` using an API-keyed engine (Claude, OpenAI, or Ollama) to query a diverse set of historical test places and output to `~/gramps-place-work/answers-table`.
     * Utility flags: `--check` verifies engine readiness, `--dry-run` displays prompts, `--report --db SNAPSHOT` executes Step 2 reporting.
   * *Required Diversity:* Include diverse geographic and historical contexts:
     * **France:** Aussonne (1997), Blagnac (2026), Toulouse, Paris (1980)
     * **Italy:** Parma (1990), Sissa (1990)
     * **Central/Eastern Europe:** Bajmok (1877), Hadad (1900), Zombor (1850)
     * **Israel:** Kfar Hess
     * **United States:** Johnston (1950, ambiguous entity)
     * **Variations:** Small villages, major metropolises, entities with historical name changes, and entities with shifting sovereign allegiance.

2. **Execute Read-Only Replay Analysis:**
   Run `python3 tools/replay_answers.py --db PATH-TO-SNAPSHOT-SQLITE` against a representative database snapshot (since tree-dependent rules require database context to fire). The tool outputs trigger counts for every proposal type and rule message, generating a detailed summary table.

3. **Evaluate Results Against Three Criteria (Groups B, C, and D):**
   * Did the rule fire, and across how many sample responses?
   * When triggered, did the rule execute correctly?
   * What is the impact of removing the rule: **data loss or database corruption** (rule must be retained), or merely a redundant UI note/proposal (rule can be safely removed)?

4. **Deprecation Criteria:**
   A rule is eligible for removal **only if** it never triggers (or triggers in fewer than 1 in 20 responses) **and** its absence poses zero risk to database integrity. Protective data-integrity rules are retained regardless of trigger frequency.

5. **Staged Removal Process:**
   Approved deprecations are carried out in distinct, incremental steps, each delivered as its own installer together with its tests (and committed on its own), so that any step can be reversed.

---

## Feature Switches (`placecompleter/rules.py`)

Every rule is assigned a unique identifier and can be dynamically toggled off for experimental verification (not exposed as end-user settings). When all switches are enabled (the default state), behavior remains standard.

Defined rule categories in `rules.py`:
* **AI Response and Feature Rules:** `ST3`, `ST6`, `LV1`, `LV2`, `LV3`, `LK`, `WL`, `CT2`, `CT4`, `CT5`.
* **Name Active Period Rules:** `NP1` (a name's years end it only when a later name is given), `NP3` (a name starts when the state that ruled then began) and `NP5` (a name of a level gets the period from the response). `NP3` and `NP5` are disabled by default. *Note: Rules `NP2`, `NP4`, and `NP6` were removed (see Table 12 of `ANALYZER_RULES.md`).*
* **Hierarchy Nesting and Link Rules:** `T1`, `T2` (`T2–T4`), `C3`, `C4`, `C5`, `C6` (`C6` and `C7`), `C8`.
* **Identity and Localization Rules:** `ID1` (disambiguates distant co-named places) and `NL` (governs administrative level name language tagging).
* **Default-Disabled Rules (`DEFAULT_OFF`):** `NP3`, `NP5` and `NL`. They can be enabled explicitly via `PLACECOMPLETER_RULES_ON=NP3,NP5,NL`, or evaluated during ablation runs using `--ablate`.
* **Analysis UI Notes:** Individual rules `M01` through `M52`, one for each note (the numbers of the notes that were removed, Table 12 of `ANALYZER_RULES.md`, are missing). Unit tests verify that every note belongs to a rule and every rule has a note.
* **Non-Switchable Core Rules:** Permanently active rules listed for completeness: `P0` (strict approval for existing data edits), `C1–C2` (hierarchy chain instantiation and matching-link preservation), `C9` (preservation of user-deselected administrative levels).

### Ablation and Diagnostic Controls

* `python3 tools/replay_answers.py --db SNAPSHOT --ablate`
  Sequentially disables each rule across saved test answers, printing net changes in generated proposals and UI notes. A rule that yields zero net changes across all samples is a candidate for removal; a rule affecting only UI notes represents informational feedback rather than functional logic.
* `--without M51,LV1`
  Disables specified rules for a standard reporting run.
* `PLACECOMPLETER_RULES_OFF=M51,LV1`
  Environment variable setting that disables specified rules across any execution of the program.
* **Non-Replay Features:** `WL`, `CT2`, `CT4`, and `CT5` operate during Wikidata interaction and database commit phases. They are evaluated via active database write tests (`test_rules.py`) rather than dry-run replays.

When a decision is made to deprecate a rule, toggling its switch serves as the initial step to verify test and response behavior, followed by code removal in a unified release build.

---

## Limitations of Replay Analysis

* **Sample Size Sensitivity:** The evaluation counts rule triggers across the available sample set. Rules designed to handle rare AI edge cases (e.g., occurring once in 100 responses) may not trigger within a 20-response test run.
* **Unsampled Edge Cases:** A rule with zero triggers may still safeguard a scenario not present in the current evaluation set. Consequently, **Group A rules are permanently exempt from automated removal.**
* **Evolving AI Engine Behavior:** AI models evolve over time and may alter response patterns. Empirical evaluations should be re-run periodically after extended real-world usage.
