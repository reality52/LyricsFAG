#!/usr/bin/env python3
"""Download a demucs pretrained-model tree so ``models/demucs/`` becomes
loadable by :class:`demucs.pretrained.LocalRepo`.

This is the "Path B" workflow described in ``models/demucs/README.md`` and
the missing piece that turns ``models/demucs/`` from a "currently empty by
design" placeholder into a real, ready-to-bundle seed for a fully offline
``LyricsFAG-Portable.exe``.

Why this script was rewritten
-----------------------------
Demucs 4.0.1's bundled ``files.txt`` (the master listing of every weight
file demucs knows about) no longer carries model-name prefixes: every
entry is a bare ``<hash>-<hash>.<ext>`` (e.g. ``955717e8-8726e21a.th``).
The mapping from model name (``htdemucs_ft``, ``htdemucs``, ``mdx_q``,
...) to the set of weight files it needs lives in the YAML descriptors
under ``demucs.pretrained.REMOTE_ROOT`` (``htdemucs_ft.yaml`` etc.).

The previous version of this script tried to filter ``files.txt`` by
``--model htdemucs_ft`` and parse ``<sig>-<hash>.<ext>`` lines, but no
``sig`` equals a model name in 4.0.1 -- every ``sig`` is also a hash.
That meant the filter always returned zero files and the script
aborted with ``no files.txt lines matched the --model 'htdemucs_ft'
select; aborting`` (confirmed empirically on 2026-07-06).

The new flow sidesteps ``files.txt`` entirely:

  1. Call :func:`demucs.pretrained.get_model(<model_name>)` (no
     ``repo=``).  Demucs 4.x uses its native torch-hub cache
     (``~/.cache/torch/hub/checkpoints/``) and auto-downloads missing
     weights with proper hash validation; if the cache is already
     warm, this is a no-op.
  2. Read the YAML descriptor for the model from the cache (demucs
     itself copies it there alongside the weights).
  3. Parse the YAML to discover the list of ``<hash>`` sub-model
     names the model needs.
  4. Copy the YAML + the matching ``<hash>-<hash>.th`` files from
     the cache to ``models/demucs/`` in the layout
     :class:`demucs.pretrained.LocalRepo` reads directly.

``htdemucs_ft`` is a :class:`BagOfModels` of 4 sub-models, so the
seeding step copies 1 YAML + 4 ``.th`` files (~336 MB).  ``htdemucs``
is a single HTDemucs (1 YAML + 1 ``.th`` file, ~84 MB).

Usage
-----
Seed the default ``htdemucs_ft`` into ``models/demucs/`` and verify
the result in one shot::

    python scripts/download_demucs_model.py --verify

Seed the legacy ``htdemucs`` (single sub-model, ~84 MB) instead::

    python scripts/download_demucs_model.py --model htdemucs --verify

List what would be copied without actually copying::

    python scripts/download_demucs_model.py --list-only

Note: ``--list-only`` still triggers demucs's auto-download if the
cache is cold (the script needs to inspect the cache to build the
listing).  Use ``--model htdemucs`` to download only the smaller
single-file variant; the previous assumption that ``htdemucs`` was a
5-sub-model ~420 MB bag no longer holds in demucs 4.0.1 (its YAML
says ``models: ['955717e8']`` -- a single 84 MB file).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Optional

# Make the ``lyricsfag_lib`` package importable when this script is run
# directly, e.g. ``python scripts/download_demucs_model.py --verify``.
# Python only puts the *script\'s* directory (``scripts/``) on
# ``sys.path[0]``; the project root (where ``lyricsfag_lib/`` lives) is
# not on the path unless we add it explicitly.  Idempotent and free of
# effect under ``python -m scripts.download_demucs_model`` (where
# ``scripts/`` is already a package on the path) and under the PyInstaller
# bundled ``.exe`` (where PyInstaller populates the frozen module table
# ahead of ``sys.path``).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DEFAULT_OUTPUT_DIR = "models/demucs"
# ``htdemucs_ft`` is the Meta-released music-only fine-tune of
# ``htdemucs``.  LyricsFAG now defaults to it for vocal isolation
# (4-sub-model BagOfModels, ~336 MB on disk).  ``htdemucs`` itself is
# a single HTDemucs (~84 MB) and remains selectable via
# ``--model htdemucs`` for users who want the smaller footprint.
DEFAULT_MODEL = "htdemucs_ft"

# Module-level probe cache for the demucs import.  ``None`` means "not
# yet attempted"; ``True`` / ``False`` record the actual outcome.  Kept
# at module scope so the import cost is paid at most once per process.
_DEMUCS_OK: Optional[bool] = None

# ---------------------------------------------------------------------------
# PyTorch 2.6 / demucs 4.0.1 ``weights_only`` compatibility
# ---------------------------------------------------------------------------
#
# The actual monkey-patch lives in the package-internal
# :mod:`lyricsfag_lib._torch_compat` so :mod:`lyricsfag_lib.audio_analysis`
# and this script share one implementation.  We pass
# ``echo_to_stderr=True`` so the confirmation line is visible without any
# logging configuration -- a user running this CLI directly
# (``python scripts/download_demucs_model.py --verify``) should see the
# line on stderr regardless of the root logger level.
from lyricsfag_lib._torch_compat import ensure_torch_load_patched


# -----------------------------------------------------------------------------
# Demucs presence + cache helpers
# -----------------------------------------------------------------------------


def _ensure_demucs() -> bool:
    """Whether the demucs 4.x package can be imported.

    Result is cached in module-level ``_DEMUCS_OK`` so a hot path can
    short-circuit the ~3 s ``import torch`` cost demucs pulls in.
    """
    global _DEMUCS_OK
    if _DEMUCS_OK is None:
        try:
            import demucs.pretrained  # noqa: F401  - presence probe only
            _DEMUCS_OK = True
        except ImportError:
            _DEMUCS_OK = False
    return bool(_DEMUCS_OK)


def _native_demucs_cache_dir() -> Path:
    """Directory where demucs 4.x's :class:`RemoteRepo` deposits weights.

    Demucs resolves its download destination via ``torch.hub.get_dir()``,
    which on Windows resolves to
    ``%USERPROFILE%\\.cache\\torch\\hub\\checkpoints``.  We surface the
    same path here so the cache-relocation step below copies from the
    directory demucs itself just wrote to.
    """
    return Path.home() / ".cache" / "torch" / "hub" / "checkpoints"


def _ensure_model_in_cache(model_name: str) -> Path:
    """Trigger demucs's native auto-download so the model lands in the
    torch hub cache, then return the path to the YAML descriptor there.

    Demucs also copies the model's ``<name>.yaml`` descriptor into the
    cache alongside the weights; that's the file
    :class:`demucs.pretrained.LocalRepo` reads to reconstruct the model
    on a subsequent ``get_model(name, repo=output_dir)`` call.

    Edge case
    ---------
    If the ``.th`` weights are already in the cache from a prior run
    (so demucs's :class:`RemoteRepo` doesn't trigger a fresh download
    and the YAML-copy step is skipped), the ``.yaml`` might be missing
    from the cache.  In that case we fall back to the descriptor
    bundled in the installed ``demucs/remote/`` directory and copy it
    in ourselves so :class:`LocalRepo` has a uniform source-of-truth
    layout to read from on the next call.  Observed empirically on
    2026-07-06 for ``htdemucs`` (single HTDemucs) when its ``.th``
    was pre-populated by a Path A attempt and ``htdemucs.yaml`` was
    not in the cache afterwards.
    """
    from demucs.pretrained import get_model

    # Idempotent: if the weights are already in the cache, this is a no-op
    # (well, a re-load into memory + discarding the model object).
    get_model(model_name)
    cache = _native_demucs_cache_dir()
    ypath = cache / f"{model_name}.yaml"
    if not ypath.exists():
        # Demucs didn't deposit the .yaml in the cache (typically because
        # the .th was already there and no download fired).  Pull the
        # descriptor from the installed demucs package and copy it in.
        import demucs.pretrained as dp

        bundled = Path(dp.REMOTE_ROOT) / f"{model_name}.yaml"
        if not bundled.exists():
            raise RuntimeError(
                f"YAML descriptor for {model_name!r} not found in the "
                f"torch hub cache ({ypath}) nor in the installed demucs "
                f"package ({bundled}). The model name may be wrong, or "
                f"the installed demucs is too old to know about "
                f"{model_name!r}."
            )
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, ypath)
    return ypath


def _needed_th_files(yaml_path: Path) -> list[str]:
    """Parse a demucs YAML descriptor and return the list of ``<hash>``
    sub-model names the model needs.

    For a single HTDemucs the YAML is minimal::

        models: ['955717e8']

    For a BagOfModels like ``htdemucs_ft`` it's::

        models: ['f7e0c4bc', 'd12395a8', '92cfc3b6', '04573f0d']
        weights: [[1.,0.,0.,0.], ...]

    Either way, each entry is the ``<hash>`` prefix of one of the
    ``<hash>-<hash>.th`` files in the cache.  ``weights`` is a
    combination matrix and is only relevant at inference time (when
    the BagOfModels averages the sub-models' outputs) -- we don't
    need to do anything with it during seeding.
    """
    import yaml

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    models = data.get("models") if isinstance(data, dict) else None
    if not models:
        raise RuntimeError(
            f"YAML at {yaml_path} has no 'models:' field; cannot "
            f"determine which .th files to seed. Inspect the file "
            f"manually -- demucs may have changed its descriptor format."
        )
    return [str(m) for m in models]


# -----------------------------------------------------------------------------
# Seed (cache -> models/demucs/)
# -----------------------------------------------------------------------------


def _format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:6.1f} {unit}"
        n /= 1024
    return f"{n:6.1f} TB"


def _find_th_for_hash(cache: Path, hash_name: str) -> list[Path]:
    """Return the non-partial ``<hash>-<hash>.th`` files in the cache.

    Filters out zero-byte ``.partial`` files (stale leftovers from
    interrupted downloads) so a half-finished transfer doesn't shadow
    a complete one.  Returns a list (not a single Path) because future
    demucs releases could publish multiple variants of the same hash.
    """
    matches = sorted(
        m for m in cache.glob(f"{hash_name}-*.th") if m.stat().st_size > 0
    )
    return matches


def _seed_models_dir(
    model_name: str,
    output_dir: Path,
    *,
    force: bool = False,
    quiet: bool = False,
) -> list[Path]:
    """Copy the YAML descriptor + the needed ``<hash>.th`` files from
    the torch hub cache to ``output_dir`` so
    ``get_model(model_name, repo=output_dir)`` works offline.

    Returns the list of files written (or already present and
    up-to-date).  Raises :class:`RuntimeError` if the cache doesn't
    contain the files the YAML references -- that means
    :func:`_ensure_model_in_cache` failed silently or demucs changed
    its cache convention.
    """
    ypath = _ensure_model_in_cache(model_name)
    cache = _native_demucs_cache_dir()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    # 1. Copy the YAML descriptor (one per model).
    dest_yaml = output_dir / ypath.name
    src_size = ypath.stat().st_size
    if force or not dest_yaml.exists() or dest_yaml.stat().st_size != src_size:
        if not quiet:
            print(f"  [copy] {ypath.name} ({_format_bytes(src_size)})")
        shutil.copy2(ypath, dest_yaml)
    written.append(dest_yaml)

    # 2. Copy each <hash>.th file the YAML references.  The YAML's
    #    `models:` list is the authoritative list -- we never copy
    #    extra files the YAML didn't ask for, so the seeded directory
    #    is exactly what LocalRepo needs and nothing more.
    needed = _needed_th_files(dest_yaml)
    for hash_name in needed:
        matches = _find_th_for_hash(cache, hash_name)
        if not matches:
            raise RuntimeError(
                f"YAML references {hash_name!r} but no file matching "
                f"{hash_name}-*.th was found in {cache}. Did "
                f"get_model({model_name!r}) complete successfully?"
            )
        for m in matches:
            dest = output_dir / m.name
            src_size = m.stat().st_size
            if force or not dest.exists() or dest.stat().st_size != src_size:
                if not quiet:
                    print(f"  [copy] {m.name} ({_format_bytes(src_size)})")
                shutil.copy2(m, dest)
            written.append(dest)
    return written


# -----------------------------------------------------------------------------
# Integrity verification -- the gate from models/demucs/README.md
# -----------------------------------------------------------------------------


def verify_layout(repo_dir: Path, expect_model: str) -> tuple[bool, str]:
    """Run ``get_model(<expect_model>, repo=<repo_dir>)`` to confirm the
    directory is :class:`LocalRepo`-loadable.

    This is the *only* way to know we built the file layout that
    :class:`LocalRepo` accepts -- there is no public schema. The
    function is the gate the README's "Verification step" calls out;
    exposing it here lets ``build-portable.bat`` invoke it safely.

    NB on the ``repo=`` argument
    ----------------------------
    demucs 4.0.1's :class:`LocalRepo` calls ``repo.is_dir()`` on the
    value we pass -- and ``str.is_dir()`` does not exist.  Pass a
    :class:`pathlib.Path` (or any :class:`os.PathLike`), NOT a ``str``.
    Observed empirically on 2026-07-06:
    ``get_model('htdemucs_ft', repo='<str-path>')`` raises
    ``AttributeError: 'str' object has no attribute 'is_dir'``;
    passing a :class:`Path` makes the same call succeed.  This is
    arguably a bug in the upstream demucs 4.0.1 signature (it would
    be friendlier to coerce ``str`` -> :class:`Path` internally), but
    we work around it by passing the right type here.  The same trap
    exists in :mod:`lyricsfag_lib.audio_analysis` (where
    ``DemucsIsolator._ensure_separator`` does
    ``get_model(name, repo=str(bundled_repo_path))``) and is fixed
    there in lockstep.
    """
    if not _ensure_demucs():
        return False, (
            "demucs package is not importable. Install with: pip install demucs"
        )
    try:
        from demucs.pretrained import get_model

        # PyTorch 2.6 / demucs 4.0.1 ``weights_only`` workaround --
        # shared implementation lives in :mod:`lyricsfag_lib._torch_compat`
        # so the script and the library can\'t drift.  ``echo_to_stderr``
        # is requested so the confirmation line shows up in the CLI
        # output even when no logging handler is configured.
        ensure_torch_load_patched(echo_to_stderr=True)

        # NOTE: repo= expects a PathLike, NOT str. See NB above.
        m = get_model(expect_model, repo=repo_dir)
    except Exception as exc:
        return False, f"get_model({expect_model!r}, repo=...) raised: {exc}"
    return True, (
        f"OK: samplerate={getattr(m, 'samplerate', '?')} "
        f"sources={getattr(m, 'sources', '?')} type={type(m).__name__}"
    )


def total_size_bytes(repo_dir: Path) -> int:
    """Sum of on-disk bytes for every file in ``repo_dir`` (no recursion)."""
    return sum(p.stat().st_size for p in repo_dir.glob("*") if p.is_file())


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="download_demucs_model",
        description=(
            "Download a demucs pretrained tree into models/demucs/ so "
            "demucs.pretrained.LocalRepo can load weights directly from "
            "the project (the missing piece for a bundled offline exe)."
        ),
    )
    p.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            f"Demucs model to seed (default: {DEFAULT_MODEL}). Must be "
            f"a model name listed in demucs/remote/*.yaml "
            f"(htdemucs_ft, htdemucs, mdx, mdx_q, ...). The seed layout "
            f"is built from the model's YAML descriptor and the files "
            f"demucs.pretrained.get_model() downloads into "
            f"~/.cache/torch/hub/checkpoints/."
        ),
    )
    p.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to place the seeded files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help=(
            "After seeding, run a verification step (calls "
            "demucs.pretrained.get_model(<model>, repo=output_dir) "
            "and prints the result). This is the gate from "
            "models/demucs/README.md."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Re-copy even if a file with matching size already exists "
            "in the output dir."
        ),
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress per-file progress lines.",
    )
    p.add_argument(
        "--list-only",
        action="store_true",
        help=(
            "Print the file listing that would be seeded and exit; "
            "useful for inspecting what will land on disk before "
            "committing to a real copy. Note: this STILL triggers "
            "demucs's auto-download if the cache is cold (we can't "
            "list without inspecting the cache)."
        ),
    )
    args = p.parse_args(argv)

    if not _ensure_demucs():
        print(
            "  [error] demucs is not importable. Install with: pip install demucs",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.output_dir).resolve()

    if args.list_only:
        # Show what would be seeded.  Triggers get_model() so the cache
        # is populated -- we can't build the listing without inspecting
        # the YAML, and the YAML only lands in the cache after get_model()
        # has run.  The copy step below is what's actually skipped.
        try:
            ypath = _ensure_model_in_cache(args.model)
        except Exception as exc:
            print(
                f"  [error] could not populate cache for {args.model!r}: {exc}",
                file=sys.stderr,
            )
            return 2
        needed = _needed_th_files(ypath)
        print(f"Planned seed for {args.model!r} (would copy to {out_dir}):")
        print(
            f"  - {ypath.name}  ({_format_bytes(ypath.stat().st_size)})"
        )
        total = ypath.stat().st_size
        for n in needed:
            matches = _find_th_for_hash(_native_demucs_cache_dir(), n)
            for m in matches:
                sz = m.stat().st_size
                total += sz
                print(f"  - {m.name}  ({_format_bytes(sz)})")
            if not matches:
                print(
                    f"  [warn] YAML references {n!r} but no <hash>-*.th "
                    f"file was found in the cache"
                )
        print()
        print(f"  total: {_format_bytes(total)} across "
              f"{1 + sum(len(_find_th_for_hash(_native_demucs_cache_dir(), n)) for n in needed)} file(s)")
        print()
        print("Use without --list-only to actually copy.")
        return 0

    # Real seed.
    try:
        written = _seed_models_dir(
            args.model, out_dir, force=args.force, quiet=args.quiet,
        )
    except Exception as exc:
        print(f"  [FAIL] seeding {args.model!r}: {exc}", file=sys.stderr)
        return 1

    total_bytes = sum(p.stat().st_size for p in written)
    print(
        f"Seeded {len(written)} file(s), {_format_bytes(total_bytes)} total -> {out_dir}"
    )

    if args.verify:
        ok, msg = verify_layout(out_dir, args.model)
        if not ok:
            print(f"  [verify FAIL] {msg}", file=sys.stderr)
            return 1
        print(f"Verification: {msg}")
        print(
            "OK -- you can now run `build.bat portable` (after PyInstaller "
            "is installed) to bundle the offline-ready tree into the exe."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
