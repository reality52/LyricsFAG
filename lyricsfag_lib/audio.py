"""Audio metadata extraction.

Reads ID3/Vorbis/MP4/etc. tags via ``mutagen`` (which supports FLAC, MP3, M4A,
OGG, OPUS, WMA, WAV, APE, WV and more). Falls back to parsing common filename
patterns such as ``(01) [Artist] Title.ext``.

Public API:
    - ``AudioFile``: lightweight dataclass holding path + parsed metadata.
    - ``iter_audio_files(root, recursive)``: walk a directory tree.
    - ``parse_audio(path)``: read metadata for a single file.
    - ``SUPPORTED_EXTENSIONS``: tuple of recognized audio extensions.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

try:
    import mutagen  # type: ignore
except ImportError as _exc:  # pragma: no cover - import-time guard
    raise ImportError(
        "mutagen is required: install with `pip install mutagen`"
    ) from _exc


# Lower-cased extensions we know how to handle.  ``mutagen`` itself does the
# dispatch internally, so this list is just for "is this likely an audio file".
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus",
    ".wma", ".wav", ".ape", ".wv", ".tak",
)


@dataclass
class AudioFile:
    """A single audio file with its tag metadata (best-effort).

    ``composer``, ``language`` and ``year`` are populated from mutagen
    tags (TCOM/©wrt/COMPOSER, TLAN/LAN, TDRC/TYER/©day/DATE/YEAR)
    on best effort and are used to populate the same-name LRC
    headers in :class:`lyricsfag_lib.lrc.LRCDocument` so dropped
    files have richer liner-notes.  All three default to empty/zero
    so callers that don't care about them see no behaviour change.
    """

    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    duration: float = 0.0
    source: str = "unknown"  # 'tags', 'filename', 'none'
    composer: str = ""
    language: str = ""
    year: int = 0

    @property
    def lrc_path(self) -> Path:
        """Path where the matching .lrc file would live."""
        return self.path.with_suffix(".lrc")

    def has_lrc(self) -> bool:
        return self.lrc_path.exists()

    def query_key(self) -> tuple[str, str]:
        """Stable (artist, title) tuple used for lyrics lookups."""
        return (self.artist.strip().lower(), self.title.strip().lower())


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

# Strip a leading track number such as "01. ", "02 - ", "(03) ", "[04] ".
_RE_LEADING_NUMBER = re.compile(
    r"^\s*(?:\d{1,3}[\.\-\s\)\(]+|\([\s]?\d{1,3}[\s]?\)|\[[\s]?\d{1,3}[\s]?\]|\d{1,3}\s+)\s*"
)
# "[Artist] Title" -- the convention used in this very repo's test album.
_RE_BRACKET_ARTIST_TITLE = re.compile(
    r"^\s*\[(?P<artist>[^\]]+)\]\s*-?\s*(?P<title>.+?)\s*$"
)


def parse_filename(path: Path) -> tuple[str, str]:
    """Best-effort extraction of (artist, title) from a filename stem.

    Recognised patterns (after stripping a leading track number):

      * ``[Artist] Title``         -- used in this repo's test album
      * ``Artist - Title``         -- "ABBA - Dancing Queen"
      * ``Artist_-_Title``         -- "ABBA_-_Dancing_Queen"
      * Fallback: ``("", stem)``   -- the whole stem becomes the title
    """
    stem = _RE_LEADING_NUMBER.sub("", path.stem).strip()

    # 1) "[Artist] Title" pattern.
    m = _RE_BRACKET_ARTIST_TITLE.match(stem)
    if m and m.group("artist"):
        return m.group("artist").strip(), m.group("title").strip()

    # 2) "Artist - Title" -- split on the first " - ".
    if " - " in stem:
        artist, _sep, title = stem.partition(" - ")
        artist, title = artist.strip(), title.strip()
        if artist and title:
            return artist, title

    # 3) "Artist_-_Title" -- common when files were downloaded with "_-_"
    # between fields.
    if stem.count("_-_") == 1 and " - " not in stem:
        artist, _, title = stem.partition("_-_")
        if artist.strip() and title.strip():
            return artist.strip(), title.strip()

    return "", stem


def parse_audio(path: Path) -> AudioFile:
    """Read metadata via ``mutagen``; fall back to filename parsing."""
    af = AudioFile(path=path, source="none")

    # 1) mutagen tags
    try:
        mf = mutagen.File(str(path))  # type: ignore[arg-type]
    except Exception:
        mf = None

    if mf is not None:
        try:
            af.duration = float(getattr(mf.info, "length", 0.0) or 0.0)
        except (TypeError, ValueError):
            af.duration = 0.0

        tags = getattr(mf, "tags", None) or {}
        title_keys = ("TIT2", "title", "\xa9nam", "TITLE")
        artist_keys = ("TPE1", "artist", "\xa9ART", "ARTIST")
        album_keys = ("TALB", "album", "\xa9alb", "ALBUM")
        composer_keys = ("TCOM", "composer", "\xa9wrt", "COMPOSER")
        language_keys = ("TLAN", "language", "LAN")
        # ``TDRC`` is ID3v2.4 recording time (may be ``"2024-08"``
        # or full ISO ``"2024-08-01"``); ``TYER`` is ID3v2.3 plain
        # ``"2024"``.  Vorbis/FLAC use ``DATE`` or ``YEAR``; MP4 uses
        # ``\xa9day``.  Format-specific keys come first so a tagged
        # ``DATE: 2024-09`` doesn't lose to a stray fallback later.
        year_keys = ("TDRC", "TYER", "\xa9day", "DATE", "YEAR")
        for k in title_keys:
            v = _first_tag(tags, k)
            if v:
                af.title = v
                break
        for k in artist_keys:
            v = _first_tag(tags, k)
            if v:
                af.artist = v
                break
        for k in album_keys:
            v = _first_tag(tags, k)
            if v:
                af.album = v
                break
        for k in composer_keys:
            v = _first_tag(tags, k)
            if v:
                af.composer = v
                break
        for k in language_keys:
            v = _first_tag(tags, k)
            if v:
                af.language = v
                break
        for k in year_keys:
            v = _first_tag(tags, k)
            if v:
                # ``TDRC`` may be ``"2024-08-01"`` -- we only want
                # the year for ``[year:YYYY]``.  First 4-digit run,
                # falling back to full int() on the slim chance the
                # tag already holds a plain 4-digit string.  Both
                # paths raise-guard so a malformed tag (``"N/A"``,
                # ``"unknown"``) lands on ``year == 0`` and the LRC
                # writer simply skips the ``[year:]`` header.
                stripped = v.strip()
                head = stripped[:4]
                if head.isdigit():
                    # ``head.isdigit()`` guarantees ``int(head)``
                    # is safe (Python's ``str.isdigit`` rejects any
                    # non-digit ASCII / Unicode char so a
                    # ``ValueError`` from the parse is unreachable
                    # here).  Falling through rather than raising
                    # for ``"0000"``-style sentinels keeps the rest
                    # of the list alive; the outer ``try / except
                    # ValueError`` below is what catches malformed
                    # tags like ``"N/A"``.
                    af.year = int(head)
                    if af.year:
                        break
                try:
                    af.year = int(stripped)
                    break
                except ValueError:
                    continue

        if af.title or af.artist:
            af.source = "tags"

    # 2) filename fallback (only if tags missing important fields)
    if not af.title or not af.artist:
        fa_artist, fa_title = parse_filename(path)
        if not af.artist:
            af.artist = fa_artist
        if not af.title:
            af.title = fa_title
        if (fa_artist or fa_title) and af.source == "none":
            af.source = "filename"

    af.artist = af.artist.strip()
    af.title = af.title.strip()
    af.album = af.album.strip()
    af.composer = af.composer.strip()
    af.language = af.language.strip()
    return af


def _first_tag(tags, key: str) -> str:
    """Return the first string value for ``key`` regardless of tag flavour.

    ``mutagen._vorbis.VorbisComment.__getitem__`` raises :class:`ValueError`
    (NOT :class:`KeyError`) for missing / malformed keys -- a real-world
    case that hit us when scanning an OGG file with no Vorbis comments at
    all or with one of the probe keys spelled/labelled unexpectedly (the
    worker crashed mid-iteration with ``ValueError`` leaking out of
    ``__getitem__`` and tore down the whole batch).  ID3 / APEv2 / MP4
    tags use :class:`KeyError` instead; ``TypeError`` covers the case
    where ``tags`` is ``None`` or has been coerced into a plain ``dict``
    that swallows nonsensical lookups.  Catch all three so a single
    badly-tagged file can't poison the whole scan.
    """
    try:
        value = tags[key]
    except (KeyError, TypeError, ValueError):
        return ""
    # mutagen returns list[str] (vorbis/APEv2) or ``mutagen.id3._TextFrame``
    # (ID3).  Handle both.  The ``value.text`` branch below is ID3-only --
    # vorbis/APEv2 values are plain ``list[str]`` and never get here --
    # so its ``except`` clause stays narrow at ``(IndexError, TypeError)``
    # (the realistic failure modes for ``list[str][0]``).  Widening it
    # would be unused coverage and a misleading comment.
    if isinstance(value, list):
        if not value:
            return ""
        item = value[0]
        if hasattr(item, "text"):
            return str(item.text[0]) if item.text else ""
        return str(item)
    if hasattr(value, "text"):
        try:
            return str(value.text[0])
        except (IndexError, TypeError):
            return ""
    return str(value)


# ---------------------------------------------------------------------------
# Directory walking
# ---------------------------------------------------------------------------


def is_audio(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def iter_audio_files(root: Path, recursive: bool = True) -> Iterator[AudioFile]:
    """Yield :class:`AudioFile` for every audio file under ``root``.

    ``recursive=False`` only scans the immediate folder.
    """
    root = Path(root)
    if root.is_file():
        if is_audio(root):
            yield parse_audio(root)
        return

    if recursive:
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                p = Path(dirpath) / name
                if is_audio(p):
                    yield parse_audio(p)
    else:
        for p in root.iterdir():
            if p.is_file() and is_audio(p):
                yield parse_audio(p)


__all__: Iterable[str] = (
    "AudioFile",
    "SUPPORTED_EXTENSIONS",
    "iter_audio_files",
    "is_audio",
    "parse_audio",
    "parse_filename",
)
