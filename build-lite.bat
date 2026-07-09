@echo off
REM Build the "lite" LyricsFAG variant: a SINGLE small .exe that handles
REM both the CLI (``lyricsfag.exe "C:\Music\Library"``) and the GUI
REM (``lyricsfag.exe`` double-click / explicit ``--gui`` flag) via the
REM auto-dispatch in :func:`lyricsfag._wants_gui`.  Does NOT bundle
REM faster-whisper / demucs / torch / scipy, so the local audio-analysis
REM chain (``--use-audio-analysis`` / the GUI "Use audio analysis"
REM checkbox) is unavailable on this build -- a user who enables it
REM gets a clean ``LyricsFailure`` telling them to grab the portable
REM build instead.
REM
REM Output (alongside any portable variant the user might have built
REM elsewhere with build-portable.bat):
REM   dist\LyricsFAG-Lite.exe    -- single dual-mode binary (~50 MB)
REM
REM How "GUI when double-clicked, CLI when run from terminal" works
REM -----------------------------------------------------------------
REM Entry point is ``lyricsfag.py`` (NOT ``lyricsfag_gui.py``).  When
REM pyinstaller builds with ``--console``, the result is a
REM ``LyricsFAG-Lite.exe`` that:
REM   * When launched from PowerShell/cmd WITH args (positional path
REM     or any flag) -> runs the CLI loop, prints colours + log lines.
REM   * When launched with NO args (typical Windows double-click)
REM     -> :func:`lyricsfag._wants_gui` returns ``True`` (empty argv
REM     rule) -> launches the Tk window.  The console process stays
REM     alive so the Tk window overlays it; closing the window exits
REM     cleanly.  This is the same pattern Git for Windows uses.
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
REM We clean our own previous .spec + .exe at the top so a standalone
REM re-run of this script gets a fresh PyInstaller pass without stale
REM configs.  We do NOT clean the whole ``dist\`` -- the orchestrator
REM ``build.bat`` wipes ``dist\`` only when ``all`` is requested, and
REM a single-target build is meant to leave the other variant's
REM outputs alone so the user can build lite at one time and portable
REM at another without losing work.

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

echo === Cleaning our own previous outputs ===
if exist dist\LyricsFAG-Lite.exe      del /q dist\LyricsFAG-Lite.exe
if exist LyricsFAG-Lite.spec          del /q LyricsFAG-Lite.spec

echo === Installing build + runtime dependencies (lite) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.*

echo === Building dual-mode binary (LyricsFAG-Lite.exe) ===
REM --console keeps stdout/stderr visible for terminal users; the Tk
REM window still pops up on no-args double-click and overlays the
REM console (Windows-native pattern).
REM --onefile produces a single self-extracting .exe.
REM Entry point is lyricsfag.py because its main() auto-dispatches
REM GUI vs CLI based on argv presence (see _wants_gui docstring).
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name LyricsFAG-Lite ^
  --paths . ^
  lyricsfag.py
if errorlevel 1 goto :fail

echo.
echo === Lite build complete ===
echo   dist\LyricsFAG-Lite.exe    (LRCLIB+Genius only; ~50 MB; dual-mode)
echo     Double-click in Explorer -> GUI window.
echo     From PowerShell:         dist\LyricsFAG-Lite.exe "C:\Music\Library"
popd
endlocal
exit /b 0

:fail
echo Lite build FAILED.
popd
endlocal
exit /b 1
