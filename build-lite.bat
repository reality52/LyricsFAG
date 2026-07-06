@echo off
REM Build the "lite" LyricsFAG variants: a small CLI/GUI .exe pair that
REM uses LRCLIB + Genius only.  Does NOT bundle faster-whisper / demucs
REM / torch / scipy, so the local audio-analysis chain
REM (``--use-audio-analysis`` / the GUI "Use audio analysis" checkbox)
REM is unavailable on this build -- a user who enables it gets a clean
REM ``LyricsFailure`` telling them to grab the portable build instead.
REM
REM Output (alongside any portable variants the user might have built
REM with build-portable.bat):
REM   dist\LyricsFAG-Lite.exe         -- CLI  (~50 MB)
REM   dist\LyricsFAG-GUI-Lite.exe     -- GUI  (~50 MB)
REM
REM Why this build is so much smaller than portable
REM ------------------------------------------------
REM ``requirements-audio.txt`` pulls in demucs, which transitively
REM installs ``torch`` (~4 GB on Windows).  PyInstaller --onefile
REM bundles the whole Python environment into the .exe, so the
REM portable build pays the full torch cost (~3.5 GB with bundled
REM model weights) and the lite build skips that cost entirely by
REM not installing requirements-audio.txt.  See
REM ``requirements-audio.txt`` and ``README.md`` for the per-variant
REM size table.
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
REM Defensive cleanup so a re-run of ``build-lite.bat`` standalone
REM doesn't leave stale .spec / .exe around (the orchestrator
REM ``build.bat`` only wipes the whole tree when ``all`` is
REM requested; for single-target runs we leave the other
REM variant's outputs alone so the user can build lite at one
REM time and portable at another without losing work).
if exist dist\LyricsFAG-Lite.exe      del /q dist\LyricsFAG-Lite.exe
if exist dist\LyricsFAG-GUI-Lite.exe  del /q dist\LyricsFAG-GUI-Lite.exe
if exist LyricsFAG-Lite.spec          del /q LyricsFAG-Lite.spec
if exist LyricsFAG-GUI-Lite.spec      del /q LyricsFAG-GUI-Lite.spec

echo === Installing build + runtime dependencies (lite) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.*

echo === Building CLI binary (LyricsFAG-Lite.exe) ===
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name LyricsFAG-Lite ^
  --paths . ^
  lyricsfag.py
if errorlevel 1 goto :fail

echo.
echo === Building GUI binary (LyricsFAG-GUI-Lite.exe, windowed) ===
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name LyricsFAG-GUI-Lite ^
  --paths . ^
  lyricsfag_gui.py
if errorlevel 1 goto :fail

echo.
echo === Lite build complete ===
echo   dist\LyricsFAG-Lite.exe       (CLI,  LRCLIB+Genius only)
echo   dist\LyricsFAG-GUI-Lite.exe   (GUI,  LRCLIB+Genius only)
popd
endlocal
exit /b 0

:fail
echo Lite build FAILED.
popd
endlocal
exit /b 1
