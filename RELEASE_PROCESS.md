# LyricsFAG release process (v1.1.5+)

*This document describes the canonical release process starting with
v1.1.5. Earlier versions (including v1.1.4) used a different flow; see
the "v1.1.4 exception" section below for the diff and how to mitigate
it if you need a self-contained v1.1.4 checkout.*


## TL;DR

For each release vX.Y.Z, build **one** "release commit" that includes
the code changes, the bilingual release notes, and the `__version__`
bump. Tag that commit. `git checkout vX.Y.Z` then lands on a
self-contained release.


## The problem this process fixes

v1.1.4 used a two-commit release flow:

* `f3ab83d` -- the chore commit with code changes
* `af149cd` -- the release-notes + version-bump commit on top

The `v1.1.4` tag was cut on `f3ab83d` per the user's request, which
left the release notes in a follow-up commit **outside** the tag.
`git checkout v1.1.4` (or any tooling that clones at the tag) sees
the code changes but **not** the release notes or the `__version__`
bump. This is a known quirk of v1.1.4.


## The new process (v1.1.5+)

For each release vX.Y.Z, **one commit** is the "release commit":

1. **Make code changes.** Stage them as usual.
2. **In the same working tree, prepend a new `## vX.Y.Z (date)` section
   to [`RELEASE_NOTES.md`](RELEASE_NOTES.md)** (bilingual EN+RU; the
   consolidated changelog holds every shipped version with the
   newest at the top — replaces the per-release-file pattern that
   v1.1.x used) and bump `__version__` in
   `lyricsfag_lib/__init__.py` to `"X.Y.Z"`.
3. `git add` **everything together** -- the code changes, the consolidated
   changelog edit, and the version bump. **No separate "docs:" or "chore:"
   commit for the release notes** -- the consolidated file already carries
   the full history. (Pre-v1.2.1 commits used per-release files; the v1.2.1
   refactor introduced the consolidated format. Old `RELEASE_NOTES_*.md`
   files are still in git history under their tagged commits for any
   tooling that checks out an older tag.)
4. `git commit` with a message like:
   ```
   release: vX.Y.Z

   <one-paragraph summary of the release>
   ```
5. `git tag -a vX.Y.Z -m "vX.Y.Z: <one-line summary>"`.
6. `git push origin <branch>` then `git push origin vX.Y.Z`.

`git checkout vX.Y.Z` now lands on a self-contained release: code,
release notes, and `__version__` bump all in the tagged commit.


## What goes in the release commit

* Every code change shipped in this version.
* A new `## vX.Y.Z (date)` section prepended to
  [`RELEASE_NOTES.md`](RELEASE_NOTES.md) (bilingual EN+RU; the
  consolidated changelog).
* The `__version__` bump in `lyricsfag_lib/__init__.py`.

It should **not** include:

* "chore:" / "docs:" preambles that would later be amended with
  release notes -- those go away entirely with this process.
* Follow-up `fix typo` / `revert:` commits -- those should either
  be amended into the release commit before tagging, or shipped as
  a follow-up patch release.


## Why one commit, not a `release-notes/vX.Y.x` branch

Two reasons:

1. **Simplicity.** A single commit is easier to reason about, easier
   to rebase, and harder to break. The branch model requires a
   second ref to maintain and a merge step at release time.
2. **Locality.** The release notes describe the code in the same
   commit they ship with. There's no risk of the notes drifting from
   the code (e.g. the release-notes commit describing a fix that
   didn't actually land because the code commit was reverted or
   amended).

The branch model is the right answer for multi-maintainer projects
where release notes are written by a different person than the code.
LyricsFAG has a single maintainer, so the single-commit model is the
better fit.


## Worked example (v1.1.5)

```bash
# 1. Code changes
git checkout -b fix/whatever main
# ... edit code files ...
git add -p

# 2. Release notes + version bump (same working tree)
$EDITOR RELEASE_NOTES.md               # bilingual EN+RU; prepend a "## vX.Y.Z (date)" section at the top
# ... edit __version__ in lyricsfag_lib/__init__.py ...

# 3. Stage everything together
git add RELEASE_NOTES.md lyricsfag_lib/__init__.py <code files>

# 4. One release commit
git commit -F - <<'MSG'
release: v1.1.5

<one-paragraph summary of the release>
MSG

# 5. Tag the release commit
git tag -a v1.1.5 -m "v1.1.5: <one-line summary>"

# 6. Push branch + tag
git push origin fix/whatever
git push origin v1.1.5
# (then merge the PR / fast-forward main, depending on workflow)
```


## The v1.1.4 exception

v1.1.4 was cut with the old two-commit flow (release notes in
`af149cd`, not in the tagged commit `f3ab83d`). The release notes
exist -- they live in `af149cd` on top of the tag -- but
`git checkout v1.1.4` does not see them. This is a one-time
exception, not a precedent.

If you need a self-contained v1.1.4 for any tooling that checks out
the tag directly, check out `af149cd` instead. (Or apply this process
retroactively by force-pushing the tag -- but that's a destructive
operation; only do it if nothing external references the current
`v1.1.4` tag SHA yet.)


## See also

* [`RELEASE_NOTES.md`](RELEASE_NOTES.md) - the consolidated changelog
  (every shipped version in one file, newest-first).
* Old `RELEASE_NOTES_*.md` per-release files (used through v1.1.4) are
  still in git history under their tagged commits; this refactor (v1.2.1)
  consolidated them into the single `RELEASE_NOTES.md`.
* `README.md` / `README.ru.md` for user-facing docs.


---

# LyricsFAG — процесс выпуска релизов (v1.1.5+)

*Этот документ описывает канонический процесс выпуска релизов,
начиная с v1.1.5. Более ранние версии (включая v1.1.4) использовали
другой flow; см. секцию "Исключение для v1.1.4" ниже для diff'а и
как его смягчить, если вам нужен self-contained v1.1.4 checkout.*


## TL;DR

Для каждого релиза vX.Y.Z соберите **один** "release-коммит", который
включает изменения в коде, билингвальные release notes и бамп
`__version__`. Теганьте этот коммит. `git checkout vX.Y.Z` тогда
приземляется на self-contained релиз.


## Проблема, которую этот процесс исправляет

v1.1.4 использовал двух-коммитный release-flow:

* `f3ab83d` -- chore-коммит с изменениями в коде
* `af149cd` -- release-notes + version-bump-коммит поверх

Тег `v1.1.4` был срезан на `f3ab83d` по запросу пользователя, что
оставило release notes в последующем коммите **за пределами** тега.
`git checkout v1.1.4` (или любой тулинг, который клонирует по тегу)
видит изменения в коде, но **не** видит release notes или бамп
`__version__`. Это известная особенность v1.1.4.


## Новый процесс (v1.1.5+)

Для каждого релиза vX.Y.Z **один коммит** -- это "release-коммит":

1. **Сделайте изменения в коде.** Застейджьте их как обычно.
2. **В том же рабочем дереве добавьте новую `## vX.Y.Z (date)` секцию
   в начало [`RELEASE_NOTES.md`](RELEASE_NOTES.md)** (билингва EN+RU;
   консолидированный changelog хранит все поставленные версии, новейшая
   сверху — заменяет per-release-file паттерн, использовавшийся в
   v1.1.x) и бампните `__version__` в `lyricsfag_lib/__init__.py`
   до `"X.Y.Z"`.
3. `git add` **всё вместе** -- изменения в коде, правка консолидированного
   changelog'а и бамп версии. **Никакого отдельного "docs:" или "chore:"
   коммита для release notes** -- консолидированный файл уже несёт полную
   историю. (До v1.2.1 коммиты использовали per-release файлы; рефактор
   v1.2.1 ввёл консолидированный формат. Старые `RELEASE_NOTES_*.md`
   файлы остались в git-истории под своими тегированными коммитами для
   любого тулинга, который чекаутит старый тег.)
4. `git commit` с сообщением вида:
   ```
   release: vX.Y.Z

   <один-параграф саммари релиза>
   ```
5. `git tag -a vX.Y.Z -m "vX.Y.Z: <one-line summary>"`.
6. `git push origin <branch>`, затем `git push origin vX.Y.Z`.

`git checkout vX.Y.Z` теперь приземляется на self-contained релиз:
код, release notes и бамп `__version__` -- всё в тегированном
коммите.


## Что идёт в release-коммит

* Каждое изменение в коде, поставляемое в этой версии.
* Новая `## vX.Y.Z (date)` секция, добавленная в начало
  [`RELEASE_NOTES.md`](RELEASE_NOTES.md) (билингва EN+RU;
  консолидированный changelog).
* Бамп `__version__` в `lyricsfag_lib/__init__.py`.

Не должно идти в release-коммит:

* Преамбулы "chore:" / "docs:", которые потом были бы дополнены
  release notes -- они полностью уходят с этим процессом.
* Последующие `fix typo` / `revert:` коммиты -- они должны либо
  быть вмержены в release-коммит до тегирования, либо выпущены
  как follow-up patch-релиз.


## Почему один коммит, а не `release-notes/vX.Y.x` ветка

Две причины:

1. **Простота.** Один коммит легче обдумывать, легче ребейзить и
   сложнее сломать. Модель с веткой требует второй ref для
   поддержки и шага merge в момент релиза.
2. **Локальность.** Release notes описывают код в том же коммите, в
   котором они поставляются. Нет риска, что notes отстают от кода
   (например, release-notes-коммит описывает фикс, который
   фактически не попал, потому что код-коммит был revert'нут или
   отредактирован).

Модель с веткой -- правильный ответ для проектов с несколькими
мейнтейнерами, где release notes пишутся не тем человеком, что
код. У LyricsFAG один мейнтейнер, так что модель с одним коммитом
-- лучший фит.


## Рабочий пример (v1.1.5)

```bash
# 1. Изменения в коде
git checkout -b fix/whatever main
# ... edit code files ...
git add -p

# 2. Release notes + бамп версии (то же рабочее дерево)
$EDITOR RELEASE_NOTES.md               # билингва EN+RU; добавьте "## vX.Y.Z (date)" секцию в начало
# ... edit __version__ in lyricsfag_lib/__init__.py ...

# 3. Застейджьте всё вместе
git add RELEASE_NOTES.md lyricsfag_lib/__init__.py <code files>

# 4. Один release-коммит
git commit -F - <<'MSG'
release: v1.1.5

<один-параграф саммари релиза>
MSG

# 5. Теганьте release-коммит
git tag -a v1.1.5 -m "v1.1.5: <one-line summary>"

# 6. Пуш ветки + тега
git push origin fix/whatever
git push origin v1.1.5
# (затем merge PR / fast-forward main, в зависимости от workflow)
```


## Исключение для v1.1.4

v1.1.4 был срезан со старым двух-коммитным flow (release notes в
`af149cd`, не в тегированном коммите `f3ab83d`). Release notes
существуют -- они живут в `af149cd` поверх тега -- но
`git checkout v1.1.4` их не видит. Это одноразовое исключение, не
прецедент.

Если вам нужен self-contained v1.1.4 для любого тулинга, который
чекаутит по тегу напрямую, чекаутните `af149cd` вместо этого. (Или
примените этот процесс ретроактивно, форс-пушнув тег -- но это
деструктивная операция; делайте это только если ничто внешнее ещё
не ссылается на текущий SHA тега `v1.1.4`.)


## См. также

* [`RELEASE_NOTES.md`](RELEASE_NOTES.md) -- консолидированный changelog
  (все поставленные версии в одном файле, newest-first).
* Старые `RELEASE_NOTES_*.md` per-release файлы (использовались до
  v1.1.4) остались в git-истории под своими тегированными коммитами;
  этот рефактор (v1.2.1) консолидировал их в единый `RELEASE_NOTES.md`.
* `README.md` / `README.ru.md` -- пользовательская документация.
