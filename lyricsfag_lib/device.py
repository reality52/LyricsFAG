"""Capability detection for CUDA + opt-in heavyweight deps (demucs).

Why this module exists
----------------------
* ``import torch`` blocks for ~3 s; we never want that on the ``--help`` path or
  for the very first Tk paint.  Every check in this module therefore imports
  its dependency **inside** the function, caches the result in a module-level
  singleton, and reuses it for the next call.
* ``faster-whisper`` ships its own CUDA probe via CTranslate2. ``demucs`` (used
  as an optional vocal isolation stage) needs ``torch``. We probe through
  ``torch.cuda.is_available()`` because that catches the same devices
  CTranslate2 would, and it also gives us the GPU model name (which
  CTranslate2 doesn't expose).
* Failure modes are deliberately tolerant: every public function swallows
  ``ImportError`` / ``RuntimeError`` and returns a safe default so callers
  don't need to wrap their own try/except.

Public surface
--------------
* :func:`resolve_device` — map ``"auto"`` → ``"cuda"`` or ``"cpu"`` (cached).
* :func:`cuda_available` — boolean raw probe.
* :func:`compute_type_for` — pick ``"float16"`` (CUDA) or ``"int8"`` (CPU).
* :func:`gpu_name`         — human-readable GPU model string, or ``None``.
* :func:`is_demucs_available`  — whether the demucs 4.x API surface is importable.
* :func:`device_snapshot`  — bundle the above for one GUI/SVG-style readout.
* :func:`format_device_badge` — render the snapshot as a short label string.
"""

from __future__ import annotations

import logging
from typing import Optional

LOG = logging.getLogger(__name__)

# Lazy singletons populated on first use.  ``None``  = "not probed yet",
# ``False`` = "probe was attempted and failed (ImportError)" /
#             "library confirmed missing".
_TORCH = None
_CTRANSLATE2 = None
_DEMUCS_IMPORTABLE = None
_CACHED_DEVICE: Optional[str] = None
_CACHED_GPU_NAME: Optional[str] = None
_CACHED_CUDA_CAPABILITY: Optional[tuple[int, int]] = None
_CACHED_SUPPORTED_CUDA_COMPUTE_TYPES: Optional[frozenset[str]] = None

# Preference ladder used to pick a CUDA ``compute_type`` from CTranslate2's
# advertised supported set.  Ordered fastest/most-quantised -> most-stable.
# ``int8_float32`` (8-bit weights, fp32 activations) sits between pure fp16
# and pure int8 because it sidesteps the lack of efficient fp16 compute on
# Pascal/sm_61 while keeping activations numerically safe.
#
# Re-exported under the public name ``CUDA_COMPUTE_PREFERENCE`` (see
# ``__all__``) so the runtime retry ladder in
# :class:`lyricsfag_lib.audio_analysis.FasterWhisperAnalyzer` shares the
# same ordering — no risk of accidental drift between picker and re-try.
CUDA_COMPUTE_PREFERENCE: tuple[str, ...] = (
    "float16",
    "int8_float32",
    "int8",
    "float32",
)
# Internal alias referenced by ``compute_type_for`` to keep the call site
# short.  Keeping both names preserves the original (private) usage while
# publishing the constant for cross-module consumers.
_CUDA_COMPUTE_PREFERENCE = CUDA_COMPUTE_PREFERENCE
# Conservative default used when the probe itself fails (e.g. ctranslate2
# not importable, which means faster-whisper literally cannot load). Kept
# to match historical behaviour so long-time users see the same first try.
_CUDA_COMPUTE_FALLBACK_DEFAULT = "float16"


# ---------------------------------------------------------------------------
# Torch + CUDA
# ---------------------------------------------------------------------------


def _ensure_torch():
    """Import :mod:`torch` on first use.

    Returns the torch module on success, or ``False`` when ``ImportError``
    fires (so we don't waste repeated 3 s waits).  The variable is
    deliberately *not* re-checked after the first call: if torch import
    works now it will keep working; if it failed it will keep failing
    with the same lib not on ``sys.path``.
    """
    global _TORCH
    if _TORCH is None:
        try:
            import torch  # type: ignore
            _TORCH = torch
        except ImportError:
            _TORCH = False
    return _TORCH


def cuda_available() -> bool:
    """``True`` iff at least one CUDA device is reachable from this process.

    Falls back to ``False`` when torch is uninstalled or when the driver
    probe raises (very rare, but seen on broken WSL/CUDA pairings).
    """
    torch = _ensure_torch()
    if not torch:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception as exc:  # pragma: no cover - GPU bring-up glitches
        LOG.debug("torch.cuda.is_available() raised: %s", exc)
        return False


def reset_device_cache() -> None:
    """Test/diagnostic helper: clear all cached device / capability probes.

    The next call to :func:`resolve_device`, :func:`gpu_name`,
    :func:`cuda_compute_capability` or :func:`supported_cuda_compute_types`
    re-probes; useful when a test stubs ``torch.cuda.is_available`` (or
    monkey-patches ctranslate2) *after* the first read.
    """
    global _CACHED_DEVICE, _CACHED_GPU_NAME, _CACHED_CUDA_CAPABILITY
    global _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES
    _CACHED_DEVICE = None
    _CACHED_GPU_NAME = None
    _CACHED_CUDA_CAPABILITY = None
    _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES = None


def resolve_device(preference: str = "auto") -> str:
    """Resolve the user's device preference to ``"cuda"`` or ``"cpu"``.

    ``"auto"`` (default) probes CUDA exactly once and caches the answer.
    Any other value (e.g. an explicit ``"cuda:1"``) is returned verbatim,
    so power users can still pin a specific device through the CLI.
    """
    global _CACHED_DEVICE
    if preference == "auto":
        if _CACHED_DEVICE is None:
            _CACHED_DEVICE = "cuda" if cuda_available() else "cpu"
        return _CACHED_DEVICE
    return preference


def compute_type_for(device: str) -> str:
    """Map a device to faster-whisper's preferred ``compute_type``.

    * ``cuda``     → the first entry of :data:`_CUDA_COMPUTE_PREFERENCE`
      (default ``float16``) that :func:`supported_cuda_compute_types`
      confirms CTranslate2 advertises for this device.  Cards like the
      Pascal/mine-edition P104 (sm_61) only have ``int8``/``float32``
      available — ``float16`` raises
      ``"Requested float16 compute type, but the target device or backend
      do not support efficient float16 computation."`` so we skip it and
      land on ``int8_float32``/``int8``/``float32``.  Ampere+ and Turing
      still pick ``float16`` exactly as before.
    * anything else → ``int8``   (CPU has no float16 path; int8 is the
      fastest setting on x86 / Apple Silicon).
    """
    if device.startswith("cuda"):
        supported = supported_cuda_compute_types(device_index=0)
        if supported:
            for cand in _CUDA_COMPUTE_PREFERENCE:
                if cand in supported:
                    return cand
            # CTranslate2 at minimum lists int8 on every CUDA arch; this
            # is a safety net for future compute types appearing in the
            # advertised set that we don't list explicitly above.
            if supported:
                return next(iter(supported))
        return _CUDA_COMPUTE_FALLBACK_DEFAULT
    return "int8"


def _ensure_ctranslate2():
    """Lazy-import :mod:`ctranslate2` for compute-type capability queries.

    Returns the ctranslate2 module on success, ``False`` on ImportError.
    The probe is best-effort: when it fails we fall back to the historical
    ``"cuda" -> "float16"`` rule so old call sites still see the same
    behaviour they did before the probe was added.
    """
    global _CTRANSLATE2
    if _CTRANSLATE2 is None:
        try:
            import ctranslate2  # type: ignore
            _CTRANSLATE2 = ctranslate2
        except ImportError:
            _CTRANSLATE2 = False
    return _CTRANSLATE2


def cuda_compute_capability(device_index: int = 0) -> Optional[tuple[int, int]]:
    """``(major, minor)`` CUDA compute capability of ``device_index``, or ``None``.

    Cached after the first successful probe so repeated device-snapshot
    calls (the GUI paints the badge ~once per second while loading) do not
    re-issue the ``cudaGetDeviceAttribute`` round-trip.
    """
    global _CACHED_CUDA_CAPABILITY
    if _CACHED_CUDA_CAPABILITY is not None:
        return _CACHED_CUDA_CAPABILITY
    torch = _ensure_torch()
    if not torch or not cuda_available():
        return None
    try:
        major, minor = torch.cuda.get_device_capability(device_index)
    except Exception as exc:  # pragma: no cover - GPU bring-up glitches
        LOG.debug("torch.cuda.get_device_capability(%d) raised: %s", device_index, exc)
        return None
    _CACHED_CUDA_CAPABILITY = (int(major), int(minor))
    return _CACHED_CUDA_CAPABILITY


def supported_cuda_compute_types(
    device_index: int = 0,
) -> Optional[frozenset[str]]:
    """The set of CUDA compute types CTranslate2 *advertises* for this device.

    Returns ``None`` when ctranslate2 is not importable or the probe fails;
    callers (notably :func:`compute_type_for`) fall back to the historical
    default in that case so behaviour is unchanged pre/post this fix.

    Authoritative source: ``ctranslate2.get_supported_compute_types('cuda',
    device_index=device_index)``.  Examples seen in the wild:

    * Pascal (sm_61, NVIDIA P104 etc.): ``{'float32', 'float16', 'int8',
      'int8_float32'}`` — but ``float16`` raises the "not efficient" error
      at *load* time on this arch, hence the probe at *pick* time.
    * Ampere (sm_80+) / Turing (sm_75) / Volta (sm_70): ``float16`` is in
      the set AND actually fast, so we pick it.
    """
    global _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES
    if _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES is not None:
        return _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES
    if not cuda_available():
        return None
    ct = _ensure_ctranslate2()
    if not ct:
        return None
    try:
        types = ct.get_supported_compute_types("cuda", device_index=device_index)
    except Exception as exc:  # pragma: no cover - driver/probe mismatch
        LOG.debug(
            "ctranslate2.get_supported_compute_types('cuda', %d) failed: %s",
            device_index, exc,
        )
        return None
    _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES = frozenset(types or ())
    return _CACHED_SUPPORTED_CUDA_COMPUTE_TYPES


def gpu_name() -> Optional[str]:
    """Human-readable GPU model (e.g. ``NVIDIA GeForce RTX 3060``), or ``None``."""
    global _CACHED_GPU_NAME
    if _CACHED_GPU_NAME is not None:
        return _CACHED_GPU_NAME
    torch = _ensure_torch()
    if not torch or not cuda_available():
        return None
    try:
        _CACHED_GPU_NAME = str(torch.cuda.get_device_name(0))
    except Exception:
        _CACHED_GPU_NAME = None
    return _CACHED_GPU_NAME


# ---------------------------------------------------------------------------
# Demucs presence + bundle helpers
# ---------------------------------------------------------------------------


def is_demucs_available() -> bool:
    """Whether the demucs 4.x API surface used by :class:`DemucsIsolator` is importable.

    The minimum required surface is
    :func:`demucs.pretrained.get_model` and :func:`demucs.apply.apply_model`
    (we probe both).  ``demucs.audio.AudioFile`` is also required for
    decoding, but is part of the same package: a broken install typically
    fails the entire ``import demucs.audio`` chain.

    The import is lazy so a project without demucs never blocks on
    ``import torch`` (~3 s) when the worker hasn't enabled audio analysis.

    History
    -------
    Demucs 4.0 removed :mod:`demucs.api` entirely (it used to expose
    ``Separator``).  Probing the legacy path would yield ``False`` on a
    correct 4.0.1 install even though the package is fully usable, so we
    explicitly look for the new API modules.
    """
    global _DEMUCS_IMPORTABLE
    if _DEMUCS_IMPORTABLE is None:
        try:
            from demucs.pretrained import get_model  # noqa: F401  -- presence check
            from demucs.apply import apply_model    # noqa: F401  -- presence check
            _DEMUCS_IMPORTABLE = True
        except ImportError:
            _DEMUCS_IMPORTABLE = False
    return bool(_DEMUCS_IMPORTABLE)


def device_snapshot() -> dict:
    """One-shot bundle used by the GUI status badge + CLI startup log."""
    return {
        "device": resolve_device("auto"),
        "gpu_name": gpu_name(),
        "compute_type": compute_type_for(resolve_device("auto")),
        "demucs_available": is_demucs_available(),
    }


def format_device_badge(snapshot: Optional[dict] = None) -> tuple[str, str]:
    """Render a short device label + colour hint for the GUI badge.

    Returns a ``(text, foreground_hex)`` pair.  Emojis are intentionally
    avoided: Tk on Windows has historically had trouble rendering them in
    ttk.Label, and the colour cue carries the same information anyway.

    On GPUs we append the chosen CTranslate2 ``compute_type`` (e.g.
    ``"GPU: NVIDIA P104-100 (int8)"``) so the user can see at a glance
    *why* :class:`faster_whisper.WhisperModel` would refuse a ``float16``
    request — Pascal/sm_61 cards in particular get auto-picked to ``int8``
    because CTranslate2 lists only ``int8``/``int8_float32``/``float32``
    as efficient on that arch.
    """
    if snapshot is None:
        snapshot = device_snapshot()
    dev = snapshot.get("device") or "cpu"
    if dev.startswith("cuda"):
        gpu = snapshot.get("gpu_name") or "GPU"
        ct = snapshot.get("compute_type")
        text = f"GPU: {gpu} ({ct})" if ct else f"GPU: {gpu}"
        return text, "#80ff80"  # green
    return "CPU", "#ffd76b"     # yellow


__all__ = (
    "CUDA_COMPUTE_PREFERENCE",
    "compute_type_for",
    "cuda_available",
    "cuda_compute_capability",
    "device_snapshot",
    "format_device_badge",
    "gpu_name",
    "is_demucs_available",
    "reset_device_cache",
    "resolve_device",
    "supported_cuda_compute_types",
)
