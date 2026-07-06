# Release 1.1.1

Hotfix: GUI crashed on launch with `AttributeError` because a
`trace_add` callback was wired up before the `StringVar` it was
watching was constructed.

## What's new

### Fix: GUI no longer crashes on launch

v1.1.0 added a new `Source` dropdown value (`audio`) and wired up a
`StringVar.trace_add("write", _on_source_change)` callback to
auto-enable the "Use audio analysis" checkbox when the user picks
`Source = audio`. The `trace_add` call was placed at the end of the
options row, but the `self.source_var = tk.StringVar(value="auto")`
it was watching wasn't constructed until the source row further
down. The trace fired before the `StringVar` existed, crashing the
GUI on every launch with:

```
AttributeError: '_tkinter.tkapp' object has no attribute 'source_var'
  File "E:\Projects\LyricsFAG\lyricsfag_gui.py", line 567, in _build_widgets
      self.source_var.trace_add("write", self._on_source_change)
```

The fix moves the `trace_add` (and its comment block) to immediately
after `self.source_var = tk.StringVar(value="auto")`. A short
breadcrumb at the original spot notes that the trace now lives below
the source row, so this class of "widget wired up in wrong order"
regression is harder to reintroduce.

No behaviour change beyond un-crashing the GUI:
- `_on_source_change` handler is unchanged.
- The persisted-settings restore flow (which fires the trace once on
  launch when a saved `source` value is restored) still works as
  designed in v1.1.0.
- The `Source = audio` → auto-enable "Use audio analysis" behaviour
  still works as designed in v1.1.0.

### Versioning

`lyricsfag_lib.__version__` was NOT bumped for this hotfix (the
constant stays at `1.1.0`). The next patch that touches
`lyricsfag_lib/__init__.py` will sync the constant with the
v1.1.x tag chain.

## Heads-up

- This is a hotfix on top of v1.1.0. **Upgrade is recommended for all
  v1.1.0 users** — the GUI is unusable without it.
- v1.0.x users are unaffected (the crash only affects the
  v1.1.0-added `source_var` trace).
- The portable build is unchanged; just re-run
  `build.bat portable` if you want a fresh `.exe` that matches this
  tag.

---

# Релиз 1.1.1

Хотфикс: GUI падал на старте с `AttributeError`, потому что
колбэк `trace_add` был привязан до того, как наблюдаемый
`StringVar` был сконструирован.

## What's new (RU)

### Фикс: GUI больше не падает на старте

В v1.1.0 добавили новое значение `Source` (`audio`) и повесили
колбэк `StringVar.trace_add("write", _on_source_change)`, чтобы
при выборе `Source = audio` автоматически включать чекбокс
«Use audio analysis». Вызов `trace_add` стоял в конце строки
опций, но `self.source_var = tk.StringVar(value="auto")`, на
который он подписывался, конструировался только ниже в строке
источника. Трейс срабатывал раньше, чем `StringVar` существовал,
и GUI падал на каждом запуске с:

```
AttributeError: '_tkinter.tkapp' object has no attribute 'source_var'
  File "E:\Projects\LyricsFAG\lyricsfag_gui.py", line 567, in _build_widgets
      self.source_var.trace_add("write", self._on_source_change)
```

Фикс переносит `trace_add` (и его комментарий) сразу после
`self.source_var = tk.StringVar(value="auto")`. На старом месте
осталась короткая пометка, что трейс теперь живёт ниже строки
источника, — чтобы регрессия класса «виджет привязан не в том
порядке» было сложнее повторить.

Никаких поведенческих изменений, кроме починки запуска:
- Хендлер `_on_source_change` не тронут.
- Поток восстановления сохранённых настроек (который дёргает
  трейс один раз на старте при восстановлении сохранённого
  `source`) работает как задумано в v1.1.0.
- Связка `Source = audio` → авто-включение «Use audio analysis»
  работает как задумано в v1.1.0.

### Версионирование

`lyricsfag_lib.__version__` НЕ бампался в этом хотфиксе
(константа остаётся `1.1.0`). Следующий патч, который тронет
`lyricsfag_lib/__init__.py`, синхронизирует константу с цепочкой
v1.1.x тегов.

## Heads-up

- Это хотфикс поверх v1.1.0. **Апгрейд рекомендуется всем
  пользователям v1.1.0** — без него GUI нерабочий.
- Пользователи v1.0.x не задеты (падение затрагивает только
  добавленный в v1.1.0 `source_var`-трейс).
- Portable-сборка без изменений — просто пересоберите
  `build.bat portable`, если хочется свежий `.exe` под этот тег.
