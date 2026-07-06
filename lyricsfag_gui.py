#!/usr/bin/env python3
"""LyricsFAG GUI: scan an audio library and create .lrc files next to it.

Launches a Tkinter window with a folder picker, source toggle, options panel,
live progress bar, colour-coded log, a Stop button, and a **device status
badge** that tracks the CUDA/CPU preference chosen by the user and the
presence of the optional ``demucs`` vocal-isolation stage.

Architecture
------------
* The Tk main thread owns every widget.
* A single :class:`threading.Thread` walks the directory and calls
  :func:`lyricsfag.process_one` per file.
* The worker installs a :class:`QueueHandler` on the ``"lyricsfag"`` logger so
  every ``LOG.info/warning/error/debug`` call lands in a thread-safe
  :class:`queue.Queue`.
* :meth:`LyricsFAGApp._poll_queue`, called via ``root.after``, drains messages
  from the main thread and applies them to widgets.
* Cancellation is a single :class:`threading.Event`; the worker checks it at
  every file boundary AND between transcription segments so the Stop button
  responds within a second even during the slow ``faster-whisper`` fallback.
* Total file count is precomputed in the worker so the progress bar is
  determinate despite the generator-style iteration in :func:`iter_audio_files`.
* Device status is probed **once at startup** via :func:`device_snapshot` so
  the GPU badge ("GPU: NVIDIA RTX 3060"  green / "CPU"  yellow) doesn't wait
  on the worker's first analyzer construction, and a ``("device_info",
  text, fg_hex)`` queue event refreshes it after the analyzer loads (which
  is when the actual device choice is final).
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# Allow `python lyricsfag_gui.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import tkinter as tk
    from tkinter import filedialog, font, messagebox, ttk
except ImportError as exc:  # pragma: no cover - tkinter is bundled with CPython
    sys.stderr.write(
        "LyricsFAG GUI requires Tkinter, which is bundled with the official "
        "Python.org installer on Windows/macOS and packaged separately on "
        "some Linux distros (e.g. `apt install python3-tk`). Underlying "
        f"error: {exc}\n"
    )
    raise SystemExit(2)

from lyricsfag_lib.audio import iter_audio_files  # noqa: E402
from lyricsfag_lib.audio_analysis import (  # noqa: E402
    SUPPORTED_MODELS as _SUPPORTED_AUDIO_MODELS,
    warn_first_run_aggregate,
)
from lyricsfag_lib.device import (  # noqa: E402
    cuda_available,
    device_snapshot,
    format_device_badge,
    gpu_name,
    resolve_device,
)
from lyricsfag_lib.lyrics import (  # noqa: E402
    ENV_GENIUS_TOKEN,
    LyricsFetcher,
)
from lyricsfag_lib.settings import (  # noqa: E402
    load_settings,
    save_settings,
    settings_path,
)
from collections import Counter
from lyricsfag import (  # noqa: E402
    STATUS_DRY_RUN,
    STATUS_FAILED,
    STATUS_MISSING,
    STATUS_SKIPPED,
    STATUS_WRITTEN,
    ProcessOutcome,
    _format_provider_breakdown,
    _format_summary_lines,
    process_one,
)

LOG = logging.getLogger("lyricsfag")


# ---------------------------------------------------------------------------
# log -> queue bridge
# ---------------------------------------------------------------------------


class QueueHandler(logging.Handler):
    """Logging handler that enqueues formatted records on a thread-safe queue."""

    def __init__(self, q: queue.Queue) -> None:
        super().__init__()
        self.queue = q
        self.setFormatter(logging.Formatter("%(levelname)s %(message)s"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(("log", record))
        except queue.Full:  # pragma: no cover - queue is unbounded
            pass


# ---------------------------------------------------------------------------
# Worker + config dataclass
# ---------------------------------------------------------------------------


@dataclass
class JobConfig:
    """Settings the worker runs with, snapshotted when ``Start`` is pressed."""

    root: Path
    recursive: bool
    force: bool
    dry_run: bool
    source: str
    genius_token: Optional[str]
    log_level: int = logging.INFO
    use_audio_analysis: bool = False
    audio_model: str = "base"
    audio_model_path: Optional[Path] = None
    device: str = "auto"           # 'auto' / 'cuda' / 'cpu'
    enable_demucs: bool = True     # on by default; user can dim via combobox


def _count_files(root: Path, recursive: bool) -> int:
    """Pre-walk ``root`` so the progress bar can be determinate."""
    if root.is_file():
        return 1
    extensions = (
        ".flac", ".mp3", ".m4a", ".mp4", ".aac", ".ogg", ".oga",
        ".opus", ".wma", ".wav", ".ape", ".wv", ".tak",
    )
    n = 0
    if recursive:
        for _dirpath, _dirs, files in os.walk(root):
            for name in files:
                if name.lower().endswith(extensions):
                    n += 1
    else:
        for p in root.iterdir():
            if p.is_file() and p.suffix.lower() in extensions:
                n += 1
    return n


def _build_audio_analyzer(cfg: JobConfig, ui_queue: "queue.Queue"):
    """Lazy-construct the optional faster-whisper + demucs analyzer.

    Emits a fresh ``("device_info", text, fg_hex)`` queue event so the GPU
    badge reflects **the analyzer's final device**, which honours the user's
    cfg.device choice (not just the auto probe at app startup).

    Also logs a one-line warning when demucs is on and the resolved device
    is CPU — demucs on CPU multiplies runtime by 5-10x and a 300-song batch
    can easily burn 25+ hours.  The user can flip the Demucs combobox to
    "off" or pick a CUDA device from the Device dropdown.
    """
    if not cfg.use_audio_analysis:
        return None
    # Aggregate pre-flight WARNING -- one line summarising total
    # first-run network bandwidth (whisper + demucs).  Fires before
    # the analyzer is constructed so the user sees the cost up-front;
    # per-model WARNINGs from deeper in the stack still fire on first use.
    warn_first_run_aggregate(
        audio_model=cfg.audio_model,
        audio_model_path=cfg.audio_model_path,
        enable_demucs=cfg.enable_demucs,
    )
    try:
        from lyricsfag_lib.audio_analysis import FasterWhisperAnalyzer
        analyzer = FasterWhisperAnalyzer(
            model_size=cfg.audio_model,
            model_path=cfg.audio_model_path,
            device=cfg.device,
            enable_demucs=cfg.enable_demucs,
        )
    except Exception as exc:  # pragma: no cover - import-time hazard
        LOG.error("Audio analyser failed to initialise: %s", exc)
        return None

    chosen_device = resolve_device(cfg.device)
    if cfg.enable_demucs and chosen_device == "cpu":
        LOG.warning(
            "Demucs vocal isolation on CPU is slow (~5-10x realtime per "
            "song). For large batches, switch the Device dropdown to "
            "'auto'/'cuda' or set Demucs to 'off'."
        )

    # Single badge-builder call so startup + worker stay consistent.
    # `format_device_badge` only reads `device` + `gpu_name`; the rest is
    # left to the analyzer.describe() log line below.
    snap = {
        "device": chosen_device,
        "gpu_name": gpu_name() if chosen_device.startswith("cuda") else None,
    }
    badge_text, badge_fg = format_device_badge(snap)
    ui_queue.put_nowait(("device_info", badge_text, badge_fg))
    LOG.info("Audio fallback: %s", analyzer.describe())
    return analyzer


def _run_worker(
    cfg: JobConfig, ui_queue: queue.Queue, stop_event: threading.Event
) -> None:
    """Background worker body.  Communicates via ``ui_queue`` only."""
    try:
        LOG.setLevel(cfg.log_level)

        LOG.info("Scanning %s ...", cfg.root)
        total = _count_files(cfg.root, cfg.recursive)
        ui_queue.put_nowait(("scan_complete", total))
        if total == 0:
            LOG.warning("No audio files found under %s", cfg.root)
            ui_queue.put_nowait(("job_done", cfg.dry_run, 0, 0, 0, 0, 0, 0.0))
            return

        audio_analyzer = _build_audio_analyzer(cfg, ui_queue)
        if cfg.use_audio_analysis and audio_analyzer is None:
            LOG.warning(
                "Audio analysis enabled but faster-whisper not installed. "
                "Install with: pip install faster-whisper"
            )
        elif audio_analyzer is not None:
            LOG.info("Local audio-analysis fallback ready.")

        fetcher = LyricsFetcher(
            source=cfg.source,
            genius_token=cfg.genius_token,
            audio_analyzer=audio_analyzer,
            cancel_event=stop_event,
        )
        if cfg.source != "genius" and not cfg.genius_token:
            LOG.info(
                "Hint: set %s to unlock the Genius database when LRCLIB has no match.",
                ENV_GENIUS_TOKEN,
            )

        started = time.monotonic()
        counters = {
            STATUS_WRITTEN: 0,
            STATUS_DRY_RUN: 0,
            STATUS_SKIPPED: 0,
            STATUS_MISSING: 0,
            STATUS_FAILED: 0,
        }
        # Tracks how many files came from each provenance so the worker
        # can emit a per-provider breakdown alongside the existing
        # ``Done in`` summary -- mirrors the CLI's totals so the two
        # surfaces stay in lockstep.
        by_provider: Counter[str] = Counter()

        for i, audio in enumerate(iter_audio_files(cfg.root, recursive=cfg.recursive), 1):
            if stop_event.is_set():
                LOG.warning("Stopped by user after %d of %d files.", i - 1, total)
                break

            ui_queue.put_nowait(("progress", i, total, audio.path.name))
            outcome = process_one(
                audio,
                fetcher,
                root=cfg.root,
                force=cfg.force,
                dry_run=cfg.dry_run,
            )
            ui_queue.put_nowait(("outcome", outcome))
            counters[outcome.status] = counters.get(outcome.status, 0) + 1
            if outcome.status == STATUS_WRITTEN and outcome.provider:
                by_provider[outcome.provider] += 1

        # Track the per-provider write count -- the worker mirrors the
        # CLI's _format_summary_lines() output so both surfaces never
        # drift apart in wording.
        elapsed = time.monotonic() - started
        # Use the shared helper so the worker's log lines and the
        # GUI summary_var text mirror :func:`lyricsfag.main` exactly.
        done_line, breakdown_line = _format_summary_lines(
            elapsed=elapsed,
            dry_run=cfg.dry_run,
            written=counters[STATUS_WRITTEN],
            dry_run_count=counters[STATUS_DRY_RUN],
            skipped=counters[STATUS_SKIPPED],
            missing=counters[STATUS_MISSING],
            failed=counters[STATUS_FAILED],
            by_provider=by_provider,
        )
        LOG.info(done_line)
        if breakdown_line:
            LOG.info(breakdown_line)
        ui_queue.put_nowait((
            "job_done",
            cfg.dry_run,
            counters[STATUS_WRITTEN],
            counters[STATUS_DRY_RUN],
            counters[STATUS_SKIPPED],
            counters[STATUS_MISSING],
            counters[STATUS_FAILED],
            elapsed,
            by_provider,
        ))
    except Exception as exc:  # last-line defence -- surface to UI
        LOG.error("Worker crashed: %s", exc)
        LOG.error(
            "Traceback (collapsed; details in console if launched with --console):\n%s",
            "\n".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
        ui_queue.put_nowait(("job_failed", f"{type(exc).__name__}: {exc}"))


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------


class LyricsFAGApp(tk.Tk):
    """Tkinter root window.  All widget construction lives in one place."""

    POLL_MS = 80  # how often the main thread drains the queue
    COLOUR_BG = "#1e1e1e"
    COLOUR_FG = "#e4e4e4"
    COLOUR_LOG_BG = "#181818"

    STATUS_TAG: dict[str, str] = {
        STATUS_WRITTEN: "ok",
        STATUS_DRY_RUN: "ok",
        STATUS_SKIPPED: "skip",
        STATUS_MISSING: "missing",
        STATUS_FAILED: "fail",
    }

    def __init__(self, log_level: int = logging.INFO) -> None:
        super().__init__()
        self.title("LyricsFAG")
        self.geometry("900x720")
        self.minsize(760, 540)

        # State
        self.ui_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.log_handler: Optional[QueueHandler] = None
        self._last_folder = str(Path.home())
        self._initial_log_level = log_level

        self._build_widgets()
        self._attach_log_handler()
        self._paint_initial_device_badge()
        self._apply_persisted_settings()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(self.POLL_MS, self._poll_queue)

    # -- construction -------------------------------------------------------

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        # Title
        ttk.Label(
            outer,
            text="LyricsFAG \u2014 Automatic LRC creator",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        # Folder picker
        ttk.Label(outer, text="Music folder:").grid(
            row=1, column=0, sticky="w", padx=(0, 6)
        )
        self.folder_var = tk.StringVar(value=self._last_folder)
        ttk.Entry(outer, textvariable=self.folder_var).grid(
            row=1, column=1, sticky="ew", padx=(0, 6)
        )
        ttk.Button(
            outer, text="Browse...", command=self._on_browse
        ).grid(row=1, column=2)

        # Options row
        opts = ttk.Frame(outer)
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 6))
        self.recursive_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Recursive", variable=self.recursive_var).pack(
            side="left", padx=(0, 14)
        )
        self.force_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Force overwrite LRC", variable=self.force_var
        ).pack(side="left", padx=(0, 14))
        self.dry_run_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Dry-run", variable=self.dry_run_var).pack(
            side="left", padx=(0, 14)
        )
        self.use_audio_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            opts, text="Use audio analysis (local)", variable=self.use_audio_var
        ).pack(side="left")

        # Source row
        src = ttk.Frame(outer)
        src.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        ttk.Label(src, text="Source:").pack(side="left", padx=(0, 6))
        self.source_var = tk.StringVar(value="auto")
        ttk.Combobox(
            src,
            textvariable=self.source_var,
            values=("auto", "lrclib", "genius"),
            state="readonly",
            width=10,
        ).pack(side="left", padx=(0, 16))

        ttk.Label(src, text=f"Genius token (env: {ENV_GENIUS_TOKEN}):").pack(
            side="left", padx=(0, 6)
        )
        self.genius_var = tk.StringVar(value=os.environ.get(ENV_GENIUS_TOKEN, ""))
        ttk.Entry(src, textvariable=self.genius_var, width=30, show="\u2022").pack(
            side="left", fill="x", expand=True
        )

        # Audio-analysis panel (two sub-rows: model+device+demucs / model path).
        audio_row = ttk.Frame(outer)
        audio_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        audio_row.columnconfigure(3, weight=1)

        ttk.Label(audio_row, text="Whisper model:").grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.audio_model_var = tk.StringVar(value="base")
        ttk.Combobox(
            audio_row,
            textvariable=self.audio_model_var,
            values=_SUPPORTED_AUDIO_MODELS,
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky="w")

        ttk.Label(audio_row, text="Device:").grid(
            row=0, column=2, sticky="e", padx=(16, 6)
        )
        self.device_choice_var = tk.StringVar(value="auto")
        ttk.Combobox(
            audio_row,
            textvariable=self.device_choice_var,
            values=("auto", "cuda", "cpu"),
            state="readonly",
            width=8,
        ).grid(row=0, column=3, sticky="w")

        ttk.Label(audio_row, text="Demucs:").grid(
            row=0, column=4, sticky="e", padx=(16, 6)
        )
        self.demucs_var = tk.StringVar(value="on")
        ttk.Combobox(
            audio_row,
            textvariable=self.demucs_var,
            values=("on", "off"),
            state="readonly",
            width=8,
        ).grid(row=0, column=5, sticky="w")

        ttk.Label(audio_row, text="Model path (optional):").grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0)
        )
        self.audio_model_path_var = tk.StringVar(value="")
        ttk.Entry(audio_row, textvariable=self.audio_model_path_var).grid(
            row=1, column=1, columnspan=5, sticky="ew", pady=(6, 0)
        )

        # Buttons row
        btns = ttk.Frame(outer)
        btns.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(2, 8))
        self.start_btn = ttk.Button(btns, text="Start", command=self._on_start)
        self.start_btn.pack(side="left", padx=(0, 6))
        self.stop_btn = ttk.Button(
            btns, text="Stop", command=self._on_stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=(0, 6))
        ttk.Button(
            btns, text="Open output folder", command=self._on_open_out
        ).pack(side="left", padx=(0, 6))

        # Progress bar
        self.progress = ttk.Progressbar(outer, mode="determinate", maximum=100)
        self.progress.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(2, 2))

        # Status row + device badge (badge right-aligned in col 2).
        self.status_var = tk.StringVar(value="Idle.")
        ttk.Label(outer, textvariable=self.status_var, foreground="#666").grid(
            row=7, column=0, columnspan=2, sticky="w"
        )
        self.device_var = tk.StringVar(value="Device: detecting...")
        self.device_label = ttk.Label(outer, textvariable=self.device_var, foreground="#888")
        self.device_label.grid(row=7, column=2, sticky="e")

        # Log panel
        log_frame = ttk.LabelFrame(outer, text="Log")
        log_frame.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        self.log_text = tk.Text(
            log_frame,
            height=18,
            wrap="word",
            state="disabled",
            bg=self.COLOUR_LOG_BG,
            fg=self.COLOUR_FG,
            insertbackground=self.COLOUR_FG,
            font=("Consolas", 9),
        )
        scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._configure_log_tags()

        # Footer (summary line).  Multi-line content (Done in... +
        # By provider breakdown) needs an explicit ``wraplength`` so a
        # long per-provider list doesn't clip horizontally on a narrow
        # window.  ``<Configure>`` fires whenever the widget is resized,
        # so we keep the wrap matched to the current label width.
        self.summary_var = tk.StringVar(value="")
        self.summary_label = ttk.Label(
            outer, textvariable=self.summary_var, font=("Segoe UI", 9, "bold")
        )
        self.summary_label.grid(
            row=9, column=0, columnspan=3, sticky="we", pady=(6, 0)
        )
        self.summary_label.bind(
            "<Configure>",
            # Tk delivers an initial ``<Configure>`` during widget
            # construction with ``e.width == 1`` (the placeholder
            # 1-pixel width before the real geometry is mapped);
            # applying that as ``wraplength`` would wrap every glyph
            # and stay broken until the user manually resizes the
            # window, so we skip until the label has a sensible width.
            lambda e: None if e.width <= 1
            else self.summary_label.configure(wraplength=e.width),
        )

        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(8, weight=1)

    def _configure_log_tags(self) -> None:
        """Colours by event outcome, level defaults to neutral."""
        base = font.Font(font=self.log_text.cget("font"))
        self.log_text.tag_configure("info", foreground="#cfcfcf")
        self.log_text.tag_configure("dim", foreground="#888")
        self.log_text.tag_configure("ok", foreground="#80ff80")
        self.log_text.tag_configure("skip", foreground="#ffd76b")
        self.log_text.tag_configure("missing", foreground="#ffd76b")
        self.log_text.tag_configure("fail", foreground="#ff6b6b")
        self.log_text.tag_configure("warn", foreground="#ffd76b")
        self.log_text.tag_configure(
            "error",
            foreground="#ff6b6b",
            font=(base.actual("family"), base.actual("size"), "bold"),
        )
        # Whisper-derived lyrics are synthetic and may carry transcription
        # errors; surface them in the GUI log panel in orange (matching the
        # CLI's ANSI 256-colour ``38;5;208``) so the user can spot them at a
        # glance during a batch run.  Only the *outcome* row uses this tag
        # (see :meth:`_render_outcome`); the per-file progress messages
        # stay on their default level-based colour.
        self.log_text.tag_configure("whisper", foreground="#ff8c00")

    # -- log plumbing -------------------------------------------------------

    def _attach_log_handler(self) -> None:
        self.log_handler = QueueHandler(self.ui_queue)
        LOG.addHandler(self.log_handler)
        # ``lyricsfag_lib.*`` loggers are SIBLINGS of ``lyricsfag`` in the
        # logging hierarchy (they share ``root`` as a parent but not each
        # other), so a WARNING emitted from e.g. ``lyricsfag_lib.audio_analysis``
        # would never reach the QueueHandler attached to ``lyricsfag`` and
        # silently disappear from the GUI log panel.  Mirror the handler
        # onto the package logger so the new pre-flight download
        # WARNINGs (``Whisper: downloading model='base' ...``,
        # ``Demucs: downloading model='htdemucs' ...``,
        # ``First run will download ~570 MB total (...)``) actually land
        # in the on-screen log.  Also raise ``lyricsfag_lib``'s level to
        # the user-selected verbosity so ``--verbose`` enables its
        # INFO/DEBUG lines here too (mirrors what
        # ``lyricsfag.setup_logging`` does for the CLI).
        self.lib_log_handler = QueueHandler(self.ui_queue)
        self._lib_log = logging.getLogger("lyricsfag_lib")
        self._lib_log.addHandler(self.lib_log_handler)
        self._lib_log.setLevel(self._initial_log_level)

    def _detach_log_handler(self) -> None:
        if self.log_handler is not None:
            LOG.removeHandler(self.log_handler)
            self.log_handler = None
        if getattr(self, "lib_log_handler", None) is not None:
            self._lib_log.removeHandler(self.lib_log_handler)
            self.lib_log_handler = None

    # -- device badge -------------------------------------------------------

    def _paint_initial_device_badge(self) -> None:
        """Probe the device once at startup so the badge is ready before Start.

        Affordable because :func:`device_snapshot` imports torch lazily; the
        very first Tk paint isn't penalised if torch is missing (we just
        fall back to a neutral '—' badge).
        """
        try:
            snap = device_snapshot()
            text, fg = format_device_badge(snap)
        except Exception:
            text, fg = "Device: —", "#888"
        self.device_var.set(text)
        self.device_label.configure(foreground=fg)

    # -- persistence --------------------------------------------------------

    def _apply_persisted_settings(self) -> None:
        """Restore last-used widget values from ``settings.json``.

        Called once in :meth:`__init__` *after* the widgets exist (so their
        StringVar/BooleanVar slots are valid) and *after* the log handler
        is attached (so the "Loaded persisted settings ..." line lands in
        the GUI log panel rather than the console).
        """
        loaded = load_settings()
        if not loaded:
            return
        LOG.info("Loaded persisted settings from %s", settings_path())
        if "folder" in loaded:
            # Update both the StringVar (visible in the entry) AND
            # ``_last_folder`` so :meth:`_on_browse` opens at the previous
            # folder rather than the in-code default of ``Path.home()``.
            self._last_folder = loaded["folder"]
            self.folder_var.set(loaded["folder"])
        for tkvar, key in (
            (self.recursive_var, "recursive"),
            (self.force_var, "force"),
            (self.dry_run_var, "dry_run"),
            (self.use_audio_var, "use_audio_analysis"),
        ):
            if key in loaded:
                tkvar.set(loaded[key])
        if "source" in loaded:
            self.source_var.set(loaded["source"])
        if "genius_token" in loaded:
            # Plaintext on disk by design -- see SECURITY note in
            # ``lyricsfag_lib.settings``. An empty string means "the user
            # deliberately cleared the field", which we honour even when
            # ``GENIUS_ACCESS_TOKEN`` is present in the environment.
            self.genius_var.set(loaded["genius_token"])
        if "audio_model" in loaded:
            self.audio_model_var.set(loaded["audio_model"])
        if "audio_model_path" in loaded:
            self.audio_model_path_var.set(loaded["audio_model_path"])
        if "device" in loaded:
            self.device_choice_var.set(loaded["device"])
        if "demucs" in loaded:
            self.demucs_var.set(loaded["demucs"])

    def _save_settings_snapshot(self) -> None:
        """Persist current widget values; never raises -- log on failure.

        Both :meth:`_on_start` (after validation, before worker spawn) and
        :meth:`_on_close` call this. We swallow :class:`OSError` so a
        full disk or permission-denied transient failure leaves the GUI
        responsive instead of disappearing mid-batch, but we DO surface
        the warning in the log panel so the user knows their UI state
        won't survive the next launch.
        """
        try:
            save_settings(
                {
                    "folder": self.folder_var.get(),
                    "recursive": self.recursive_var.get(),
                    "force": self.force_var.get(),
                    "dry_run": self.dry_run_var.get(),
                    "use_audio_analysis": self.use_audio_var.get(),
                    "source": self.source_var.get(),
                    "genius_token": self.genius_var.get(),
                    "audio_model": self.audio_model_var.get(),
                    "audio_model_path": self.audio_model_path_var.get(),
                    "device": self.device_choice_var.get(),
                    "demucs": self.demucs_var.get(),
                }
            )
            LOG.debug("Saved settings to %s", settings_path())
        except OSError as exc:
            LOG.warning("Could not save settings to %s: %s", settings_path(), exc)

    # -- event handlers -----------------------------------------------------

    def _on_browse(self) -> None:
        initial = self.folder_var.get().strip() or self._last_folder
        chosen = filedialog.askdirectory(
            title="Select your music folder",
            initialdir=initial,
            mustexist=True,
        )
        if chosen:
            self.folder_var.set(chosen)
            self._last_folder = chosen

    def _on_start(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            messagebox.showwarning("No folder", "Please pick a music folder first.")
            return
        root = Path(folder).expanduser().resolve()
        if not root.exists():
            messagebox.showerror("Path not found", f"Folder does not exist:\n{root}")
            return

        audio_model_path_raw = self.audio_model_path_var.get().strip()
        try:
            audio_model_path = (
                Path(audio_model_path_raw).expanduser().resolve()
                if audio_model_path_raw
                else None
            )
        except OSError as exc:
            messagebox.showerror(
                "Invalid model path", f"Could not resolve path:\n{exc}"
            )
            return

        cfg = JobConfig(
            root=root,
            recursive=self.recursive_var.get(),
            force=self.force_var.get(),
            dry_run=self.dry_run_var.get(),
            source=self.source_var.get(),
            genius_token=self.genius_var.get().strip() or None,
            log_level=self._initial_log_level,
            use_audio_analysis=self.use_audio_var.get(),
            audio_model=self.audio_model_var.get(),
            audio_model_path=audio_model_path,
            device=self.device_choice_var.get(),
            enable_demucs=(self.demucs_var.get() == "on"),
        )

        # Manual CUDA override without hardware -> fall back to CPU here so
        # the user is told an explicit chose-cuda was invalid, instead of
        # half-way through a 300-song batch.
        if cfg.device == "cuda" and not cuda_available():
            LOG.warning(
                "Device 'cuda' requested but no CUDA hardware detected; "
                "falling back to CPU."
            )
            cfg.device = "cpu"

        if cfg.source == "genius" and not cfg.genius_token:
            messagebox.showwarning(
                "Genius token required",
                "Source 'genius' was selected but no token was supplied.",
            )
            return

        # Reset UI for a fresh run
        self._reset_for_new_run()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

        # Surface the user's device choice immediately so the badge
        # reflects *intent* while the worker warms up.
        self._refresh_badge_for_choice(cfg.device)

        # Persist the validated config snapshot BEFORE the worker spawns.
        # If the run crashes the worker without ever calling _on_close,
        # the next launch still comes up with the same settings.
        self._save_settings_snapshot()

        self.stop_event.clear()
        self.worker = threading.Thread(
            target=_run_worker,
            args=(cfg, self.ui_queue, self.stop_event),
            name="lyricsfag-worker",
            daemon=True,
        )
        self.worker.start()

    def _refresh_badge_for_choice(self, choice: str) -> None:
        """Update the badge from user combobox choice only.

        Doesn't re-probe torch — that happens in the worker. The colour
        hint here is just the intent (green=preferred CUDA, yellow=CPU)
        so the badge stays useful even before the analyzer loads weights.
        """
        if choice == "cpu":
            self.device_var.set("CPU")
            self.device_label.configure(foreground="#ffd76b")
        elif choice == "cuda":
            self.device_var.set("GPU: requested (loading...)")
            self.device_label.configure(foreground="#80ff80")
        else:
            # auto — defer to the existing snapshot.
            try:
                _t, fg = format_device_badge(device_snapshot())
                self.device_label.configure(foreground=fg)
            except Exception:
                self.device_label.configure(foreground="#888")

    def _on_stop(self) -> None:
        if not (self.worker and self.worker.is_alive()):
            return
        self.stop_btn.configure(state="disabled")
        self.status_var.set("Stopping after current file (or transcription step)...")
        self.stop_event.set()

    def _on_open_out(self) -> None:
        folder = self.folder_var.get().strip() or self._last_folder
        path = Path(folder).expanduser().resolve()
        if path.is_dir():
            try:
                if sys.platform == "win32":
                    os.startfile(path)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    os.system(f'open "{path}"')
                else:
                    os.system(f'xdg-open "{path}"')
            except Exception as exc:
                messagebox.showerror("Open folder failed", str(exc))

    def _on_close(self) -> None:
        if self.worker and self.worker.is_alive():
            if not messagebox.askokcancel(
                "Run in progress", "A scan is still running. Stop and exit?"
            ):
                return
            self.stop_event.set()
            self.worker.join(timeout=20)
        # Last-ditch save: even if the worker aborted before persisting,
        # the widget values on screen right now are what the next launch
        # should come up with.
        self._save_settings_snapshot()
        self._detach_log_handler()
        self.destroy()

    # -- polling + widget updates ------------------------------------------

    def _reset_for_new_run(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.progress.configure(value=0, maximum=100)
        self.summary_var.set("")
        self.status_var.set("Working...")

    def _append_log(self, record: logging.LogRecord) -> None:
        msg = (
            self.log_handler.format(record)
            if self.log_handler
            else record.getMessage()
        )
        try:
            level_tag = {
                logging.WARNING: "warn",
                logging.ERROR: "error",
                logging.DEBUG: "dim",
            }[record.levelno]
        except KeyError:
            level_tag = "info"

        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", (level_tag,))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)

    def _set_progress_determinate(self, total: int) -> None:
        self.progress.configure(mode="determinate", maximum=max(total, 1), value=0)

    def _update_progress(self, current: int, total: int, file_name: str) -> None:
        self.progress.configure(maximum=max(total, 1), value=current)
        self._set_status(f"({current}/{total}) {file_name}")

    def _render_outcome(self, outcome: ProcessOutcome) -> None:
        # Whisper-written rows get a dedicated orange tag so the user
        # can scan a long batch and immediately see which songs were
        # transcribed locally (and therefore may carry ASR errors that
        # warrant a manual pass).  Other statuses keep their usual
        # severity-based colour so green/yellow/red still mean what
        # they meant before this change.
        whisper_written = (
            outcome.status == STATUS_WRITTEN and outcome.provider == "whisper"
        )
        tag = "whisper" if whisper_written else self.STATUS_TAG.get(outcome.status, "info")
        line = f"  -> {outcome.status.upper().replace('_', '-')}: {outcome.shown}"
        if outcome.provider and outcome.status == "written":
            line += f" (provider={outcome.provider})"
        if outcome.reason:
            line += f" ({outcome.reason})"
        elif outcome.detail:
            line += f" ({outcome.detail})"
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n", (tag,))
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_device_badge(self, text: str, fg: str) -> None:
        self.device_var.set(text)
        self.device_label.configure(foreground=fg)

    def _set_summary(
        self,
        cfg_dry_run: bool,
        written: int,
        dry_run_count: int,
        skipped: int,
        missing: int,
        failed: int,
        elapsed: float,
        by_provider: Counter[str] | None = None,
    ) -> None:
        done_line, breakdown_line = _format_summary_lines(
            elapsed=elapsed,
            dry_run=cfg_dry_run,
            written=written,
            dry_run_count=dry_run_count,
            skipped=skipped,
            missing=missing,
            failed=failed,
            by_provider=by_provider or Counter(),
        )
        text = done_line + ("\n" + breakdown_line if breakdown_line else "")
        self.summary_var.set(text)
        self.status_var.set("Idle.")
        self.progress.configure(value=self.progress.cget("maximum"))
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _poll_queue(self) -> None:
        try:
            while True:
                item = self.ui_queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._append_log(item[1])
                elif kind == "scan_complete":
                    self._set_progress_determinate(item[1])
                elif kind == "progress":
                    self._update_progress(item[1], item[2], item[3])
                elif kind == "outcome":
                    self._render_outcome(item[1])
                elif kind == "device_info":
                    # ("device_info", text, fg_hex)
                    self._set_device_badge(item[1], item[2])
                elif kind == "job_done":
                    self._set_summary(*item[1:])
                elif kind == "job_failed":
                    self.status_var.set("Worker crashed.")
                    self.summary_var.set(f"Failed: {item[1]}")
                    self.start_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.after(self.POLL_MS, self._poll_queue)


def main(log_level: int = logging.INFO) -> int:
    LyricsFAGApp(log_level=log_level).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
