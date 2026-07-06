# `models/demucs/` — reserved for a future bundled-tree workflow

This directory is **empty by design** in the current codebase. Demucs
weights are **not** stored here at runtime — they live in PyTorch Hub's
native cache, and LyricsFAG lets demucs use that path as-is.

If `models/demucs/` looks empty on a fresh clone, that is the intended
state.

> **Lite build note (v1.1.3+).** The `build-lite.bat` PyInstaller
> variant does **not** bundle Demucs (or the `torch` it depends on)
> so the resulting `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe`
> stay at the documented ~50 MB footprint. Users who run the lite
> build and tick "Use audio analysis" get a clean `LyricsFailure`
> pointing at the portable build instead of the misleading
> `pip install demucs` hint. See `README.md` →
> "Building the executable" for the per-variant size table.

> **Note — default Demucs model.** LyricsFAG's
> :class:`DemucsIsolator` defaults to ``htdemucs_ft`` (Meta's
> music-only fine-tune), not the original ``htdemucs``. The fine-tune
> gives noticeably cleaner vocal isolation on dense mixes but is itself
> a :class:`demucs.pretrained.BagOfModels` of 4 sub-models
> (~336 MB on disk: 4 × ~84 MB). The "single pretrained run" framing
> only applies to ``htdemucs`` itself (~84 MB on demucs 4.0.1 — the
> legacy 5-sub-model description pre-dates 4.0.1 and no longer
> applies). Use ``DemucsIsolator(model="htdemucs")`` /
> ``FasterWhisperAnalyzer(demucs_model="htdemucs")`` to switch to the
> lighter single-model variant if you want the ~84 MB download.


## Quick reference

| Where                                          | What lives there            | When it's populated                                                 |
|------------------------------------------------|-----------------------------|---------------------------------------------------------------------|
| `~/.cache/torch/hub/checkpoints/<hash>.th`     | Demucs weights (size varies — see below) | first `python -m demucs …` or LyricsFAG run with `--use-audio-analysis`|
| `models/demucs/` *(this directory)*            | _intentionally empty_       | future seed-and-bundle (Path B pending — see "Future workflow")     |
| `models/whisper-base/`                         | faster-whisper weights      | `python scripts/download_whisper_model.py --size base`              |

**Which Demucs model?** LyricsFAG's
:class:`lyricsfag_lib.audio_analysis.DemucsIsolator` defaults to
**``htdemucs_ft``** (Meta's music-only fine-tune), a
:class:`demucs.pretrained.BagOfModels` of 4 sub-models that downloads
~336 MB on first use (4 × ~84 MB). ``htdemucs`` itself is a single
pretrained HTDemucs (~84 MB) on demucs 4.0.1 — the legacy
5-sub-model framing pre-dates 4.0.1 and no longer applies (the
relevant YAML is ``htdemucs.yaml`` whose ``models:`` list contains
exactly one entry, e.g. ``955717e8``). Pre-seed whichever model
LyricsFAG will look for; if you pin ``DemucsIsolator(model="htdemucs")`` /
``FasterWhisperAnalyzer(demucs_model="htdemucs")``, seed the single
``htdemucs`` weight instead via
``python scripts/download_demucs_model.py --model htdemucs``.


## Why is this folder empty?

`lyricsfag_lib/audio_analysis.DemucsIsolator._ensure_separator` calls
`demucs.pretrained.get_model(self.model_name)` **with no `repo=` argument**.
Demucs 4.x's two paths are:

* `repo=None` (the default and what we use): demucs auto-downloads files
  with **hash** names (e.g. `955717e8-8726e21a.th`) into the native
  PyTorch Hub cache.
* `repo=<path>`: demucs's `LocalRepo` parses `<path>` looking for
  model-skeleton files (`<name>.th` / `<name>.yaml`) — it does **not**
  auto-download, and it expects names *not* hashes.

So the runtime flow today is: demucs handles its own cache, you pay a
one-time ~336 MB download if you stick with the default ``htdemucs_ft``
(4 sub-models × ~84 MB) or a much smaller ~84 MB if you pin
``htdemucs`` (single pretrained model). See the Quick reference table
above for the per-model breakdown. ``models/demucs/`` stays empty
unless a developer runs an explicit seed workflow (see
`scripts/download_demucs_model.py --help`).


## Size comparison

| Bundle                          | Files              | Disk      | Notes                                                                 |
|---------------------------------|--------------------|-----------|-----------------------------------------------------------------------|
| `models/whisper-base/`          | 4 (config, model.bin, tokenizer, vocabulary) | ~140 MB   | `base` size; ships with the `--add-data` flag for offline .exe        |
| `models/demucs/` (when seeded)  | demucs's own layout (e.g. `<name>.th`/`<name>.yaml`) | **~336 MB total** for the default `htdemucs_ft` (BagOfModels of 4 sub-models × ~84 MB); **~84 MB total** for legacy `htdemucs` (single pretrained model) | Each `.th` is ~84 MB on demucs 4.0.1. `htdemucs_ft.yaml` lists `models: ['f7e0c4bc', 'd12395a8', '92cfc3b6', '04573f0d']` (4 sub-models); `htdemucs.yaml` lists `models: ['955717e8']` (1 sub-model). The historical "2 GB" figure was **demucs 3.x** and does **not** apply to 4.x. |


## Demucs 4.x CLI flags — the actual ones

For context, the only flags demucs 4.0.1's `python -m demucs` CLI
exposes that touch the filesystem are:

* `-o OUT` / `--out OUT` — where separated **stems** (e.g. `vocals.wav`,
  `drums.wav`) get written. A subfolder with the model name is created
  under this. This is **not** where weights live.
* `--repo REPO` — folder containing **pre-trained** models to use *as
  input* with `-n`. Empty / wrong files raise `is neither a single
  pre-trained model or a bag of models`.
* `-d DEVICE` / `--device DEVICE` — `cuda` vs `cpu`. **NOT a directory
  flag**; renaming your output dir to `-d` will get demucs to try and
  load nothing useful (or fail on a non-existent CUDA device).

There is **no** "dump the model cache to my chosen directory" subcommand
in demucs 4.0.1. That's why the seed workflow is "TBD" here.


## Demucs's own file listing (relevant to Path B)

Confirmed by `python -c "import demucs.pretrained as dp; print(dp.REMOTE_ROOT, dp.ROOT_URL)"`:

* `dp.REMOTE_ROOT`  — `_WindowsPath('<python>/Lib/site-packages/demucs/remote')`.
  This is the demucs-shipped directory containing `files.txt` (along
  with other model-specific YAML files). `_parse_remote_files` reads
  this file at runtime and treats it as the single source of truth for
  what models exist and where to fetch them.
* `dp.ROOT_URL`     — `'https://dl.fbaipublicfiles.com/demucs/'`. Every
  entry in `files.txt` is downloaded as `<ROOT_URL><root-prefix><line>`.
* Each line of `files.txt` is `<sig>-<hash>.<ext>` (e.g. `htdemucs-f7e0c4bc.th`).
  `_parse_remote_files` returns a `Dict[str, str]` keyed by signature.

A custom downloader (Path B) can therefore: read
`<REMOTE_ROOT>/files.txt`, fetch each line from `<ROOT_URL><root><line>`,
and strip the `-<hash>` suffix to land at the bare `<sig>.<ext>` name
that `LocalRepo` expects.


## Future workflow: seed-and-bundle — _STATUS: Path A ✗ (confirmed broken 2026-07-06); Path B is the next step_

The intended workflow when you're ready to ship a fully-offline exe.
This is **forward-looking**: demucs 4.0.1 does not expose a single CLI
command that produces a `LocalRepo`-loadable directory out of the box.

**Prerequisite to bundling**: Path A (manual copy) was empirically tested
on demucs 4.0.1 and fails (see "Path A (REFUTED)" below — the error
`demucs.repo.ModelLoadingError: htdemucs is neither a single pre-trained
model or a bag of models` is the actual exception raised). A custom
downloader (Path B) is the hard requirement to achieve a working seed
that passes the Verification step.

### Path A — manual copy after CLI auto-download (REFUTED)

Step 1: trigger demucs's auto-download by running a normal separation:

```bat
python -m demucs --out models\demucs --device cuda ^
  "test\2000 - Gourmandises\(07) [Alizee] Veni Vedi Vici.flac"
```

What this produces:
- Separated stems at `models\demucs\<model>\<track>\vocals.wav` etc.
  (we don't actually want these — they're noise for our use case).
- As a side-effect, the model weights are downloaded to
  `%USERPROFILE%\.cache\torch\hub\checkpoints\`, hash-named.

Step 2: copy the weight files into `models\demucs\`:

```bat
REM /Y overwrites any stale .th files left over from a previous seed
REM attempt; without it xcopy silently skips, and the verification step
REM then runs against mixed old + new content and produces an
REM ambiguous result.
xcopy /I /Y /E %USERPROFILE%\.cache\torch\hub\checkpoints\*.th models\demucs\
```

Step 3: Path A is **empirically confirmed broken** (tested 2026-07-06,
demucs 4.0.1, Windows). Running the Verification step with the 5
copied `.th` files in `models/demucs/` raises:

```
demucs.repo.ModelLoadingError: htdemucs is neither a single pre-trained model or a bag of models.
```

Exit code 1. The copied files were deleted after the test; this
directory is back to the "intentionally empty" state. **Do not use
Path A.** The empirical result is a hard requirement for Path B
(custom downloader) — see below.

### Path B — custom downloader (correct end-state)

Implement `scripts/download_demucs_model.py` that mirrors the existing
`scripts/download_whisper_model.py`:

1. Read `demucs.pretrained.REMOTE_ROOT / "files.txt"` (the same listing
   demucs itself reads at runtime; see the section above for the
   confirmed symbol names).
2. For each non-comment line, download from
   `demucs.pretrained.ROOT_URL + root-prefix + line` and save under
   `models/demucs/<sig>.<ext>` — strip the trailing `-<hash>` from the
   filename so the cache layer doesn't sneak another random suffix in.
3. Verify md5 against the listing's hash table (demucs surfaces this
   list at `_parse_remote_files` time; either parse `files.txt` again
   or compute the hash inline).
4. Print a `DONE.-now run the verification step.` message on success.

Once this script exists, the workflow collapses to:

```bat
python scripts\download_demucs_model.py --model htdemucs
```

…and Path A's manual steps are gone.

### Verification step (gate both paths)

**Required before bundling.** Run from the project root (use `%CD%` to
make the path absolute so it works from any cwd):

```bat
python -c "import os; from pathlib import Path; from demucs.pretrained import get_model; repo = Path(os.environ.get('CD', os.getcwd())) / 'models' / 'demucs'; m = get_model('htdemucs', repo=repo); print('OK:', m.samplerate, m.sources)"
```

When run against a manual copy (Path A), this is empirically confirmed
to raise `is neither a single pre-trained model or a bag of models`,
preventing PyInstaller from baking ~336 MB of deadweight into the
`.exe` (the default `htdemucs_ft` BagOfModels of 4 sub-models × ~84 MB;
pinned `htdemucs` is a single ~84 MB model). Once Path B is implemented
and tested, this command is expected to print
`OK: <samplerate> <sources>`.

### Build hookup (parallel to the existing whisper-base branch)

`build.bat` would gain a `DEMUCS_ARGS` block alongside `AUDIO_ARGS`.
Demonstrative version, using a portable `.bat` construct that avoids
the `for / set` delayed-expansion trap:

```bat
set "AUDIO_ARGS="
if exist models\whisper-base\model.bin (
    set "AUDIO_ARGS=--add-data models\whisper-base;models\whisper-base --hidden-import faster_whisper"
)

set "DEMUCS_ARGS="
REM Require at least one .th weight file before baking the directory in
REM -- `dir /a-d /b models\demucs\*.th` succeeds iff a real weights file
REM exists. An empty directory returns exit 1 ("File Not Found"), so the
REM gate stays false and DEMUCS_ARGS stays unset (no wasteful ~336 MB
REM in exe for the default htdemucs_ft / ~84 MB for legacy htdemucs;
REM matches the Quick reference table).
dir /a-d /b models\demucs\*.th >nul 2>&1
if not errorlevel 1 (
    set "DEMUCS_ARGS=--collect-all demucs"
)

pyinstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name LyricsFAG ^
  --paths . ^
  %AUDIO_ARGS% ^
  %DEMUCS_ARGS% ^
  lyricsfag.py
```

Notes on the snippet:
- `dir /b models\demucs >nul 2>&1` succeeds iff the directory exists
  **and** contains at least one file. The `if not errorlevel 1` then
  sets `DEMUCS_ARGS`. This avoids the `for %%F in (…) do (set …)`
  block-form pitfall (which requires `setlocal enabledelayedexpansion`).
- `--collect-all demucs` is preferred over `--hidden-import demucs`
  because demucs uses lazy submodule imports inside `apply_model` and
  PyInstaller's static analysis alone will miss some. `--collect-all`
  pulls in every demucs submodule, data file, and binary dependency
  in one flag. (If you ever see `ModuleNotFoundError: demucs.something`
  at `.exe` runtime, this is the bit to widen.)
- **Trade-off**: `--collect-all demucs` is conservative and will also
  pull in any `demucs[extras]` you have installed — e.g. if you used
  `pip install demucs[tensorflow]` or `demucs[parakeet]` for some
  reason, those extras end up baked into the `.exe` (TensorFlow alone
  **reportedly** adds ~500 MB — **unverified**, based on the published
  TF wheel footprint rather than an actual demucs install). If you
  want a leaner build, switch to `--hidden-import demucs
   --hidden-import demucs.apply --hidden-import demucs.audio
   --hidden-import demucs.pretrained` and verify LyricsFAG still
  starts at `.exe` runtime; this **may** work on demucs 4.0.1 because
  demucs's static imports cover the runtime path — but **unverified**:
  confirm the `.exe` actually starts before relying on this for a
  shipped bundle.
- `--add-data models\demucs;models\demucs` is **omitted**: the
  verification step already confirmed the directory is LocalRepo-loadable
  (or Path B produced it via `download_demucs_model.py`), so demucs's
  running code can find it from `sys.executable.parent/models/demucs`
  once PyInstaller has finished.

### End-user experience after a successful bundle

* First run on a fresh end-user machine: demucs loads instantly from
  `models/demucs/` (extracted by PyInstaller `--onefile`); no
  `~/.cache/torch` write happens.
* Subsequent runs: same path; cache stays clean.
* Users without the bundle: fall back to today's auto-download path
  (~336 MB once, then cached) for the default `htdemucs_ft`
  (4 sub-models × ~84 MB). Pinning the legacy `htdemucs` drops the
  one-time download to ~84 MB (single pretrained model). See the
  Quick reference table above for the per-model breakdown.


## Caveats / gotchas

* **Hash-vs-name file naming is the fundamental blocker (empirically
  confirmed 2026-07-06).** Demucs's native cache stores weights as
  `<hash>-<hash>.th`; `LocalRepo` reads `<name>.<ext>`. Without a
  translation step, `LocalRepo` refuses to load the directory
  (`demucs.repo.ModelLoadingError: ... is neither a single pre-trained
  model or a bag of models`). Until `scripts/download_demucs_model.py`
  (Path B) is implemented and verified, no auto-downloaded CLI layout
  is usable here — Path A is therefore REFUTED, not just unverified.

* **Empty ≠ broken.** If `models/demucs/` is empty, LyricsFAG still
  works — demucs just uses the native cache. The directory exists
  only to reserve the bundled-tree layout, and `_ensure_separator`
  does call `mkdir(parents=True, exist_ok=True)` so this README isn't
  alone in the tree.

* **Demucs-version lock-in.** If upstream demucs changes its file
  layout between releases, a baked bundle from an older version will
  stop loading cleanly. Re-seed + rebuild whenever upgrading `demucs`.

* **PyInstaller `--onefile` quirk.** Each launch re-extracts the
  bundled weights directory to a temp dir: ~336 MB for the default
  `htdemucs_ft` (4 sub-models × ~84 MB; see Size comparison above),
  or ~84 MB if you pinned the single-model `htdemucs`. For a faster
  cold-start, switch to `--onedir` (folder-based distribution) once
  demucs weights are bundled — same trade-off `models/whisper-base`
  already pays at ~140 MB.

* **`build.bat` env vars.** The existing `LYRICSFAG_AUDIO=1` flag
  installs `faster-whisper`. A future `LYRICSFAG_DEMUCS=1` (or a
  combined `LYRICSFAG_AUDIO_FULL=1`) should additionally
  `pip install demucs` before invoking PyInstaller. Out of scope for
  this README; raise when ready.


## What NOT to do

* Don't `git add` auto-downloaded `<hash>.th` files into this folder:
  they are hash-named, `LocalRepo` reads by model name — copying
  creates a confusing mixed tree that fails the verification step.
* Don't run `python -m demucs --repo models\demucs …` against this
  empty directory: it raises `is neither a single pre-trained model or
  a bag of models` immediately.
* Don't treat `-d` as a directory flag in the demucs CLI. `-d` is
  `--device` (cuda vs cpu); use `-o`/`--out` for separated audio and
  `--repo` for an input model-cache directory.


## Next step (Implementation of Path B)

Path A was empirically tested on 2026-07-06 (`demucs.repo.ModelLoadingError`
on a manually-copied directory) and is REFUTED — see the (REFUTED)
note on Path A above. The single remaining next step is to implement
Path B.

**Implementation:** Write `scripts/download_demucs_model.py` mirroring
`scripts/download_whisper_model.py`. The script must do the layout
translation that `LocalRepo` requires — i.e. read
`demucs.pretrained.REMOTE_ROOT / "files.txt"`, download from
`demucs.pretrained.ROOT_URL`, and save under
`models/demucs/<sig>.<ext>` (stripping the trailing `-<hash>` so
`LocalRepo` can read by name). Once it lands and the Verification
step returns `OK: <samplerate> <sources>`, the seed workflow becomes a
one-liner and the offline-bundle story moves from "Path A ✗" to
"shipping".


## See also

* `models/whisper-base/` — the bundled faster-whisper tree, with the
  same `--add-data` pattern. See `scripts/download_whisper_model.py`
  for a working example of how a custom model downloader writes into
  a sibling `models/<name>/` directory — Path B above should mirror
  this design.
* `lyricsfag_lib/audio_analysis.py::DemucsIsolator` — the runtime
  side; confirms demucs is loaded with `repo=None` today
  (auto-download path is what runs at first launch).
* `build.bat` — the build script that needs the new `DEMUCS_ARGS`
  branch once the seed workflow (Path B) actually lands.
