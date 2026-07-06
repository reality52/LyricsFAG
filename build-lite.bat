@echo off
REM Build the "lite" LyricsFAG variants: a small CLI/GUI .exe pair that
REM installs faster-whisper and demucs but does NOT bundle the model
REM weights. First run with --use-audio-analysis will download the
REM weights from HuggingFace / facebookresearch/demucs.
REM
REM Output (alongside any portable variants the user might have built
REM with build-portable.bat):
REM   dist\LyricsFAG-Lite.exe         -- CLI  (~50 MB)
REM   dist\LyricsFAG-GUI-Lite.exe     -- GUI  (~50 MB)
REM
REM Implementation notes:
REM   * faster-whisper is installed (and hidden-imported) so users can
REM     still flip on --use-audio-analysis; the analyzer just downloads
REM     the model on first use. Demucs is intentionally NOT installed
REM     here -- if a user explicitly wants demucs in their lite build,
REM     they can run build-portable.bat which does the right thing.

setlocal

set "ROOT=%~dp0"
pushd "%ROOT%"

echo === Installing build + runtime dependencies (lite) ===
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.*
pip install faster-whisper==1.*

echo === Cleaning previous build artifacts ===
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist
del /q LyricsFAG-Lite.spec LyricsFAG-GUI-Lite.spec 2>nul

echo === Building CLI binary (LyricsFAG-Lite.exe) ===
pyinstaller ^
  --noconfirm ^
  --onefile ^
  --console ^
  --name LyricsFAG-Lite ^
  --paths . ^
  --hidden-import faster_whisper ^
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
  --hidden-import faster_whisper ^
  lyricsfag_gui.py
if errorlevel 1 goto :fail

echo.
echo === Lite build complete ===
echo   dist\LyricsFAG-Lite.exe       (CLI, download models on first use)
echo   dist\LyricsFAG-GUI-Lite.exe   (GUI, download models on first use)
popd
endlocal
exit /b 0

:fail
echo Lite build FAILED.
popd
endlocal
exit /b 1
