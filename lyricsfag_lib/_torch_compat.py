"""Shared PyTorch 2.6 / demucs 4.0.1 ``weights_only`` compatibility shim.

Why this module exists
----------------------
PyTorch 2.6 changed :func:`torch.load`\'s default ``weights_only`` argument
from ``False`` to ``True``.  demucs 4.0.1 pickles its ``HTDemucs`` /
``BagOfModels`` weights with several class references
(``demucs.htdemucs.HTDemucs``, ``fractions.Fraction``, and more as the
unpickler walks deeper into the state dict).  Each missing class surfaces
as ``WeightsUnpickler error: Unsupported global: GLOBAL ...`` and the
documented workaround is ``torch.serialization.add_safe_globals([...])``
per class -- but the list grows as the unpickler walks, so you can\'t
predict the full set without iterating.

The pragmatic fix is to disable ``weights_only`` for ``.th`` files
*specifically* -- safe because we only ever load files we (or demucs\'s
own ``RemoteRepo``) just downloaded from ``facebookresearch/demucs``.
The ``.th``-only filter keeps the safe PyTorch 2.6 default for any other
``torch.load`` caller in the process (e.g. faster-whisper\'s Silero VAD,
which loads ``*.pt`` files we don\'t want to weaken the policy for).

This module is *package-internal* (leading underscore on the filename)
because:

  * the only legitimate consumers are the runtime library
    (:mod:`lyricsfag_lib.audio_analysis`) and the seeding script
    (:mod:`scripts.download_demucs_model`);
  * the function applies a *process-wide* monkey-patch and we want to
    keep that scope of effect under one explicit, auditable call site.

Public surface
--------------
The only export is :func:`ensure_torch_load_patched`.  The implementation
is:

  * **Lazy** -- ``import torch`` is paid on first call, not on module
    import (saves the ~3 s torch import cost for users who never enable
    the audio-analysis fallback).
  * **Idempotent** -- a module-level ``_torch_load_patched`` flag makes
    repeat calls a cheap no-op.
  * **Robust** -- inspects every positional AND keyword argument for a
    path-like that ends in ``.th`` (via :func:`os.path.splitext`), so
    it works regardless of which kwarg name demucs uses
    (``torch.load(path, 'cpu')`` vs ``torch.load(f=path, ...)`` vs
    ``torch.load(map_location='cpu', f=path)``).
  * **Auditable** -- emits a one-line INFO log on first application so
    the user can confirm the workaround is active.  Callers running in
    a CLI context (no logging configured) can additionally request an
    unconditional ``stderr`` echo via ``echo_to_stderr=True``.
"""

from __future__ import annotations

import logging

LOG = logging.getLogger(__name__)

# Process-global latch: set to ``True`` the first time
# :func:`ensure_torch_load_patched` actually patches ``torch.load``.
# Module-level so all callers see the same state (the function is
# intentionally process-wide -- patching the real ``torch.load`` is
# the whole point, and re-patching a second time would just re-wrap
# the already-wrapped function).
_torch_load_patched: bool = False


def _is_th_path(arg: object) -> bool:
    """Return ``True`` iff ``arg`` is a ``str``/``PathLike`` ending in ``.th``.

    Centralised here so the heuristic is identical across every caller
    and any future tightening (e.g. requiring an absolute path) happens
    in one place.  Uses :func:`os.path.splitext` rather than
    ``str.endswith(".th")`` so a hypothetical future caller passing
    ``".TH"`` or ``"foo.th.bak"`` gets the same answer it would from
    pathlib\'s suffix-based API.
    """
    import os
    if not isinstance(arg, (str, os.PathLike)):
        return False
    return os.path.splitext(os.fspath(arg))[1] == ".th"


def ensure_torch_load_patched(*, echo_to_stderr: bool = False) -> None:
    """Apply the ``.th``-scoped :func:`torch.load` monkey-patch on first use.

    No-op on subsequent calls.  The wrapper inspects every positional
    AND keyword argument for a path-like that ends in ``.th`` and, on a
    match, forwards ``weights_only=False`` to the original
    :func:`torch.load`.  This is robust to demucs calling with the path
    as ``torch.load(path, 'cpu')``, ``torch.load(f=path, ...)``,
    ``torch.load(map_location='cpu', f=path)``, or any other signature
    permutation -- we don\'t depend on the path being ``args[0]`` or any
    specific kwarg name.

    Parameters
    ----------
    echo_to_stderr:
        When ``True``, also print the confirmation line to ``sys.stderr``
        unconditionally.  The :mod:`scripts.download_demucs_model` CLI
        uses this so the line is visible without any logging
        configuration.  Library callers (:mod:`lyricsfag_lib.audio_analysis`)
        leave it ``False`` and rely on the standard logging pipeline.
    """
    global _torch_load_patched
    if _torch_load_patched:
        return
    import torch

    _orig_torch_load = torch.load

    def _demucs_torch_load(*args, **kwargs):
        # Only force ``weights_only=False`` when the caller didn\'t
        # already pin an explicit value -- if a future demucs release
        # or a deliberate test wants the strict-unpickler behaviour,
        # honour that and don\'t second-guess.
        if "weights_only" not in kwargs:
            for _arg in (*args, *kwargs.values()):
                if _is_th_path(_arg):
                    kwargs["weights_only"] = False
                    break
        return _orig_torch_load(*args, **kwargs)

    torch.load = _demucs_torch_load
    _torch_load_patched = True

    message = (
        "torch.load monkey-patch active for .th files "
        "(PyTorch 2.6 weights_only workaround for demucs 4.0.1)"
    )
    LOG.info(message)
    if echo_to_stderr:
        import sys
        print(message, file=sys.stderr)


__all__ = ("ensure_torch_load_patched",)
