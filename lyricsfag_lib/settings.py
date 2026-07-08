"""Persistent GUI settings: cross-platform config dir + JSON load/save.

This module keeps the *last-used* values of the Tk widgets in
``lyricsfag_gui.LyricsFAGApp`` on disk so they survive between launches.
It is intentionally tiny and stdlib-only (no ``platformdirs``, ``tomli``,
``pydantic``) so the ``.exe`` produced by ``build.bat`` does not grow by
a single MB.

Storage location
----------------
* Windows : ``%APPDATA%\\LyricsFAG\\settings.json`` (falls back to
  ``~\\LyricsFAG\\settings.json`` when ``%APPDATA%`` is unset).
* macOS   : ``~/Library/Application Support/LyricsFAG/settings.json``.
* Linux   : ``$XDG_CONFIG_HOME/lyricsfag/settings.json`` (falls back to
  ``~/.config/lyricsfag/settings.json``).

The directory is created on first save with ``parents=True, exist_ok=True``
so the GUI works out-of-the-box on a fresh install.

Schema
------
All keys are *optional*; missing keys keep their in-code defaults in the
GUI. Loaded values are validated with :func:`sanitize` so a hand-edited
or stale ``settings.json`` (e.g. a removed Whisper model size) cannot
crash the GUI on startup -- it will silently fall back to the default.

* ``folder``              ``str``  (music folder; not required to exist on load)
* ``recursive``           ``bool``
* ``force``               ``bool``
* ``dry_run``             ``bool``
* ``use_audio_analysis``  ``bool``
* ``source``              ``str`` in ``{"auto", "lrclib", "genius"}``
* ``genius_token``        ``str``  (plaintext; see SECURITY note below)
* ``audio_model``         ``str``  in ``SUPPORTED_MODELS``
* ``audio_model_path``    ``str``  (may be empty)
* ``device``              ``str``  in ``{"auto", "cuda", "cpu"}``

Note: demucs was mandatory as of v1.1.0, so a stale ``"demucs"`` key
from a pre-v1.1.0 ``settings.json`` is silently dropped.

Write semantics
---------------
:func:`save_settings` writes atomically via a ``.tmp`` swap (mirrors the
pattern in :func:`lyricsfag_lib.lrc.write_lrc`) so an interrupted save
never produces a half-written ``settings.json``. A ``JSONDecodeError`` or
``OSError`` on read falls back to an empty dict and surfaces as ``None``
from :func:`load_settings` -- callers can check ``if loaded is None`` to
know whether to log a warning. Errors during *write* are raised to the
caller: silently swallowing "disk full" or "permission denied" would
leave the user wondering why their UI state disappears the next launch.

SECURITY
--------
The Genius access token is stored in **plaintext**. This is an
acceptable tradeoff for a desktop tool that the user invokes manually
(the same token already lives in the process environment via
``GENIUS_ACCESS_TOKEN``); a future hardening path uses the OS keyring
(``keyring`` package), but that adds a hard dependency and breaks the
"single .exe, no extra installs" promise of ``build.bat``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from .audio_analysis import SUPPORTED_MODELS

LOG = logging.getLogger(__name__)

# Allowed-value sets used by ``sanitize``. Kept in one place so the GUI and
# the validator stay in lockstep without copy-paste drift.
_VALID_SOURCES: frozenset[str] = frozenset({"auto", "lrclib", "genius"})
_VALID_DEVICES: frozenset[str] = frozenset({"auto", "cuda", "cpu"})
_VALID_AUDIO_MODELS: frozenset[str] = frozenset(SUPPORTED_MODELS)

# Sub-directory under the OS config root.  ``LyricsFAG`` matches the
# executable name (``LyricsFAG.exe`` / ``LyricsFAG-GUI.exe``) so the user
# can find it via Window's ``%APPDATA%`` listing next to the .exe.
_DIR_NAME = "LyricsFAG"


def settings_dir() -> Path:
    """Return the OS-appropriate root for LyricsFAG settings.

    Returns ``~`` fallback when neither the env-var nor the conventional
    OS path is available (very rare; e.g. locked-down Linux containers
    with no ``$HOME``).
    """
    home = Path.home()

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else home
        return base / _DIR_NAME

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / _DIR_NAME

    # Linux / other Unix: honour $XDG_CONFIG_HOME, fall back to
    # ``~/.config`` per the freedesktop.org spec.
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home / ".config"
    return base / _DIR_NAME.lower()  # "lyricsfag", not "LyricsFAG", on Linux


def settings_path() -> Path:
    """Absolute path to ``settings.json``."""
    return settings_dir() / "settings.json"


def sanitize(raw: dict) -> dict:
    """Drop unknown keys and coerce every value to its expected type/range.

    Always returns a fresh dict (the caller may mutate it freely) so a
    buggy caller can't accidentally poison next-launch defaults via
    in-place edits on the loaded mapping.
    """
    out: dict = {}

    folder = raw.get("folder")
    if isinstance(folder, str):
        out["folder"] = folder

    for key in ("recursive", "force", "dry_run", "use_audio_analysis"):
        val = raw.get(key)
        if isinstance(val, bool):
            out[key] = val

    src = raw.get("source")
    if isinstance(src, str) and src in _VALID_SOURCES:
        out["source"] = src

    tok = raw.get("genius_token")
    if isinstance(tok, str):
        out["genius_token"] = tok

    model = raw.get("audio_model")
    if isinstance(model, str) and model in _VALID_AUDIO_MODELS:
        out["audio_model"] = model

    model_path = raw.get("audio_model_path")
    if isinstance(model_path, str):
        out["audio_model_path"] = model_path

    dev = raw.get("device")
    if isinstance(dev, str) and dev in _VALID_DEVICES:
        out["device"] = dev

    # ``demucs`` (pre-v1.1.0 on/off toggle) dropped silently -- knob removed.

    return out


def load_settings(path: Optional[Path] = None) -> Optional[dict]:
    """Return sanitized settings from ``path`` (default :func:`settings_path`).

    Returns ``None`` on missing/unreadable/unparseable file -- the caller
    may then fall back to in-code defaults. We log the reason so a user
    with a broken ``settings.json`` can see the cause in the GUI log
    panel without needing ``--verbose``.
    """
    p = path or settings_path()
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
    except OSError as exc:
        LOG.warning("Failed to read settings %s: %s", p, exc)
        return None
    try:
        raw = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as exc:
        LOG.warning("Failed to parse settings %s: %s", p, exc)
        return None
    if not isinstance(raw, dict):
        LOG.warning("Settings %s did not contain a JSON object", p)
        return None
    return sanitize(raw)


def save_settings(data: dict, path: Optional[Path] = None) -> None:
    """Atomically write ``data`` (after :func:`sanitize`) to ``path``.

    Raises on disk errors so the GUI can surface "could not save
    settings" rather than letting the user think their UI state was
    persisted when it wasn't.
    """
    p = path or settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    # Power-loss housekeeping: an interrupted previous save can leave
    # ``settings.json.<random>.tmp`` siblings behind. They're never
    # read by :func:`load_settings`, but they accumulate over many
    # crash-during-save cycles. Sweep them out before opening a fresh
    # tmp handle so the directory stays tidy.
    for leftover in p.parent.glob(p.name + ".*.tmp"):
        try:
            leftover.unlink()
        except OSError:
            # Best-effort: a permission error here is harmless (the
            # user can clean manually), don't fail the whole save.
            pass

    clean = sanitize(data)
    payload = json.dumps(clean, ensure_ascii=False, indent=2, sort_keys=True)

    # Atomic write via a sibling .tmp + replace. ``dir=p.parent`` so the
    # rename is on the same filesystem (required for atomicity on POSIX;
    # harmless extra safety on Windows).
    fd, tmp_name = tempfile.mkstemp(
        prefix=p.name + ".", suffix=".tmp", dir=str(p.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, p)
    except Exception:
        # Don't leak the .tmp on partial failure.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


__all__: Iterable[str] = (
    "load_settings",
    "sanitize",
    "save_settings",
    "settings_dir",
    "settings_path",
)
