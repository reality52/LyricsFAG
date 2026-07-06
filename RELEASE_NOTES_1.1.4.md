# LyricsFAG v1.1.4 — release notes

*Shipped 2026-07-07. Patch release (v1.1.3 → v1.1.4).*

## TL;DR

The audio stack no longer crashes on first run under PyTorch 2.6
(the `Weights only load failed ... GLOBAL fractions.Fraction`
`WeightsUnpickler` error is fixed via a shared, `.th`-scoped
`torch.load` monkey-patch). The first-run Demucs download warning
now reports correct sizes (`htdemucs_ft` is a 4-sub-model ~336 MB
`BagOfModels`, not a single ~84 MB model; the legacy `htdemucs` is
a single ~84 MB model, not a 5-sub-model ~420 MB bag). The
`models/demucs/README.md` is brought in line with demucs 4.0.1
reality in 8 places. As a bonus, the `build.bat` `TARGET=all`
guard is fixed for older Windows batch parsers, and the
`lyricsfag_lib/lyrics.py` instrumental short-circuit regex is
re-anchored to explicit boundaries with the no-separator filename
patterns (`offvocal`, `novocal`) re-added.


## What's new

### Compat: PyTorch 2.6 / demucs 4.0.1 — `Weights only load failed` no longer breaks the audio path

PyTorch 2.6 changed `torch.load()`'s default `weights_only` argument
from `False` to `True`. demucs 4.0.1 pickles its `HTDemucs` /
`BagOfModels` weights with class references (`HTDemucs`,
`fractions.Fraction`, and more as the unpickler walks deeper into
the state dict) that the strict unpickler rejects, surfacing as
`WeightsUnpickler error: Unsupported global: GLOBAL fractions.Fraction
was not an allowed global by default`. v1.1.3 and earlier crashed
on first run when demucs tried to load weights under PyTorch 2.6.

The fix is a **`.th`-scoped** monkey-patch of `torch.load` that
forwards `weights_only=False` only for files ending in `.th` (the
demucs weights we just downloaded from `facebookresearch/demucs`)
and keeps the safe PyTorch 2.6 default for every other `torch.load`
caller in the process (e.g. faster-whisper's Silero VAD, which
loads `*.pt` files we don't want to weaken the policy for).

The patch lives in the new package-internal module
`lyricsfag_lib/_torch_compat.py` and is applied **lazily** on
first demucs use (so users who never enable the audio analysis
fallback don't pay the ~3 s `import torch` cost). **Idempotent**
and emits a one-line INFO log on first application so the
workaround is auditable from the log:

```
INFO lyricsfag_lib._torch_compat: torch.load monkey-patch active for .th files
(PyTorch 2.6 weights_only workaround for demucs 4.0.1)
```

Both call sites (`DemucsIsolator._ensure_separator` in
`lyricsfag_lib/audio_analysis.py` and the
`scripts/download_demucs_model.py --verify` gate) now share the
single implementation, so the library and the script can no longer
drift.

### Fix: first-run Demucs download warning reported inverted sizes

`_DEMUCS_DOWNLOAD_HINTS_MB` in `lyricsfag_lib/audio_analysis.py` had
its two entries swapped:

* `htdemucs_ft` was advertised as **~84 MB**; in demucs 4.0.1 it is
  actually a `BagOfModels` of 4 sub-models (~336 MB total:
  4 × ~84 MB).
* `htdemucs` was advertised as **~420 MB**; in demucs 4.0.1 it is
  actually a single pretrained `HTDemucs` (~84 MB).

The numbers fed the `First run will download ~N MB total` WARNING
that fires once on a fresh install. v1.1.4 corrects the values so
the WARNING now reads:

* `htdemucs_ft` (default) → `~336 MB`
* `htdemucs` (legacy single-model variant) → `~84 MB`

The pre-existing comment block above the dict (which made the same
inverted claim) is also updated to match demucs 4.0.1 reality.

### Docs: `models/demucs/README.md` corrected for demucs 4.0.1

The README still described the pre-4.0.1 layout (where `htdemucs`
was a 5-sub-model bag) in 8 places. v1.1.4 updates the Quick
reference table, the "Note — default Demucs model" callout, the
"Which Demucs model?" paragraph, the "Why is this folder empty?"
section, the size comparison, the "End-user experience" bullet, the
PyInstaller `--onefile` quirk bullet, and the "Verification step"
explanation to match demucs 4.0.1 reality.

The size-comparison table now also cites the actual demucs YAML
contents (`htdemucs_ft.yaml` lists 4 sub-models; `htdemucs.yaml`
lists 1) so the per-model footprint claim is grep-able from the
YAML rather than relying on observed disk size.

### Build: `build.bat` `TARGET=all` guard fixed for older Windows batch parsers

`build.bat` had a parenthesised `if ... ( ... )` block guarding
`rmdir /s /q build` + `rmdir /s /q dist` under the `all` target.
The parenthesised form triggered `. was unexpected at this time` on
some Windows batch parser versions. v1.1.4 splits the block into
two single-line compound-`if` statements (semantics identical:
clean `build\` + `dist\` only when `TARGET=all`).

### Lyrics: `INSTRUMENTAL_FILENAME_RE` re-anchored + no-separator patterns re-added

The compiled regex in `lyricsfag_lib/lyrics.py` had its boundary
class reverted from the v1.1.2 / v1.1.3 `r"\b(...)"` form back to
the explicit `r"(?:^|[\s\-_.])(...)(?:$|[\s\-_.])"` form. The
explicit anchors keep the boundary semantics grep-able for
downstream tooling and avoid the `\b` corner cases the v1.1.2
hotfix worked around (the v1.1.3 review flagged the `\b` form as
over-eager on certain filename shapes).

`offvocal` and `novocal` are also re-added to
`_INSTRUMENTAL_FILENAME_PATTERNS` as belt-and-suspenders entries
for all-lowercase filenames like `songoffvocal` where the CamelCase
normalisation split doesn't fire. The comment above the pattern
list is updated to explain the rationale: the re-adds were dead
code under the `\b` boundary, but the v1.1.4 explicit-boundary
form is reachable for them again.


## Upgrade notes

* **No code-level migration is required.** Drop-in upgrade from
  v1.1.3 — settings.json still loads cleanly, CLI flags / GUI
  widgets are unchanged.
* The `.th`-scoped `torch.load` monkey-patch is process-global.
  If you embed LyricsFAG in a process that does its own
  `torch.load` policy, the patch will forward `weights_only=False`
  for any `*.th` file you load via `torch.load(...)` too. In the
  unlikely event this matters, your own `torch.load` calls can pin
  `weights_only=True` explicitly and the patch will honour your
  value.
* The first-run Demucs WARNING now shows the correct download size.
  If you've already cached weights, the WARNING is suppressed and
  you won't see any change in behaviour.
* PyInstaller users rebuilding the .exe get the same ~50 MB
  (lite) / ~3.5 GB (portable) sizes as v1.1.3; no new deps, no
  removed deps. `requirements.txt` and `requirements-audio.txt`
  are unchanged.


## Files changed

* `lyricsfag_lib/_torch_compat.py` — **new file**, the shared
  `.th`-scoped `torch.load` monkey-patch.
* `lyricsfag_lib/audio_analysis.py` — `DemucsIsolator._ensure_separator`
  now uses the shared monkey-patch (no inline duplicate);
  `_DEMUCS_DOWNLOAD_HINTS_MB` values corrected
  (`htdemucs_ft` 84→336, `htdemucs` 420→84) and the comment block
  above the dict updated.
* `scripts/download_demucs_model.py` — same monkey-patch import
  (with `echo_to_stderr=True` so the confirmation line is visible
  from the CLI); `sys.path` manipulation so `python scripts/...py`
  from any cwd can import `lyricsfag_lib`; rewritten
  pre-seed-and-verify flow (delegates to `demucs.pretrained.get_model`
  + mirrors the YAML + per-hash `.th` files into `models/demucs/`
  from the native torch-hub cache).
* `models/demucs/README.md` — 8 places updated to match demucs
  4.0.1.
* `build.bat` — `TARGET=all` guard split into two compound-`if`
  lines (Windows batch parser compatibility).
* `lyricsfag_lib/lyrics.py` — `INSTRUMENTAL_FILENAME_RE`
  re-anchored to explicit `(?:^|[\s\-_.])` boundaries; `offvocal`
  and `novocal` patterns re-added to
  `_INSTRUMENTAL_FILENAME_PATTERNS`.


## Backward compatibility

* **Non-breaking.** No API or config-file changes. Settings.json
  from v1.1.3 still loads cleanly. The CLI / GUI surface is
  unchanged.
* The `.th`-scoped `torch.load` patch is the only behavioural
  change in the runtime library; it activates only on `.th` paths,
  leaves the safe PyTorch 2.6 default for everything else, and
  emits an INFO log line so the workaround is auditable. Users with
  cached Demucs weights see no behaviour change at all (the WARNING
  is suppressed when the cache is warm).
* The `_DEMUCS_DOWNLOAD_HINTS_MB` fix changes the WARNING text but
  not the underlying download behaviour (the model weights
  themselves were always ~336 MB / ~84 MB — only the user-facing
  message was wrong).


---

# LyricsFAG v1.1.4 — заметки о релизе

*Выпущено 2026-07-07. Patch-релиз (v1.1.3 → v1.1.4).*

## TL;DR

Аудио-стек больше не падает на первом запуске под PyTorch 2.6
(ошибка `Weights only load failed ... GLOBAL fractions.Fraction`
из `WeightsUnpickler` исправлена через общий, `.th`-scoped
monkey-patch на `torch.load`). WARNING про объём Demucs-весов при
первом запуске теперь показывает корректные числа (`htdemucs_ft` —
это `BagOfModels` из 4 sub-models на ~336 МБ, а не одна модель на
~84 МБ; legacy `htdemucs` — одна модель на ~84 МБ, а не 5-sub-model
bag на ~420 МБ). `models/demucs/README.md` приведён в соответствие
с реальностью demucs 4.0.1 в 8 местах. Бонусом: `build.bat`-guard
для `TARGET=all` исправлен под старые Windows batch-парсеры, а
short-circuit-regex для инструменталов в `lyricsfag_lib/lyrics.py`
пере-анкерован к явным границам с возвратом no-separator
паттернов (`offvocal`, `novocal`).


## Что нового

### Совместимость: PyTorch 2.6 / demucs 4.0.1 — `Weights only load failed` больше не ломает аудио-путь

PyTorch 2.6 поменял дефолт `weights_only` в `torch.load()` с
`False` на `True`. demucs 4.0.1 пиклить `HTDemucs` /
`BagOfModels` веса с ссылками на классы (`HTDemucs`,
`fractions.Fraction` и другие, по мере того как анпиклер
углубляется в state dict), которые строгий анпиклер отвергает, что
выливается в `WeightsUnpickler error: Unsupported global: GLOBAL
fractions.Fraction was not an allowed global by default`. v1.1.3
и более ранние падали на первом запуске, когда demucs пытался
загрузить веса под PyTorch 2.6.

Фикс — это **`.th`-scoped** monkey-patch на `torch.load`,
пробрасывающий `weights_only=False` только для файлов с расширением
`.th` (это веса demucs, которые мы только что скачали с
`facebookresearch/demucs`) и сохраняющий безопасный PyTorch 2.6
дефолт для всех остальных вызовов `torch.load` в процессе
(например, Silero VAD в faster-whisper, который грузит `*.pt`
файлы — для них политику ослаблять не нужно).

Патч живёт в новом package-internal модуле
`lyricsfag_lib/_torch_compat.py` и применяется **лениво** при
первом использовании demucs (так что пользователи, которые не
включают аудио-анализ, не платят ~3 с за `import torch`).
**Идемпотентный**, при первом применении логирует одну INFO-строку,
так что воркэраунд аудитабелен из лога:

```
INFO lyricsfag_lib._torch_compat: torch.load monkey-patch active for .th files
(PyTorch 2.6 weights_only workaround for demucs 4.0.1)
```

Оба call-сайта (`DemucsIsolator._ensure_separator` в
`lyricsfag_lib/audio_analysis.py` и gate-`--verify` в
`scripts/download_demucs_model.py`) теперь шарят единственную
реализацию, так что библиотека и скрипт больше не могут
разъехаться.

### Фикс: WARNING про объём Demucs при первом запуске показывал инвертированные числа

В `_DEMUCS_DOWNLOAD_HINTS_MB` в `lyricsfag_lib/audio_analysis.py`
значения для двух моделей были перепутаны:

* `htdemucs_ft` рекламировался как **~84 МБ**; в demucs 4.0.1 это
  на самом деле `BagOfModels` из 4 sub-models (~336 МБ суммарно:
  4 × ~84 МБ).
* `htdemucs` рекламировался как **~420 МБ**; в demucs 4.0.1 это
  на самом деле одна предобученная `HTDemucs` (~84 МБ).

Эти числа попадали в WARNING `First run will download ~N MB total`,
который срабатывает один раз на свежей установке. v1.1.4
исправляет значения, так что WARNING теперь читается:

* `htdemucs_ft` (по умолчанию) → `~336 МБ`
* `htdemucs` (legacy-вариант с одной моделью) → `~84 МБ`

Пре-существующий комментарий-блок над словарём (в котором было то
же инвертированное утверждение) тоже обновлён под реальность
demucs 4.0.1.

### Документация: `models/demucs/README.md` исправлен под demucs 4.0.1

README до сих пор описывал pre-4.0.1 раскладку (где `htdemucs`
был 5-sub-model bag'ом) в 8 местах. v1.1.4 обновляет Quick
reference-таблицу, callout "Note — default Demucs model",
параграф "Which Demucs model?", секцию "Why is this folder empty?",
size comparison, буллет "End-user experience", буллет PyInstaller
`--onefile` quirk и объяснение в "Verification step" — всё
приведено в соответствие с реальностью demucs 4.0.1.

Size-comparison-таблица теперь также цитирует реальное содержимое
YAML-дескрипторов demucs (`htdemucs_ft.yaml` перечисляет 4
sub-models; `htdemucs.yaml` — 1), так что утверждение про
per-model футпринт грепабельно прямо из YAML, а не опирается на
наблюдаемый размер на диске.

### Сборка: `build.bat`-guard для `TARGET=all` исправлен под старые Windows batch-парсеры

`build.bat` имел parenthesised `if ... ( ... )`-блок, охраняющий
`rmdir /s /q build` + `rmdir /s /q dist` под целью `all`.
Parenthesised форма триггерила `. was unexpected at this time`
на некоторых версиях Windows batch-парсера. v1.1.4 разбивает
блок на две однострочные compound-`if` инструкции (семантика
идентична: чистить `build\` + `dist\` только когда `TARGET=all`).

### Lyrics: `INSTRUMENTAL_FILENAME_RE` пере-анкеруется + no-separator паттерны возвращаются

Скомпилированный regex в `lyricsfag_lib/lyrics.py` получил
обратный переход от v1.1.2 / v1.1.3 формы `r"\b(...)"` к явной
форме `r"(?:^|[\s\-_.])(...)(?:$|[\s\-_.])"`. Явные анкеры
делают семантику границ грепабельной для downstream-тулинга и
уходят от `\b`-краевых случаев, которые v1.1.2-hotfix обходил
(v1.1.3-ревьюер отметил `\b`-форму как чрезмерно жадную на
некоторых формах имён файлов).

`offvocal` и `novocal` также возвращены в
`_INSTRUMENTAL_FILENAME_PATTERNS` как belt-and-suspenders-записи
для полностью нижне-регистровых имён файлов вроде `songoffvocal`,
где CamelCase-сплит нормализации не срабатывает. Комментарий над
списком паттернов обновлён с пояснением рационала: эти re-add'ы
были мёртвым кодом под `\b`-границей, но v1.1.4 explicit-boundary
форма снова достижима для них.


## Заметки по обновлению

* **Кодовой миграции не требуется.** Drop-in апгрейд с v1.1.3 —
  settings.json по-прежнему загружается чисто, CLI-флаги / виджеты
  GUI не изменились.
* `.th`-scoped `torch.load` monkey-patch — process-global. Если вы
  встраиваете LyricsFAG в процесс, у которого своя политика
  `torch.load`, патч пробросит `weights_only=False` и для ваших
  `*.th`-файлов, загружаемых через `torch.load(...)` тоже. В
  маловероятном случае, если это важно, ваши собственные вызовы
  `torch.load` могут явно пинить `weights_only=True`, и патч это
  значение уважает.
* WARNING про объём Demucs при первом запуске теперь показывает
  корректный размер. Если у вас уже закешированы веса, WARNING
  подавлен и вы не увидите никаких изменений в поведении.
* Пользователи PyInstaller, пересобирающие .exe, получат те же
  ~50 МБ (lite) / ~3.5 ГБ (portable), что и в v1.1.3; новых
  зависимостей нет, удалённых нет. `requirements.txt` и
  `requirements-audio.txt` не изменились.


## Изменённые файлы

* `lyricsfag_lib/_torch_compat.py` — **новый файл**, общий
  `.th`-scoped monkey-patch на `torch.load`.
* `lyricsfag_lib/audio_analysis.py` — `DemucsIsolator._ensure_separator`
  теперь использует общий monkey-patch (без inline-дубликата);
  значения `_DEMUCS_DOWNLOAD_HINTS_MB` исправлены
  (`htdemucs_ft` 84→336, `htdemucs` 420→84) и комментарий-блок
  над словарём обновлён.
* `scripts/download_demucs_model.py` — тот же monkey-patch import
  (с `echo_to_stderr=True`, чтобы строка подтверждения была видна
  из CLI); `sys.path`-манипуляция, чтобы `python scripts/...py`
  из любого cwd мог импортировать `lyricsfag_lib`; переписанный
  pre-seed-and-verify flow (делегирует `demucs.pretrained.get_model`
  + зеркалит YAML и per-hash `.th`-файлы в `models/demucs/` из
  нативного torch-hub кеша).
* `models/demucs/README.md` — 8 мест обновлено под demucs 4.0.1.
* `build.bat` — `TARGET=all` guard разбит на две compound-`if`
  строки (Windows batch parser compatibility).
* `lyricsfag_lib/lyrics.py` — `INSTRUMENTAL_FILENAME_RE` пере-анкерован
  к явным `(?:^|[\s\-_.])`-границам; паттерны `offvocal` и
  `novocal` возвращены в `_INSTRUMENTAL_FILENAME_PATTERNS`.


## Обратная совместимость

* **Без ломающих изменений.** API и схема config-файла не
  изменились. Settings.json от v1.1.3 по-прежнему загружается
  чисто. CLI / GUI-поверхность не изменилась.
* `.th`-scoped `torch.load`-патч — единственное поведенческое
  изменение в runtime-библиотеке; он активируется только на
  `.th`-путях, сохраняет безопасный PyTorch 2.6 дефолт для всего
  остального и логирует INFO-строку, так что воркэраунд
  аудитабелен. Пользователи с закешированными Demucs-весами не
  видят никаких изменений в поведении (WARNING подавлен, когда
  кеш прогрет).
* Фикс `_DEMUCS_DOWNLOAD_HINTS_MB` меняет текст WARNING'а, но не
  базовое поведение загрузки (сами веса модели всегда были
  ~336 МБ / ~84 МБ — неправильным было только пользовательское
  сообщение).
