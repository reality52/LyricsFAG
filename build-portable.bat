@echo off
REM Build the "portable" LyricsFAG variants: a CLI/GUI .exe pair that
REM bundles the full audio stack (torch + demucs + faster-whisper +
REM scipy, installed via ``requirements-audio.txt``) and, when
REM available, the model weights themselves (models\whisper-base\,
REM models\demucs\ when populated) for fully offline first-run
REM operation.
REM
REM Output (alongside any lite variants):
REM   dist\LyricsFAG-Portable.exe         -- CLI  (~3.5 GB)
REM   dist\LyricsFAG-GUI-Portable.exe     -- GUI  (~3.5 GB)
REM
REM Footprint breakdown
REM -------------------
REM   * torch (transitive of demucs 4.x)    ~3.8 GB
REM   * bundled whisper weights             ~150 MB (only if
REM                                            models\whisper-base\
REM                                            exists)
REM   * bundled demucs weights              ~84 MB (only if
REM                                            models\demucs\*.th
REM                                            exists; the default
REM                                            ``htdemucs_ft`` is
REM                                            a single ~84 MB file;
REM                                            ``htdemucs`` is a
REM                                            5-sub-model bag of
REM                                            ~420 MB)
REM   * everything else                     ~30 MB
REM
REM Prerequisite for a fully-bundled build:
REM   python scripts\download_whisper_model.py --size base
REM   python scripts\download_demucs_model.py
REM     (defaults to htdemucs_ft, Meta's music-only fine-tune, ~84 MB.
REM      Pass --model htdemucs to seed the legacy 5-sub-model BagOfModels
REM      instead; LyricsFAG only uses that one when explicitly pinned via
REM      DemucsIsolator(model="htdemucs") / FasterWhisperAnalyzer(demucs_model="htdemucs").)
REM
REM The build will skip whichever model directories are absent (and warn
REM about it), so a quick `build-portable.bat` run without seeded
REM weights produces a partially-portable .exe that still downloads the
REM missing bits on first use.
REM
REM Cleanup
REM -------
REM We DO clean our own previous .spec + .exe at the top so a
REM standalone re-run of this script (or the orchestrator's
REM ``all`` path, which wipes everything anyway) gets a fresh
REM PyInstaller pass without stale configs.  We do NOT clean the
REM whole ``dist\`` -- the orchestrator only does that when
REM ``all`` is requested, and a single-target build is meant to
REM leave the other variant's outputs alone.  This was the
REM v1.1.3 reviewer-flagged behaviour.

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

echo === Cleaning our own previous outputs ===
REM See the matching block in build-lite.bat for the rationale --
REM the orchestrator only wipes dist\ wholesale when ``all`` is
REM requested, so single-target builds preserve the other
REM variant's outputs.
if exist dist\LyricsFAG-Portable.exe      del /q dist\LyricsFAG-Portable.exe
if exist dist\LyricsFAG-GUI-Portable.exe  del /q dist\LyricsFAG-GUI-Portable.exe
if exist LyricsFAG-Portable.spec          del /q LyricsFAG-Portable.spec
if exist LyricsFAG-GUI-Portable.spec      del /q LyricsFAG-GUI-Portable.spec

echo === Installing build + runtime dependencies (portable) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-audio.txt
pip install pyinstaller==6.*

REM Compose the PyInstaller --add-data flags.  Order matters only for the
REM log output; both flags can coexist safely.
set "WHISPER_ARGS="
set "DEMUCS_ARGS="

REM Whisper weights: bundle when models\whisper-base\model.bin exists.
REM The same probe semantics as the previous monolithic build.bat, kept
REM verbatim so an already-seeded repo doesn't get re-implemented.
REM Reference: scripts/download_whisper_model.py writes model.bin into
REM models\whisper-base\ and that path is what PyInstaller's --add-data
REM will pick up.
if exist models\whisper-base (
    if exist models\whisper-base\model.bin (
        echo Bundling models\whisper-base\ into the .exe (~150 MB).
        set "WHISPER_ARGS=--add-data models\whisper-base;models\whisper-base --hidden-import faster_whisper"
    ) else (
        echo.
        echo === WARNING: models\whisper-base\ exists but model.bin is missing ===
        echo   The bundled .exe will require users to run
        echo   `python scripts\download_whisper_model.py --size base`
        echo   on the target machine BEFORE --use-audio-analysis works.
        echo   Get it from https://huggingface.co/Systran/faster-whisper-base (138 MB).
        set "WHISPER_ARGS=--hidden-import faster_whisper"
    )
) else (
    set "WHISPER_ARGS=--hidden-import faster_whisper"
)

REM Demucs weights: bundle when models\demucs\ has at least one .th.
REM Reference: scripts/download_demucs_model.py strips per-file `<hash>`
REM suffixes so the result is LocalRepo-loadable.
REM
REM `dir /a-d /b models\demucs\*.th >nul 2>&1` succeeds iff a real
REM weights file exists. The empty-directory case returns exit 1 ("File
REM Not Found"), which is exactly the gate we want: a README-only
REM models\demucs\ MUST NOT trigger a 420 MB bake into a 50 MB .exe.
dir /a-d /b models\demucs\*.th >nul 2>&1
if not errorlevel 1 (
    echo Bundling models\demucs\ into the .exe (~84 MB with htdemucs_ft).
    set "DEMUCS_ARGS=--add-data models\demucs;models\demucs --collect-all demucs"
) else (
    echo.
    echo === NOTE: models\demucs\ has no .th files ===
    echo   Demucs will download ~84 MB on first --use-audio-analysis
    echo   (htdemucs_ft, the new default).
    echo   To bundle: python scripts\download_demucs_model.py
    echo   For legacy htdemucs BagOfModels (~420 MB):
    echo     python scripts\download_demucs_model.py --model htdemucs
)

echo.
echo === Building CLI binary (LyricsFAG-Portable.exe) ===
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name LyricsFAG-Portable ^
  --paths . ^
  %WHISPER_ARGS% ^
  %DEMUCS_ARGS% ^
  lyricsfag.py
if errorlevel 1 goto :fail

echo.
echo === Building GUI binary (LyricsFAG-GUI-Portable.exe, windowed) ===
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name LyricsFAG-GUI-Portable ^
  --paths . ^
  %WHISPER_ARGS% ^
  %DEMUCS_ARGS% ^
  lyricsfag_gui.py
if errorlevel 1 goto :fail

echo.
echo === Portable build complete ===
echo   dist\LyricsFAG-Portable.exe       (CLI,  ~3.5 GB; torch+demucs+faster-whisper+models)
echo   dist\LyricsFAG-GUI-Portable.exe   (GUI,  ~3.5 GB; torch+demucs+faster-whisper+models)
popd
endlocal
exit /b 0

:fail
echo Portable build FAILED.
popd
endlocal
exit /b 1
