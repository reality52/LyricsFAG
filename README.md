# LyricsFAG

[![GitHub repo](https://img.shields.io/badge/GitHub-reality52%2FLyricsFAG-181717?logo=github)](https://github.com/reality52/LyricsFAG)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

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

[LRC]: https://en.wikipedia.org/wiki/LRC_(file_format)
[LRCLIB.net]: https://lrclib.net/
[Genius]: https://genius.com/
[Demucs]: https://github.com/facebookresearch/demucs
[Whisper]: https://github.com/SYSTRAN/faster-whisper


## Quick start (Windows)

1. Install Python 3.10+ and `git` (or download this folder as a zip).
2. From the project root:

   ```bat
   pip install -r requirements.txt
   python lyricsfag.py "C:\Music\Library"
   ```

3. To build prebuilt `.exe` binaries (no Python required for the user):

   ```bat
   build.bat                REM builds BOTH lite and portable into dist\
   build.bat lite           REM only LyricsFAG-Lite*.exe (~50 MB, downloads models on first use)
   build.bat portable       REM only LyricsFAG-Portable*.exe (~600 MB, fully offline)
   ```

   See [Building the executable](#building-the-executable) below for the
   per-variant output table and the helper scripts that pre-seed weights.

4. *(Optional)* Pre-seed the local audio-analysis weights before your
   first run with the bundled helper scripts. Both live in `scripts/`
   and only need `python` plus the corresponding optional dependency
   (`faster-whisper`, `demucs`) from `requirements.txt`:

   ```bat
   REM Whisper weights (~150 MB for the default 'base' size).
   python scripts\download_whisper_model.py --size base

   REM Demucs weights (~420 MB for 'htdemucs' = 5 sub-models x ~84 MB).
   REM --verify runs an end-to-end load check before you bake them in.
   python scripts\download_demucs_model.py --model htdemucs
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
* **Source** dropdown (``auto`` / ``lrclib`` / ``genius``)
* **Genius token** entry (or set ``GENIUS_ACCESS_TOKEN`` once in your shell)
* **Start** / **Stop** buttons with live, cancellable progress
* **Colour-coded log** (green = written/dry-run, yellow = skipped/missing,
  red = failed)
* **Open output folder** button to jump straight to your library in Explorer


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
2. Read tags via `mutagen` (`title`, `artist`, `album`, `duration`). When
   metadata is missing, parse the filename -- e.g. `(01) [Artist] Title.ext`
   and `Artist - Title.ext` are recognised.
3. Query `LRCLIB.net/api/get?artist_name=…&track_name=…&duration=…`. If
   synced lines come back, write them straight into the LRC.
4. If LRCLIB returns nothing, query [Genius] (token required). Plain text
   is formatted as plain lines under the metadata headers, which all
   major players (`foobar2000`, `AIMP`, `PowerAmp`, `MusicBee`, `Vanilla`,
   `Musicolet`, `VLC`) display as a static/unsynced view.
5. (With `--use-audio-analysis`) If both providers missing, transcribe the
   audio locally via `faster-whisper` and write **synced** LRC lines
   derived from segment-level timestamps. Hallucinated/silent segments
   are filtered via `no_speech_prob` and a small phrase blocklist.


## LRC format used

```
[ti:Moi... Lolita]
[ar:Alizée]
[al:Gourmandises]
[length:04:26]

[00:12.34]Moi je m'appelle Lolita
[00:16.78]Lo lo lo lo lo lo Lolita
```

Unsynced fallback (from Genius) drops the timestamps and keeps only the
metadata headers + a plain text body.


## Configuration

- `--genius-token` *or* environment variable `GENIUS_ACCESS_TOKEN`.
  Get a free token at <https://genius.com/api-clients>.
- Without a Genius token, the tool will still try LRCLIB. When LRCLIB has
  no synced lyrics but returns plain text, that text is used; otherwise the
  track is reported as a miss.


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
| `tiny`     | ~75 MB | ~10-30×                   | Fast; tends to hallucinate on long instrumentals. |
| `base`     | ~150 MB| ~3-10×                    | **Default**; balanced for most music.            |
| `small`    | ~500 MB| ~1-3×                     | Cleaner LRC timestamps; noticeably slower.       |
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

### Notes

- After `pip install faster-whisper` and the model is on disk, the
  analyzer loads it with `local_files_only=True` (no internet needed).
- Provide your own model directory via `--audio-model-path` to ship a
  pre-downloaded model with your .exe. The portable build helper
  `build-portable.bat` auto-detects whatever is in `models\whisper-base\`
  and `models\demucs\` and bundles whatever it finds -- no env-var
  required to opt in. The legacy `LYRICSFAG_AUDIO=1` env var is still
  honoured as a synonym for `build.bat portable` for backward
  compatibility, but new code should pass the explicit arg.
- The GUI checkbox "Use audio analysis (local)" enables the same chain
  (LRCLIB → Genius → faster-whisper) without re-running the CLI.

## Building the executable

`build.bat` is a thin orchestrator that dispatches to **two** PyInstaller
variants. Both produce a CLI and a windowed GUI .exe into the SAME
`dist\` directory, distinguished by filename so they coexist:

| Variant   | Output binaries                                  | Footprint       | Network on first run |
|-----------|--------------------------------------------------|-----------------|----------------------|
| **lite**  | `dist\LyricsFAG-Lite.exe`, `dist\LyricsFAG-GUI-Lite.exe` | ~50 MB          | Yes — downloads Whisper (~150 MB) and Demucs (~420 MB) weights on first `--use-audio-analysis` |
| **portable** | `dist\LyricsFAG-Portable.exe`, `dist\LyricsFAG-GUI-Portable.exe` | ~600 MB       | No  — once weights are pre-seeded via the helper scripts below, the .exe is fully offline |

### Build commands

```bat
REM Both variants (default; produces four .exe files in dist\).
build.bat

REM Only one variant.
build.bat lite
build.bat portable
```

The legacy `LYRICSFAG_AUDIO=1` env var is still honoured — it maps to
`build.bat portable`. Either invocation is equivalent:

```bat
set LYRICSFAG_AUDIO=1 ^& build.bat       REM (legacy)
build.bat portable                        REM (preferred)
```

### Producing a fully-bundled portable build

The portable .exe only ships weights that you pre-seed into `models\`
*before* running `build.bat portable`. Run both helper scripts in turn:

```bat
REM 1. Whisper weights (~150 MB; ~150 MB after download).
python scripts\download_whisper_model.py --size base

REM 2. Demucs weights (~420 MB; 5 sub-models of ~84 MB each).
REM    The script reads demucs's own files.txt listing so the layout is
REM    automatically LocalRepo-loadable (Path B in models\demucs\README.md).
python scripts\download_demucs_model.py --model htdemucs

REM 3. Verify the directory is in a working state before baking.
python scripts\download_demucs_model.py --model htdemucs --verify

REM 4. Build the offline-ready .exe pair.
build.bat portable
```

If you skip step 2, `build-portable.bat` warns and ships a partially-portable
.exe that still downloads Demucs on first audio-analysis use — Whisper itself
is always bundled (it's small enough).

### Identifying which .exe is which

* `LyricsFAG-Lite.exe` / `LyricsFAG-GUI-Lite.exe` — for users with
  occasional audio-analysis needs and a stable internet connection.
* `LyricsFAG-Portable.exe` / `LyricsFAG-GUI-Portable.exe` — for USB-stick
  / air-gapped / corporate-DPI-restricted environments where a 420 MB
  fetch at first launch would be blocked.

For a *nix build, the equivalent manual command line is:

```bash
# lite
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Lite  --paths . --hidden-import faster_whisper lyricsfag.py
pyinstaller --noconfirm --onefile --windowed --name LyricsFAG-GUI-Lite  --paths . --hidden-import faster_whisper lyricsfag_gui.py

# portable (only after the two download scripts have seeded models/)
pyinstaller --noconfirm --onefile --console  --name LyricsFAG-Portable --paths . \
  --add-data models/whisper-base;models/whisper-base --hidden-import faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag.py
pyinstaller --noconfirm --onefile --windowed --name LyricsFAG-GUI-Portable --paths . \
  --add-data models/whisper-base;models/whisper-base --hidden-import faster_whisper \
  --add-data models/demucs;models/demucs --collect-all demucs \
  lyricsfag_gui.py
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
│   ├── device.py            # CUDA / demucs capability probes
│   ├── lyrics.py            # LRCLIB + Genius clients
│   ├── lrc.py               # LRC serializer
│   └── settings.py          # persistent GUI settings (JSON under %APPDATA%)
├── requirements.txt
├── build.bat                # orchestrator: lite / portable / all
├── build-lite.bat           # ~50 MB .exe pair (download models on first use)
├── build-portable.bat       # ~600 MB .exe pair (weights bundled in)
├── scripts/
│   ├── download_whisper_model.py    # HF-mirror Range-resume downloader (Whisper)
│   └── download_demucs_model.py     # demucs files.txt reader + LocalRepo seed
├── models/
│   ├── whisper-base/        # faster-whisper weights (bundled when present)
│   └── demucs/              # demucs weights (bundled when populated)
└── test/                    # Alizée test album
```


## Tray / background mode

The GUI runs entirely in the foreground by default.  If you want to wire it
into a tray icon for silent background runs, look at ``pystray`` -- drop the
existing ``LyricsFAGApp.mainloop()`` call in ``lyricsfag_gui.py`` and replace
with a tray icon callback that calls ``_on_start`` periodically (out of scope
for the initial release).


## License & credits

This project is licensed under MIT — see [LICENSE](LICENSE).

Upstream services and libraries that make LyricsFAG work:

- [LRCLIB.net](https://lrclib.net/) — free public lyrics API.
- [Genius](https://genius.com/) — lyrics database (requires your own free token).
- [lyricsgenius](https://github.com/johnwmillr/lyricsgenius) — MIT, used for Genius integration.
- [mutagen](https://github.com/quodlibet/mutagen) — GPLv2, used for reading audio tags.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — MIT, optional local audio transcription.
- [Demucs](https://github.com/facebookresearch/demucs) — MIT, optional vocal isolation in front of Whisper.

This codebase was written with substantial help from an AI coding
assistant ([Codebuff](https://codebuff.com), model `minimax/minimax-m3`)
under human direction and review; see the AI-assisted note at the top
of this README for the full disclaimer.
