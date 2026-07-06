# Release 1.1.2

Hotfix: `INSTRUMENTAL_FILENAME_RE` boundary class widened from a
narrow ASCII set to Unicode-aware `\b`, so filenames with parens,
brackets, braces, quotes, colons, or commas around the keyword now
correctly short-circuit the audio branch.

## What's new

### Fix: filenames like `Song (Off Vocal).flac` are no longer sent to demucs+whisper

v1.1.0's filename-based short-circuit for the audio branch compiled
its keyword anchors with the narrow ASCII boundary class `[\s\-_.]`
(whitespace, hyphen, underscore, dot). That class does NOT include
parens, brackets, braces, quotes, colons, or commas — so filenames
where the keyword is wrapped in any of those punctuation chars
silently failed the boundary check and the track fell through to
the demucs+whisper audio branch.

User's bug report: `Song (Off Vocal).flac` and similar files were
still being processed with demucs+whisper despite the filename
clearly marking them as off-vocal.

The fix replaces `[\s\-_.]` with `\b` (Unicode word boundary) in
`_INSTRUMENTAL_FILENAME_RE`. Python 3's default `re` module is
Unicode-aware, so `\b` correctly treats parens, brackets, braces,
quotes, colons, commas, Cyrillic letters, and CJK as word
boundaries. All the user's reported cases now match:

- `Song (Off Vocal).flac` → BLOCKED
- `Song [Off Vocal].flac` → BLOCKED
- `Song {Backing Track}.flac` → BLOCKED
- `Song "Off Vocal".flac` → BLOCKED
- `Song, Off Vocal.flac` → BLOCKED
- `Song : Off Vocal.flac` → BLOCKED
- `[Instrumental] Take On Me.flac` → BLOCKED
- Cyrillic variants (`Песня (Караоке).flac`, `Песня-Инструментал.flac`,
  CamelCase `ПесняИнструментал.flac`) → BLOCKED

The false-positive guards are preserved:

- `tracklist.flac` → still does NOT match `backing track`
- `TheInstrumentalization.flac` → still does NOT match
  `instrumental` (no word boundary between `l` and `i`)
- `Inoffensive.flac` → still does NOT match `off vocal` (no space)
- `Nonvocal.flac` → still does NOT match `no vocal` (no word
  boundary between `n` and `o`)

The change is in `lyricsfag_lib/lyrics.py` — only the two regex
boundary lines (`r"\b("` and `r")\b"`) inside the compiled
`_INSTRUMENTAL_FILENAME_RE`. The pattern list, the CamelCase
normalisation split (ASCII + Cyrillic), and the
`_filename_blocks_audio` method are unchanged.

### Cleanup: dead `offvocal` / `novocal` patterns removed

The previous session added `offvocal` and `novocal` to
`_INSTRUMENTAL_FILENAME_PATTERNS` as belt-and-suspenders entries
for all-lowercase filenames like `songoffvocal` where the
CamelCase split doesn't fire. Those patterns cannot match with the
new `\b` boundary (there's no word boundary between two adjacent
word characters, e.g. between `g` and `o` in `songoffvocal`), so
they were removed as dead code. The real-world cases (CamelCase
`SongOffVocal`, separator-based `Song-Off-Vocal`, `Song_Off_Vocal`,
`Song Off Vocal`) are all handled by the existing `off vocal`
pattern + the CamelCase normalisation split + the new `\b`
boundary.

### Versioning

`lyricsfag_lib.__version__` was bumped from `1.1.0` to `1.1.2` to
sync the package version with the git tag chain (the v1.1.1 tag
landed without bumping the constant).

## Heads-up

- This is a hotfix on top of v1.1.1. **Upgrade is recommended for
  all v1.1.0 / v1.1.1 users** — the affected filenames are the
  most common off-vocal / karaoke naming conventions.
- v1.0.x users are unaffected.
- The portable build is unchanged; just re-run
  `build.bat portable` if you want a fresh `.exe` that matches this
  tag.
- **Known follow-up:** the comment block above the compiled regex
  in `lyricsfag_lib/lyrics.py` (~lines 454-459) still describes the
  old `[\s\-_.]` class and the old "cheaper than 11" pattern count.
  The exact-match anchor for the comment update failed during the
  fix script run due to a 2-backslash escaping issue. The code is
  correct; the comment is just misleading. Will be addressed in a
  v1.1.3 doc-only patch.

---

# Релиз 1.1.2

Хотфикс: boundary-класс в `INSTRUMENTAL_FILENAME_RE` расширен с
узкого ASCII-набора на Unicode-aware `\b`, так что имена файлов
с круглыми/квадратными/фигурными скобками, кавычками, двоеточиями
или запятыми вокруг ключевого слова теперь корректно шорткатят
аудио-ветку.

## What's new (RU)

### Фикс: файлы вида `Song (Off Vocal).flac` больше не уходят в demucs+whisper

Шорткат по имени файла для аудио-ветки в v1.1.0 якорил ключевые
слова узким ASCII-классом `[\s\-_.]` (пробел, дефис, подчёркивание,
точка). Этот класс НЕ включает круглые/квадратные/фигурные скобки,
кавычки, двоеточия и запятые — поэтому имена файлов, где ключевое
слово обёрнуто в любой из этих знаков препинания, молча проваливали
boundary-проверку и трек уходил в аудио-ветку demucs+whisper.

Баг-репорт пользователя: `Song (Off Vocal).flac` и подобные
файлы по-прежнему обрабатывались через demucs+whisper, несмотря
на то, что имя файла явно маркировало их как off-vocal.

Фикс заменяет `[\s\-_.]` на `\b` (Unicode word boundary) в
`_INSTRUMENTAL_FILENAME_RE`. Дефолтный `re`-модуль в Python 3
Unicode-aware, поэтому `\b` корректно трактует круглые/квадратные/
фигурные скобки, кавычки, двоеточия, запятые, кириллические буквы
и CJK как границы слов. Все случаи из баг-репорта теперь
сматчатся:

- `Song (Off Vocal).flac` → BLOCKED
- `Song [Off Vocal].flac` → BLOCKED
- `Song {Backing Track}.flac` → BLOCKED
- `Song "Off Vocal".flac` → BLOCKED
- `Song, Off Vocal.flac` → BLOCKED
- `Song : Off Vocal.flac` → BLOCKED
- `[Instrumental] Take On Me.flac` → BLOCKED
- Кириллические варианты (`Песня (Караоке).flac`,
  `Песня-Инструментал.flac`, CamelCase `ПесняИнструментал.flac`)
  → BLOCKED

Защиты от false-positive сохранены:

- `tracklist.flac` → по-прежнему НЕ сматчит `backing track`
- `TheInstrumentalization.flac` → по-прежнему НЕ сматчит
  `instrumental` (нет word boundary между `l` и `i`)
- `Inoffensive.flac` → по-прежнему НЕ сматчит `off vocal`
  (нет пробела)
- `Nonvocal.flac` → по-прежнему НЕ сматчит `no vocal` (нет word
  boundary между `n` и `o`)

Изменение в `lyricsfag_lib/lyrics.py` — только две строки с
границами regex'а (`r"\b("` и `r")\b"`) внутри скомпилированного
`_INSTRUMENTAL_FILENAME_RE`. Список паттернов, CamelCase-сплит
нормализации (ASCII + кириллица) и метод `_filename_blocks_audio`
не тронуты.

### Чистка: мёртвые паттерны `offvocal` / `novocal` удалены

В прошлой сессии в `_INSTRUMENTAL_FILENAME_PATTERNS` добавили
`offvocal` и `novocal` как belt-and-suspenders для полностью
нижне-регистровых имён файлов вроде `songoffvocal`, где
CamelCase-сплит не срабатывает. Эти паттерны не могут сматчиться
с новой границей `\b` (между двумя соседними word-символами нет
word boundary, например между `g` и `o` в `songoffvocal`), так что
они были удалены как мёртвый код. Реальные случаи (CamelCase
`SongOffVocal`, через разделитель `Song-Off-Vocal`,
`Song_Off_Vocal`, `Song Off Vocal`) все покрываются существующим
паттерном `off vocal` + CamelCase-сплитом нормализации + новой
границей `\b`.

### Версионирование

`lyricsfag_lib.__version__` бамплен с `1.1.0` на `1.1.2`, чтобы
синхронизировать версию пакета с цепочкой git-тегов (тег v1.1.1
вышел без бампа константы).

## Heads-up

- Это хотфикс поверх v1.1.1. **Апгрейд рекомендуется всем
  пользователям v1.1.0 / v1.1.1** — задетые имена файлов — это
  самые распространённые соглашения об именовании off-vocal /
  караоке.
- Пользователи v1.0.x не задеты.
- Portable-сборка без изменений — просто пересоберите
  `build.bat portable`, если хочется свежий `.exe` под этот тег.
- **Известный follow-up:** комментарий-блок над скомпилированным
  regex'ом в `lyricsfag_lib/lyrics.py` (~строки 454-459) всё ещё
  описывает старый класс `[\s\-_.]` и старое «дешевле 11
  проверок». Точный anchor для обновления комментария упал во
  время прогона fix-скрипта из-за проблемы с 2-бэкслешным
  экранированием. Код корректен; комментарий просто слегка
  вводит в заблуждение. Будет исправлен в v1.1.3 doc-only патче.
