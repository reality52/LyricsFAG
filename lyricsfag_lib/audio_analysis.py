"""Local audio-analysis fallback for the lyrics chain.

When LRCLIB and Genius both miss, a third-tier :class:`FasterWhisperAnalyzer`
runs the audio file through ``faster-whisper`` on the local machine.  When
:class:`DemucsIsolator` is enabled, vocals are isolated **before** whisper
runs, which materially improves LRC quality on dense mixes.

Design choices (per project design pass):

* ``faster-whisper`` is a **soft** dependency. Import is guarded; if it's not
  installed, ``FasterWhisperAnalyzer.enabled`` is ``False`` and ``get()``
  yields a :class:`LyricsFailure` with a helpful hint.
* ``torch`` is **lazy**: ``device.py`` keeps the import inside functions so
  ``--help`` and the initial Tk paint cost zero seconds. CUDA detection and
  ``gpu_name()`` cache their results.
* Device and compute-type are resolved on first model load (``device='auto'``
  probes CUDA then caches). Default ``compute_type`` is ``float16`` on CUDA,
  ``int8`` on CPU.  Both can be overridden explicitly via the CLI / GUI.
* ``demucs`` is **opt-in** but defaults to ON when the analyzer is enabled
  and the package is importable.  When Demucs fails (OOM, missing dep,
  cancel), the analyzer falls through to whisper-on-raw-mix and logs the
  reason. The pipeline never aborts because Demucs failed.
* Cancellation: the analyzer accepts a ``threading.Event`` and stops between
  segments.  The GUI's Stop button reaches a mid-file transcription almost
  instantly (Demucs cancel is checked just before resampling).
* Hallucination filter: ``no_speech_prob > 0.6`` or ``avg_logprob < -1.0`` are
  dropped, plus a small blocklist for short spurious multi-word tokens.
* Bundling: the model directory is resolved via ``sys._MEIPASS`` first
  (PyInstaller unpacked location) and falls back to a relative
  ``models/whisper-base`` next to the package for dev runs.
"""

from __future__ import annotations

import logging
import math
import sys
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from .audio import AudioFile
from .device import (
    CUDA_COMPUTE_PREFERENCE,
    compute_type_for,
    cuda_compute_capability,
    gpu_name,
    is_demucs_available,
    resolve_device,
    supported_cuda_compute_types,
)
from .lyrics import LyricsFailure, LyricsResult
from .lrc import format_timestamp_ms

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PyTorch 2.6 / demucs 4.0.1 ``weights_only`` compatibility
# ---------------------------------------------------------------------------
#
# The actual monkey-patch lives in the package-internal
# :mod:`lyricsfag_lib._torch_compat` so :mod:`scripts.download_demucs_model`
# and this module share one implementation.  See that module\'s
# docstring for the full rationale (PyTorch 2.6 changed
# ``torch.load``\'s ``weights_only`` default to ``True``; demucs 4.0.1
# pickles ``HTDemucs`` / ``fractions.Fraction`` / ... that the strict
# unpickler rejects; we disable ``weights_only`` for ``.th`` files only
# to keep the safe default for other ``torch.load`` callers).
from ._torch_compat import ensure_torch_load_patched


# Recognised Whisper model ids (passed to ``WhisperModel(model_size_or_path=...)``).
SUPPORTED_MODELS: tuple[str, ...] = ("tiny", "base", "small", "medium", "large-v3")

# Approximate download sizes (in MB) for the Whisper models in
# :data:`SUPPORTED_MODELS`.  Used to warn the user before the first run
# pulls weights down from HuggingFace so they aren't surprised by a
# multi-hundred-MB / 1-2-minute download on a typical connection.
# Numbers come from each model's published size and drift slightly
# between HuggingFace releases -- the warning is intentionally
# approximate (we say "~N MB") rather than pin exact values.
_WHISPER_DOWNLOAD_HINTS_MB: dict[str, int] = {
    "tiny": 75,
    "base": 150,
    "small": 500,
    "medium": 1500,
    "large-v3": 3000,
}

# Approximate download sizes (in MB) for the Demucs models we ship out
# of the box.  ``htdemucs_ft`` (the default) is a
# :class:`demucs.pretrained.BagOfModels` of 4 sub-models
# (4 x ~84 MB = ~336 MB on disk after first download);
# ``htdemucs`` is a single pretrained HTDemucs (~84 MB).  The
# numbers are intentionally approximate (the WARNING surfaces them
# as ``~N MB``) so the user gets a realistic ballpark without us
# pinning per-release byte counts.  We surface the chosen model's
# size up front in :meth:`DemucsIsolator._ensure_separator` so the
# bandwidth cost of enabling Demucs is no longer a surprise.
_DEMUCS_DOWNLOAD_HINTS_MB: dict[str, int] = {
    "htdemucs_ft": 336,
    "htdemucs": 84,
}


def planned_first_run_download(
    *,
    audio_model: str = "base",
    audio_model_path: Optional[Path] = None,
    enable_demucs: bool = True,
    demucs_model: Optional[str] = None,
) -> tuple[bool, bool, int]:  # noqa: D401
    """Plan what ``--use-audio-analysis`` will download on first run.

    Returns ``(will_download_whisper, will_download_demucs, total_mb)``
    so callers can both log the upstream pre-flight summary AND branch
    on the answer (e.g. the CLI uses this in
    :func:`lyricsfag._build_audio_analyzer` to emit a single WARNING
    *before* per-model warnings fire from deeper in the stack).

    ``will_download_whisper`` is True only when *neither* the bundled
    ``models/whisper-base`` nor a user-supplied ``--audio-model-path``
    resolves to an existing directory -- in that branch faster-whisper
    is forced to fall back to HuggingFace on first use.

    ``will_download_demucs`` is True when demucs is enabled AND the
    torch hub cache at ``~/.cache/torch/hub/checkpoints`` is empty
    (no ``*.th`` files); any ``.th`` file there is almost certainly
    from a prior demucs run since torch hub users overwhelmingly
    serialize as ``.pth`` (torchvision) or ``.bin`` (HuggingFace).

    ``total_mb`` is the sum of approximate sizes from
    :data:`_WHISPER_DOWNLOAD_HINTS_MB` and
    :data:`_DEMUCS_DOWNLOAD_HINTS_MB`, or ``0`` when nothing will be
    pulled from the network.
    """
    demucs_model = demucs_model or DemucsIsolator.DEFAULT_MODEL
    will_w = _resolve_model_path(audio_model, audio_model_path) is None
    will_d = enable_demucs and not any(_native_demucs_cache_dir().glob("*.th"))
    total = 0
    if will_w:
        total += _WHISPER_DOWNLOAD_HINTS_MB.get(audio_model, 0)
    if will_d:
        total += _DEMUCS_DOWNLOAD_HINTS_MB.get(demucs_model, 0)
    return will_w, will_d, total


def warn_first_run_aggregate(
    *,
    audio_model: str = "base",
    audio_model_path: Optional[Path] = None,
    enable_demucs: bool = True,
) -> tuple[bool, bool, int]:
    """Emit a single WARNING summarising first-run network bandwidth.

    Calls :func:`planned_first_run_download` to compute the plan, then
    renders one WARNING line like::

        First run will download ~234 MB total (whisper-base ~150 MB +
        htdemucs_ft ~84 MB) from the network. Subsequent runs use the
        cached weights. Use --audio-model-path or pre-populate
        ~/.cache/torch/hub/checkpoints/*.th to skip one or both.

    Skips the WARNING entirely when ``total_mb == 0`` so subsequent
    runs (whose caches are warm) stay quiet.  Returns the same plan
    tuple so callers can branch on it ("did we just announce this?").

    The default Demucs model is :attr:`DemucsIsolator.DEFAULT_MODEL`
    (``"htdemucs_ft"`` today, ~84 MB) so the standard first-run WARNING
    string reads roughly::

        First run will download ~234 MB total (whisper-base ~150 MB +
        htdemucs_ft ~84 MB) from the network. ...

    If a user pins ``--demucs-model htdemucs`` (the legacy 5-sub-model
    bag, ~420 MB) the breakdown shifts accordingly.
    """
    will_w, will_d, total_mb = planned_first_run_download(
        audio_model=audio_model,
        audio_model_path=audio_model_path,
        enable_demucs=enable_demucs,
    )
    if total_mb <= 0:
        return will_w, will_d, total_mb
    parts: list[str] = []
    if will_w:
        parts.append(
            f"whisper-{audio_model} "
            f"~{_WHISPER_DOWNLOAD_HINTS_MB.get(audio_model, 0)} MB"
        )
    demucs_default = DemucsIsolator.DEFAULT_MODEL
    if will_d:
        parts.append(
            f"{demucs_default} "
            f"~{_DEMUCS_DOWNLOAD_HINTS_MB.get(demucs_default, 0)} MB"
        )
    LOG.warning(
        "First run will download ~%d MB total (%s) from the network. "
        "Subsequent runs use the cached weights. Use --audio-model-path "
        "or pre-populate ~/.cache/torch/hub/checkpoints/*.th to skip one "
        "or both downloads.",
        total_mb, " + ".join(parts),
    )
    return will_w, will_d, total_mb

# Hallucination guard: very low confidence or very likely silence -> skip segment.
_NO_SPEECH_THRESHOLD = 0.6
_AVG_LOGPROB_THRESHOLD = -1.0

# Common hallucinations on instrumental sections.  Kept multi-word only so we
# don't false-positive on legitimate lyric fragments like ``"Oh oh oh"``,
# ``"You you you"``, ``"Bye bye bye"`` — those are real refrains in songs.
# Single-word entries (``"you"``, ``"yeah"``, ...) were intentionally dropped:
# they catch genuine lyrics far too often to be worth blocking.
_HALLUCINATION_BLOCKLIST = frozenset({
    "thank you", "thank you.", "thank you!",
    "thanks for watching", "thanks for watching.",
    "subscribe", "subscribe.",
    "see you next time", "see you next time.",
    "goodbye", "goodbye.",
    "[music]", "(music)", "[applause]", "[laughter]",
})

# Bundled model location (relative to project root for dev; resolved via
# ``sys._MEIPASS`` at runtime in the PyInstaller bundled ``.exe``).
_BUNDLED_MODEL_DIR = Path("models") / "whisper-base"

# Default repo path for ``demucs.pretrained.get_model(..., repo=...)``.
# Mirrors the ``models/whisper-base`` Whisper convention so all bundled
# model weights live under a single ``models/`` tree next to the script.
# Demucs populates this on first run (htdemucs + bag-of-models weights
# are ~80 MB; the auxiliary ``955717e8-...th`` checkpoint demucs uses
# for ``htdemucs``'s hybrid-transformer core is ~2 GB).
_BUNDLED_DEMUCS_REPO_DIR = Path("models") / "demucs"

# Pre-flight thresholds for the instrumental-detector shortcut.  Anything
# below this RMS on the 16 kHz mono decode is treated as silent / very-low-
# energy (badly ripped, all-noise, dead air) and short-circuited to
# ``[Instrumental]`` *before* the heavy Whisper model is loaded.
_INSTRUMENTAL_SILENCE_RMS = 0.005
# Provider name used for the LRC metadata so users can see the synthetic
# source for files that bypassed Whisper.
_INSTRUMENTAL_PROVIDER = "vad-preflight"

try:
    import numpy as np  # type: ignore
    from faster_whisper import WhisperModel  # type: ignore
    from faster_whisper.audio import decode_audio  # type: ignore
    from faster_whisper.vad import (  # type: ignore
        get_speech_timestamps,
        get_vad_model,
    )
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only when missing
    _FASTER_WHISPER_AVAILABLE = False
    WhisperModel = None  # type: ignore[assignment]
    decode_audio = None  # type: ignore[assignment]
    get_speech_timestamps = None  # type: ignore[assignment]
    get_vad_model = None  # type: ignore[assignment]


@dataclass
class AnalyzerSegment:
    """Decoupled from ``faster_whisper`` so tests can fill it cheaply."""

    start: float
    end: float
    text: str
    no_speech_prob: float = 0.0
    avg_logprob: float = 0.0


class AudioAnalyzer(ABC):
    """Common interface so the chain in LyricsFetcher stays uniform."""

    name: str = "audio"

    @property
    @abstractmethod
    def enabled(self) -> bool: ...

    @abstractmethod
    def get(
        self,
        audio: AudioFile,
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> LyricsResult | LyricsFailure: ...


# -----------------------------------------------------------------------
# helpers
# -----------------------------------------------------------------------


def missing_audio_hint(pkg: str) -> str:
    """User-facing error string for a missing optional audio dependency.

    Two branches:
      * Normal dev run: hint at ``pip install <pkg>``.
      * Frozen PyInstaller build (most likely the lite build, which
        intentionally omits the audio stack so the .exe stays at the
        documented ~50 MB): point the user at the **portable** build
        instead.  ``pip install`` can't be done inside a read-only
        bundled .exe, so the dev-run hint would just confuse them.

    The function is now part of the public surface (no leading
    underscore) so :mod:`lyricsfag` and :mod:`lyricsfag_gui` can
    import it and route their own "audio not available" warnings
    through the same dev / frozen branch.  The two internal call
    sites below (:meth:`FasterWhisperAnalyzer.get` and
    :meth:`DemucsIsolator._ensure_separator`) and the three
    external ones in :mod:`lyricsfag` and :mod:`lyricsfag_gui`
    all share this string so a lite `.exe` user always gets a
    consistent "use the portable build" hint instead of the
    misleading "pip install ..." that can't run inside a
    read-only bundled binary.  The output is rendered as a
    :class:`LyricsFailure.reason` for the GUI / CLI log panel,
    so it should stay a single sentence (no bullet lists or
    newlines) to match the surrounding error formatting.
    """
    if getattr(sys, "frozen", False):
        return (
            f"{pkg} not bundled in this .exe (the lite build does "
            "not include the audio-analysis stack; use the portable "
            "build to enable local Whisper + Demucs)"
        )
    return f"{pkg} not installed (pip install {pkg})"


def _resolve_model_path(model_id: str, model_path: Optional[Path]) -> Optional[Path]:
    """Return the absolute path to use for ``WhisperModel(..., local_files_only=True)``.

    Priority: explicit ``model_path`` -> bundled dir under ``sys._MEIPASS`` ->
    bundled dir next to the package.
    """
    if model_path is not None:
        return Path(model_path).expanduser().resolve()

    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidate = base / _BUNDLED_MODEL_DIR
    return candidate if candidate.exists() else None


def _resolve_demucs_repo() -> Path:
    """Return the *absolute* default ``repo=`` path for :func:`demucs.pretrained.get_model`.

    Resolution order
    ----------------
    1. **Frozen PyInstaller bundle, ``--onefile``**: ``sys._MEIPASS`` is the
       per-launch temp tree where ``build-portable.bat`` drops
       ``models/demucs/`` via ``--add-data``; PyInstaller wipes that tree at
       process exit, which means cached weights would re-extract on every
       launch (acceptable: the .exe is self-contained, no network needed).
    2. **Frozen PyInstaller bundle, ``--onedir``** (no ``_MEIPASS``):
       fallback to ``models/demucs/`` next to the executable so a folder
       distribution stays usable.
    3. **Dev run** (no ``sys.frozen``): point at ``models/demucs/`` next
       to the project root (``Path(__file__).resolve().parents[1]``).

    Demucs only treats the repo path as a SOURCE for *already-downloaded*
    model files (see :class:`demucs.pretrained.LocalRepo`); it does NOT
    auto-download into this directory.  Callers therefore ORchestrate
    the load in two steps:

      * ``get_model(name, repo=this_path)`` -- the cheap "is it
        populated?" probe;
      * ``get_model(name)`` (no ``repo=``) -- falls back to the native
        cache and auto-downloads on first run, after which the freshly
        landed files are mirrored into this directory by
        :func:`_mirror_demucs_cache` so subsequent runs take the
        ``repo=`` branch.

    Note for build distribution
    ---------------------------
    To ship a fully pre-bundled exe (no first-run download), also add
    ``--add-data models/demucs;models/demucs`` to ``build.bat`` (mirroring
    how ``models/whisper-base`` is currently bundled).  The path
    resolution above already supports that layout -- it just resolves
    to wherever the bundle places ``models/demucs/`` relative to
    ``sys.executable.parent``.
    """
    if getattr(sys, "frozen", False):
        # Probe ``_MEIPASS`` first so ``--add-data models/demucs;models/demucs``
        # (used by ``build-portable.bat``) lands correctly under ``--onefile``;
        # fall back to ``sys.executable.parent`` for ``--onedir`` distributions.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            base = Path(meipass)
        else:
            base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parents[1]
    return (base / _BUNDLED_DEMUCS_REPO_DIR).resolve()


def _native_demucs_cache_dir() -> Path:
    """Return the directory where demucs' default cache (``repo=None``) deposits weights.

    Demucs 4.x's :class:`RemoteRepo` resolves its download destination
    via ``torch.hub.get_dir()`` (PyTorch's default Hub cache), which on
    Windows resolves to ``%USERPROFILE%\\.cache\\torch\\hub\\checkpoints``.
    We surface the same path here so the ``repo=`` value logged by
    :meth:`DemucsIsolator._ensure_separator` after a fallback load
    matches the on-disk location downstream code can inspect.
    """
    return Path.home() / ".cache" / "torch" / "hub" / "checkpoints"




def _segment_ok(seg: AnalyzerSegment) -> bool:
    """Drop hallucinated / silent segments before they reach the LRC."""
    text = (seg.text or "").strip().lower()
    if not text:
        return False
    if text in _HALLUCINATION_BLOCKLIST:
        LOG.debug("dropping hallucination blocklist segment: %r", text)
        return False
    if seg.no_speech_prob > _NO_SPEECH_THRESHOLD:
        LOG.debug("dropping low-speech segment (no_speech_prob=%.2f): %r",
                  seg.no_speech_prob, text)
        return False
    if seg.avg_logprob != 0.0 and seg.avg_logprob < _AVG_LOGPROB_THRESHOLD:
        LOG.debug("dropping low-logprob segment (avg_logprob=%.2f): %r",
                  seg.avg_logprob, text)
        return False
    return True


def _instrumental_result(
    audio: AudioFile, *, rms: float, decision: str
) -> LyricsResult:
    """Build the ``[Instrumental]`` LyricsResult for either pre-flight path."""
    return LyricsResult(
        provider=_INSTRUMENTAL_PROVIDER,
        title=audio.title,
        artist=audio.artist,
        album=audio.album,
        length_seconds=float(audio.duration or 0.0),
        plain_text="[Instrumental]",
        instrumental=True,
        raw_extras={"rms": round(rms, 6), "decision": decision},
    )


def _detect_instrumental_preflight(audio: AudioFile) -> Optional[LyricsResult]:
    """Cheap vocal/energy probe that runs *before* loading the Whisper model.

    Two-stage check returns a ``LyricsResult(instrumental=True,
    plain_text="[Instrumental]")`` if either:

      * the decoded 16 kHz mono float32 buffer has near-zero RMS
        (silent, badly-ripped, or pure-noise files); or
      * the bundled Silero VAD (``faster_whisper.vad``) finds zero speech
        segments anywhere in the track (vocal-free music / karaoke).

    Returns ``None`` (so the caller proceeds to Whisper) when the deps are
    missing, the decode/VAD call fails, or speech is detected.
    """
    if not _FASTER_WHISPER_AVAILABLE:
        return None

    try:
        samples = decode_audio(str(audio.path), sampling_rate=16000)
    except Exception as exc:
        LOG.debug(
            "Instrumental pre-flight: decode failed (%s) for %s",
            exc, audio.path.name,
        )
        return None

    # faster-whisper returns ``(channels, samples)`` for stereo sources when
    # ``split_stereo=False``; reduce to mono so RMS / Silero VAD see a proper
    # 1-D signal instead of interleaved L/R. The transpose guard handles a
    # hypothetical future release that flips to ``(samples, channels)`` --
    # channels are always small (<= 8 even on 7.1 audio), so anything where
    # ``shape[1] < shape[0]`` is by definition wrong-orientation.
    arr = np.asarray(samples)
    if arr.ndim == 2:
        if arr.shape[1] < arr.shape[0]:
            arr = arr.T
        arr = arr.mean(axis=0)
    if arr.size == 0:
        return None

    # ``max(head_rms, tail_rms)`` over the first/last ~30 s keeps a song with
    # a long silent intro or outro from sneaking under the silence threshold
    # — the vocal body still hits a high RMS even if the head is dead air.
    window = 16000 * 30
    head = arr[:window] if arr.size > window else arr
    tail = arr[-window:] if arr.size > window else arr
    rms = max(
        float(np.sqrt(np.mean(head * head))),
        float(np.sqrt(np.mean(tail * tail))),
    )
    if rms < _INSTRUMENTAL_SILENCE_RMS:
        LOG.info(
            "Pre-flight: %s looks silent (rms=%.4f < %.4f); marking [Instrumental].",
            audio.path.name, rms, _INSTRUMENTAL_SILENCE_RMS,
        )
        return _instrumental_result(audio, rms=rms, decision="silence")

    try:
        vad = get_vad_model()
        speech = get_speech_timestamps(arr, vad)
    except Exception as exc:  # pragma: no cover - VAD output shapes are hard to mock deterministically
        LOG.debug(
            "Instrumental pre-flight: VAD failed (%s) for %s",
            exc, audio.path.name,
        )
        return None

    if not speech:
        LOG.info(
            "Pre-flight: Silero VAD found no speech in %s; marking [Instrumental].",
            audio.path.name,
        )
        return _instrumental_result(audio, rms=rms, decision="vad")

    return None  # speech present; let Whisper take over


# -----------------------------------------------------------------------
# Demucs vocal isolator (optional pre-stage)
# -----------------------------------------------------------------------


DEMUCS_SR = 44100          # demucs htdemucs native sample rate
WHISPER_SR = 16000         # faster-whisper expected sample rate


class DemucsIsolator:
    """Wrap demucs 4.x's pretrained model + :func:`apply_model` to return
    vocals at 16 kHz mono.

    Demucs 4.0 removed the legacy :class:`demucs.api.Separator` class
    entirely.  The 4.x flow is:

      * :func:`demucs.pretrained.get_model` -- obtain the model object
        (an :class:`HTDemucs` *or* a :class:`BagOfModels` of several of
        them).
      * :func:`demucs.audio.AudioFile.from_file` -- decode the source
        audio to a float tensor at the model's native sample rate.
      * :func:`demucs.apply.apply_model` -- run separation and receive
        per-source tensors.

    Weights are downloaded and loaded once on the first song of a batch
    and reused thereafter.  Used by :class:`FasterWhisperAnalyzer`
    *after* the cheap VAD pre-flight so we never pay the demucs cost on
    a track that already failed the cheap speech check.

    Failure semantics
    -----------------
    Any failure (``ImportError`` for demucs 4.x surface, decode error
    in :func:`AudioFile.from_file`/``read``, OOM / driver error in
    :func:`apply_model`, missing ``vocals`` source, ...) returns
    ``None`` and logs a warning so the analyser can fall through to the
    unmodified audio mix. :attr:`enabled` proxies
    :func:`is_demucs_available`, so the precondition is reported
    cleanly even before any heavy load.
    """

    name = "demucs"
    # ``htdemucs_ft`` is the Meta-released music-only fine-tune of
    # ``htdemucs``. Fine-tuning improves vocal isolation quality on dense
    # mixes and produces noticeably cleaner Whisper output, at the cost
    # of being a single pretrained run rather than a 5-model bag
    # (one ~84 MB download vs ~420 MB). The ``htdemucs`` base model is
    # still selectable via ``DemucsIsolator(model="htdemucs")`` /
    # ``FasterWhisperAnalyzer(demucs_model="htdemucs")`` for users who
    # want the larger ensemble.
    DEFAULT_MODEL = "htdemucs_ft"

    def __init__(
        self,
        *,
        device: str = "auto",
        model: str = DEFAULT_MODEL,
        repo: Optional[Path] = None,
    ) -> None:
        self.device_pref = device
        self.model_name = model
        # demucs 4.x removed the ``Separator`` wrapper class; we now hold
        # the pretrained model object directly (HTDemucs or BagOfModels).
        self._model = None
        self._sources: Optional[list[str]] = None
        self._resolved_device: Optional[str] = None
        # ``repo`` is the cache directory passed to
        # ``demucs.pretrained.get_model(..., repo=...)``.  ``None`` here
        # means "use the default ``models/demucs`` next to the script",
        # resolved lazily inside :meth:`_ensure_separator` so a
        # PyInstaller-bundled exe resolves inside ``sys._MEIPASS`` while
        # a dev run resolves against the project root.
        self._repo: Optional[Path] = repo

    @property
    def enabled(self) -> bool:
        return is_demucs_available()

    def _ensure_separator(self) -> None:
        """Load the pretrained model on first call; reuse thereafter.

        The method name is kept for backward compatibility with the
        existing code paths even though :class:`demucs.api.Separator` is
        no longer used -- internally we populate ``self._model`` and
        ``self._sources`` from
        :func:`demucs.pretrained.get_model`.
        """
        if self._model is not None:
            return
        if not self.enabled:
            raise RuntimeError(missing_audio_hint("demucs"))
        from demucs.pretrained import get_model

        # PyTorch 2.6 / demucs 4.0.1 ``weights_only`` workaround --
        # shared implementation lives in :mod:`lyricsfag_lib._torch_compat`
        # so the script and the library can\'t drift.  The confirmation
        # log line fires on first application, which is useful for
        # confirming the patch is actually in effect.
        ensure_torch_load_patched()

        self._resolved_device = resolve_device(self.device_pref)
        # We never pass ``repo=`` here because :class:`demucs.pretrained.LocalRepo`
        # requires an ALREADY-POPULATED directory of model metadata files (e.g.
        # ``htdemucs.yaml``, ``htdemucs.th``).  Demucs does NOT auto-download
        # into ``repo=``, so passing our freshly mkdir'd ``models/demucs`` would
        # trigger ``"is neither a single pre-trained model or a bag of models"``
        # and the user would see a confusing fallback to raw audio.  The
        # portable fix is: let demucs use its native cache
        # (``~/.cache/torch/hub/checkpoints`` via :func:`_native_demucs_cache_dir`),
        # auto-download on first run (each model is only ~80 MB so the cost is
        # fine), and merely *create* ``models/demucs/`` so a developer who
        # later runs ``python -m demucs -d models/demucs htdemucs`` can seed
        # it for an offline-first ``--onefile`` bundle in ``build.bat``.
        bundled_repo_path = self._repo if self._repo else _resolve_demucs_repo()
        bundled_repo_path.mkdir(parents=True, exist_ok=True)
        # Bundled-repo detection: when ``build-portable.bat`` baked a
        # populated ``models/demucs/`` into the .exe via ``--add-data``,
        # prefer that ``LocalRepo`` source so the first launch is offline
        # and doesn't trigger a ~420 MB fetch from facebookresearch/demucs.
        # We probe only ``.th`` here because demucs's :class:`LocalRepo`
        # reads ``<model_name>.th``; a yaml-only bundle would fail the
        # subsequent ``get_model(...)`` call and demote this branch to a
        # warning (the existing exception path in :meth:`isolate_vocals`
        # already handles that).  ``sorted`` keeps the count deterministic
        # across Python invocations (``Path.glob`` order is
        # filesystem-dependent on Windows) so the log line says
        # ``N weight file(s)`` instead of jittering.
        _bundled_weights = sorted(bundled_repo_path.glob("*.th"))
        # Cache-hit detection (for the *non-bundled* fallback path): skip the
        # "downloading ~N MB" warning on subsequent runs.  Demucs' native
        # cache lives at ``~/.cache/torch/hub/checkpoints`` and any ``.th``
        # file there is almost certainly from a prior demucs run (other
        # torch hub modules rarely use this exact name).  On a complete
        # cache hit we emit INFO ("loading from local cache") instead of
        # WARNING ("downloading ~420 MB") so the user is no longer misled
        # into thinking a multi-hundred-MB fetch is about to happen every
        # run.
        _native_cache = _native_demucs_cache_dir()
        _cache_has_weights = any(_native_cache.glob("*.th"))
        if _bundled_weights:
            # Bundled tree wins over the native cache: the user opted into
            # the portable build, so we honour the bundle (offline-safe,
            # doesn't hit facebookresearch/demucs, deterministic across
            # machines).  ``str(...)`` so demucs doesn't see a Pathlib
            # instance on Python 3.9 / older demucs 4.0 prereleases.
            LOG.info(
                "Demucs: loading model='%s' from bundled repo at %s; "
                "no download required (%d weight file(s)).",
                self.model_name, bundled_repo_path, len(_bundled_weights),
            )
            # NOTE: ``repo=`` expects a :class:`pathlib.Path` (or any
            # :class:`os.PathLike`), NOT a ``str`` -- demucs 4.0.1's
            # :class:`LocalRepo` calls ``repo.is_dir()`` on the value
            # we pass and ``str.is_dir`` does not exist.  See the
            # :func:`scripts.download_demucs_model.verify_layout` docstring
            # for the same trap on the script side.
            self._model = get_model(self.model_name, repo=bundled_repo_path)
        elif _cache_has_weights:
            LOG.info(
                "Demucs: loading model='%s' from local cache at %s; "
                "no download required.",
                self.model_name, _native_cache,
            )
            self._model = get_model(self.model_name)
        else:
            # Pre-flight warning so the user knows the first run will
            # pull Demucs weights from facebookresearch/demucs. The
            # model-shape descriptor is data-driven (the default
            # ``htdemucs_ft`` is a single fine-tuned run; ``htdemucs``
            # is a :class:`BagOfModels` of 5 sub-models) so we don't
            # lie about the footprint for users who pinned a non-default.
            _mb = _DEMUCS_DOWNLOAD_HINTS_MB.get(self.model_name)
            _shape_note = (
                "BagOfModels of 5 sub-models"
                if self.model_name == "htdemucs"
                else "single fine-tuned model"
                if self.model_name == "htdemucs_ft"
                else "pretrained run"
            )
            if _mb is not None:
                LOG.warning(
                    "Demucs: downloading model='%s' from "
                    "facebookresearch/demucs (~%d MB, approximate; "
                    "%s) on first use; "
                    "subsequent runs use the cached weights at "
                    "%s. Disable the audio analysis fallback (uncheck "
                    "'Use audio analysis' in the GUI / drop "
                    "--use-audio-analysis from the CLI) to skip this "
                    "heavy vocal-isolation pre-stage.",
                    self.model_name, _mb, _shape_note, _native_cache,
                )
            else:
                LOG.warning(
                    "Demucs: downloading model='%s' (%s) from "
                    "facebookresearch/demucs on first use; disable the "
                    "audio analysis fallback (uncheck 'Use audio "
                    "analysis' in the GUI / drop --use-audio-analysis "
                    "from the CLI) to skip this heavy vocal-isolation "
                    "pre-stage.",
                    self.model_name, _shape_note,
                )
            self._model = get_model(self.model_name)
        self._model.to(self._resolved_device)
        self._model.eval()
        # ``HTDemucs.sources`` is ``['drums', 'bass', 'other', 'vocals']``;
        # ``BagOfModels`` derives sources from the union of its child
        # models. ``getattr`` keeps us safe if a future demucs release
        # drops the attribute.
        self._sources = list(getattr(self._model, "sources", []))
        LOG.info(
            "Demucs: model=%s device=%s bundled=%s native=%s sources=%s",
            self.model_name, self._resolved_device,
            bundled_repo_path, _native_demucs_cache_dir(), self._sources,
        )

    def describe(self) -> str:
        """One-line summary used by logs + GUI status badge."""
        if not self.enabled:
            return "demucs=off(lib)"
        if self._resolved_device:
            return f"demucs=on(model={self.model_name},device={self._resolved_device})"
        return f"demucs=on(model={self.model_name},device={self.device_pref}(unresolved))"

    def isolate_vocals(
        self,
        audio_path: Path,
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> "Optional[np.ndarray]":
        """Return vocals as ``np.ndarray[float32]`` at 16 kHz mono.

        Returns ``None`` (with a logged reason) for: missing dependency,
        model load failure, audio decode failure, separation failure, or
        cancellation. The caller is expected to fall back to the
        unmodified audio path.

        Demucs 4.x flow
        ---------------
        1. :func:`demucs.audio.AudioFile.from_file` decodes the source
           audio to a numpy ``(channels, samples)`` float buffer at the
           model's ``samplerate`` (44.1 kHz for ``htdemucs``).
        2. We wrap it as a torch tensor and call
           :func:`demucs.apply.apply_model`, which returns a tensor of
           shape ``(1, n_sources, channels, samples)``.
        3. We slice ``[0, vocals_idx]`` for the ``vocals`` source,
           collapse to mono, then resample to 16 kHz for the Whisper
           stage.
        """
        if not self.enabled:
            return None
        try:
            self._ensure_separator()
        except Exception as exc:
            LOG.warning("Demucs: model load failed (%s); using raw audio", exc)
            return None

        # Local torch import: demucs 4.x is built on torch, but we keep
        # it lazy so the `--help` and bare-GUI-paint paths do not pay
        # the torch import cost when demucs is disabled.
        try:
            import torch
        except ImportError as exc:  # pragma: no cover - demucs itself pulls torch in
            LOG.warning("Demucs: torch not importable (%s); using raw audio", exc)
            return None

        # 1. Decode to a numpy buffer at the model's native sample rate.
        try:
            from demucs.audio import AudioFile as _AF
            # ``from_file`` exists in some early 4.0 prereleases; 4.0.1
            # only exposes the constructor.  We keep the AttributeError
            # fallback so we don't break bleeding-edge builders that
            # happen to ship the prerelease shape again.
            try:
                af = _AF.from_file(str(audio_path))
            except AttributeError:
                af = _AF(Path(str(audio_path)))
            # ``self._model.samplerate`` is an int on demucs 4.0.1's
            # ``HTDemucs``/``BagOfModels``, but we got bitten by the same
            # ``int(callable)`` failure just above (``af.channels``); if
            # a future demucs release ships it as a no-arg method, fall
            # back to calling it before ``int()`` instead of crashing.
            sr_v = getattr(self._model, "samplerate", DEMUCS_SR)
            if callable(sr_v):
                sr_v = sr_v()
            model_sr = int(sr_v)
            # ``streams=0`` selects the first audio track in the
            # container (the only one for FLAC / MP3 / OGG).  Do NOT
            # query ``af.channels`` here -- in demucs 4.0.1 it is a
            # bound method that ``int()`` rejects ("int() ... not
            # 'method'"), and even when called it can disagree with
            # the actual stream count of mono FLAC files (which then
            # yields ``streams=[0, 1] -> IndexError: index 1 is out of
            # bounds`` in ``af.read``).
            wave = af.read(streams=0, samplerate=model_sr)
            mix = torch.from_numpy(
                np.asarray(wave, dtype=np.float32)
            ).to(self._resolved_device)
        except Exception as exc:
            LOG.warning("Demucs: audio decode failed (%s); using raw audio", exc)
            return None

        if stop_event is not None and stop_event.is_set():
            LOG.warning("Demucs: cancelled before inference; using raw audio")
            return None

        # 2. Run separation. ``apply_model`` expects a batched tensor
        #    ``(batch, channels, samples)``; ``mix`` is already
        #    ``(channels, samples)``, so add a leading batch axis here.
        try:
            from demucs.apply import apply_model
            with torch.no_grad():
                sources = apply_model(
                    self._model,
                    mix.unsqueeze(0),
                    shifts=1,
                    split=True,
                    overlap=0.25,
                    progress=False,
                    device=self._resolved_device,
                    num_workers=0,
                )
        except Exception as exc:
            LOG.warning("Demucs: separation failed (%s); using raw audio", exc)
            return None

        if stop_event is not None and stop_event.is_set():
            LOG.warning("Demucs: cancelled after separation; using raw audio")
            return None

        if self._sources is None or "vocals" not in self._sources:
            LOG.warning("Demucs: 'vocals' source missing; using raw audio")
            return None

        # 3. Extract the vocals source. ``sources`` is shape
        #    ``(1, n_sources, channels, samples)``; ``sources[0, vocals_idx]``
        #    is ``(channels, samples)`` on the model's device.
        try:
            vocals_idx = self._sources.index("vocals")
            vocals = sources[0, vocals_idx]
        except (ValueError, IndexError) as exc:
            LOG.warning("Demucs: 'vocals' index failed (%s); using raw audio", exc)
            return None

        if hasattr(vocals, "detach"):
            vocals = vocals.detach().cpu().numpy()
        elif hasattr(vocals, "cpu"):
            vocals = vocals.cpu().numpy()
        vocals = np.asarray(vocals, dtype=np.float32)
        if vocals.ndim >= 2:
            # ``htdemucs`` emits stereo (n_sources x stereo); collapse
            # any axis > 0 (channel, time) into a single mono time-series.
            vocals = vocals.mean(axis=tuple(range(vocals.ndim - 1)))
        if vocals.size == 0:
            LOG.warning("Demucs: empty vocal buffer; using raw audio")
            return None

        vocals_16k = self._resample(vocals, model_sr, WHISPER_SR)
        if vocals_16k.size == 0:
            LOG.warning("Demucs: resampled vocals are empty; using raw audio")
            return None
        return vocals_16k

    @staticmethod
    def _resample(
        audio_np: "np.ndarray", orig_sr: int, target_sr: int
    ) -> "np.ndarray":
        """Resample a 1-D float32 array from ``orig_sr`` to ``target_sr``.

        Order of preference:
          1. ``torchaudio.functional.resample`` — exact, GPU-aware, ships
             transitively with demucs.
          2. ``scipy.signal.resample_poly``    — exact rational ratio.
          3. ``numpy.interp``                 — last-resort linear; quality
             is poor on long stretches, but it never raises.
        """
        # 1. torchaudio (preferred — maintains stereo/array semantics).
        try:
            import torch  # noqa: F401  - presence probe so an ImportError falls through
            import torchaudio.functional as F  # type: ignore
            t = torch.from_numpy(audio_np).unsqueeze(0)
            out = F.resample(t, orig_sr, target_sr)
            return out.squeeze(0).numpy().astype(np.float32, copy=False)
        except Exception:
            pass

        # 2. scipy — exact polyphase resampling.
        try:
            from scipy.signal import resample_poly
            g = math.gcd(orig_sr, target_sr)
            return resample_poly(
                audio_np, up=target_sr // g, down=orig_sr // g
            ).astype(np.float32, copy=False)
        except Exception:
            pass

        # 3. numpy linear interpolation (rarely exercised; demucs pulls
        #    torchaudio in v4.x so this is a sheer safety net).
        ratio = target_sr / orig_sr
        n = int(audio_np.shape[0] * ratio)
        if n <= 1:
            return audio_np.copy()
        xp = np.linspace(0.0, audio_np.shape[0] - 1, n)
        return np.interp(
            xp, np.arange(audio_np.shape[0]), audio_np
        ).astype(np.float32, copy=False)


# -----------------------------------------------------------------------
# faster-whisper implementation
# -----------------------------------------------------------------------


class FasterWhisperAnalyzer(AudioAnalyzer):
    """Local transcription via the optional ``faster-whisper`` package.

    Optional **vocal isolation** via :class:`DemucsIsolator` runs **after**
    the cheap VAD pre-flight (so instrumentals short-circuit) and **before**
    Whisper (so heavy mixes get cleaner input). Demucs failures fall through
    silently to the raw audio path.
    """

    name = "whisper"

    def __init__(
        self,
        *,
        model_size: str = "base",
        model_path: Optional[Path] = None,
        device: str = "auto",
        compute_type: Optional[str] = None,
        language: Optional[str] = None,
        enable_demucs: bool = True,
        demucs_device: Optional[str] = None,
        demucs_model: str = DemucsIsolator.DEFAULT_MODEL,
        demucs_repo: Optional[Path] = None,
    ) -> None:
        if model_size not in SUPPORTED_MODELS and model_path is None:
            LOG.warning(
                "Unknown model size %r; expected one of %s",
                model_size, SUPPORTED_MODELS,
            )
        self.model_size = model_size
        self.model_path = model_path
        self._resolved_path = _resolve_model_path(model_size, model_path)
        self.device_pref = device
        self.compute_type_pref = compute_type
        self.language = language
        self._model = None  # lazy init on first .get() call
        # Filled in by _ensure_model() so .describe() always reports the
        # actual chosen device even after auto-detection.
        self._resolved_device: Optional[str] = None
        self._resolved_compute: Optional[str] = None

        # Demucs pre-stage (created eagerly, model loads lazily).
        self._demucs_enabled = enable_demucs
        self._demucs: Optional[DemucsIsolator]
        if enable_demucs:
            self._demucs = DemucsIsolator(
                device=demucs_device if demucs_device is not None else device,
                model=demucs_model,
                repo=demucs_repo,
            )
        else:
            self._demucs = None

    @property
    def enabled(self) -> bool:
        return _FASTER_WHISPER_AVAILABLE

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        if not _FASTER_WHISPER_AVAILABLE or WhisperModel is None:
            raise RuntimeError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            )
        self._resolved_device = resolve_device(self.device_pref)
        if self._resolved_path is not None:
            model_id_or_path = str(self._resolved_path)
            local_files_only = True
        else:
            model_id_or_path = self.model_size
            local_files_only = False
            # Pre-flight warning so the user knows they're about to
            # pull weights down from HuggingFace.  Skipped when the
            # caller supplied ``--audio-model-path`` (or a bundled
            # ``models/whisper-base`` exists) -- in that branch
            # ``local_files_only`` is True and no network call happens.
            _mb = _WHISPER_DOWNLOAD_HINTS_MB.get(self.model_size)
            if _mb is not None:
                LOG.warning(
                    "Whisper: downloading model='%s' from HuggingFace "
                    "(~%d MB, approximate) on first use; subsequent runs "
                    "use the cached weights. Pass --audio-model-path to "
                    "point at an already-downloaded directory and skip "
                    "this download.",
                    self.model_size, _mb,
                )
            else:
                LOG.warning(
                    "Whisper: downloading model='%s' from HuggingFace on "
                    "first use; pass --audio-model-path to skip this "
                    "download.",
                    self.model_size,
                )

        # First pick honours any user-pinned ``compute_type`` (``compute_type=...``
        # in FasterWhisperAnalyzer.__init__).  Failing that, we ask
        # :func:`compute_type_for` which already consults CTranslate2's
        # advertised supported set.
        user_pinned = self.compute_type_pref is not None
        primary_ct = self.compute_type_pref or compute_type_for(self._resolved_device)

        # Build a defensive fallback ladder *only* when the user did not pin a
        # compute type.  CTranslate2 advertises "float16" as supported on
        # Pascal/sm_61 from the probe but still raises "do not support
        # efficient float16 computation" at load time on that arch, so an
        # explicit try-then-downgrade path is the cheapest insurance.
        attempts: list[str] = [primary_ct]
        if not user_pinned and self._resolved_device.startswith("cuda"):
            supported = supported_cuda_compute_types(device_index=0) or frozenset()
            ladder_supported = [
                ct for ct in CUDA_COMPUTE_PREFERENCE
                if ct in supported and ct != primary_ct
            ]
            attempts.extend(ladder_supported)

        last_exc: Optional[Exception] = None
        for ct in attempts:
            kwargs: dict = {
                "device": self._resolved_device,
                "compute_type": ct,
            }
            if local_files_only:
                kwargs["local_files_only"] = True
            try:
                self._model = WhisperModel(model_id_or_path, **kwargs)
            except Exception as exc:
                last_exc = exc
                if ct == attempts[-1]:
                    LOG.warning(
                        "Whisper: load failed for all candidate compute types "
                        "(last attempt was %s: %s)",
                        ct, exc,
                    )
                else:
                    LOG.debug(
                        "Whisper: load with compute_type=%s failed (%s); "
                        "trying next fallback",
                        ct, exc,
                    )
                continue

            # Success: publish the chosen compute type and log with severity
            # that reflects whether the user pinned it, we picked it, or we
            # had to downgrade at load time.
            self._resolved_compute = ct
            if user_pinned:
                LOG.info(
                    "Whisper: loading model=%s device=%s compute_type=%s "
                    "(user-pinned)",
                    model_id_or_path, self._resolved_device, ct,
                )
            elif ct == primary_ct:
                cap = cuda_compute_capability(0)
                cap_str = f"sm_{cap[0]}{cap[1]}" if cap else "sm_?"
                LOG.info(
                    "Whisper: loading model=%s device=%s compute_type=%s (%s)",
                    model_id_or_path, self._resolved_device, ct, cap_str,
                )
            else:
                cap = cuda_compute_capability(0)
                cap_str = f"sm_{cap[0]}{cap[1]}" if cap else "sm_?"
                LOG.warning(
                    "Whisper: %s not usable on %s (%s); fell back to "
                    "compute_type=%s after %s rejected the load",
                    primary_ct, self._resolved_device, cap_str, ct, primary_ct,
                )
            return

        # All attempts failed; surface the last exception so
        # :meth:`get` formats it into a clean ``LyricsFailure``.
        assert last_exc is not None  # noqa: S101 - attempts is never empty
        raise last_exc

    def _transcribe_and_collect(
        self,
        audio_input,
        *,
        vad_filter: bool,
        stop_event: Optional[threading.Event],
    ) -> tuple[list["AnalyzerSegment"], bool, object]:
        """Run ``self._model.transcribe`` once and collect usable segments.

        Centralises the per-segment coercion so :meth:`get` can fall back
        to a VAD-disabled pass without duplicating the loop.  Returns
        ``(collected, cancelled, info)``: ``cancelled`` is True when the
        user pressed Stop mid-segment (caller turns that into a
        :class:`LyricsFailure`), and ``info`` is faster-whisper's
        :class:`TranscriptionInfo` payload (carries ``duration``/
        ``language`` for diagnostics).
        """
        segments_iter, info = self._model.transcribe(
            audio_input,
            language=self.language,
            vad_filter=vad_filter,
            condition_on_previous_text=False,
        )
        collected: list[AnalyzerSegment] = []
        cancelled = False
        for raw in segments_iter:
            if stop_event is not None and stop_event.is_set():
                cancelled = True
                LOG.warning(
                    "Transcription cancelled mid-song (%d/%d).",
                    len(collected),
                    getattr(info, "duration", -1) or -1,
                )
                break
            seg = AnalyzerSegment(
                start=float(getattr(raw, "start", 0.0) or 0.0),
                end=float(getattr(raw, "end", 0.0) or 0.0),
                text=(getattr(raw, "text", "") or "").strip(),
                no_speech_prob=float(getattr(raw, "no_speech_prob", 0.0) or 0.0),
                avg_logprob=float(getattr(raw, "avg_logprob", 0.0) or 0.0),
            )
            if _segment_ok(seg):
                collected.append(seg)
        return collected, cancelled, info

    def describe(self) -> str:
        """One-line summary for logs + the GUI status badge."""
        parts: list[str] = []
        # ``name`` keeps long paths short for the GUI badge.
        if self._resolved_path is not None:
            parts.append(f"model={self._resolved_path.name}")
        else:
            parts.append(f"model={self.model_size}")
        if self._resolved_device is not None:
            parts.append(f"device={self._resolved_device}")
            gpu = gpu_name()
            if gpu:
                parts.append(f"gpu={gpu}")
            parts.append(f"compute={self._resolved_compute}")
        else:
            parts.append(f"device={self.device_pref}(unresolved)")
            parts.append(
                f"compute={self.compute_type_pref or compute_type_for(self.device_pref)}"
            )
        if self._demucs is not None:
            parts.append(f"demucs={'on' if self._demucs.enabled else 'off(lib)'}")
        return ", ".join(parts)

    def get(
        self,
        audio: AudioFile,
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> LyricsResult | LyricsFailure:
        if not self.enabled:
            return LyricsFailure(self.name, missing_audio_hint("faster-whisper"))

        # 1. Cheap pre-flight: detect pure-silence or no-vocals so we never
        #    pay the cost of loading + running Demucs / Whisper on an
        #    instrumental track.  Falls through when the answer is "maybe".
        preflight = _detect_instrumental_preflight(audio)
        if preflight is not None:
            return preflight

        # 2. Demucs pre-stage (AFTER pre-flight, BEFORE Whisper).  Vocal
        #    isolation improves LRC quality on dense mixes; failures fall
        #    back to whisper-on-raw-mix so the pipeline never aborts.
        vocals_for_whisper: "Optional[np.ndarray]" = None
        if self._demucs is not None and self._demucs.enabled:
            try:
                vocals_for_whisper = self._demucs.isolate_vocals(
                    audio.path, stop_event=stop_event,
                )
            except Exception as exc:  # defensive: no failure should kill the song
                LOG.warning("Demucs: unexpected error (%s); using raw audio", exc)
                vocals_for_whisper = None

        if stop_event is not None and stop_event.is_set():
            return LyricsFailure(self.name, "cancelled by user")

        # 3. Whisper transcription on either vocals or raw audio.
        try:
            self._ensure_model()
        except Exception as exc:  # pragma: no cover - lazy init path
            return LyricsFailure(self.name, f"model load failed: {exc}")

        # Pick the input stream up-front so the auto-retry below can
        # re-issue ``transcribe`` without duplicating the if/else.
        if vocals_for_whisper is not None:
            # ``vocals_for_whisper`` is already 16 kHz mono float32.
            audio_input = vocals_for_whisper
            source_tag = "demucs"
        else:
            audio_input = str(audio.path)
            source_tag = "raw"

        collected: list[AnalyzerSegment] = []
        cancelled = False
        try:
            collected, cancelled, info = self._transcribe_and_collect(
                audio_input, vad_filter=True, stop_event=stop_event,
            )

            # Self-healing fallback: faster-whisper's bundled Silero VAD
            # (``vad_filter=True``) can be over-aggressive on tracks with
            # sparse or quietly-mixed vocals -- it strips everything as
            # silence and yields 0 segments even when the listener can
            # hear lyrics clearly.  Try once more with VAD bypassed.
            # Tracks that still produce 0 segments a second time are
            # genuinely unsalvageable on the current model/compute combo.
            if not collected and not cancelled:
                LOG.info(
                    "First pass produced 0 segments for %s (internal "
                    "VAD likely too aggressive); retrying without VAD.",
                    audio.path.name,
                )
                _collected, _cancelled, _info = self._transcribe_and_collect(
                    audio_input, vad_filter=False, stop_event=stop_event,
                )
                # ``info`` from the no-VAD pass carries the same
                # ``duration`` / ``language`` we used for diagnostics
                # above (faster-whisper sets them at decode time, not
                # during VAD filtering), so binding them here keeps the
                # ``raw_extras`` dict consistent across passes.
                collected = _collected
                cancelled = _cancelled
                info = _info

            if cancelled:
                return LyricsFailure(self.name, "cancelled by user")

            if not collected:
                return LyricsFailure(
                    self.name,
                    "transcription produced no usable segments "
                    "(likely instrumental or all-flagged as hallucination)",
                )

            synced = [
                (format_timestamp_ms(int(round(s.start * 1000))), s.text)
                for s in collected
            ]
            return LyricsResult(
                provider=self.name,
                title=audio.title,
                artist=audio.artist,
                album=audio.album,
                length_seconds=audio.duration,
                synced_lines=synced,
                plain_text="",
                raw_extras={
                    "language": getattr(info, "language", None),
                    "duration": getattr(info, "duration", None),
                    "segments_kept": len(collected),
                    "model": str(self._resolved_path or self.model_size),
                    "vocal_isolation": source_tag,
                    "device": self._resolved_device,
                    "compute_type": self._resolved_compute,
                },
            )
        except Exception as exc:  # network/read/decode errors
            LOG.exception("Whisper transcription failed")
            return LyricsFailure(self.name, f"transcription error: {exc}")


# -----------------------------------------------------------------------
# Fake / mock analyzer for tests
# -----------------------------------------------------------------------


class FakeAnalyzer(AudioAnalyzer):
    """Returns a canned response -- used in unit tests."""

    name = "fake"

    def __init__(self, canned: LyricsResult | LyricsFailure) -> None:
        self.canned = canned
        self.calls: list[str] = []

    @property
    def enabled(self) -> bool:
        return True

    def get(
        self,
        audio: AudioFile,
        *,
        stop_event: Optional[threading.Event] = None,
    ) -> LyricsResult | LyricsFailure:
        self.calls.append(audio.path.name)
        return self.canned


def describe_models_layout(
    *,
    audio_model: str = "base",
    audio_model_path: Optional[Path] = None,
) -> tuple[Optional[Path], Path]:
    """Return ``(whisper_repo_or_none, demucs_repo)`` so callers can announce the path layout.

    ``whisper_repo_or_none`` is ``None`` when neither a user-supplied
    ``--audio-model-path`` nor a bundled ``models/whisper-base`` exists --
    in that branch faster-whisper falls back to the HuggingFace cache the
    first time it sees the model id.

    ``demucs_repo`` is always concrete (it defaults to
    ``models/demucs/`` next to the script even when empty), but
    demucs's :class:`LocalRepo` only honours it when ``models/demucs/``
    already contains ``.th`` files (otherwise it falls back to the
    native torch hub cache at ``~/.cache/torch/hub/checkpoints``).
    """
    return _resolve_model_path(audio_model, audio_model_path), _resolve_demucs_repo()


__all__: Iterable[str] = (
    "AnalyzerSegment",
    "AudioAnalyzer",
    "DEMUCS_SR",
    "DemucsIsolator",
    "FakeAnalyzer",
    "FasterWhisperAnalyzer",
    "SUPPORTED_MODELS",
    "WHISPER_SR",
    "describe_models_layout",
    "missing_audio_hint",
    "planned_first_run_download",
    "warn_first_run_aggregate",
)
