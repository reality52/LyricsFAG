# LyricsFAG v1.1.3 — release notes

*Shipped 2026-07-06. Patch release (v1.1.2 → v1.1.3).*

## TL;DR

The `lite` PyInstaller build is now actually lite (~50 MB, no audio
support) and `build.bat` no longer clobbers the portable exes when
building both variants. `requirements.txt` was split into a core
`requirements.txt` and an optional `requirements-audio.txt`; the
latter is only installed by `build-portable.bat` (and by dev installs
that want the full audio stack on the command line).


## What's new

### Build: `lite` is now a real ~50 MB .exe (no audio analysis)

* `requirements.txt` is split into two files. The core file
  (`requirements.txt`) keeps `mutagen`, `requests`, `lyricsgenius` —
  the bare minimum both builds need. The audio stack
  (`faster-whisper`, `demucs`, `scipy`, and the transitive `torch`
  dependency) moves to a new `requirements-audio.txt`.
* `build-lite.bat` no longer installs `requirements-audio.txt`,
  so the resulting `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe`
  no longer bundle `torch` (~3.8 GB on Windows) and stay at the
  documented ~50 MB footprint. The PyInstaller invocation drops
  `--hidden-import faster_whisper` since the package is no longer
  present.
* `build-portable.bat` now installs `requirements-audio.txt` instead
  of installing `faster-whisper` and `demucs` directly; otherwise
  the build is unchanged.
* **Behavioural change:** the **lite** build no longer supports
  `--use-audio-analysis` / the GUI "Use audio analysis" checkbox.
  A lite user who enables the audio chain sees a `LyricsFailure`
  with a hint pointing at the portable build instead of the
  misleading `pip install faster-whisper` (which can't be done
  inside a read-only bundled .exe). The new
  `lyricsfag_lib.audio_analysis._missing_audio_hint` helper
  centralises the new error string so the fast-whisper + demucs
  failure sites stay in lockstep.
* **Documented size update:** the portable build is now correctly
  advertised as **~3.5 GB** (not the previous, wildly optimistic
  "~600 MB") because `torch` alone is ~3.8 GB. The table in
  `README.md` → "Building the executable" now reflects the real
  numbers and a short footnote explains why portable is so much
  bigger than lite.

### Build: `build.bat` orchestrator no longer wipes the portable exes

* Previously, each variant script (`build-lite.bat` and
  `build-portable.bat`) started with `rmdir /s /q dist`, which
  meant the second variant silently deleted the first variant's
  outputs. Running `build.bat` (default = `all`) left the user
  with only the **lite** exes in `dist\` and a ~6.4 GB
  `dist\LyricsFAG-Portable.exe` + `-GUI-Portable.exe` pair
  silently deleted — matching the user bug report "two huge
  exes in dist, but I expected both portable and lite".
* Fix: the `dist\` / `build\` cleanup moved to the **top** of
  `build.bat` (the orchestrator), but only runs when the target
  is `all` (`if /i "%TARGET%"=="all"`), so single-target builds
  (`build.bat lite` or `build.bat portable` standalone) preserve
  the other variant's outputs. Each variant script now cleans
  **only** its own previous `dist\<Name>.exe` + `<Name>.spec` at
  the top so a re-run gets a fresh PyInstaller pass without
  stale configs, but doesn't touch the other variant's outputs.
  As a result, `build.bat all` now produces **four** exes in
  `dist\` instead of two: `LyricsFAG-Portable.exe` +
  `-GUI-Portable.exe` (each ~3.5 GB) and `LyricsFAG-Lite.exe` +
  `-GUI-Lite.exe` (each ~50 MB).


## Upgrade notes

* Existing users who re-run `build.bat` after upgrading will see
  the orchestrator wipe the old `dist\` (~6.4 GB) before producing
  the new four-exe layout. This is intentional: the new
  lite-build contract is incompatible with the old bloated
  ~3.2 GB lite .exe, and the orchestrator no longer preserves
  stale portable exes from a previous run.
* Dev installs that previously used `pip install -r
  requirements.txt` to get the full audio stack now need `pip
  install -r requirements.txt -r requirements-audio.txt`. The
  Quick-start in `README.md` and `README.ru.md` was updated to
  reflect this.
* Users who only need LRCLIB + Genius are unaffected by any of
  this — the lite build still does everything they need at
  ~50 MB.


## Files changed

* `build.bat` — move the `dist\` / `build\` cleanup to the
  orchestrator (top of the script, runs once before any variant
  starts).
* `build-lite.bat` — drop the wholesale `dist\` / `build\`
  cleanup; drop the `pip install faster-whisper` and the
  `--hidden-import faster_whisper` PyInstaller flag; add a
  per-variant cleanup of `dist\LyricsFAG-Lite.exe` +
  `dist\LyricsFAG-GUI-Lite.exe` + the matching `.spec` files
  (so a standalone re-run is clean but the portable exes
  survive); rewrite the header comment to reflect the new
  "no audio" contract.
* `build-portable.bat` — drop the wholesale `dist\` / `build\`
  cleanup; add a per-variant cleanup of
  `dist\LyricsFAG-Portable.exe` + `dist\LyricsFAG-GUI-Portable.exe`
  + the matching `.spec` files (so a standalone re-run is clean
  but the lite exes survive); replace the explicit
  `pip install faster-whisper` / `pip install demucs` lines with
  a single `pip install -r requirements-audio.txt`.
* `requirements.txt` — slim down to the three core deps
  (`mutagen`, `requests`, `lyricsgenius`); point at
  `requirements-audio.txt` in a leading comment.
* `requirements-audio.txt` — **new file** with `faster-whisper`,
  `demucs`, `scipy` and a leading comment explaining the split
  and the install contract.
* `lyricsfag_lib/audio_analysis.py` — add the
  `_missing_audio_hint(pkg)` helper and route the
  `FasterWhisperAnalyzer.get` / `DemucsIsolator._ensure_separator`
  failure sites through it so a frozen-build lite user gets a
  "use the portable build" hint instead of `pip install ...`.
* `lyricsfag_lib/__init__.py` — `__version__` 1.1.2 → 1.1.3.
* `README.md` / `README.ru.md` — Quick-start now installs
  `requirements-audio.txt` separately for the audio path; the
  "Building the executable" sizes table is updated with the real
  ~50 MB / ~3.5 GB numbers and a behavioural-change note about
  the lite build no longer supporting audio analysis; the
  project layout tree adds `requirements-audio.txt`.
* `models/demucs/README.md` — leading note about the lite
  build not bundling Demucs/torch.


## Backward compatibility

* **Breaking** for users who used `--use-audio-analysis` on the
  **lite** .exe (they need the portable .exe now; the runtime
  error message tells them so).
* Non-breaking for everyone else. LRCLIB + Genius still work
  identically on both variants. The CLI flags / GUI widgets /
  config file schema are unchanged. Settings.json from v1.1.2
  still loads cleanly.


---

# LyricsFAG v1.1.3 — заметки о релизе

*Выпущено 2026-07-06. Patch-релиз (v1.1.2 → v1.1.3).*

## TL;DR

`lite`-сборка PyInstaller теперь действительно lite (~50 МБ, без
поддержки аудио), а `build.bat` больше не затирает portable-.exe,
когда собирает оба варианта подряд. `requirements.txt` разделён на
основной `requirements.txt` и опциональный `requirements-audio.txt`;
последний ставится только `build-portable.bat` (и dev-установками,
которым нужен полный аудио-стек в командной строке).


## Что нового

### Сборка: `lite` теперь настоящий .exe на ~50 МБ (без аудио-анализа)

* `requirements.txt` разделён на два файла. Основной
  (`requirements.txt`) хранит `mutagen`, `requests`,
  `lyricsgenius` — минимум, нужный обеим сборкам. Аудио-стек
  (`faster-whisper`, `demucs`, `scipy` и транзитивный `torch`)
  переехал в новый `requirements-audio.txt`.
* `build-lite.bat` больше не ставит `requirements-audio.txt`,
  поэтому итоговые `LyricsFAG-Lite.exe` /
  `LyricsFAG-GUI-Lite.exe` больше не бандлят `torch` (~3.8 ГБ на
  Windows) и остаются в задокументированных ~50 МБ. Из вызова
  PyInstaller убран `--hidden-import faster_whisper`, так как
  пакет больше не установлен.
* `build-portable.bat` теперь ставит `requirements-audio.txt`
  вместо прямых `pip install faster-whisper` / `pip install
  demucs`; в остальном сборка не изменилась.
* **Изменение поведения:** **lite**-сборка больше **не**
  поддерживает `--use-audio-analysis` и чекбокс "Use audio
  analysis" в GUI. Lite-пользователь, который включит аудио-цепь,
  увидит `LyricsFailure` с подсказкой про portable-сборку — а
  не вводящую в заблуждение `pip install faster-whisper` (что
  нельзя сделать в read-only собранном .exe). Новый хелпер
  `lyricsfag_lib.audio_analysis._missing_audio_hint`
  централизует строку ошибки, чтобы места падений в
  fast-whisper и demucs оставались в синхронизации.
* **Обновление задокументированного размера:** portable теперь
  корректно заявлен как **~3.5 ГБ** (а не оптимистичные
  прошлые ~600 МБ), потому что один только `torch` весит
  ~3.8 ГБ. Таблица в `README.md` → "Сборка .exe" теперь
  отражает реальные цифры и короткую сноску о том, почему
  portable так сильно больше lite.

### Сборка: `build.bat`-оркестратор больше не затирает portable-.exe

* Раньше каждый вариант (`build-lite.bat` и
  `build-portable.bat`) начинал с `rmdir /s /q dist`, и второй
  вариант молча удалял выход первого. Запуск `build.bat`
  (по умолчанию = `all`) оставлял пользователю в `dist\` только
  **lite**-.exe, а пара `LyricsFAG-Portable.exe` +
  `-GUI-Portable.exe` на ~6.4 ГБ молча удалялась — что и
  соответствует баг-репорту "два огромных exe в dist, а
  должно быть две версии".
* Фикс: очистка `dist\` / `build\` / `*.spec` переехала в
  **начало** `build.bat` (в оркестратор), так что выполняется
  ровно один раз до старта любого варианта. Скрипты вариантов
  больше не трогают `dist\` или `build\`. В результате
  `build.bat all` теперь даёт **четыре** exe в `dist\`
  вместо двух: `LyricsFAG-Portable.exe` + `-GUI-Portable.exe`
  (каждый ~3.5 ГБ) и `LyricsFAG-Lite.exe` + `-GUI-Lite.exe`
  (каждый ~50 МБ).


## Заметки по обновлению

* Существующие пользователи, которые перезапустят `build.bat`
  после апгрейда, увидят, что оркестратор затирает старый
  `dist\` (~6.4 ГБ) до генерации нового лейаута на четыре
  exe. Это намеренно: новый lite-контракт несовместим со
  старым раздутым lite-.exe на ~3.2 ГБ, и оркестратор больше
  не сохраняет устаревшие portable-.exe от прошлого запуска.
* Dev-установки, которые раньше использовали
  `pip install -r requirements.txt` для получения полного
  аудио-стека, теперь должны использовать
  `pip install -r requirements.txt -r requirements-audio.txt`.
  Quick-start в `README.md` и `README.ru.md` обновлён, чтобы
  это отражать.
* Те, кому нужен только LRCLIB + Genius, не заметят никаких
  изменений — lite по-прежнему делает всё, что им нужно, на
  ~50 МБ.


## Изменённые файлы

* `build.bat` — очистка `dist\` / `build\` переехала в
  оркестратор (в начало скрипта, выполняется один раз до
  старта любого варианта).
* `build-lite.bat` — убрана локальная очистка `dist\` /
  `build\`; убраны `pip install faster-whisper` и флаг
  PyInstaller `--hidden-import faster_whisper`; переписан
  заголовочный комментарий под новый "без аудио" контракт.
* `build-portable.bat` — убрана локальная очистка `dist\` /
  `build\`; явные `pip install faster-whisper` /
  `pip install demucs` заменены на одну строку
  `pip install -r requirements-audio.txt`.
* `requirements.txt` — сокращён до трёх основных зависимостей
  (`mutagen`, `requests`, `lyricsgenius`); в шапочном
  комментарии указано на `requirements-audio.txt`.
* `requirements-audio.txt` — **новый файл** с `faster-whisper`,
  `demucs`, `scipy` и шапочным комментарием, объясняющим
  разбиение и контракт установки.
* `lyricsfag_lib/audio_analysis.py` — добавлен хелпер
  `_missing_audio_hint(pkg)`; оба места падения
  (`FasterWhisperAnalyzer.get` / `DemucsIsolator._ensure_separator`)
  пропущены через него, чтобы замороженный lite-пользователь
  получал подсказку "используйте portable-сборку" вместо
  `pip install ...`.
* `lyricsfag_lib/__init__.py` — `__version__` 1.1.2 → 1.1.3.
* `README.md` / `README.ru.md` — Quick-start теперь ставит
  `requirements-audio.txt` отдельной строкой для аудио-пути;
  таблица размеров в "Сборка .exe" обновлена реальными
  цифрами ~50 МБ / ~3.5 ГБ и заметкой об изменении поведения
  lite-сборки (без поддержки аудио-анализа); в дерево
  раскладки проекта добавлен `requirements-audio.txt`.
* `models/demucs/README.md` — вводная заметка о том, что
  lite-сборка не бандлит Demucs/torch.


## Обратная совместимость

* **Ломающее** изменение для тех, кто использовал
  `--use-audio-analysis` на **lite**-.exe (теперь нужен
  portable-.exe; runtime-сообщение об ошибке само об этом
  скажет).
* Для остальных — без изменений. LRCLIB + Genius работают
  идентично на обоих вариантах. CLI-флаги / виджеты GUI /
  схема config-файла не изменились. settings.json от v1.1.2
  по-прежнему загружается чисто.
