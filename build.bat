@echo off
REM Master build orchestrator for LyricsFAG.
REM
REM Two output variants ship side by side into dist\, ONE binary each:
REM   * lite     -- ~50 MB single dual-mode .exe (LRCLIB + Genius
REM                 only; downloads whisper + demucs weights on first
REM                 use).  Entry point lyricsfag.py auto-dispatches to
REM                 GUI when launched without argv, CLI otherwise.
REM   * portable -- ~3.5 GB single dual-mode .exe with the full audio
REM                 stack (torch + demucs + faster-whisper + scipy) +
REM                 bundled weights (``models\whisper-small\`` ~500 MB,
REM                 ``models\demucs\`` ~84 MB).  Fully offline.
REM
REM Usage:
REM     build.bat                -- build BOTH variants (default; same as `all`)
REM     build.bat lite           -- only LyricsFAG-Lite.exe (~50 MB)
REM     build.bat portable       -- only LyricsFAG-Portable.exe (~3.5 GB)
REM     build.bat all            -- both variants, sequentially
REM
REM Legacy flag still honoured for backward compatibility:
REM     set LYRICSFAG_AUDIO=1 ^& build.bat   -- equivalent to `build.bat portable`

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

set "TARGET="
if /i "%~1"=="lite"      set "TARGET=lite"
if /i "%~1"=="portable"  set "TARGET=portable"
if /i "%~1"=="all"       set "TARGET=all"
REM Explicit arg wins.  Only when no arg was passed do we honour the
REM legacy LYRICSFAG_AUDIO=1 env var (backward compat for users who
REM remember the old single-build script).  Then ``all`` is the default
REM for first-time users with no arg and no env var.
if "%~1"=="" if defined LYRICSFAG_AUDIO if /i "%LYRICSFAG_AUDIO%"=="1" set "TARGET=portable"
if not defined TARGET if "%~1"=="" set "TARGET=all"
if not defined TARGET (
    echo Unknown argument: %~1
    echo Usage: build.bat [lite^|portable^|all]
    exit /b 2
)

echo === LyricsFAG build orchestrator ===
echo   target: %TARGET%
echo.

REM Clean previous artifacts ONCE here so the variant scripts don't
REM clobber each other.  Previously each variant script did its own
REM ``rmdir /s /q dist`` at the top, which meant the second variant
REM wiped the first variant's outputs -- e.g. ``build.bat all`` used
REM to leave only the lite exes in dist\, with the portable ones
REM silently deleted (the bug report was: "two huge exes in dist,
REM but I expected both portable and lite").  Doing the wipe here
REM once means all four .exe files
REM (``LyricsFAG-Portable.exe`` + ``LyricsFAG-GUI-Portable.exe``
REM  + ``LyricsFAG-Lite.exe`` + ``LyricsFAG-GUI-Lite.exe``)
REM coexist in dist\ after a ``build.bat all`` run.
REM When building both variants (``all``), wipe dist/ + build/ +
REM .spec files at the top so the variant scripts don't have to
REM (each variant only needs to clean its own previous .spec + .exe
REM in case the user invokes it standalone).  For single-target
REM builds we leave the other variant's outputs alone so the user
REM can build one variant at a time without nuking the other --
REM a destructive single-target cleanup was the behaviour the
REM v1.1.3 reviewer flagged.
REM Two single-line compound-if statements (no parenthesized block)
REM for maximum batch-parser compatibility -- the previous parenthesized
REM form triggered . was unexpected at this time on some Windows
REM versions.  Semantics are identical: clean dist\ + build\ only when
REM TARGET=all.
if /i "%TARGET%"=="all" if exist build rmdir /s /q build
if /i "%TARGET%"=="all" if exist dist  rmdir /s /q dist

REM Order matters: portable first (longer), then lite. Both write to the
REM SAME dist\ directory but with distinct names so the four .exe files
REM coexist.  Callers that only want one variant pass the matching arg
REM and skip the build they don't need.
if /i "%TARGET%"=="portable" goto :build_portable
if /i "%TARGET%"=="lite" goto :build_lite

REM `all` -- build both, sequentially
call :build_portable
if errorlevel 1 goto :fail
call :build_lite
if errorlevel 1 goto :fail
goto :summary

:build_portable
echo.
echo === Building portable variant (LyricsFAG-Portable.exe; dual-mode) ===
echo.
call "%ROOT%build-portable.bat"
if errorlevel 1 exit /b 1
if /i "%TARGET%"=="portable" goto :summary
exit /b 0

:build_lite
echo.
echo === Building lite variant (LyricsFAG-Lite.exe; dual-mode) ===
echo.
call "%ROOT%build-lite.bat"
if errorlevel 1 exit /b 1
exit /b 0

:summary
echo.
echo === Build complete ===
echo.
if /i "%TARGET%"=="all" (
    echo   dist\LyricsFAG-Lite.exe        ^(dual-mode, ~50 MB, downloads models on first use^)
    echo     CLI:    dist\LyricsFAG-Lite.exe "C:\Music\Library"
    echo     GUI:    Double-click in Explorer.  Same .exe -- _wants_gui() auto-dispatches.
    echo.
    echo   dist\LyricsFAG-Portable.exe   ^(dual-mode, ~3.5 GB, fully offline; seeded small whisper + htdemucs_ft^)
    echo     CLI:    dist\LyricsFAG-Portable.exe "C:\Music\Library"
    echo     GUI:    Double-click in Explorer.  Same .exe -- _wants_gui() auto-dispatches.
) else if /i "%TARGET%"=="portable" (
    echo   dist\LyricsFAG-Portable.exe   ^(dual-mode, ~3.5 GB, fully offline^)
    echo     CLI:    dist\LyricsFAG-Portable.exe "C:\Music\Library"
    echo     GUI:    Double-click in Explorer.  Same .exe ^(--gui=1^).
) else (
    echo   dist\LyricsFAG-Lite.exe        ^(dual-mode, ~50 MB, downloads models on first use^)
    echo     CLI:    dist\LyricsFAG-Lite.exe "C:\Music\Library"
    echo     GUI:    Double-click in Explorer.  Same .exe ^(--gui=1^).
)
popd
endlocal
exit /b 0

:fail
popd
endlocal
exit /b 1
