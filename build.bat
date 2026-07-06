@echo off
REM Master build orchestrator for LyricsFAG.
REM
REM Two output variants ship side by side into dist\:
REM   * lite     -- ~50 MB CLI/GUI .exe; downloads faster-whisper + demucs
REM                 weights on first use (existing behaviour from before
REM                 the split).
REM   * portable -- drops the same dependencies in plus the weight files
REM                 themselves (models\whisper-base\, models\demucs\ when
REM                 populated); produces ~600 MB self-contained .exe
REM                 binaries that need no network access.
REM
REM Usage:
REM     build.bat                -- build BOTH variants (default; same as `all`)
REM     build.bat lite           -- only LyricsFAG-Lite.exe + LyricsFAG-GUI-Lite.exe
REM     build.bat portable       -- only LyricsFAG-Portable.exe + LyricsFAG-GUI-Portable.exe
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
echo === Building portable variant (LyricsFAG-Portable.exe / -GUI.exe) ===
echo.
call "%ROOT%build-portable.bat"
if errorlevel 1 exit /b 1
if /i "%TARGET%"=="portable" goto :summary
exit /b 0

:build_lite
echo.
echo === Building lite variant (LyricsFAG-Lite.exe / -GUI.exe) ===
echo.
call "%ROOT%build-lite.bat"
if errorlevel 1 exit /b 1
exit /b 0

:summary
echo.
echo === Build complete ===
echo.
if /i "%TARGET%"=="all" (
    echo   dist\LyricsFAG-Lite.exe        ^(CLI,  ~50 MB, downloads models on first use^)
    echo        usage: dist\LyricsFAG-Lite.exe "C:\Music\Library"
    echo.
    echo   dist\LyricsFAG-GUI-Lite.exe    ^(GUI,  ~50 MB, downloads models on first use^)
    echo        Double-click to open.
    echo.
    echo   dist\LyricsFAG-Portable.exe   ^(CLI,  ~600 MB, fully offline^)
    echo        usage: dist\LyricsFAG-Portable.exe "C:\Music\Library"
    echo.
    echo   dist\LyricsFAG-GUI-Portable.exe ^(GUI,  ~600 MB, fully offline^)
    echo        Double-click to open.
) else if /i "%TARGET%"=="portable" (
    echo   dist\LyricsFAG-Portable.exe    ^(CLI,  ~600 MB, fully offline^)
    echo   dist\LyricsFAG-GUI-Portable.exe ^(GUI, ~600 MB, fully offline^)
) else (
    echo   dist\LyricsFAG-Lite.exe        ^(CLI,  ~50 MB, downloads models on first use^)
    echo   dist\LyricsFAG-GUI-Lite.exe    ^(GUI,  ~50 MB, downloads models on first use^)
)
popd
endlocal
exit /b 0

:fail
popd
endlocal
exit /b 1
