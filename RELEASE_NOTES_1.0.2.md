# Release 1.0.2

Pre-release polish — no API changes. GUI gets a Help button, hover
tooltips, a completion popup, and the resolved `models/` paths get
surfaced at startup. Dead code is cleaned up and the long-stale
`lyricsfag_lib.__version__` (`0.1.0`) is finally aligned with the tagged
release.

## What's new

### GUI
- New **`?  Help`** button (last in the toolbar row, right of Open output
  folder) opens `messagebox.showinfo("LyricsFAG — Quick start", …)`
  describing:
  - The provider chain (LRCLIB → Genius → local audio, in that order).
  - The `GENIUS_ACCESS_TOKEN` env var (or `--genius-token`) requirement
    for the Genius fallback.
  - The first-run download sizes (Whisper base ~150 MB, Demucs htdemucs_ft
    ~84 MB) so the popup is the place users land when they want to know
    why their first run pulled the network.
  - A `--dry-run` safety tip ("try it on a copy of your library first").
- **Tooltips on every primary input widget.** New `Tooltip` class
  (Toplevel-based, binds `<Enter>` / `<Leave>` / `<ButtonPress>`, 500 ms
  hover delay, 8 s auto-dismiss). Hover targets: the folder entry, recursive/force/
  dry-run checkboxes, source dropdown, Genius token, Whisper model +
  Device, Demucs model + model path, the Use audio-analysis checkbox,
  and all four row buttons (`Start`, `Stop`, `Open output folder`,
  `Help`).
- **Completion popup.** The worker still emits the same queue events
  (`job_done` / `job_stopped` / `job_empty`); `_set_summary` now pops
  - `messagebox.showinfo("Done", summary)` on a clean run.
  - `messagebox.showinfo("Stopped", partial summary)` when the user
    pressed Stop.
  - `messagebox.showerror("Worker crashed", traceback)` on exceptions,
    routed via the existing `job_errored` channel.
  - Empty folders (or fully-skipped runs) skip the popup so accidental
    one-click runs don't wake the user with a useless modal. The
    `_on_close` race with a late summary is guarded by `winfo_exists()`
    so we never call `showinfo` on a torn-down `Tk`.

### Startup visibility
- `audio_analysis.describe_models_layout(audio_model: str)` returns
  `(whisper_repo: str | None, demucs_repo: str)`. Both `lyricsfag.py`
  (CLI) and `lyricsfag_gui.py` (GUI) call it immediately after the
  analyzer is constructed and emit a multi-line `LOG.info` showing the
  resolved paths so the user can verify where weights actually land:
  - Whisper enabled → `models/whisper-base/` adjacent to the script.
  - Whisper disabled → reports "audio analysis off, no whisper repo".
  - Demucs always reports `models/demucs/` (the LocalRepo layout
    `./models/demucs/<name>.th`, matching demucs's own `files.txt`).
  The path contract is unchanged; this just makes it visible.

### Cleanup
- `lyricsfag_lib.__init__.py` now exposes `__version__ = "1.0.2"` —
  resolves the `0.1.0` drift going all the way back to the initial
  scaffolding. Anything that reads the lib version gets a real answer.
- Removed unused GUI constant `LyricsFAGApp.COLOUR_BG = "#1e1e1e"`
  (defined but never referenced after the dark-mode experiment got
  abandoned earlier in the project).
- Dropped the unused `_format_provider_breakdown` import from
  `lyricsfag_gui.py`.
- Renamed the audio-row "Device:" label to `audio_device_label` to
  stop it from shadowing the status-row badge variable named
  `device_label`. Two same-named attrs on the same `LyricsFAGApp`
  instance was a latent bug that would have bitten any future code
  reading the badge widget by handle.

## Commits in this release

- `e922d1c` — pre-release: GUI polish + dead-code cleanup + models/ path verification

(plus the version-bump commit that lands this file.)

## Heads-up

- AI-assisted project — see the AI-assisted note at the top of the README.
- `lyricsfag.py` makes network requests to LRCLIB / Genius and (opt-in)
  downloads Whisper / Demucs weights on the first run. Always try it on
  a copy of your library before unleashing it on the real one.
- The portable build is unchanged; just re-run `build.bat portable` if
  you want a fresh bundle that matches this tag.

---

# Релиз 1.0.2

Полировка перед релизом. API не меняется. GUI получает кнопку Help,
тултипы на 16 элементах, попап завершения и видимый сразу лог путей
до `models/`. Удалён мёртвый код, и `lyricsfag_lib.__version__`
наконец-то синхронизирован с тегом (раньше возвращал `0.1.0`
со времён скелета).

## What's new (RU)

### GUI
- Новая кнопка **`?  Help`** (последняя в ряду, правее Open output
  folder) → `messagebox.showinfo(...)`,
  внутри: цепочка провайдеров (LRCLIB → Genius → локальное аудио),
  напоминание про `GENIUS_ACCESS_TOKEN` / `--genius-token`, размеры
  весов при первом запуске (Whisper base ~150 MB, Demucs htdemucs_ft ~84 MB)
  и подсказка «сначала прогон на копии через `--dry-run`».
- **Тултипы на всех основных интерактивных элементах.** Новый класс
  `Tooltip` (Toplevel, bind на `<Enter>` / `<Leave>` / `<ButtonPress>`,
  задержка hover 500 мс, автоскрытие 8 с). Навешиваются на: поле выбора папки, чекбоксы
  recursive / force / dry-run, source-комбобокс, поле Genius-токена,
  Whisper model + Device, Demucs model + model path, чекбокс
  «Use audio analysis», и все 4 кнопки ряда (Start, Stop, Open output folder, Help).
- **Попап завершения.** Воркер по-прежнему пушит `job_done` / `job_stopped`
  / `job_empty` в очередь; `_set_summary` теперь открывает:
  - `messagebox.showinfo("Done", summary)` при штатном окончании.
  - `messagebox.showinfo("Stopped", частичный summary)` если жмякнули Stop.
  - `messagebox.showerror("Worker crashed", traceback)` на крашах
    воркера (через существующий канал `job_errored`).
  Пустые папки (или полностью пропущенные папки) больше не открывают
  модальный попап — иначе один случайный клик пробуждал пользователя
  бесполезным алертом. Гонка с `_on_close` (если попап прилетает после
  destroy) страхуется `winfo_exists()` — на снесённом Tk уже не дёргаемся.

### Видимость путей при старте
- `audio_analysis.describe_models_layout(audio_model)` возвращает
  `(whisper_repo: str | None, demucs_repo: str)`. И `lyricsfag.py`,
  и `lyricsfag_gui.py` зовут её сразу после построения анализатора
  и печатают многострочный `LOG.info`, чтобы пользователь без grep'а
  по исходникам видел, куда реально лягут веса:
  - Whisper включён → `models/whisper-base/` рядом со скриптом.
  - Whisper выключен → пишет «audio analysis off, no whisper repo».
  - Demucs всегда → `models/demucs/` (LocalRepo-лейаут
    `./models/demucs/<name>.th`, как и у самого demucs'а в `files.txt`).
  Контракт путей прежний — просто теперь видимый.

### Cleanup
- `lyricsfag_lib/__init__.py` теперь честно возвращает `__version__ ==
  "1.0.2"` (раньше залипало на `0.1.0` со времён самой первой
  разметки проекта). Любой код, который читает версию либы, получит
  реальный ответ.
- Удалена неиспользуемая константа `LyricsFAGApp.COLOUR_BG = "#1e1e1e"`
  (определялась, но ни разу не читалась после того, как эксперимент
  с dark mode сам собой отвалился по дороге).
- Удалён неиспользуемый импорт `_format_provider_breakdown` из GUI.
- Аудио-лейбл «Device:» переименован в `audio_device_label`, чтобы
  не перекрывать бейдж статуса (тоже назывался `device_label`). Два
  одинаковых атрибута на одном `LyricsFAGApp` были латентным багом
  — любой будущий код, который читает бейдж по handle, получил бы
  вместо него аудио-лейбл.

## Коммиты в этом релизе

- `e922d1c` — pre-release: GUI polish + dead-code cleanup + models/ path verification

(плюс коммит с бампом версии, который и тащит этот файл.)

## Heads-up

- Проект с существенной помощью AI — см. AI-дисклеймер в шапке README.
- `lyricsfag.py` ходит в сеть за LRCLIB / Genius и (опционально) качает
  Whisper / Demucs при первом запуске. Сначала на копии библиотеки.
- Portable-сборка без изменений — просто пересоберите `build.bat portable`,
  если хочется свежий `.exe` под этот тег.
