@echo off
REM Build the "portable" LyricsFAG variant: a SINGLE .exe that bundles the
REM full audio stack (torch + demucs + faster-whisper + scipy, installed
REM via ``requirements-audio.txt``) plus, when available, the model
REM weights themselves (``models\whisper-small\`` by default,
REM ``models\whisper-base\`` as a backward-compat fallback,
REM ``models\demucs\``) for fully offline first-run operation.
REM
REM Output (alongside any lite variant):
REM   dist\LyricsFAG-Portable.exe    -- single dual-mode binary (~3.5 GB)
REM
REM How the dual-mode dispatch works
REM ---------------------------------
REM Entry point is ``lyricsfag.py``: when launched with no argv the
REM :func:`lyricsfag._wants_gui` pre-check returns ``True`` and the
REM Tk window pops up (overlaying the console host pyinstaller
REM allocated via ``--console``).  When launched from a terminal with
REM a path or any flag the same .exe runs the CLI loop.  This is the
REM standard Windows pattern (``git.exe``, ``pythonw.exe``, ...).
REM
REM What gets baked in (when seeded)
REM ---------------------------------
REM   * torch (~3.8 GB; transitively via demucs)
REM   * demucs + faster-whisper + scipy (via requirements-audio.txt)
REM   * models\whisper-small\model.bin (~500 MB; the v1.2.1 default
REM     Whisper size -- cleaner transcription than ``base`` and what
REM     ``download_whisper_model.py`` drops when run with no flags).
REM     Falls back to models\whisper-base\model.bin (~150 MB) when the
REM     small/ seed is missing AND the base/ seed is present (dev-tree
REM     v1.2.x compatibility).
REM   * models\demucs\*.th files (~84-336 MB; htdemucs_ft default)
REM   * everything else ~30 MB
REM
REM Prerequisite for a fully-bundled build:
REM   REM 1. Whisper small weights (~500 MB)
REM   python scripts\download_whisper_model.py
REM   REM 2. Demucs weights for the default 'htdemucs_ft' (~84 MB single model
REM   REM    under demucs 4.0.1; the legacy 5-sub-model bag still applies
REM   REM    only when --demucs-model htdemucs is explicitly pinned).
REM   python scripts\download_demucs_model.py
REM   REM 3. (Optional) End-to-end load check before baking into the .exe.
REM   python scripts\download_demucs_model.py --verify
REM
REM Without seeded weights the .exe ships as partially-portable: it
REM still ships torch + demucs + faster-whisper, but on first use the
REM missing ``model.bin`` / ``*.th`` files download from the cache the
REM normal way.
REM
REM Cleanup
REM -------
REM Standalone re-run cleanup: we wipe our own previous .spec + .exe
REM only.  The orchestrator's ``build.bat all`` does a wholesale wipe.
REM The v1.1.3 reviewer-flagged behaviour (variant script wipes the
REM whole dist\ so the other variant's outputs vanish) is preserved
REM HERE so the user can rebuild one variant at a time without losing
REM the other.

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

echo === Cleaning our own previous outputs ===
if exist dist\LyricsFAG-Portable.exe      del /q dist\LyricsFAG-Portable.exe
if exist LyricsFAG-Portable.spec          del /q LyricsFAG-Portable.spec

echo === Installing build + runtime dependencies (portable) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-audio.txt
pip install pyinstaller==6.*

REM Compose the PyInstaller --add-data flags.  Order matters only for the
REM log output; both flags can coexist safely.
set "WHISPER_ARGS="
set "DEMUCS_ARGS="

REM Whisper weights: prefer models\whisper-small\ (~500 MB; the v1.2.1
REM default).  Fall back to models\whisper-base\ (~150 MB) when the small/
REM directory is missing AND the base/ seed is present -- that keeps
REM v1.2.x dev trees working without forcing a re-seed.
if exist models\whisper-small (
    if exist models\whisper-small\model.bin (
        echo Bundling models\whisper-small\ into the .exe (~500 MB).
        set "WHISPER_ARGS=--add-data models\whisper-small;models\whisper-small --collect-all faster_whisper"
    ) else (
        echo.
        echo === WARNING: models\whisper-small\ exists but model.bin is missing ===
        echo   The bundled .exe will require users to run
        echo   `python scripts\download_whisper_model.py` (default --size small)
        echo   on the target machine BEFORE --use-audio-analysis works.
        echo   Get it from https://huggingface.co/Systran/faster-whisper-small (484 MB).
        set "WHISPER_ARGS=--collect-all faster_whisper"
    )
) else if exist models\whisper-base (
    if exist models\whisper-base\model.bin (
        echo Bundling models\whisper-base\ into the .exe (~150 MB; backward-compat).
        echo NOTE: models\whisper-small not seeded; falling back to the v1.2.x default.
        echo       Run `python scripts\download_whisper_model.py` to switch to small.
        set "WHISPER_ARGS=--add-data models\whisper-base;models\whisper-base --collect-all faster_whisper"
    ) else (
        echo.
        echo === WARNING: models\whisper-base\ exists but model.bin is missing ===
        echo   The bundled .exe will require users to manually re-run
        echo   `python scripts\download_whisper_model.py` (default --size small)
        echo   on the target machine BEFORE --use-audio-analysis works.
        set "WHISPER_ARGS=--collect-all faster_whisper"
    )
) else (
    set "WHISPER_ARGS=--collect-all faster_whisper"
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
echo === Building dual-mode binary (LyricsFAG-Portable.exe) ===
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
echo === Portable build complete ===
echo   dist\LyricsFAG-Portable.exe    (~3.5 GB; torch+demucs+faster-whisper+small-whisper+demucs-weights; dual-mode)
echo     Double-click in Explorer -> GUI window.
echo     From PowerShell:           dist\LyricsFAG-Portable.exe "C:\Music\Library"
popd
endlocal
exit /b 0

:fail
echo Portable build FAILED.
popd
endlocal
exit /b 1
