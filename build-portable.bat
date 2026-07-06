@echo off
REM Build the "portable" LyricsFAG variants: a CLI/GUI .exe pair that
REM bundles faster-whisper weights (models\whisper-base\) and, when
REM available, the demucs weights (models\demucs\) for fully offline
REM first-run operation.
REM
REM Output (alongside any lite variants):
REM   dist\LyricsFAG-Portable.exe         -- CLI  (~600 MB)
REM   dist\LyricsFAG-GUI-Portable.exe     -- GUI  (~600 MB)
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

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

echo === Installing build + runtime dependencies (portable) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.*
pip install faster-whisper==1.*
pip install demucs>=4.0

echo === Cleaning previous build artifacts ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
del /q LyricsFAG-Portable.spec LyricsFAG-GUI-Portable.spec 2>nul

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
echo   dist\LyricsFAG-Portable.exe       (CLI,  ~600 MB with bundled weights)
echo   dist\LyricsFAG-GUI-Portable.exe   (GUI,  ~600 MB with bundled weights)
popd
endlocal
exit /b 0

:fail
echo Portable build FAILED.
popd
endlocal
exit /b 1
