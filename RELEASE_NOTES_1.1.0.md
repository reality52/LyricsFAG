# Release 1.1.0

Audio-analysis contract change + new local-only `audio` source.
**Behavioural breaking change for users running the audio fallback:**
demucs vocal isolation is now always on with `--use-audio-analysis`
(no UI toggle to turn it off). The `--no-demucs` CLI flag has been
removed. To opt out of the local fallback entirely, drop the
`--use-audio-analysis` flag (CLI) or uncheck "Use audio analysis" (GUI).

## What's new

### Demucs is mandatory with the audio fallback
The audio panel in the GUI no longer has the `Demucs` on/off combobox.
Demucs vocal isolation is hardcoded on whenever the audio-analysis
fallback is engaged. Rationale: a Whisper pass on the raw stereo mix
of a dense song hallucinates wildly; the demucs pre-stage is the
difference between usable lyrics and nonsense. The user can still
opt out of the whole local fallback by unchecking the
`Use audio analysis` master switch.

- Removed: the `Demucs: off/auto/on` combobox widget from
  `lyricsfag_gui.py` and its corresponding `self.demucs_var` /
  `self.demucs_label` / `self.demucs_combo` attributes.
- Removed: the `--no-demucs` CLI flag from `lyricsfag.py`. Trying
  it now exits with `argparse` error
  (`unrecognized arguments: --no-demucs`).
- Removed: the `cfg.enable_demucs` knob from `JobConfig`; the
  GUI's `_build_audio_analyzer()` now calls
  `warn_first_run_aggregate(enable_demucs=True, ...)` unconditionally
  and constructs the analyzer with the demucs pre-stage baked in.
- The CPU warning in `lyricsfag.py` and `lyricsfag_gui.py` no longer
  tells the user to "set Demucs to 'off'" — that escape hatch is gone.
  The new escape hatches are: switch the Device dropdown to
  `'auto'`/`'cuda'`, or uncheck `Use audio analysis` entirely.

### New `audio` source option
The Source dropdown in the GUI and the `--source` CLI flag now
accept `audio` as a value. When picked, the lyrics chain is
**just** the local Whisper + Demucs pipeline — LRCLIB and Genius
are skipped entirely.

- Useful for: fully-offline runs, batches where you know LRCLIB
  won't have matches (obscure / instrumental-heavy libraries), or
  when you explicitly don't want network calls during a run.
- In the GUI, picking `Source = audio` auto-checks
  `Use audio analysis` and greys out the checkbox so the chain
  stays consistent (you can't accidentally leave the master
  switch off while asking for the audio-only chain).
- In the CLI, `--source audio` is a no-op unless
  `--use-audio-analysis` is also passed (the audio analyzer is
  only constructed when that flag is on; the GUI's auto-check
  exists for the same reason).
- The `lyrics.LyricsFetcher` dispatches this cleanly:
  `source="auto"` still chains `LRCLIB → Genius → audio`; the new
  `source="audio"` builds an order list with just the audio
  provider and returns its result (or its `LyricsFailure`) directly.

### Filename-based short-circuit for the audio branch
The audio branch now refuses to run Whisper on tracks whose
**filename** (case- and punctuation-insensitive) contains any of:
- `instrumental`
- `instrumental version`
- `karaoke`
- `off vocal`
- `no vocal` / `no vocals`
- `vocal removed` / `vocals removed`
- `minus one`
- `backing track`
- `inst version`

The check is anchored on word/punctuation boundaries (so
`"tracklist"` doesn't trigger `backing track`, and `"instrument"`
doesn't trigger `instrumental`). It is applied **only** to the
audio branch — the LRCLIB and Genius branches are unaffected, on
purpose: a karaoke file is often a faithful cover of a real song
that LRCLIB knows, and the user almost certainly wants that match
rather than no LRC at all. When the short-circuit fires, the file
is reported as `missing` with the reason
`filename matches karaoke/instrumental pattern; audio analysis
skipped` and the run keeps going.

The check lives in `lyricsfag_lib/lyrics.py` as
`LyricsFetcher._INSTRUMENTAL_FILENAME_PATTERNS`,
`_INSTRUMENTAL_FILENAME_RE`, and
`LyricsFetcher._filename_blocks_audio(audio)`. The patterns
tuple + the compiled regex are class-level so the regex is
compiled once per process, not once per file.

### Backward compatibility
- v1.0.x `settings.json` files that contain the `demucs` key
  (which the previous GUI wrote) are now silently ignored on load
  instead of crashing the GUI on launch with
  `AttributeError: 'LyricsFAGApp' object has no attribute
  'demucs_var'`. The corresponding branch in
  `_apply_persisted_settings` was removed.
- v1.1.0 still recognises and honours every other v1.0.x setting
  (folder, recursive, force, dry_run, use_audio_analysis, source,
  genius_token, audio_model, audio_model_path, device). The
  persisted `source=audio` value is honoured verbatim.

### Versioning
- `lyricsfag_lib.__version__` is now `"1.1.0"`.


## Heads-up

- **Behavioural breaking change:** demucs is now mandatory with the
  audio fallback. Existing `--no-demucs` invocations (in scripts,
  CI, READMEs) need to drop that flag. CPU-only users who were
  relying on `--no-demucs` to make the audio fallback tractable
  should now drop `--use-audio-analysis` entirely — Whisper on a
  raw mix without demucs is generally not worth the wall-clock.
- AI-assisted project — see the AI-assisted note at the top of the
  README.
- `lyricsfag.py` makes network requests to LRCLIB / Genius and
  (opt-in) downloads Whisper / Demucs weights on the first run.
  Always try it on a copy of your library before unleashing it
  on the real one.
- The portable build is unchanged; just re-run
  `build.bat portable` if you want a fresh bundle that matches
  this tag.

---

# Релиз 1.1.0

Изменение контракта аудио-фолбэка + новый локальный источник `audio`.
**Поведенческий breaking change для пользователей аудио-фолбэка:**
Demucs теперь всегда включён вместе с `--use-audio-analysis`
(переключателя в GUI больше нет). CLI-флаг `--no-demucs` удалён.
Чтобы полностью отключить локальный фолбэк — уберите
`--use-audio-analysis` (CLI) или снимите галку «Use audio analysis»
(GUI).

## What's new (RU)

### Demucs обязателен с аудио-фолбэком
В аудио-панели GUI больше нет выпадающего списка `Demucs` on/off.
Вокальная изоляция Demucs хардкодом включена, когда задействован
аудио-фолбэк. Обоснование: прогон Whisper по сырой стерео-смеси
плотной песни дико галлюцинирует; Demucs — это разница между
юзабельным текстом и ерундой. Пользователь всё ещё может
выключить локальный фолбэк целиком, сняв главный переключатель
`Use audio analysis`.

- Удалены: виджет `Demucs: off/auto/on` из `lyricsfag_gui.py` и
  соответствующие атрибуты `self.demucs_var` / `self.demucs_label`
  / `self.demucs_combo`.
- Удалён: CLI-флаг `--no-demucs` из `lyricsfag.py`. Попытка его
  передать теперь завершается ошибкой `argparse`
  (`unrecognized arguments: --no-demucs`).
- Удалена: ручка `cfg.enable_demucs` из `JobConfig`; GUI'шный
  `_build_audio_analyzer()` теперь вызывает
  `warn_first_run_aggregate(enable_demucs=True, ...)` безусловно
  и конструирует анализатор с принудительно включённой
  Demucs-стадией.
- CPU-предупреждения в `lyricsfag.py` и `lyricsfag_gui.py` больше
  не советуют «поставить Demucs в 'off'» — этой лазейки больше нет.
  Новые лазейки: переключить Device в `'auto'`/`'cuda'`, или
  снять галку `Use audio analysis` целиком.

### Новый источник `audio`
Source-комбобокс в GUI и CLI-флаг `--source` теперь принимают
`audio` как значение. При его выборе цепочка текстов состоит
**только** из локального пайплайна Whisper + Demucs — LRCLIB и
Genius полностью пропускаются.

- Полезно для: полностью офлайновых прогонов, батчей, для которых
  заведомо нет совпадений в LRCLIB (малоизвестные /
  инструментально-тяжёлые библиотеки), или когда сетевые вызовы
  во время прогона нежелательны.
- В GUI при выборе `Source = audio` чекбокс `Use audio analysis`
  автоматически включается и блокируется, чтобы цепочка оставалась
  согласованной (нельзя случайно оставить главный переключатель
  выключенным, запрашивая аудио-only цепочку).
- В CLI `--source audio` — no-op без `--use-audio-analysis`
  (аудио-анализатор конструируется только при этом флаге; авто-чек
  в GUI существует ровно по той же причине).
- `lyrics.LyricsFetcher` обрабатывает это чисто: `source="auto"`
  по-прежнему собирает цепочку `LRCLIB → Genius → audio`;
  новый `source="audio"` строит список порядка с единственным
  аудио-провайдером и сразу возвращает его результат (или
  `LyricsFailure` от него).

### Шорткат по имени файла для аудио-ветки
Аудио-ветка теперь отказывается гнать Whisper по трекам, в **имени
файла** (без учёта регистра и пунктуации) встречается любое из:
- `instrumental`
- `instrumental version`
- `karaoke`
- `off vocal`
- `no vocal` / `no vocals`
- `vocal removed` / `vocals removed`
- `minus one`
- `backing track`
- `inst version`

Проверка якорится на границах слов/пунктуации (поэтому
`"tracklist"` не триггерит `backing track`, а `"instrument"` не
триггерит `instrumental`). Применяется **только** к аудио-ветке —
LRCLIB и Genius намеренно не задеты: караоке-файл часто является
точным кавером реальной песни, о которой LRCLIB знает, и
пользователь почти наверняка хочет это совпадение, а не
отсутствующий LRC. Когда шорткат срабатывает, файл репортится
как `missing` с причиной
`filename matches karaoke/instrumental pattern; audio analysis
skipped`, прогон продолжается.

Проверка живёт в `lyricsfag_lib/lyrics.py` как
`LyricsFetcher._INSTRUMENTAL_FILENAME_PATTERNS`,
`_INSTRUMENTAL_FILENAME_RE` и
`LyricsFetcher._filename_blocks_audio(audio)`. Кортеж паттернов +
скомпилированный regex — class-level, поэтому regex компилируется
один раз на процесс, а не на файл.

### Обратная совместимость
- `settings.json` от v1.0.x с ключом `demucs` (который писал
  прошлый GUI) теперь молча игнорируется при загрузке вместо
  падения GUI на старте с
  `AttributeError: 'LyricsFAGApp' object has no attribute
  'demucs_var'`. Соответствующая ветка в
  `_apply_persisted_settings` удалена.
- v1.1.0 по-прежнему распознаёт и уважает все прочие настройки
  из v1.0.x (folder, recursive, force, dry_run, use_audio_analysis,
  source, genius_token, audio_model, audio_model_path, device).
  Сохранённое значение `source=audio` учитывается буквально.

### Версионирование
- `lyricsfag_lib.__version__` теперь `"1.1.0"`.


## Heads-up

- **Поведенческий breaking change:** Demucs теперь обязателен с
  аудио-фолбэком. Существующие вызовы `--no-demucs` (в скриптах,
  CI, README'ах) должны убрать этот флаг. Пользователям только-на-CPU,
  которые полагались на `--no-demucs`, чтобы сделать аудио-фолбэк
  посильно-быстрым, теперь лучше убрать `--use-audio-analysis`
  целиком — Whisper по сырой смеси без Demucs в целом не стоит
  потраченного времени.
- Проект с существенной помощью AI — см. AI-дисклеймер в шапке README.
- `lyricsfag.py` ходит в сеть за LRCLIB / Genius и (опционально)
  качает Whisper / Demucs при первом запуске. Сначала на копии библиотеки.
- Portable-сборка без изменений — просто пересоберите
  `build.bat portable`, если хочется свежий `.exe` под этот тег.
