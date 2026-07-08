# LyricsFAG v1.2.0 — release notes

*Shipped 2026-07-08. Minor release (v1.1.4 → v1.2.0).*

## TL;DR

Genius is now reliably sane: wiki/list pages such as `List of Virtual
YouTubers (VTubers)` — which used to dump 2000+ lines of name-registry
gibberish into the user's `.lrc` — are now rejected before the lyrics
chain falls through to the next provider. Wrong-song auto-corrects
(`"Yesterday"` by the Beatles matched to `"Imagine"` by John Lennon
because of a Genius typo-tolerant search) are also rejected with a
diagnostic that names the query and the response so the user can fix
their tags at a glance. As a bonus, the long-broken / dead-coded
title-tag instrumental heuristic, the ASCII backslash path docs in
`settings.py`, the `_VALID_DEMUCS` frozenset left over from v1.1.0's
demucs-toggle removal, and the paranoid `getattr(args, …)` defaults
on existing argparse arguments are all pruned so the codebase reads
cleanly ahead of the next minor cycle. No settings.json migration;
no CLI or GUI surface change.

## What's new

### Lyrics: Genius index-page filter — `LyricsFailure` on wiki/list bodies

Some Genius pages are wiki articles rather than songs — most
prominently `List of *` entries whose "lyrics" body is an
alphabet-navigation header (`A | B | C | … | Z`) followed by a
name-registry dump (`Kageyama Shien / 影山シエン (HOLOSTARS)`, …)
totalling thousands of lines. `lyricsgenius.search_song` happily
returns such a page when the user's audio tags happen to
partial-match the title; before v1.2.0 the lyrics chain then wrote
the entire registry into the user's `.lrc`. v1.2.0 inserts a
module-level `_classify_genius_text(text)` filter inside
`GeniusClient.get()` that rejects the body when **either** of two
*binary* signals fires:

* **Alphabet-navigation header.** The first 30 non-blank lines of
  the body contain ≥ 8 single-character ASCII alpha lines
  (`A`, `B`, `C`, …) — the form a Genius table-of-contents renders
  with each letter on its own cell. The predicate is
  `len(l) == 1 and l.isascii() and l.isalpha()` — strictly ASCII
  alpha — so a poetic song that legitimately opens with one CJK
  ideograph per line (think: a Japanese verse ending each line
  with a single kanji) cannot false-positive.
* **Long-body cap.** `text.count("\n")` exceeds 1000. Wiki articles,
  transcripts, and book chapters routinely run that long; even the
  longest reasonable song (Rap-God-class with explicit `[Verse]` /
  `[Chorus]` markers) renders to well under 300 lines in
  `lyricsgenius`' output, leaving ~3× safety margin.

The filter returns `(matched, why)` so `LyricsFailure.reason`
includes the diagnostic — e.g.

```
genius: page looks like a Genius list/index (alphabet-navigation header detected)
genius: page looks like a Genius list/index (body has 1107 lines (cap=1000))
```

The fetcher falls through to the next provider (LRCLIB, then
audio) instead of writing the wiki page into the `.lrc`.

### Lyrics: Genius song-mismatch auto-correct guard — token-set Overlap Coefficient

Even after the index-page filter, Genius can return a *real* song
whose title/artist partial-match the query when the user actually
wanted a different (less popular) one. A typo-tolerant search for
`"Yesterday" by "Beatles"` can match `"Imagine" by "John Lennon"`
on partial keyword overlap; v1.2.0 catches this with a
module-level `_is_genius_match(query_title, query_artist,
response_title, response_artist)` helper that requires
**token-set Overlap Coefficient** `|A ∩ B| / min(|A|, |B|)` ≥ 0.5
on BOTH title and artist independently. The metric is forgiving
for surface variants that don't change song identity:

* Leading `The` in artist names — `Beatles` query vs `The Beatles`
  response → score 1.0 after `the` is dropped at tokenisation.
* Featured artists — `Lose Yourself` by `Eminem` query vs
  `Lose Yourself feat. Rihanna` by `Eminem` response → score 1.0
  after `feat` is dropped.
* Release-variant suffixes — `Yesterday` query vs
  `Yesterday - Remastered 2009` response → score 1.0 after
  `remastered` is dropped.
* Common prepositions / articles in album/venue suffixes —
  `from`, `in`, `of`, `on`, `at`, `the`, `a`, `an` are dropped
  so a query of `Sounds` does not spuriously match
  `Sounds of Silence` only by article overlap.

…while still rejecting a wholly different song that shares one
common word with the query. The `LyricsFailure.reason` includes
both query and response strings plus the raw overlap scores so
the user can fix their tags without re-running:

```
genius: song mismatch: query 'Yesterday' by 'Beatles' != response 'Imagine' by 'John Lennon' (title=0.00, artist=1.00)
```

The same logic forgives abbreviated artist names (`M. Jackson`
vs `Michael Jackson` → 0.50 after tokenisation, exactly at
threshold) and partial artist last names (`Lennon` vs `John
Lennon` → 0.50).

### Cleanup: dead code + redundant paranoia

* `lyricsfag_lib/lyrics.py`: removed the `@staticmethod
  _looks_instrumental` and the compiled `_INSTRUMENTAL_TITLE_RE`
  regex (and their explanatory docstrings) — neither was called
  from the GUI/CLI; only the filename-based
  `_filename_blocks_audio` short-circuit on the audio branch is
  in use since v1.1.0. Updated `LyricsFetcher.fetch()`'s leading
  comment to reflect the actual current state.
* `lyricsfag_lib/settings.py`: removed `_VALID_DEMUCS` frozenset
  and the `demucs` key sanitization branch — the GUI's
  `_save_settings_snapshot` / `_apply_persisted_settings` never
  persisted that key post-v1.1.0 (when the on/off demucs
  combobox was removed in lockstep with the `--no-demucs` CLI
  flag), so the validator was reading dead data. Schema
  docstring updated to note that a pre-v1.1.0 `demucs` key in an
  old `settings.json` file is silently dropped.
* `lyricsfag.py` `_build_audio_analyzer`: replaced
  `getattr(args, "enable_demucs", True)` with a literal `True`
  plus a comment explaining the demucs-mandatory invariant
  (the `--enable-demucs` CLI flag was never added; the getattr
  was a no-op defaulting to True). Same simplification for
  `args.audio_model`, `args.audio_model_path`, `args.device`,
  which ARE registered on the parser and so didn't need
  getattr paranoia; the cleanup tightens the call sites to
  direct attribute access.
* Module-level `SyntaxWarning` fix: the `settings.py` module
  docstring had `\` immediately followed by non-escape
  characters in three Windows path examples
  (`%APPDATA%\LyricsFAG\…`) which triggered
  `SyntaxWarning: invalid escape sequence` under
  `python -W error::SyntaxWarning`. These are now `\\` so the
  docstring renders genuine backslashes and the warning is
  silenced.

## Upgrade notes

* **No code-level migration is required.** Drop-in upgrade from
  v1.1.4 — `settings.json` still loads cleanly, CLI flags / GUI
  widgets are unchanged, the lyrics chain's provider order is
  unchanged.
* Genius now rejects *bad* results more aggressively. Users with
  legitimately misspelled tags in their audio files will see
  `genius: no match` / `genius: song mismatch: …` / `genius:
  page looks like a Genius list/index (…)` log entries instead
  of silently bad `.lrc` files. The user-facing chain falls
  through to LRCLIB and then the local audio fallback so the
  overall hit-rate is unchanged for correctly-tagged files; the
  difference is that misclassified Genius hits now produce
  actionable diagnostics instead of garbage `.lrc` content.
* Python 3.x is unchanged. PyInstaller users rebuilding the
  `.exe` get the same sizes as v1.1.4 (~50 MB lite / ~3.5 GB
  portable); no new deps, no removed deps. `requirements.txt`
  / `requirements-audio.txt` are unchanged.

## Files changed

* `lyricsfag_lib/lyrics.py`:
  * **New module-level helpers** (above `class GeniusClient:`):
    `_classify_genius_text(text)` (alphabet-navigation header
    OR >1000-line cap, returns `(matched, why)`); the
    `_GENIUS_INDEX_HEAD_LEN`,
    `_GENIUS_INDEX_HEAD_MIN_SINGLE_CHARS`,
    `_GENIUS_INDEX_MAX_LINES` constants. `_is_genius_match(...)`
    (token-set Overlap Coefficient on title AND artist, both
    ≥ 0.5); `_genius_match_tokens(text)` / `_overlap_coef(a, b)`
    internals; the `_GENIUS_MATCH_THRESHOLD` and
    `_GENIUS_MATCH_STOPWORDS` constants (covers
    `the/a/an/in/of/on/at/from`, `feat/ft/featuring/with`,
    release variants `remastered/live/acoustic/radio/
    edit/edition/version/remix/mix/demo/take`, and a few
    Genius-noise tokens like `original/single/album/ost`).
  * `from itertools import islice` added to the stdlib imports
    (used in `_classify_genius_text` for early-exit on the
    head-sample).
  * `GeniusClient.get()`: after the empty-text check, calls
    `_classify_genius_text(text)`. On `(True, why)`, returns
    `LyricsFailure("genius", "page looks like a Genius
    list/index (<why>)")`. After the body filter, extracts
    `r_title = song.title or title` and `r_artist =
    _extract_name(primary, default=artist)`, calls
    `_is_genius_match(title, artist, r_title, r_artist)`, and on
    `(False, mismatch_why)` returns `LyricsFailure("genius", f"song mismatch: {mismatch_why}")`.
  * **Removed:** `LyricsFetcher._looks_instrumental` static
    method and the `_INSTRUMENTAL_TITLE_RE` compiled regex
    (no external callers — the title-tag short-circuit was
    *intended* but never wired into `process_one`; the regex
    was orphaned since v1.1.0's filename-only short-circuit).
    The `_INSTRUMENTAL_FILENAME_PATTERNS` /
    `_INSTRUMENTAL_FILENAME_RE` / `_filename_blocks_audio`
    triple (active on the audio branch since v1.1.0) is
    unchanged.
  * `LyricsFetcher.fetch()` leading comment: replaced the
    obsolete "instrumental title-tag short-circuit lives here"
    rationale with the actual current state (filename-based,
    gated to the `audio` branch via `_filename_blocks_audio`).
* `lyricsfag_lib/settings.py`:
  * Removed `_VALID_DEMUCS` frozenset and the `demucs` key
    sanitization branch in `sanitize()`. The Schema docstring
    entry is replaced with a one-line note that pre-v1.1.0
    `settings.json` files with a `demucs` key are silently
    dropped.
  * Module docstring: fixed `SyntaxWarning: invalid escape
    sequence` by changing three Windows path examples from
    `%APPDATA%\LyricsFAG\…` to
    `%APPDATA%\\LyricsFAG\\…` (so the docstring renders real
    backslashes and the file passes
    `-W error::SyntaxWarning`).
* `lyricsfag.py`:
  * `_build_audio_analyzer` simplified to direct
    `args.audio_model` / `args.audio_model_path or None` /
    `args.device` access (the getter-with-default idiom was
    redundant given these three are all registered on
    `build_parser`). The literal `enable_demucs=True` is
    hardcoded with an inline comment explaining the
    demucs-mandatory invariant.
  * The "Demucs on CPU is slow" warning no longer gates on
    `getattr(args, "enable_demucs", True)` — the same
    demucs-mandatory assumption.
* `lyricsfag_gui.py`:
  * Removed two stale `(demucs_label removed in v1.1.0 --
    demucs is now mandatory)` comments that referenced widgets
    deleted in v1.1.0. They're not needed; the code below
    them (audio_model_path_label, etc.) is the only audio row.
* `lyricsfag_lib/__init__.py`:
  * `__version__` bumped `1.1.4 → 1.2.0`.

## Backward compatibility

* **Non-breaking.** No API or config-file schema change. CLI
  flags / GUI widgets / `settings.json` keys are unchanged.
  Audio and lyrics chain provider order is unchanged.
* Genius misclassification rejection (`LyricsFailure` instead
  of silent bad `.lrc`) is the only user-visible behavioural
  change; it improves correctness without affecting the hit-rate
  on correctly-tagged audio files.
* The cleanup pass removes no functionality and no public
  surface — `_looks_instrumental` and `_INSTRUMENTAL_TITLE_RE`
  were private (`_`-prefixed) helpers with no callers anywhere
  in the codebase, and the `_VALID_DEMUCS` / `demucs`-key
  sanitization was reading dead data because the GUI's
  `_save_settings_snapshot` / `_apply_persisted_settings`
  never persisted that key post-v1.1.0.


---

# LyricsFAG v1.2.0 — заметки о релизе

*Выпущено 2026-07-08. Минорный релиз (v1.1.4 → v1.2.0).*

## TL;DR

Genius теперь надёжно разумен: wiki/list-страницы вроде
`List of Virtual YouTubers (VTubers)` — которые раньше высыпали
в пользовательский .lrc по 2000+ строк мусорного name-registry
— теперь отбраковываются до того, как lyrics-цепочка
передаёт управление следующему провайдеру. Wrong-song
auto-corrects (`"Yesterday"` by the Beatles ошибочно
резолвится в `"Imagine"` by John Lennon благодаря typo-tolerant
поиску Genius) тоже отбраковываются с диагностикой, которая
называет query и response, чтобы пользователь мог
мгновенно поправить свои теги. Бонусом: давно сломанный /
мёртвый title-tag инструментальный heuristic, ASCII backslash-
пути в доках settings, оставшийся от v1.1.0 `_VALID_DEMUCS`
frozenset и параноидальные `getattr(args, …)` дефолты на
реальных argparse-аргументах — всё прибрано, чтобы кодовая
база читалась чисто перед следующим минорным циклом. Без
миграции settings.json; без изменений CLI или GUI-поверхности.

## Что нового

### Lyrics: Genius index-page filter — `LyricsFailure` на wiki/list-телах

Некоторые страницы Genius — это wiki-статьи, а не песни —
особенно `List of *`-страницы, чьё "lyrics" тело — это
alphabet-navigation header (`A | B | C | … | Z`), за которым
следует name-registry дамп (`Kageyama Shien / 影山シエン
(HOLOSTARS)`, …) на тысячи строк. `lyricsgenius.search_song`
с удовольствием возвращает такую страницу, когда аудио-теги
пользователя случайно частично матчат заголовок; до v1.2.0
lyrics-цепочка затем писала весь реестр в пользовательский
`.lrc`. v1.2.0 вставляет модульный `_classify_genius_text(text)`
фильтр внутрь `GeniusClient.get()`, который отбраковывает
тело, когда срабатывает **любой** из двух *бинарных* сигналов:

* **Alphabet-navigation header.** Первые 30 непустых строк
  тела содержат ≥ 8 одиночных ASCII alpha символов (`A`, `B`,
  `C`, …) — форму, в которую Genius переводит содержимое
  своего table-of-contents, по одной букве на ячейку.
  Предикат — `len(l) == 1 and l.isascii() and l.isalpha()` —
  строго ASCII alpha, чтобы поэтическая песня, легитимно
  открывающаяся одним CJK иероглифом на строке (представьте
  японский куплет, где каждая строка заканчивается одним
  кандзи), не срабатывала false-positive.
* **Long-body cap.** `text.count("\n")` превышает 1000. Wiki-
  статьи, транскрипты и главы книг обычно такой длины; даже
  самая длинная разумная песня (уровня Rap God с явными
  `[Verse]` / `[Chorus]` маркерами) рендерится в well under
  300 строк в выходе `lyricsgenius`, оставляя ~3× запаса.

Фильтр возвращает `(matched, why)` так что
`LyricsFailure.reason` включает диагностику — например:

```
genius: page looks like a Genius list/index (alphabet-navigation header detected)
genius: page looks like a Genius list/index (body has 1107 lines (cap=1000))
```

Fetcher передаёт управление следующему провайдеру (LRCLIB,
потом audio) вместо записи wiki-страницы в `.lrc`.

### Lyrics: Genius song-mismatch auto-correct guard — token-set Overlap Coefficient

Даже после index-page фильтра Genius может вернуть *реальную*
песню, чей title/artist частично матчат query, когда
пользователь на самом деле хотел другую (менее популярную).
Typo-tolerant поиск по `"Yesterday" by "Beatles"` может
заматчить `"Imagine" by "John Lennon"` на частичном keyword-
overlap; v1.2.0 ловит это модульным
`_is_genius_match(query_title, query_artist, response_title,
response_artist)` хелпером, который требует **token-set Overlap
Coefficient** `|A ∩ B| / min(|A|, |B|)` ≥ 0.5 на ОБА title и
artist независимо. Метрика прощает поверхностные варианты,
не меняющие song-identity:

* Ведущий `The` в именах артистов — `Beatles` query против
  `The Beatles` response → score 1.0 после того, как `the`
  отбрасывается при токенизации.
* Featured-артисты — `Lose Yourself` by `Eminem` query
  против `Lose Yourself feat. Rihanna` by `Eminem` response
  → score 1.0 после того, как `feat` отбрасывается.
* Release-variant суффиксы — `Yesterday` query против
  `Yesterday - Remastered 2009` response → score 1.0 после
  отбрасывания `remastered`.
* Распространённые предлоги/артикли в album/venue
  суффиксах — `from`, `in`, `of`, `on`, `at`, `the`, `a`,
  `an` отбрасываются, так что query `Sounds` не матчит
  false-positive `Sounds of Silence` только за счёт article
  overlap.

…при этом всё ещё отбраковывает совсем другую песню,
которая шарит одно общее слово с query. `LyricsFailure.reason`
включает строки query и response, плюс сырые overlap-скоры,
чтобы пользователь мог поправить теги без re-run:

```
genius: song mismatch: query 'Yesterday' by 'Beatles' != response 'Imagine' by 'John Lennon' (title=0.00, artist=1.00)
```

Та же логика прощает сокращённые имена артистов (`M. Jackson`
vs `Michael Jackson` → 0.50 после токенизации, ровно на
грани) и частичные фамилии (`Lennon` vs `John Lennon` →
0.50).

### Cleanup: мёртвый код + избыточная паранойя

* `lyricsfag_lib/lyrics.py`: удалены `@staticmethod
  _looks_instrumental` и скомпилированный `_INSTRUMENTAL_TITLE_RE`
  regex (и их пояснительные docstring) — ни один не
  вызывался из GUI/CLI; только filename-based
  `_filename_blocks_audio` шорткат на audio-ветке в
  активном использовании с v1.1.0. Лидирующий комментарий
  `LyricsFetcher.fetch()` обновлён под актуальное состояние.
* `lyricsfag_lib/settings.py`: удалены `_VALID_DEMUCS`
  frozenset и ветка санитизации ключа `demucs` — GUI'шные
  `_save_settings_snapshot` / `_apply_persisted_settings`
  никогда не персистили этот ключ после v1.1.0 (когда
  demucs on/off combobox был удалён в lockstep с CLI-флагом
  `--no-demucs`), так что валидатор читал мёртвые данные.
  Schema-docstring обновлён короткой заметкой, что
  pre-v1.1.0 `settings.json`-файлы с ключом `demucs` молча
  отбрасываются.
* `lyricsfag.py` `_build_audio_analyzer`: `getattr(args,
  "enable_demucs", True)` заменён на литеральный `True` плюс
  комментарий, поясняющий инвариант обязательности demucs
  (CLI-флаг `--enable-demucs` никогда не добавлялся, так что
  getattr был no-op, дефолтящим в True). То же упрощение
  для `args.audio_model`, `args.audio_model_path`,
  `args.device`, которые РЕГИСТРИРУЮТСЯ в парсере и так не
  нуждались в getattr-паранойе; cleanup затягивает call-
  сайты на прямой attribute-access.
* Module-level `SyntaxWarning`-фикс: в docstring модуля
  `settings.py` стоял `\` сразу перед не-escape символами в
  трёх Windows-path примерах
  (`%APPDATA%\LyricsFAG\…`), что триггерило
  `SyntaxWarning: invalid escape sequence` под
  `python -W error::SyntaxWarning`. Теперь это `\\`,
  docstring рендерит реальные backslash'и, варнинг замолкает.

## Заметки по обновлению

* **Кодовой миграции не требуется.** Drop-in апгрейд с
  v1.1.4 — `settings.json` по-прежнему загружается чисто,
  CLI-флаги / виджеты GUI не изменились, порядок
  провайдеров в lyrics-цепочке не изменился.
* Genius теперь отбраковывает *плохие* результаты более
  агрессивно. Пользователи с легитимно опечатанными тегами
  в аудио-файлах увидят `genius: no match` / `genius: song
  mismatch: …` / `genius: page looks like a Genius
  list/index (…)` записи в логе вместо молча плохих
  `.lrc`-файлов. User-facing цепочка передаёт управление на
  LRCLIB, потом локальный audio-fallback, так что общий
  hit-rate не меняется для корректно-тегированных файлов;
  разница в том, что неправильно классифицированные
  Genius-хиты теперь дают actionable-диагностику вместо
  мусорного `.lrc`-контента.
* Python 3.x не изменился. Пользователи PyInstaller,
  пересобирающие `.exe`, получат те же размеры, что и в
  v1.1.4 (~50 МБ lite / ~3.5 ГБ portable); ни новых
  зависимостей, ни удалённых. `requirements.txt` /
  `requirements-audio.txt` неизменны.

## Изменённые файлы

* `lyricsfag_lib/lyrics.py`:
  * **Новые модульные хелперы** (над
    `class GeniusClient:`): `_classify_genius_text(text)`
    (alphabet-navigation header ИЛИ >1000-line cap,
    возвращает `(matched, why)`), и константы
    `_GENIUS_INDEX_HEAD_LEN`,
    `_GENIUS_INDEX_HEAD_MIN_SINGLE_CHARS`,
    `_GENIUS_INDEX_MAX_LINES`. `_is_genius_match(...)`
    (token-set Overlap Coefficient на title И artist,
    оба ≥ 0.5); внутренности `_genius_match_tokens(text)` /
    `_overlap_coef(a, b)`; константы
    `_GENIUS_MATCH_THRESHOLD` и `_GENIUS_MATCH_STOPWORDS`
    (покрывают
    `the/a/an/in/of/on/at/from`,
    `feat/ft/featuring/with`, release-варианты
    `remastered/live/acoustic/radio/edit/edition/version/
    remix/mix/demo/take`, плюс несколько Genius-шумовых
    токенов вроде `original/single/album/ost`).
  * `from itertools import islice` добавлен в stdlib-
    импорты (используется в `_classify_genius_text` для
    early-exit на head-sample).
  * `GeniusClient.get()`: после проверки на пустой текст
    вызывается `_classify_genius_text(text)`. На
    `(True, why)` возвращает `LyricsFailure("genius",
    "page looks like a Genius list/index (<why>)")`.
    После индексации-фильтра извлекаются
    `r_title = song.title or title` и `r_artist =
    _extract_name(primary, default=artist)`, вызывается
    `_is_genius_match(title, artist, r_title, r_artist)`,
    и на `(False, mismatch_why)` возвращает
    `LyricsFailure("genius", f"song mismatch: {mismatch_why}")`.
  * **Удалено:** `LyricsFetcher._looks_instrumental`
    static-method и скомпилированный `_INSTRUMENTAL_TITLE_RE`
    regex (нет внешних вызывающих — title-tag шорткат был
    *задуман*, но никогда не подключён к `process_one`;
    regex оставался осиротевшим с v1.1.0). Тройка
    `_INSTRUMENTAL_FILENAME_PATTERNS` /
    `_INSTRUMENTAL_FILENAME_RE` /
    `_filename_blocks_audio` (активна на audio-ветке с
    v1.1.0) не тронута.
  * Лидирующий комментарий `LyricsFetcher.fetch()`:
    устаревшая формулировка про "instrumental title-tag
    short-circuit lives here" заменена на актуальное
    состояние (filename-based, гейтится на `audio`-ветке
    через `_filename_blocks_audio`).
* `lyricsfag_lib/settings.py`:
  * Удалены `_VALID_DEMUCS` frozenset и ветка санитизации
    ключа `demucs` в `sanitize()`. Schema-docstring
    обновлён короткой заметкой, что pre-v1.1.0
    `settings.json`-файлы с ключом `demucs` молча
    отбрасываются.
  * Module-docstring: исправлен `SyntaxWarning: invalid
    escape sequence` — три Windows-path примера изменены
    с `%APPDATA%\LyricsFAG\…` на
    `%APPDATA%\\LyricsFAG\\…` (docstring теперь
    рендерит реальные backslash'и, файл проходит
    `-W error::SyntaxWarning`).
* `lyricsfag.py`:
  * `_build_audio_analyzer` упрощён на прямой
    `args.audio_model` / `args.audio_model_path or None` /
    `args.device` доступ (идиома getter-with-default была
    избыточной, так как эти три регистрируются в
    `build_parser`). Литеральный `enable_demucs=True`
    хардкоден с inline-комментарием, поясняющим инвариант
    обязательности demucs.
  * "Demucs on CPU is slow" варнинг больше не гейтится на
    `getattr(args, "enable_demucs", True)` — то же
    допущение обязательности demucs.
* `lyricsfag_gui.py`:
  * Удалены два устаревших комментария
    `(demucs_label removed in v1.1.0 -- demucs is now
    mandatory)`, ссылавшихся на виджеты, удалённые в
    v1.1.0. Они не нужны; код под ними
    (audio_model_path_label и т.п.) — единственная audio-
    row.
* `lyricsfag_lib/__init__.py`:
  * `__version__` бамп `1.1.4 → 1.2.0`.

## Обратная совместимость

* **Без ломающих изменений.** Никаких изменений API или
  схемы config-файла. CLI-флаги / виджеты GUI / ключи
  `settings.json` не изменились. Порядок провайдеров в
  audio и lyrics-цепочке не изменился.
* Genius misclassification rejection (`LyricsFailure`
  вместо молча плохого `.lrc`) — единственное видимое
  пользователю поведенческое изменение; улучшает
  корректность, не влияя на hit-rate для корректно-
  тегированных аудиофайлов.
* Cleanup-проход не удаляет функциональности и публичной
  поверхности — `_looks_instrumental` и
  `_INSTRUMENTAL_TITLE_RE` были приватными (`_`-prefixed)
  хелперами без вызывающих где-либо в кодовой базе, а
  `_VALID_DEMUCS` / `demucs`-key санитизация читала мёртвые
  данные, потому что GUI'шные
  `_save_settings_snapshot` /
  `_apply_persisted_settings` никогда не персистили этот
  ключ после v1.1.0.
