#!/usr/bin/env python3
"""LyricsFAG CLI: scan an audio library and create .lrc files next to it.

Usage:
    python lyricsfag.py PATH [--recursive|--no-recursive] [--force]
                             [--source auto|lrclib|genius|audio]
                             [--genius-token TOKEN] [--dry-run] [--quiet]
                             [--use-audio-analysis] [--audio-model MODEL]
                             [--audio-model-path PATH]
    python lyricsfag.py --gui

Run ``python lyricsfag.py --help`` for the full option list.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

# Allow `python lyricsfag.py` from the project root without setup headaches.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lyricsfag_lib.audio import AudioFile, iter_audio_files  # noqa: E402
from lyricsfag_lib.audio_analysis import (  # noqa: E402
    SUPPORTED_MODELS as _WHISPER_MODELS,
    warn_first_run_aggregate,
)
from lyricsfag_lib.device import resolve_device  # noqa: E402
from lyricsfag_lib.lyrics import (  # noqa: E402
    ENV_GENIUS_TOKEN,
    LyricsFailure,
    LyricsFetcher,
    LyricsResult,
)
from lyricsfag_lib.lrc import write_lrc  # noqa: E402

LOG = logging.getLogger("lyricsfag")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class Colors:
    """ANSI colour helpers.  Disabled when output is not a TTY or --no-color."""

    enabled = sys.stdout.isatty()

    @classmethod
    def enable(cls, force_on: bool, force_off: bool) -> None:
        if force_on:
            cls.enabled = True
        elif force_off:
            cls.enabled = False

    @staticmethod
    def wrap(code: str, text: str) -> str:
        if not Colors.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    @classmethod
    def green(cls, t: str) -> str:
        return cls.wrap("32", t)

    @classmethod
    def yellow(cls, t: str) -> str:
        return cls.wrap("33", t)

    @classmethod
    def red(cls, t: str) -> str:
        return cls.wrap("31", t)

    @classmethod
    def cyan(cls, t: str) -> str:
        return cls.wrap("36", t)

    @classmethod
    def orange(cls, t: str) -> str:
        """Wrap ``t`` in ANSI 256-colour orange (``38;5;208``).

        208 is the canonical "pure orange" palette index — ``33`` would
        give the paler 16-colour yellow that most terminals render as
        brown.  ANSI escape nesting is well-defined, so an orange
        wrapper around an already-coloured string (e.g. cyan provider
        tag) renders as expected on every modern terminal.  On the rare
        pre-Windows-10 ``cmd.exe`` that doesn't honour 256-colour, the
        worst case is the line shows without colour — never garbled.
        """
        return cls.wrap("38;5;208", t)

    @classmethod
    def dim(cls, t: str) -> str:
        return cls.wrap("90", t)


_LEVEL_STYLES = {
    logging.DEBUG: Colors.dim,
    logging.INFO: lambda t: t,
    logging.WARNING: Colors.yellow,
    logging.ERROR: Colors.red,
}


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        renderer = _LEVEL_STYLES.get(record.levelno, lambda t: t)
        msg = super().format(record)
        return renderer(msg)


# ---------------------------------------------------------------------------
# CLI plumbing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lyricsfag",
        description=(
            "Scan a folder for audio files and create matching .lrc files "
            "with synchronized lyrics from LRCLIB and Genius."
        ),
    )
    p.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Folder (or single audio file) to process. Default: current directory.",
    )
    p.add_argument(
        "--recursive",
        dest="recursive",
        action="store_true",
        default=True,
        help="Recurse into subdirectories (default).",
    )
    p.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Process only the top-level folder.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing .lrc files.",
    )
    p.add_argument(
        "--source",
        choices=("auto", "lrclib", "genius", "audio"),
        default="auto",
        help=(
            "Lyrics provider. 'auto' (default) tries LRCLIB first (synced "
            "lyrics), then Genius; with --use-audio-analysis it adds local "
            "faster-whisper as a 3rd fallback. Use 'audio' to skip web "
            "providers and go straight to local transcription."
        ),
    )
    p.add_argument(
        "--genius-token",
        dest="genius_token",
        default=None,
        help=(
            f"Genius API access token. Falls back to env var {ENV_GENIUS_TOKEN}. "
            "Get one free at https://genius.com/api-clients."
        ),
    )
    p.add_argument(
        "--use-audio-analysis",
        dest="use_audio_analysis",
        action="store_true",
        help=(
            "Local audio transcription via faster-whisper as a 3rd fallback "
            "(after LRCLIB + Genius). Requires `pip install faster-whisper`."
        ),
    )
    p.add_argument(
        "--audio-model",
        choices=_WHISPER_MODELS,
        default="base",
        help=(
            "faster-whisper model size used by --use-audio-analysis. "
            "Default: base (~150 MB, balanced)."
        ),
    )
    p.add_argument(
        "--audio-model-path",
        dest="audio_model_path",
        default=None,
        help=(
            "Path to a local faster-whisper model directory. If omitted, the "
            "model with name --audio-model is downloaded on first use."
        ),
    )
    p.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help=(
            "Compute device for faster-whisper (and demucs, when used). "
            "'auto' picks CUDA when torch sees a usable GPU, else CPU. "
            "Default: auto."
        ),
    )
    p.add_argument(
        "--no-demucs",
        dest="enable_demucs",
        action="store_false",
        default=True,
        help=(
            "Disable demucs vocal isolation; faster-whisper runs on the raw "
            "audio mix instead. Demucs is enabled by default whenever the "
            "package is importable."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done, write nothing.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Only print errors and final summary.",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    p.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Coloured output. Default: auto (TTY only).",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after writing this many LRC files. 0 = no limit.",
    )
    return p


def setup_logging(args: argparse.Namespace, level: Optional[int] = None) -> None:
    """Configure the ``lyricsfag`` logger."""
    Colors.enable(force_on=args.color == "always", force_off=args.color == "never")
    if level is None:
        level = logging.WARNING if args.quiet else logging.INFO
        if args.verbose:
            level = logging.DEBUG

    handler = logging.StreamHandler()
    handler.setFormatter(
        ColorFormatter("%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    )
    LOG.handlers.clear()
    LOG.addHandler(handler)
    LOG.setLevel(level)
    # Propagate the requested level to ``lyricsfag_lib`` child loggers so
    # ``--verbose`` actually surfaces their INFO/DEBUG lines (e.g.
    # ``Demucs: model=htdemucs device=...`` and ``Whisper: loading model=...``
    # from ``lyricsfag_lib.audio_analysis``).  Each child logger defaults to
    # ``WARNING`` and silently drops INFO records even when the parent root
    # logger is at DEBUG -- we have to override the package level here so
    # they inherit the caller's chosen verbosity.
    logging.getLogger("lyricsfag_lib").setLevel(level)


# ---------------------------------------------------------------------------
# Processing loop
# ---------------------------------------------------------------------------


# Outcome codes for one audio file.  Strings are stable (stringified to logs).
STATUS_WRITTEN = "written"
STATUS_DRY_RUN = "dry_run"
STATUS_SKIPPED = "skipped"
STATUS_MISSING = "missing"
STATUS_FAILED = "failed"


@dataclass
class ProcessOutcome:
    """Result of processing a single audio file.

    Both the CLI and the GUI consume this object so behaviour stays in lockstep
    without duplicating the per-file logic.
    """

    status: str
    audio_path: Path
    shown: str  # relative-to-root path, for log lines
    detail: str = ""
    target_path: Optional[Path] = None
    provider: Optional[str] = None
    reason: Optional[str] = None  # provider error reason, set on STATUS_FAILED
    line_count: int = 0
    synced: bool = False


def _shown_path(audio: AudioFile, root: Path) -> str:
    try:
        rel = audio.path.relative_to(root)
        return rel.as_posix() if rel.parts[:-1] else audio.path.name
    except ValueError:
        return audio.path.name


def process_one(
    audio: AudioFile,
    fetcher: LyricsFetcher,
    *,
    root: Path,
    force: bool,
    dry_run: bool,
) -> ProcessOutcome:
    """Process a single audio file and return a :class:`ProcessOutcome`."""
    shown = _shown_path(audio, root)

    if not audio.title and not audio.artist:
        return ProcessOutcome(
            status=STATUS_MISSING,
            audio_path=audio.path,
            shown=shown,
            detail="no title/artist in tags or filename",
        )

    if audio.has_lrc() and not force:
        return ProcessOutcome(
            status=STATUS_SKIPPED,
            audio_path=audio.path,
            shown=shown,
            detail="lrc exists (use --force to overwrite)",
        )

    LOG.debug(
        "Querying %s - %s (%.1fs)", audio.artist, audio.title, audio.duration
    )
    result = fetcher.fetch(audio)

    if isinstance(result, LyricsFailure):
        return ProcessOutcome(
            status=STATUS_FAILED,
            audio_path=audio.path,
            shown=shown,
            detail=f"{result.provider}: {result.reason}",
            provider=result.provider,
            reason=result.reason,
        )

    doc = result.to_document()
    if not doc.title:
        doc.title = audio.title
    if not doc.artist:
        doc.artist = audio.artist
    if not doc.album:
        doc.album = audio.album
    if not doc.length_seconds:
        doc.length_seconds = audio.duration

    target = audio.lrc_path
    if dry_run:
        return ProcessOutcome(
            status=STATUS_DRY_RUN,
            audio_path=audio.path,
            shown=shown,
            target_path=target,
            provider=result.provider,
            line_count=len(doc.lines),
            synced=result.is_synced,
        )

    try:
        write_lrc(target, doc, overwrite=True)
    except OSError as exc:
        return ProcessOutcome(
            status=STATUS_FAILED,
            audio_path=audio.path,
            shown=shown,
            detail=f"write failed: {exc}",
            provider=result.provider,
            reason=str(exc),
        )

    return ProcessOutcome(
        status=STATUS_WRITTEN,
        audio_path=audio.path,
        shown=shown,
        target_path=target,
        provider=result.provider,
        line_count=len(doc.lines),
        synced=result.is_synced,
    )


def _log_outcome(outcome: ProcessOutcome) -> None:
    """Emit a single coloured log line for a :class:`ProcessOutcome`."""
    # Whisper-derived lyrics are synthetic and may carry transcription
    # errors, so the provider tag is coloured ORANGE to flag the row at
    # a glance -- the rest of the line keeps the standard INFO palette
    # so severity-based log parsing is unaffected.  Other elements
    # (filename, kind, line count) keep their pre-existing colours per
    # branch; we deliberately do not touch them.
    provider_name = outcome.provider or "?"
    is_whisper = provider_name == "whisper"

    if outcome.status == STATUS_WRITTEN:
        # Filename green on success; provider cyan by default, ORANGE
        # when whisper transcription produced the lyrics.
        provider_styler = Colors.orange if is_whisper else Colors.cyan
        kind = "synced" if outcome.synced else "plain"
        LOG.info(
            "%s :: wrote %s [%s, %s, %d lines]",
            outcome.shown,
            Colors.green(outcome.target_path.name if outcome.target_path else "?"),
            provider_styler(provider_name),
            kind,
            outcome.line_count,
        )
    elif outcome.status == STATUS_DRY_RUN:
        # Filename stays plain (no green) in dry-run -- the existing
        # convention is green on the *provider* in this branch.  Whisper
        # still swaps to orange so the synthetic-source flag is visible
        # in both branches.
        provider_styler = Colors.orange if is_whisper else Colors.green
        LOG.info(
            "%s :: would write %s [%s] %d lines (synced=%s)",
            outcome.shown,
            outcome.target_path.name if outcome.target_path else "?",
            provider_styler(provider_name),
            outcome.line_count,
            outcome.synced,
        )
    elif outcome.status == STATUS_SKIPPED:
        LOG.info("%s :: lrc exists, skipping (use --force to overwrite)", outcome.shown)
    elif outcome.status == STATUS_MISSING:
        LOG.warning(
            "%s :: no title/artist found in tags or filename -- skipping",
            outcome.shown,
        )
    elif outcome.status == STATUS_FAILED:
        if outcome.provider:
            LOG.warning(
                "%s :: %s: %s",
                outcome.shown,
                Colors.cyan(outcome.provider),
                outcome.reason or outcome.detail,
            )
        else:
            LOG.error("%s :: %s", outcome.shown, outcome.detail)


def process(
    audio_iter: Iterable[AudioFile],
    fetcher: LyricsFetcher,
    *,
    root: Path,
    force: bool,
    dry_run: bool,
    limit: int,
) -> tuple[int, int, int, int, int, Counter[str]]:
    """Walk ``audio_iter`` and write LRC files.

    Returns ``(written, dry_run_count, skipped, missing, failed,
    by_provider)`` where ``by_provider`` is a :class:`collections.Counter`
    of provider-name -> count for ``STATUS_WRITTEN`` outcomes.  Used by
    :func:`main` to print the per-provider breakdown after the
    aggregate ``"Done in"`` line so the user can see at a glance how
    many files came from each upstream source (lrclib, whisper, genius,
    heuristic, vad-preflight, ...).
    """
    written = dry_run_count = skipped = missing = failed = 0
    by_provider: Counter[str] = Counter()

    for audio in audio_iter:
        if limit and written >= limit:
            LOG.info("Hit --limit=%d; stopping.", limit)
            break

        outcome = process_one(
            audio, fetcher, root=root, force=force, dry_run=dry_run
        )
        _log_outcome(outcome)

        if outcome.status == STATUS_WRITTEN:
            written += 1
            # Only tally providers on actual writes -- a dry-run run
            # increments ``dry_run_count`` instead, so the breakdown
            # correctly says ``(none)`` when nothing was really saved.
            if outcome.provider:
                by_provider[outcome.provider] += 1
        elif outcome.status == STATUS_DRY_RUN:
            dry_run_count += 1
        elif outcome.status == STATUS_SKIPPED:
            skipped += 1
        elif outcome.status == STATUS_MISSING:
            missing += 1
        elif outcome.status == STATUS_FAILED:
            failed += 1

    return written, dry_run_count, skipped, missing, failed, by_provider


def _format_provider_breakdown(by_provider: Counter[str]) -> str:
    """Render ``by_provider`` as a brief ``provider=count`` summary.

    Output is sorted by descending count then ascending provider name
    so the most-used source always leads.  Zero-count entries are
    hidden to keep the line brief; an empty Counter (or one whose
    values are all zero) collapses to ``"(none)"`` so the GUI runtime
    doesn't print an empty trailing line.
    """
    items = [(p, n) for p, n in by_provider.items() if n > 0]
    if not items:
        return "(none)"
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(f"{p}={n}" for p, n in items)


def _format_summary_lines(
    *,
    elapsed: float,
    dry_run: bool,
    written: int,
    dry_run_count: int,
    skipped: int,
    missing: int,
    failed: int,
    by_provider: Counter[str],
) -> tuple[str, str]:
    """Build the two-line end-of-run summary used by both CLI and GUI.

    Returns ``(done_line, breakdown_line)``.  When ``by_provider`` has
    no non-zero entries (no actual writes were recorded -- e.g. a
    dry-run-only run, or one where every successful provider returned
    ``None``), ``breakdown_line`` is the empty string so callers can
    skip emitting it; the existing ``Done in -- written=N`` (or
    ``would_write=N``) line already conveys that no real saves happened
    and a trailing ``(none)`` would just be duplicative.

    Sharing this helper between :func:`main` and
    :meth:`lyricsfag_gui._run_worker` (and indirectly :meth:`_set_summary`)
    keeps the two surfaces in lockstep -- changing wording or schema
    only needs to happen once.
    """
    verb = "would write" if dry_run else "written"
    primary = written if not dry_run else dry_run_count
    done = (
        f"Done in {elapsed:.1f}s -- {verb}={primary}, "
        f"dry-run={dry_run_count}, skipped={skipped}, "
        f"missing-meta={missing}, failed={failed}"
    )
    # ``not by_provider`` covers both ``None`` and an empty ``Counter``
    # in one guard; the ``sum(...) == 0`` would AttributeError on None
    # and is otherwise redundant with it, so the OR makes the helper
    # safe against future call-site mistakes AND suppresses the
    # breakdown line when every provider ended up with zero writes.
    if not by_provider or sum(by_provider.values()) == 0:
        return done, ""
    return done, f"By provider (created): {_format_provider_breakdown(by_provider)}"


# ---------------------------------------------------------------------------
# Audio analyser wiring (lazy import)
# ---------------------------------------------------------------------------


def _build_audio_analyzer(args: argparse.Namespace):
    """Instantiate the optional audio analyzer and surface explicit errors.

    Returns ``None`` (and logs a hint) when ``faster-whisper`` isn't installed
    or the user didn't opt in.
    """
    if not args.use_audio_analysis:
        return None
    # Aggregate pre-flight WARNING -- one line summarising the total
    # first-run network bandwidth (whisper + demucs).  Fires before the
    # analyzer is constructed so the user sees the cost up-front; the
    # per-model WARNINGs from deeper in the stack still fire on first use.
    warn_first_run_aggregate(
        audio_model=getattr(args, "audio_model", "base"),
        audio_model_path=Path(args.audio_model_path).expanduser().resolve()
        if getattr(args, "audio_model_path", None)
        else None,
        enable_demucs=getattr(args, "enable_demucs", True),
    )
    try:
        from lyricsfag_lib.audio_analysis import FasterWhisperAnalyzer
        analyzer = FasterWhisperAnalyzer(
            model_size=getattr(args, "audio_model", "base"),
            model_path=Path(args.audio_model_path).expanduser().resolve()
            if getattr(args, "audio_model_path", None)
            else None,
            device=getattr(args, "device", "auto"),
            enable_demucs=getattr(args, "enable_demucs", True),
        )
    except Exception as exc:  # pragma: no cover - import-time hazard
        LOG.error("Audio analyser failed to initialise: %s", exc)
        return None
    if not analyzer.enabled:
        LOG.warning(
            "--use-audio-analysis set but faster-whisper is not installed. "
            "Install with: pip install faster-whisper"
        )
        return None
    # Demucs on CPU is a 5–10x realtime trap; warn before committing to
    # a potentially 25+ hour batch. The `--device cuda` override is also
    # documented here so the user sees both opt-outs in one line.
    if getattr(args, "enable_demucs", True) and resolve_device(
        getattr(args, "device", "auto")
    ) == "cpu":
        LOG.warning(
            "Demucs vocal isolation on CPU is slow (~5-10x realtime per "
            "song). For large batches, pass --no-demucs or --device cuda "
            "(requires an NVIDIA GPU)."
        )
    LOG.info(
        "Local audio-analysis fallback enabled (%s)",
        analyzer.describe(),
    )
    return analyzer


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _wants_gui(argv: Optional[list[str]]) -> bool:
    """Cheap pre-check for ``--gui`` / ``-g`` without invoking argparse."""
    import re
    needle = re.compile(r"^--?gui(=|$)")
    return any(needle.search(a) for a in (argv or sys.argv[1:]))


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point used by both the CLI and the GUI dispatcher."""
    if _wants_gui(argv):
        # Defer tkinter import to keep the CLI fast at module load.
        from lyricsfag_gui import main as gui_main

        return gui_main(log_level=_resolve_log_level(argv))

    args = build_parser().parse_args(argv)
    setup_logging(args)

    root = Path(args.path).resolve()
    if not root.exists():
        LOG.error("Path not found: %s", root)
        return 2

    genius_token = args.genius_token or os.environ.get(ENV_GENIUS_TOKEN)
    if args.source == "genius" and not genius_token:
        LOG.error(
            "Genius requested but no token supplied. "
            "Pass --genius-token or set %s.",
            ENV_GENIUS_TOKEN,
        )
        return 2

    audio_analyzer = _build_audio_analyzer(args)
    if args.source == "audio" and audio_analyzer is None:
        LOG.warning(
            "--source audio requires a working audio analyser -- falling back to 'auto'."
        )
        args.source = "auto"

    fetcher = LyricsFetcher(
        source=args.source,
        genius_token=genius_token,
        audio_analyzer=audio_analyzer,
    )
    if args.source != "genius" and not genius_token:
        LOG.info(
            "Hint: set %s to unlock the Genius database when LRCLIB has no match.",
            ENV_GENIUS_TOKEN,
        )

    started = time.monotonic()
    written, dry_run_count, skipped, missing, failed, by_provider = process(
        iter_audio_files(root, recursive=args.recursive),
        fetcher,
        root=root,
        force=args.force,
        dry_run=args.dry_run,
        limit=args.limit,
    )
    elapsed = time.monotonic() - started

    done_line, breakdown_line = _format_summary_lines(
        elapsed=elapsed,
        dry_run=args.dry_run,
        written=written,
        dry_run_count=dry_run_count,
        skipped=skipped,
        missing=missing,
        failed=failed,
        by_provider=by_provider,
    )
    LOG.info(done_line)
    # Per-provider breakdown of actually-written files so the user can
    # see at a glance how many of each provenance (lrclib, whisper,
    # genius, heuristic, ...).  Skipped automatically when nothing was
    # actually written (dry-run-only runs, or all providers returned
    # None) -- the ``written=0`` line above already says so.
    if breakdown_line:
        LOG.info(breakdown_line)
    if failed:
        return 1
    return 0


def _resolve_log_level(argv: Optional[list[str]]) -> int:
    """Pick a logging level for the GUI from CLI hints (``--quiet``/``--verbose``)."""
    args_list = argv or sys.argv[1:]
    if "--verbose" in args_list or "-v" in args_list:
        return logging.DEBUG
    if "--quiet" in args_list or "-q" in args_list:
        return logging.WARNING
    return logging.INFO


if __name__ == "__main__":
    raise SystemExit(main())
