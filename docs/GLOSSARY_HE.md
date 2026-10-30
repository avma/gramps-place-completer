# The Hebrew words of Gramps for the terms that the addon uses

The addon's Hebrew follows the official words of Gramps (the rule of the project: *official Gramps terms*). They are read from the catalog of Gramps itself
(`gramps.mo`) and differ in a few words between the versions: where they differ, the version of the user's tree is the one to follow. The names of the types of
places (Town, Village ...) are not translated by the addon at all: the window shows the word that Gramps shows (`kinds.type_name`).

| English | Gramps 6.0.8 | Gramps 6.1 |
|---|---|---|
| Place | מקום | מקום |
| Places | מקומות | מקומות |
| Repository | מאגר | מאגר |
| Repositories | מאגרים | מאגרים |
| Source | מקור | מקור |
| Sources | מקורות | מקורות |
| Citation | מובאה | מובאה |
| Citations | מובאות | מובאות |
| Note | הערה | הערה |
| Notes | הערות | הערות |
| Confidence | ודאות | ודאות |
| Enclosed By | מוכל בתוך | מוכל בתוך |
| Edit | עריכה | עריכה |
| Undo | הסגה | הסגה |
| Merge Places | מיזוג מקומות | מיזוג מקומות |
| Name | שם | שם |
| Type | סוג | סוג |
| Date | תאריך | תאריך |
| Language | שפה | שפה |
| Latitude | קו רוחב | קו רוחב |
| Longitude | קו אורך | קו אורך |
| Alternative Names | שמות חלופיים | שמות חלופיים |
| Place Name | שם המקום | שם המקום |
| Event | אירוע | אירוע |
| Events | אירועים | אירועים |
| Tool | כלי | כלי |
| Tools | כלים | כלים |
| Gramplet | גרמפלט | גרמפלט |
| Apply | החלה | החלה |
| Cancel | ביטול | ביטול |
| Close | סגירה | סגירה |
| Select | בחירה | בחירה |
| Remove | הסרה | הסרה |
| Download | הורדה | הורדה |
| Title | תואר | תואר |
| Code | קוד | קוד |
| Private | פרטי | פרטי |
| Tag | תג | תג |
| Quick View | מצג מהיר | מצג מהיר |

## The guidelines of the Hebrew translation (`הנחיות תרגום גרמפס ויקי לעברית`, version 2026-05-11.1)

The Hebrew of the addon follows the guidelines that the owner keeps for the translation of the Gramps wiki, in the parts that apply to an interface (the sections about
MediaWiki code, images, anchors and the output in a wiki block do not apply to a catalog of texts).

| Rule | What it means in the addon |
|---|---|
| 1.1 indirect address, always | no imperative (*בחר*, *הזן*, *לחץ*, *בדוק*): an action noun (*בחירת*, *הזנת*, *בדיקת*), or *יש ל…* (*יש לבחור*, *יש להקיש*); the buttons are action nouns too (*שליחה*, *ניתוח*, *החלה*) |
| 1.2 one term, one word | the same Hebrew for a label everywhere (the name of a button in the sentences that name it) |
| 1.3 the agreed dictionary first, then the Academy | the table below; the words of the Gramps interface where the guidelines say nothing (*הסגה*, *מיזוג מקומות*, *ודאות*) |
| 1.4 pure Hebrew | *מיזם, מלל, מסמך, מדומה*; and so *בינה מלאכותית* (not *AI*), *מסוף* (not *טרמינל*), *לוח בקרה* (not *Console*) |
| 1.7, 1.8 direction | a path, a file name, a command, an address or an identifier inside a Hebrew sentence is wrapped in LRE ... PDF (U+202A ... U+202C), also the `%s` that stands for one |
| 1.9, 4.4 code is not translated | commands (`ollama pull`, `chmod 600`), keys of the settings (`key_file`, `base_url`), names of the forms of the question (`auto`, `table` ...) stay in Latin letters |
| 1.13 *ש־* | used where it is natural (*שנשלח*, *ששמורה*) |
| 2.1 mouse | click = *הקשה* (*יש להקיש על ...*) |
| 2.2 start and open | start Gramps = *אתחול גרמפס*; launch = *שיגור*; restart = *שתחול*; reset = *שיצוב*; open (a file, a window) = *פתיחה* |
| 2.4 | *לדוגמה* (not *למשל*), *ועוד* (not *וכו'*), *כלומר*, *הערה*, *אזהרה*, *דוגמה* |
| 2.5 arrows | the path of a menu is `←` : *עריכה ← הסגה*, *עריכה ← מיזוג מקומות* |
| 2.6 | *גרמפס* (masculine); *גרמפלט* |

| English | Hebrew (guidelines) | English | Hebrew (guidelines) |
|---|---|---|---|
| family tree | אילן־יוחסין (*אילן־היוחסין*) | hierarchy | מדרג |
| coordinates | נקודות־ציון | clipboard | לוח־גזירים |
| password | ססמה | Internet, web | מרשתת |
| text | מלל | project | מיזם |
| citation | מובאה | repository | מאגר |
| place, location | מקום, מיקום | settlement, village | יישוב, כפר |
| format | תסדיר | template | תבנית |
| page | עמוד | button | לחצן |
| interface | מנשק | widget | יישומון |
| alternative | חלופי | specific, unique, single | מסוים, ייחודי, יחיד |
| version | גרסה | package | חבילה |
| database | מסד־נתונים | directory | מחיצה |
| automatic | אוטומטי | virtual | מדומה |

### Where the addon departs from the guidelines (each is a choice that the owner can change)

1. **Arrows between names of places** (`Sissa -> Provincia di Parma`, `Parma -> Italy`) stay `->`. The rule 2.5 is about paths of menus and sequences of actions. Between Latin names the
   run is left-to-right, so `←` would read backwards (Provincia to Sissa); the `>` of `->` is mirrored by the display in a right-to-left run, so it is right in both.
2. **Undo is *הסגה*** (the label of Gramps in the menu *עריכה*), not *להסיג*, because a text that names a menu must name what the user sees (rule 1.2).
3. **The names of the types of places** are not translated by the addon: the window shows what Gramps shows (`kinds.type_name`), so *Locality* is the word of the Gramps version in use.
4. **Names of products** stay in Latin letters, in direction marks (*Ollama*, *Claude*, *Wikidata*, *Google AI mode*). *API*, *GB*, *ASCII*, *HTTP* too.
5. **The button *Ask* is *שליחה*** (an action noun: the question is sent to the AI or copied for a browser); *Analyze* is *ניתוח*, *Apply checked changes* is *החלת השינויים שסומנו*.
6. **The quotation marks** around the name of a button are ״ ״ and around names of places « »; the guidelines do not say.
