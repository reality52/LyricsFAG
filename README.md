# LyricsFAG

[![GitHub repo](https://img.shields.io/badge/GitHub-reality52%2FLyricsFAG-181717?logo=github)](https://github.com/reality52/LyricsFAG)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Latest release](https://img.shields.io/badge/release-v1.2.1-blue)](RELEASE_NOTES.md)

> **AI-assisted project.** This codebase was written with substantial help
> from an AI coding assistant ([Codebuff](https://codebuff.com), model
> `minimax/minimax-m3`) under human direction and review. The code has
> been tested but not certified — running LyricsFAG against your music
> library (network calls to LRCLIB / Genius, Whisper / Demucs weight
> downloads, writes to `.lrc` files next to your audio) is **at your own
> risk**. Try it on a copy of your library first before trusting it with
> a real one.

A small, dependency-light command-line tool that walks a music library,
reads audio tags, and writes matching `.lrc` files next to each track.

It pulls [LRC] data from **[LRCLIB.net]** (free, no auth, returns synced
lyrics whenever possible) and falls back to **[Genius]** (huge database,
plain text) when LRCLIB has nothing or you supply a Genius token.
If neither source has lyrics for a track, it will try to generate a
`.lrc` file locally with the help of [Demucs] and [Whisper]. It can run
on a CUDA-capable GPU or fall back to CPU (notably slower).

Supports the following audio formats (anything `mutagen` can read):
`FLAC`, `MP3`, `M4A/MP4`, `AAC`, `OGG`, `OPUS`, `WMA`, `WAV`, `APE`, `WV`,
`TAK`.

Read in another language: [Русский (`README.ru.md`)](README.ru.md).

[LRC]: https://en.wikipedia.org/wiki/LRC_(file_format)
[LRCLIB.net]: https://lrclib.net/
[Genius]: https://genius.com/
[Demucs]: https://github.com/facebookresearch/demucs
[Whisper]: https://github.com/SYSTRAN/faster-whisper


## Features at a glance

- **Synced-first, plain-text fallback.** LRCLIB for time-stamped lyrics,
  Genius for plain text, local Whisper + Demucs as a 3rd-tier synthetic
  fallback when both web sources miss.
- **Opt-in tag embedding.** Pass `--embed-in-tags` (CLI) / tick
  "Embed lyrics in tags" (GUI) and LyricsFAG also writes a plain-text
  lyrics tag into each audio file -- ID3 `USLT` for MP3, Vorbis
  `LYRICS` for FLAC/OGG/OPUS, atom `©lyr` for MP4/M4A, descriptor
  `WM/Lyrics` for WMA, APEv2 `LYRICS` for WavPack/APE. The `.lrc`
  sidecar keeps the synced / header-rich view; the tag holds only the
  lyric text. WAV, TAK and raw AAC have no standard tag and are
  skipped cleanly (a `[tags=skipped (no standard tag)]` suffix in
  the log, never a batch failure). `--force` overwrites; `--no-force`
  honours any pre-existing tag symmetrically with the `.lrc`
  behaviour.
- **Richer `.lrc` headers.** Every shipped file gets `[ti:]` / `[ar:]`
  / `[al:]` / `[length:]` and, when the source file's tags carry them,
  `[au:composer]`, `[lang:language]`, `[year:YYYY]`. A
  `[tool:LyricsFAG X.Y.Z]` producer credit is stamped on every write
  so the file is always attributable. *(New in v1.2.1.)*
- **Defensive Genius filters.** Wiki/list pages that used to dump 2000+
  lines of name-registry into your `.lrc` are detected and rejected
  cleanly, as are wrong-song auto-corrects that share one keyword
  with your query. *(New in v1.2.0.)*
- **Two PyInstaller builds, one binary each.** A slim `~50 MB` `lite`
  `.exe` (LRCLIB + Genius only) and a `~4 GB` `portable` `.exe` that
  bundles `torch` + `demucs` + `faster-whisper` + the model weights
  (default `whisper-small` ~500 MB + `htdemucs_ft` ~84 MB) for fully
  offline use. Each binary is dual-mode: a double-click pops the Tk
  GUI, a `path` argument from a terminal runs the CLI.
- **PyTorch 2.6 ready.** A shared `.th`-scoped `torch.load` monkey-patch
  fixes the `Weights only load failed` `WeightsUnpickler` error that
  crashes demucs 4.0.1 on first run under PyTorch 2.6+. *(New in v1.1.4.)*
- **Both surfaces share one engine.** The Tk-based GUI (`lyricsfag_gui.py`)
  and the CLI (`lyricsfag.py`) consume the same `process_one()` worker
  so `_format_summary_lines()` / the `Done in N.--..` line is identical
  in both.


## Quick start (Windows)

1. Install Python 3.10+ and `git` (or download this folder as a zip).
2. From the project root:

   ```bat
   REM Core chain (LRCLIB + Genius).  Always installed.
   pip install -r requirements.txt
   python lyricsfag.py "C:\Music\Library"
   ```

   To add local audio analysis (Whisper + Demucs, ~4 GB extra) for
   `--use-audio-analysis` on the command line, install the
   `requirements-audio.txt` extra **next**:

   ```bat
   pip install -r requirements.txt
   pip install -r requirements-audio.txt
   ```

   The split exists so the `build-lite.bat` PyInstaller .exe can
   stay at the documented ~50 MB footprint without bundling `torch`;
   see [Building the executable](#building-the-executable) for the
   per-variant contract.

3. To build a prebuilt `.exe` (no Python required for the user):

   ```bat
   build.bat                REM builds BOTH lite and portable into dist\ (one .exe each)
   build.bat lite           REM only LyricsFAG-Lite.exe      (~50 MB; downloads models on first audio-analysis use)
   build.bat portable       REM only LyricsFAG-Portable.exe  (~4 GB; fully offline; bakes in whisper-small + htdemucs_ft)
   ```

   The resulting `.exe` is dual-mode: double-click in Explorer pops the
   Tk GUI; running it with a path argument (from PowerShell / cmd) runs
   the CLI loop. Same binary, same dispatch logic in `lyricsfag._wants_gui`.
   See [Building the executable](#building-the-executable) below for the
   per-variant output table and the helper scripts that pre-seed weights.

4. *(Optional)* Pre-seed the local audio-analysis weights before your
   first run with the bundled helper scripts. Both live in `scripts/`
   and only need `python` plus the corresponding optional dependency
   (`faster-whisper`, `demucs`) from `requirements-audio.txt`:

   ```bat
   REM Whisper weights (~150 MB for the default 'base' size).
   python scripts\download_whisper_model.py --size base

   REM Demucs weights for the default 'htdemucs_ft' (~336 MB:
   REM BagOfModels of 4 sub-models x ~84 MB on demucs 4.0.1).
   REM --verify runs an end-to-end load check before you bake them in.
   REM (No --model flag needed -- scripts/download_demucs_model.py
   REM  defaults to htdemucs_ft now.)
   python scripts\download_demucs_model.py
   python scripts\download_demucs_model.py --verify
   ```

   *(If you explicitly opted into the legacy 5-sub-model bag via
   ``--demucs-model htdemucs``, seed that one instead: it's a single
   pretrained HTDemucs on demucs 4.0.1 (~84 MB) -- the legacy
   5-sub-model framing pre-dates 4.0.1 and no longer applies:*

   ```bat
   python scripts\download_demucs_model.py --model htdemucs --verify
   ```

   Both scripts support `Range:`-header resume, so re-running them on a
   flaky connection only re-downloads the missing bytes. Full reference
   for flags, mirrors, and troubleshooting lives in
   [Local audio-analysis fallback (faster-whisper)](#local-audio-analysis-fallback-faster-whisper)
   and [Building the executable](#building-the-executable) below.


## Graphical mode

A Tk-based desktop UI ships alongside the CLI. After ``pip install -r
requirements.txt``:

```bat
python lyricsfag_gui.py
```

Or, from the CLI binary, request the GUI over the same flag:

```bat
dist\LyricsFAG.exe --gui
```

The window offers:

* **Folder picker** with a Browse button
* **Recursive** / **Force overwrite** / **Dry-run** checkboxes
* **Source** dropdown (``auto`` / ``lrclib`` / ``genius`` / ``audio``)
* **Genius token** entry (or set ``GENIUS_ACCESS_TOKEN`` once in your shell)
* **Use audio analysis (local)** master switch — when ticked, Demucs is
  hardcoded on (no separate toggle); when ``Source = audio`` is selected
  the checkbox is force-enabled and greyed out so the chain stays consistent
* **Whisper model** + **Device** dropdowns + optional local **Model path**
* **Start** / **Stop** buttons with live, cancellable progress
* **GPU / CPU badge** at the bottom-right of the window that tracks the
  user's Device pick
* **Colour-coded log** (green = written/dry-run, yellow = skipped/missing,
  red = failed, **orange = Whisper-transcribed** — synthetic, may carry
  ASR errors so you can spot them at a glance)
* **Completion popup** — Done / Stopped / worker-crashed, after every run
  except empty folders
* **Open output folder** button to jump straight to your library in Explorer
* **`?`  Help** button (last in the toolbar row) opens a startup tip
  describing the provider chain, the Genius token hint, first-run
  download sizes, and the `--dry-run` safety tip
* **Hover tooltips** on every primary input widget (entries, checkbuttons,
  combos, buttons) — 500 ms hover delay, 8 s auto-dismiss


## CLI

```
python lyricsfag.py PATH [options]

positional:
  PATH                       Folder or single audio file. Default: current dir.

options:
  --recursive | --no-recursive
                             Walk subdirectories or only the top folder.
                             Default: --recursive.
  --force                    Overwrite existing .lrc files.
  --source {auto|lrclib|genius|audio}
                             Lyrics provider. Default: auto (LRCLIB then Genius).
                             'audio' goes straight to local transcription.
  --genius-token TOKEN       Genius API token (or set GENIUS_ACCESS_TOKEN).
  --use-audio-analysis       Add local faster-whisper as a 3rd fallback.
  --audio-model {tiny|base|small|medium|large-v3}
                             Whisper model size. Default: base (~150 MB).
  --audio-model-path PATH    Local directory with the model files.
  --device {auto|cuda|cpu}   Compute device for faster-whisper (+ demucs).
                             Default: auto (CUDA if available, else CPU).
  --embed-in-tags            Also write a plain-text lyrics tag into
                             each audio file (USLT / LYRICS / ©lyr /
                             WM/Lyrics / APEv2 LYRICS). Off by default.
  --dry-run                  Print what would happen, write nothing.
  --quiet | --verbose        Log level.
  --color {auto|always|never}
                             ANSI colours. Default: auto (TTY only).
  --limit N                  Stop after writing N files (0 = no limit).
  -h, --help                 Show this help.
```

Exit codes:
- `0` every selected track processed cleanly
- `1` one or more tracks failed (network errors, no match)
- `2` bad arguments (missing path, requested Genius without a token, ...)


## How it works

```
path/Artist - Album/
  01 - Song A.flac  ───────►  01 - Song A.lrc   (synced, from LRCLIB)
  02 - Song B.flac  ───────►  02 - Song B.lrc   (synced, from LRCLIB)
  03 - Song C.flac  ───────►  03 - Song C.lrc   (plain text, from Genius)
  04 - Song D.flac  ───────►  04 - Song D.lrc   (synced, from local Whisper)
```

1. Walk the directory, collect every file whose extension looks like audio.
2. Read tags via `mutagen` (`title`, `artist`, `album`, `composer`,
   `language`, `year`, `duration`). When metadata is missing, parse the
   filename -- e.g. `(01) [Artist] Title.ext` and `Artist - Title.ext`
   are recognised.
3. Query `LRCLIB.net/api/get?artist_name=…&track_name=…&duration=…`. If
   synced lines come back, write them straight into the LRC.
4. If LRCLIB returns nothing, query [Genius] (token required). The
   response is validated by the **Genius safety filters** (v1.2.0+):
   * Wiki / list pages whose body is an alphabet-navigation header
     (`A | B | C | ... | Z`) or exceeds 1000 lines are rejected with a
     `genius: page looks like a Genius list/index (...)` diagnostic
     -- they used to dump 2000+ lines of name-registry into the user's
     `.lrc`.
   * Wrong-song auto-corrects whose title / artist don't share enough
     keywords with the user's tags are rejected with a
     `genius: song mismatch: query 'Yesterday' by 'Beatles' != response
     'Imagine' by 'John Lennon' (title=0.00, artist=1.00)` diagnostic --
     so the user can fix their tags without re-running.
   Plain text from legitimate matches is formatted as plain lines under
   the metadata headers, which all major players (`foobar2000`, `AIMP`,
   `PowerAmp`, `MusicBee`, `Vanilla`, `Musicolet`, `VLC`) display as a
   static/unsynced view.
5. (With `--use-audio-analysis`) If both providers miss, transcribe the
   audio locally via `faster-whisper`. Hallucinated / silent segments
   are filtered via `no_speech_prob` and a small phrase blocklist.
   Demucs 4.x vocal isolation is run **mandatorily before** Whisper
   (mandatory as of v1.1.0, with no on/off knob -- the user opts out
   of the *whole* local fallback by unchecking `Use audio analysis`).
6. **(Opt-in `--embed-in-tags`)** Independently of the .lrc sidecar
   above, write a plain-text lyrics tag into each audio file's native
   metadata. The .lrc keeps the synced / header-rich view; the tag
   holds only the lyric text. The dispatch is by audio format:

   | Format               | Tag key written           | Read by (most) |
   |----------------------|---------------------------|----------------|
   | MP3 (ID3v2)          | `USLT` (UTF-8, lang='eng')| foobar, AIMP, iTunes, MusicBee, WMP, Vanilla |
   | FLAC                 | Vorbis `LYRICS`           | foobar, AIMP, MusicBee, Vanilla, Musicolet |
   | OGG-Vorbis / Opus    | Vorbis `LYRICS`           | foobar, AIMP, MusicBee, VLC |
   | MP4 / M4A            | atom `©lyr`               | iTunes, MusicBee (plugin), JRiver, foobar |
   | WMA (ASF)            | descriptor `WM/Lyrics`    | Windows Media Player, MusicBee, foobar |
   | WavPack / APE        | APEv2 `LYRICS`            | foobar, AIMP, MusicBee |
   | WAV · TAK · raw AAC  | *(skipped: no standard tag, log-warned)* | -- |

   Tag-failure does **not** downgrade the .lrc outcome -- the sidecar
   is already on disk and you get a `[tags=ERROR: …]` suffix per
   file, not a red fail. `--no-force` honours any pre-existing tag
   the same way it does for the `.lrc`.


## LRC format written

```lrc
[ti:Moi... Lolita]
[ar:Alizée]
[al:Gourmandises]
[au:Laurent Boutonnat]
[lang:fr]
[year:2000][tool:LyricsFAG 1.2.1] 
[length:04:26]

[00:12.34]Moi je m'appelle Lolita
[00:16.78]Lo lo lo lo lo lo Lolita
```

A few things worth knowing about the headers:

* `[ti:]` / `[ar:]` / `[al:]` are emitted only when the source audio's
  tags (or the parsed filename) populate them.
* `[au:composer]` is emitted only when `TCOM` / `\xa9wrt` /
  `COMPOSER` is non-empty. *(New in v1.2.1.)*
* `[lang:language]` is emitted only when `TLAN` / `LAN` is non-empty.
  Pass-through (no ISO-639-1 sanitization) so a tagged `English` lands
  as `[lang:English]`. *(New in v1.2.1.)*
* `[year:YYYY]` is emitted only when the year extraction yields a
  4-digit value. The reader takes the first 4-digit run from
  `TDRC` / `TYER` / `\xa9day` / `DATE` / `YEAR` so a tagged
  `TDRC:"2024-08-01"` lands cleanly on `2024`. *(New in v1.2.1.)*
* `[tool:LyricsFAG X.Y.Z]` is emitted on **every** write by `process_one()`
  unconditionally, so the running library version is always stamped
  into the file. Use it as the cheapest upgrade-verifier: re-process a
  single file and look for `[tool:LyricsFAG 1.2.1]` in the resulting
  `.lrc`. *(New in v1.2.1; bumped on every release.)*
* `[length:]` is emitted when the source audio's duration is known.

Unsynced fallback (from Genius) drops the timestamps and keeps only the
metadata headers + a plain text body, but the new liner-notes fields
above still appear unchanged.


## Configuration

- `--genius-token` *or* environment variable `GENIUS_ACCESS_TOKEN`.
  Get a free token at <https://genius.com/api-clients>.
- Without a Genius token, the tool will still try LRCLIB. When LRCLIB has
  no synced lyrics but returns plain text, that text is used; otherwise
  the track is reported as a miss.
- GUI state (folder, recursive / force / dry-run / source / genius_token
  / audio_model / audio_model_path / device) is persisted to
  `settings.json` under the OS config dir on **Start** and on **Close**,
  so the same widgets come up populated the next launch. Genius token
  is stored plaintext by design (it already lives in the process
  environment anyway); see the SECURITY note in
  `lyricsfag_lib/settings.py` for the rationale.
- Pre-v1.1.0 `settings.json` files with a stale `demucs` key are
  silently dropped on load (the on/off demucs combobox was removed in
  lockstep with the `--no-demucs` CLI flag in v1.1.0).


## Local audio-analysis fallback (faster-whisper)

For tracks that LRCLIB and Genius cannot match, you can run the same
audio through a local `faster-whisper` model that produces **synced**
timestamps straight out of the audio. This is opt-in.

```bat
pip install faster-whisper

REM 1. Fetch the model (uses a mirror that bypasses the LFS CDN block when the
REM    canonical path is unreachable). Resumes across TCP RST mid-stream.
python scripts/download_whisper_model.py --size base

REM 2. Run with the audio fallback enabled
python lyricsfag.py "C:\Music\Library" --use-audio-analysis --audio-model base
```

Model sizes (CPU-laptop-friendly):

| Model      | Size  | Speed vs. realtime (CPU) | Quality note                        |
|------------|-------|--------------------------|-------------------------------------|
| `tiny`     | ~75 MB | ~10-30x                   | Fast; tends to hallucinate on long instrumentals. |
| `base`     | ~150 MB| ~3-10x                    | **Default**; balanced for most music.            |
| `small`    | ~500 MB| ~1-3x                     | Cleaner LRC timestamps; noticeably slower.       |
| `medium`   | ~1.5 GB| < realtime                | Highest accuracy; significant CPU+RAM cost.      |
| `large-v3` | ~3 GB  | < realtime                | Best accuracy; GPU strongly recommended.         |

### What ends up on disk

`python scripts/download_whisper_model.py --size base` writes into
`models/whisper-base/` adjacent to the project (the path the analyzer
auto-discovers):

```
models/whisper-base/
├── config.json          (~2 KB)
├── model.bin            (~138 MB -- the heavy weights)
├── tokenizer.json       (~2 MB)
└── vocabulary.txt       (~450 KB)
```

### If the script can't fetch `model.bin`

The download defaults to `https://hf-mirror.com` with Range-header
resume. On networks where the LFS storage layer (`cdn-lfs.huggingface.co`)
is unreachable for the heavy `model.bin` (typical Windows + corporate
DPI setup), the script prints a `FAILED` line **with the exact mirror and
canonical URLs** so you can drop the file into the right place from any
browser:

1. Open `https://hf-mirror.com/Systran/faster-whisper-base/tree/main`
   (or the canonical `https://huggingface.co/Systran/faster-whisper-base/tree/main`).
2. Download **`model.bin`** (~138 MB) into `models/whisper-base/`.
3. Re-run the script (it'll skip already-downloaded files because the
   local size matches Content-Length).
4. Verify with `python lyricsfag.py ... --use-audio-analysis --audio-model base --dry-run`.

If `model.bin` is missing entirely, the analyzer returns a clean
`LyricsFailure("whisper", "model load failed: ...")` -- your run keeps
going on the LRCLIB+Genius chain without crashing.

### Demucs download sizes (v1.1.4+)

The pre-flight WARNING on first run reports the **correct** sizes for
the demucs 4.0.1 model layout:

| Model | Size | Notes |
|-------|------|-------|
| `htdemucs_ft` *(default)* | ~336 MB | `BagOfModels` of 4 sub-models (4 × ~84 MB) per `htdemucs_ft.yaml`. Meta's music-only fine-tune. |
| `htdemucs` *(legacy)* | ~84 MB | Single pretrained `HTDemucs` per `htdemucs.yaml`. Use this for the lighter download footprint. |

The previous README values (~84 MB for `htdemucs_ft`, ~420 MB for
`htdemucs`) were inverted; the WARNING now points at the right numbers
for the demucs 4.0.1 reality.

### PyTorch 2.6 workaround (v1.1.4+)

A shared `.th`-scoped `torch.load` monkey-patch
(`lyricsfag_lib/_torch_compat.py`) fixes the
`Weights only load failed ... GLOBAL fractions.Fraction` crash that
hits demucs 4.0.1 on first run under PyTorch 2.6+. The patch forwards
`weights_only=False` only for `*.th` files (the demucs weights just
downloaded from `facebookresearch/demucs`) and keeps the safe 2.6
default for every other `torch.load` caller in the process (notably
faster-whisper's Silero VAD). The patch is lazy (only on first demucs
use) and idempotent.

### Notes

- After `pip install -r requirements-audio.txt` (which pulls
  `faster-whisper`) and the model is on disk, the analyzer loads it
  with `local_files_only=True` (no internet needed).
- The **lite** PyInstaller build does **not** install
  `requirements-audio.txt`, so its users see a `LyricsFailure`
  with a hint pointing at the portable build. See
  [Building the executable](#building-the-executable) for why.
- Provide your own model directory via `--audio-model-path` to ship a
  pre-downloaded model with your `.exe`. The portable build helper
  `build-portable.bat` auto-detects whatever is in `models\whisper-base\`
  and `models\demucs\` and bundles whatever it finds -- no env-var
  required to opt in. The legacy `LYRICSFAG_AUDIO=1` env var is still
  honoured as a synonym for `build.bat portable` for backward
  compatibility, but new code should pass the explicit arg.
- The GUI checkbox "Use audio analysis (local)" enables the same chain
  (LRCLIB -> Genius -> faster-whisper) without re-running the CLI.


## Building the executable

`build.bat` is a thin orchestrator that dispatches to **two** PyInstaller
variants. Each variant produces **one dual-mode `.exe`** into the
`dist\` directory. The single binary handles both surfaces:

* **Double-click in Explorer (no argv)** → `_wants_gui()` returns `True` →
  `lyricsfag_gui.main()` launches the Tk window. The pyinstaller-hosted
  console process stays alive underneath and the window overlays it
  (the standard Windows pattern, same as `git.exe` / `python.exe`).
* **Run with arguments from a terminal** (a positional path or any flag) →
  `_wants_gui()` returns `False` → argparse-driven CLI loop, coloured
  log lines, final summary. Same `.exe`, no second binary.

| Variant     | Output binary              | Footprint  | Audio analysis                          | Network on first run |
|-------------|---------------------------|------------|-----------------------------------------|----------------------|
| **lite**    | `dist\LyricsFAG-Lite.exe`  | **~50 MB** | **Not supported** (LRCLIB + Genius only)| Yes  -- whisper + demucs weights are downloaded on first audio-analysis use (lite users get a `LyricsFailure` hint pointing at the portable build instead) |
| **portable**| `dist\LyricsFAG-Portable.exe` | **~4 GB** | Full Whisper (default `small`) + Demucs (`htdemucs_ft`) + bundled weights | No  -- once the helper scripts below pre-seed `models\whisper-small\` and `models\demucs\`, the `.exe` is fully offline |

> **Why is the lite build 50 MB but the portable build ~4 GB?**
> `demucs` 4.x pulls in `torch` transitively (~3.8 GB on Windows).
> PyInstaller `--onefile` bundles the whole Python environment into
> the `.exe`, so the portable build pays the full torch cost plus the
> bundled `whisper-small` weights (~500 MB) plus `htdemucs_ft` (~84 MB)
> = ~4 GB. The lite build skips that cost entirely by not installing
> `requirements-audio.txt`. The **only** difference between the two
> variants is whether `requirements-audio.txt` is installed before
> `pyinstaller`. See `requirements.txt` and `requirements-audio.txt`
> for the split.

> **Behavioural change vs v1.1.2:** the **lite** build no longer
> supports the local audio-analysis chain. Users who tick "Use audio
> analysis" in the lite GUI (or pass `--use-audio-analysis` to the
> lite CLI) get a clean `LyricsFailure` pointing at the portable
> build instead of the misleading `pip install faster-whisper`
> hint. This is the only way to deliver a true ~50 MB lite `.exe` --
> `torch` alone is ~3.8 GB.

### Build commands

```bat
REM Both variants (default; produces two dual-mode .exe files in dist\).
build.bat

REM Only one variant.
build.bat lite
build.bat portable
```

The resulting `.exe` is dual-mode out of the box: no GUI / CLI
sub-binaries to ship side-by-side. The dispatch is one line in
`lyricsfag._wants_gui()`:

```python
if not args_list:                                  # 1. double-click
    return True
if re.search(r"^--?gui(=|$)", any_arg):           # 2. explicit --gui
    return True
return False                                      # 3. CLI otherwise
```

The legacy `LYRICSFAG_AUDIO=1` env var is still honoured -- it maps to
`build.bat portable`. Either invocation is equivalent:

```bat
set LYRICSFAG_AUDIO=1 ^& build.bat       REM (legacy)
build.bat portable                        REM (preferred)
```

### Producing a fully-bundled portable build

The portable `.exe` only ships weights that you pre-seed into `models\`
*before* running `build.bat portable`. Run both helper scripts in turn:

```bat
REM 1. Whisper 'small' weights (~500 MB; the v1.2.1 default baked into
REM    the portable build).  --size base / --size medium work too if
REM    you'd rather ship a different model, but the build helper
REM    auto-detects models\whisper-[small|base] whichever is seeded.
python scripts\download_whisper_model.py

REM 2. Demucs weights for the default 'htdemucs_ft' (~84 MB single
REM    pretrained run on demucs 4.0.1). The script reads demucs's own
REM    YAML descriptor so the layout is automatically LocalRepo-loadable
REM    (Path B in models\demucs\README.md).
REM    (No --model flag needed -- the script defaults to htdemucs_ft.)
python scripts\download_demucs_model.py

REM 3. Verify the directory is in a working state before baking.
python scripts\download_demucs_model.py --verify

REM    (If you pinned the legacy --demucs-model htdemucs, pass --model htdemucs
REM    here instead of the default -- on demucs 4.0.1 that's a single
REM    pretrained HTDemucs on ~84 MB; the previous 5-sub-model framing
REM    pre-dates 4.0.1 and no longer applies.)

REM 4. Build the offline-ready .exe.
build.bat portable
```

If you skip step 2, `build-portable.bat` warns and ships a partially-portable
`.exe` that still downloads Demucs on first audio-analysis use -- Whisper itself
is always bundled (it's small enough).

### Identifying which `.exe` is which

* `LyricsFAG-Lite.exe` -- for users with occasional audio-analysis
  needs and a stable internet connection (Whisper + Demucs weights
  download on first `--use-audio-analysis` use).
* `LyricsFAG-Portable.exe` -- for USB-stick / air-gapped /
  corporate-DPI-restricted environments where a 500 MB fetch at
  first launch would be blocked. Bundles `models\whisper-small\`
  and `models\demucs\` for fully offline operation.

You'll get an end-of-build summary along the lines of::

```
=== Build complete ===
  dist\LyricsFAG-Lite.exe       (dual-mode, ~50 MB; downloads models on first use)
    CLI:    dist\LyricsFAG-Lite.exe "C:\Music\Library"
    GUI:    Double-click in Explorer.  Same .exe -- _wants_gui() auto-dispatches.
  dist\LyricsFAG-Portable.exe   (dual-mode, ~4 GB; fully offline; seeded small whisper + htdemucs_ft)
    CLI:    dist\LyricsFAG-Portable.exe "C:\Music\Library"
    GUI:    Double-click in Explorer.  Same .exe -- _wants_gui() auto-dispatches.
```

For a *nix build, the equivalent manual command line is:

```bash
# lite (single dual-mode .exe)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Lite  --paths . lyricsfag.py

# portable (single dual-mode .exe; only after the two download scripts
#  have seeded models/whisper-small + models/demucs)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Portable --paths . \
  --add-data models/whisper-small;models/whisper-small --collect-all faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag.py
```


## Project layout

```
LyricsFAG/
├── lyricsfag.py             # CLI entry point (also handles --gui)
├── lyricsfag_gui.py         # Tkinter desktop GUI
├── lyricsfag_lib/
│   ├── __init__.py
│   ├── audio.py             # tag/filename parsing (mutagen)
│   ├── audio_analysis.py    # faster-whisper + demucs (local audio-analysis fallback)
│   ├── _torch_compat.py     # PyTorch 2.6 / demucs 4.0.1 weights_only monkey-patch
│   ├── device.py            # CUDA / demucs capability probes
│   ├── lyrics.py            # LRCLIB + Genius clients (+ safety filters, v1.2.0+)
│   ├── lrc.py               # LRC serializer (+ liner-notes fields, v1.2.1+)
│   └── settings.py          # persistent GUI settings (JSON under %APPDATA%)
├── requirements.txt         # core deps (always installed)
├── requirements-audio.txt   # optional Whisper + Demucs + torch
├── build.bat                # orchestrator: lite / portable / all
├── build-lite.bat           # single ~50 MB .exe (downloads models on first use)
├── build-portable.bat       # single ~4 GB .exe (weights bundled in)
├── scripts/
│   ├── download_whisper_model.py    # HF-mirror Range-resume downloader (Whisper)
│   └── download_demucs_model.py     # demucs YAML-descriptor + LocalRepo seed
├── models/
│   ├── whisper-small/       # faster-whisper weights (v1.2.1 default; bundled when present)
│   └── demucs/              # demucs weights (bundled when populated)
└── test/                    # Alizée test album
```


## Tray / background mode

The GUI runs entirely in the foreground by default. If you want to wire it
into a tray icon for silent background runs, look at ``pystray`` -- drop the
existing ``LyricsFAGApp.mainloop()`` call in ``lyricsfag_gui.py`` and replace
with a tray icon callback that calls ``_on_start`` periodically (out of scope
for the current release).


## Current version: v1.2.1

Detailed release notes for every shipped version live in
[`RELEASE_NOTES.md`](RELEASE_NOTES.md) -- one consolidated reverse-chronological
changelog. The big-picture per-release changes are summarised below so a fresh
reader doesn't have to scroll all the way through `RELEASE_NOTES.md`:

### v1.2.1 -- LRC liner-notes + `--embed-in-tags` + dual-mode 2-EXE build (patch release)

* **LRC liner-notes headers.** Read the source audio's tags for
  `TCOM` / `\xa9wrt` / `COMPOSER`, `TLAN` / `LAN`, and `TDRC` /
  `TYER` / `\xa9day` / `DATE` / `YEAR`, then propagate them into the
  LRC as `[au:]` / `[lang:]` / `[year:YYYY]` headers (each header
  is conditional on a non-empty / non-zero value -- silent skip on
  malformed tags).
* **`[tool:LyricsFAG 1.2.1]` producer credit** stamped on **every**
  `.lrc` write so the file is always attributable. Use it as the
  cheapest upgrade-verifier: re-process a single file and look for
  `[tool:LyricsFAG 1.2.1]` in the resulting `.lrc`.
* **`--embed-in-tags` opt-in tag embedding.** `--embed-in-tags` (CLI)
  / "Embed lyrics in tags" (GUI) writes a plain-text lyrics tag into
  each audio file's native metadata -- ID3 `USLT` (UTF-8, lang='eng')
  for MP3, Vorbis `LYRICS` for FLAC/OGG-Vorbis/Opus, MP4 atom `©lyr`
  for M4A, ASF descriptor `WM/Lyrics` for WMA, APEv2 `LYRICS` for
  WavPack/APE. WAV, TAK and raw AAC have no standard tag and are
  skipped cleanly with a `[tags=skipped (no standard tag)]` log
  suffix (never a batch failure). The `.lrc` keeps the synced /
  header-rich view; the tag holds only the lyric text.
  `--force` overwrites; `--no-force` honours any pre-existing tag
  the same way it does for the `.lrc`. Tag-failure does **not**
  downgrade the `.lrc` outcome -- the sidecar is already on disk and
  you get a `[tags=ERROR: ...]` suffix, not a red fail.
* **Dual-mode 2-EXE build.** Each build variant now produces **one**
  dual-mode `.exe` (not a CLI + GUI pair). Distinguishing surface is
  resolved at runtime by `lyricsfag._wants_gui()`: empty argv pops
  the Tk GUI; `--gui` / `-g` does the same explicitly; any other
  argv (positional path or any flag) runs the CLI loop. Same
  `.exe`, same entry point (`lyricsfag.py`), no second binary to
  ship.
* **Whisper-small bundled by default in the portable build.**
  `build-portable.bat` bakes `models/whisper-small\` (~500 MB, the
  size `download_whisper_model.py` defaults to) instead of the
  smaller `models/whisper-base/` (~150 MB). Cleaner transcription
  timestamps mean noticeably less hand-editing on dense mixes. The
  build helper still auto-detects `whisper-base` as a backward-compat
  fallback -- v1.2.x dev trees don't need a re-seed.
* **PyInstaller `--collect-all faster_whisper`** replaces the older
  `--hidden-import faster_whisper` so the bundled `.exe` carries all
  of faster-whisper's runtime data + CTranslate2 .so files, matching
  the parity we already had for demucs.
* **`lyricsfag_lib.tags` module** -- new home for the mutagen-based
  embed dispatch. `embed_lyrics(path, plain_text, force=...)` returns
  an `EmbedResult` dataclass (status, format, tag_name, error) so the
  CLI / GUI can render the `[tags=...]` log suffix without inspecting
  exceptions themselves.
* Files touched: `lyricsfag.py`, `lyricsfag_gui.py`, `lyricsfag_lib/`
  (new `tags.py`; audio.py / lrc.py / settings.py / audio_analysis.py
  tweaks), `scripts/download_whisper_model.py` (default size `small`,
  default output dir `models/whisper-small`), `build.bat`,
  `build-lite.bat`, `build-portable.bat`, `README.md`, `README.ru.md`.

### v1.2.0 -- Genius safety filters + dead-code cleanup (minor release)

* `lyrics.LyricsFetcher` (formerly the typo-and-spell-prone Genius
  step) now rejects two classes of bad results that used to land in
  the user's `.lrc` without warning:
  * **Wiki / list pages** whose body is an alphabet-navigation header
    (`A | B | C | ... | Z`) or runs longer than 1000 lines. Pages like
    `List of Virtual YouTubers (VTubers)` used to dump 2000+ lines of
    name-registry into the song's `.lrc` -- now we reject with a
    `LyricsFailure("genius", "page looks like a Genius list/index (...)")`
    and fall through to LRCLIB.
  * **Wrong-song auto-corrects** -- Genius's typo-tolerant search
    could, e.g., match `"Yesterday" by "Beatles"` to `"Imagine" by
    "John Lennon"` on partial keyword overlap. Token-set
    Overlap Coefficient `|A ∩ B| / min(|A|, |B|)` ≥ 0.5 on BOTH title
    and artist independently catches these with a diagnostic that
    names both sides.
* Cleanup: removed dead `_looks_instrumental` / `_INSTRUMENTAL_TITLE_RE`
  in `lyrics.py`, the empty `_VALID_DEMUCS` frozenset in `settings.py`,
  redundant `getattr(args, …)` defaults in `lyricsfag.py`, and a
  `SyntaxWarning: invalid escape sequence` from `\` in `settings.py`'s
  docstring Windows path examples that triggered under
  `python -W error::SyntaxWarning` -- the literal `\` was replaced with
  `\\` so the docstring renders real backslashes and the warning is
  silenced.
* No behavioural change for correctly-tagged files; both filters are
  additive rejections only.

### v1.1.4 -- PyTorch 2.6 compat + Demucs download-size fix (patch release)

* **PyTorch 2.6 ready.** A shared `.th`-scoped `torch.load`
  monkey-patch (`lyricsfag_lib/_torch_compat.py`) fixes the
  `Weights only load failed ... GLOBAL fractions.Fraction`
  `WeightsUnpickler` error that crashes demucs 4.0.1 on first run
  under PyTorch 2.6+. The patch is lazy (only on first demucs use)
  and idempotent; it forwards `weights_only=False` only for `*.th`
  files so the safe PyTorch 2.6 default stays for any other
  `torch.load` caller in the process.
* **Demucs download sizes corrected.** `_DEMUCS_DOWNLOAD_HINTS_MB`
  in `audio_analysis.py` had its two entries swapped; the WARNING
  reported `~84 MB` for the 4-sub-model `htdemucs_ft` and `~420 MB`
  for the single pretrained `htdemucs`. The numbers now match demucs
  4.0.1 reality.
* `models/demucs/README.md` updated in 8 places to match the 4.0.1
  YAML descriptors.
* `build.bat` `TARGET=all` guard split into two single-line
  compound-`if`s for older Windows batch-parser compatibility.
* Filename-based instrumental short-circuit re-anchored to explicit
  `(?:^|[\s\-_.])` boundaries (the v1.1.2 `\b` form was over-eager
  on certain filename shapes).

### v1.1.3 -- Lite build is now actually lite (patch release)

* `requirements.txt` split into a core `requirements.txt` and an
  optional `requirements-audio.txt`. The latter is only installed
  by `build-portable.bat` (and by dev installs that want the full
  audio stack on the command line).
* `build-lite.bat` no longer installs `requirements-audio.txt`, so the
  resulting `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe` no longer
  bundle `torch` (~3.8 GB on Windows) and stay at the documented ~50 MB
  footprint. The PyInstaller invocation drops `--hidden-import
  faster_whisper` since the package is no longer present.
* `build.bat` orchestrator no longer wipes the portable exes when
  building both variants. Previously each variant script did its own
  `rmdir /s /q dist` at the top, meaning `build.bat all` left only the
  lite exes in `dist\` and a ~6.4 GB portable pair was silently
  deleted. As a result, `build.bat all` now produces **four** exes in
  `dist\` (one CLI + one GUI per variant).

### v1.1.2 -- Instrumental regex boundary fix (hotfix)

* `INSTRUMENTAL_FILENAME_RE` boundary class widened from a narrow
  ASCII set to Unicode-aware `\b`, so filenames with parens, brackets,
  braces, quotes, colons, or commas around the keyword now correctly
  short-circuit the audio branch. `Song (Off Vocal).flac`,
  `Song [Instrumental].flac`, Cyrillic variants, etc. all match.

### v1.1.1 -- GUI crash hotfix

* GUI crashed on launch with `AttributeError` because a `trace_add`
  callback was wired up before the `StringVar` it was watching was
  constructed. The `trace_add` now lives below the source row, after
  `self.source_var = tk.StringVar(value="auto")`, with a breadcrumb
  at the original spot so this class of regression is harder to
  reintroduce.

### v1.1.0 -- Audio-analysis contract + `audio` source

* **Demucs is mandatory** whenever the audio-analysis fallback is
  enabled. The on/off `Demucs` combobox in the audio panel is gone --
  demucs vocal isolation is always on with `--use-audio-analysis`.
  To skip the local fallback entirely, uncheck `Use audio analysis`
  (GUI) or drop the `--use-audio-analysis` flag (CLI). The `--no-demucs`
  CLI flag has been removed; the demucs weights layout and the
  `htdemucs_ft` default are unchanged.
* **New `audio` source** (GUI Source dropdown + CLI `--source audio`).
  Skips LRCLIB / Genius entirely and goes straight to the local
  Whisper + Demucs pipeline. Useful for fully-offline runs, large
  karaoke / original-instrumental batches, or any time you explicitly
  don't want network calls. In the GUI, picking `Source = audio` forces
  the `Use audio analysis` checkbox on and greys it out so the chain
  stays consistent.
* **Filename-based short-circuit** for the audio branch. Tracks whose
  filename contains `instrumental`, `karaoke`, `off vocal`, `no vocal`,
  `minus one`, `backing track`, etc. are never sent through Whisper.
  The LRCLIB / Genius branches still try first (a karaoke file's
  original is often a real song with real lyrics), so only the audio
  branch is short-circuited.
* v1.0.x `settings.json` files that contain the now-removed `demucs`
  key are silently ignored on load.

### v1.0.2 -- Pre-release polish

* **GUI:** `?  Help` button (last in the toolbar row, right of Open
  output folder) opens `messagebox.showinfo(...)` with the
  LRCLIB -> Genius -> local-audio provider chain, the
  `GENIUS_ACCESS_TOKEN` / `--genius-token` hint, first-run Whisper /
  Demucs sizes, and a `--dry-run` safety tip.
* **GUI:** hover tooltips on every primary input widget -- 500 ms hover
  delay, 8 s auto-dismiss (16 widgets total).
* **GUI:** completion popup -- Done / Stopped / worker-crashed, with
  `winfo_exists()` race protection against `_on_close`. Empty folders
  no longer trigger one.
* **Startup:** `audio_analysis.describe_models_layout()` logs the
  resolved `models/whisper-base/` + `models/demucs/` paths so users
  can verify where weights actually land without grepping the source.
* **Cleanup:** dropped unused `COLOUR_BG` constant and unused
  `_format_provider_breakdown` import; renamed the audio-row Device
  label to stop shadowing the status-row badge.

### v1.0.1 -- First tagged release

* Polish and LRC formatting changes since the v1.0.0 initial commit.
  README badges + Whisper/Demucs helper-script callouts in Quick
  start, AI-assistance disclaimer, bilingual README pair
  (`README.md` + `README.ru.md`). LRC format: dropped the verbose
  Whisper diagnostic line in favour of one human-readable
  `[# Generated Lyrics with Whisper]` or
  `[# Generated Lyrics with Demucs + Whisper]`.

See [`RELEASE_NOTES.md`](RELEASE_NOTES.md) for the full per-commit
breakdown of every shipped version (newest first, consolidated changelog).


## License & credits

This project is licensed under MIT -- see [LICENSE](LICENSE).

Upstream services and libraries that make LyricsFAG work:

- [LRCLIB.net](https://lrclib.net/) -- free public lyrics API.
- [Genius](https://genius.com/) -- lyrics database (requires your own free token).
- [lyricsgenius](https://github.com/johnwmillr/lyricsgenius) -- MIT, used for Genius integration.
- [mutagen](https://github.com/quodlibet/mutagen) -- GPLv2, used for reading audio tags.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) -- MIT, optional local audio transcription.
- [Demucs](https://github.com/facebookresearch/demucs) -- MIT, optional vocal isolation in front of Whisper.

This codebase was written with substantial help from an AI coding
assistant ([Codebuff](https://codebuff.com), model `minimax/minimax-m3`)
under human direction and review; see the AI-assisted note at the top
of this README for the full disclaimer.
