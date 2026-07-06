#!/usr/bin/env python3
"""Download a demucs pretrained-model tree so ``models/demucs/`` becomes
loadable by :class:`demucs.pretrained.LocalRepo`.

This is the "Path B" workflow described in ``models/demucs/README.md`` and the
missing piece that turns ``models/demucs/`` from a "currently empty by design"
placeholder into a real, ready-to-bundle seed for a fully offline
``LyricsFAG-Portable.exe``.

Why this script exists
----------------------
Demucs 4.x's auto-download path stores files in PyTorch Hub's native cache
(``~/.cache/torch/hub/checkpoints/<hash>-<hash>.th``), but its
:class:`demucs.pretrained.LocalRepo` -- the only thing that respects a
``repo=`` argument to :func:`demucs.pretrained.get_model` -- looks for
``<model_name>.th`` (no hash).  Without a translation step the cache and the
bundled layout are incompatible (``ModelLoadingError: htdemucs is neither a
single pre-trained model or a bag of models``), which we verified
empirically on 2026-07-06 when "Path A" (manual copy) was REFUTED.

The two established demucs endpoints we rely on:

* :data:`demucs.pretrained.REMOTE_ROOT` -- the directory bundled inside the
  installed ``demucs`` package that holds ``files.txt`` (the canonical
  master listing of every weight file demucs knows about).
* :data:`demucs.pretrained.ROOT_URL` -- typically
  ``https://dl.fbaipublicfiles.com/demucs/``.

Each line in ``files.txt`` has the form ``<sig>-<hash>.<ext>`` (e.g.
``htdemucs-f7e0c4bc.th``) and is fetched verbatim as ``<ROOT_URL><line>``.
We translate that to ``<sig>.<ext>`` on disk -- the bare shape
:class:`LocalRepo` reads.

Usage
-----
Mirror all demucs files into ``models/demucs/`` (default)::

    python scripts/download_demucs_model.py

Filter to the ``htdemucs`` model only (smaller, default for LyricsFAG)::

    python scripts/download_demucs_model.py --model htdemucs

Verify the resulting directory works with ``get_model(..., repo=...)``::

    python scripts/download_demucs_model.py --model htdemucs --verify

The mirror default (``https://dl.fbaipublicfiles.com/demucs/``) is the
canonical endpoint because the file sizes are large (~84 MB each) and the
firewall / DPI appliances that block the HuggingFace LFS CDN don't
typically interfere with this one; if you DO hit a wall, use
``--url <mirror>`` to point at a known-good mirror.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable, Optional

# Match "<sig>-<hash>.<ext>" so that future releases using hyphens inside
# the sig (e.g. "htdemucs-ft-abcd1234.th" or "htdemucs_ft-abcd1234.th")
# still parse correctly. The anchor on the trailing hash+ext is what gives
# us certainty: the hash must be 6-12 lowercase hex chars, and the
# extension must start with a literal "." followed by alphanumerics --
# this combination is what demucs uses today and would have to change
# substantively for this regex to misfire.
#
# The sig itself is captured non-greedily (".+?") so multi-hyphen sigs
# truncate at the *last* matching "-<hash>." boundary. By way of
# counter-example, the older stricter pattern ``[^-/.\s]+`` rejected any
# hyphens in the sig -- safe today (htdemucs, htdemucs_ft, ...) but
# fragile for forward compatibility.
_F_LINE = re.compile(r"^(?P<sig>.+?)-(?P<hash>[0-9a-f]{6,12})(?P<ext>\.[A-Za-z0-9]+)$")

DEFAULT_OUTPUT_DIR = "models/demucs"
# ``htdemucs_ft`` is the music-only fine-tune of ``htdemucs`` --
# LyricsFAG now defaults to it for vocal isolation (single ~84 MB
# download vs htdemucs's 5-sub-model bag at ~420 MB). ``htdemucs``
# remains selectable via ``--model htdemucs`` for users who want the
# base ensemble.
DEFAULT_MODEL = "htdemucs_ft"
DEFAULT_URL = "https://dl.fbaipublicfiles.com/demucs/"

CHUNK_BYTES = 64 * 1024
HTTP_TIMEOUT = 120
MAX_RETRIES = 6
RETRY_BACKOFF_S = 2.0
USER_AGENT = "lyricsfag-downloader/1.0 (demucs)"

# Aggressive check: a populated `models/demucs/` for htdemucs is ~5 weight
# files of ~84 MB each, so anything below this is either partial / corrupt
# or mirroring the wrong directory. Used for a soft warning only -- the
# script still succeeds if the user explicitly wants a smaller build.
MIN_HTDEMUCS_BYTES = 5 * 70 * 1024 * 1024  # 350 MB slack (5 * 70 MB)

# Module-level probe cache. ``None`` means "not yet attempted"; ``True`` /
# ``False`` record the actual outcome. We keep this state at module scope
# rather than inside the function so the import cost is paid at most once
# per process and so unit tests can poke it without monkey-patching.
_DEMUCS_OK: Optional[bool] = None


# -----------------------------------------------------------------------------
# Networking helpers (mirror scripts/download_whisper_model.py style)
# -----------------------------------------------------------------------------


def _open(url: str, *, method: str = "GET", extra_headers: Optional[dict] = None):
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)
    return urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)


def remote_file_size(url: str) -> Optional[int]:
    """Return Content-Length of the URL (HEAD), or None if unavailable."""
    try:
        with _open(url, method="HEAD") as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else None
    except urllib.error.HTTPError as exc:
        if exc.code == 405:
            return None
        raise


def supports_partial_content(url: str) -> bool:
    try:
        with _open(url, extra_headers={"Range": "bytes=0-0"}) as r:
            return r.status == 206
    except urllib.error.HTTPError as exc:
        if exc.code == 416:
            return True
        return False
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Demucs metadata discovery
# -----------------------------------------------------------------------------


def _ensure_demucs() -> bool:
    """Whether the demucs 4.x package can be imported.

    Result is cached in module-level ``_DEMUCS_OK`` so a hot path
    (e.g. ``main()`` checking it under ``--verify``) can short-circuit
    the ~3 s ``import torch`` cost demucs pulls in.
    """
    global _DEMUCS_OK
    if _DEMUCS_OK is None:
        try:
            import demucs.pretrained  # noqa: F401  - presence probe only
            _DEMUCS_OK = True
        except ImportError:
            _DEMUCS_OK = False
    return bool(_DEMUCS_OK)


def _demucs_paths():
    """Return ``(files_txt_path, root_url)`` from the installed demucs."""
    import demucs.pretrained as dp  # only entered when --verify/--list is used
    return Path(dp.REMOTE_ROOT) / "files.txt", dp.ROOT_URL


def list_repo_lines(files_txt: Path) -> list[str]:
    """Return the non-comment, non-blank lines of ``files.txt``.

    demucs 4.0.1's ``_parse_remote_files`` deliberately ignores comment /
    blank lines; we mirror that behaviour here so the listing we work on
    is the SAME set of lines demucs itself would consume.
    """
    if not files_txt.exists():
        raise FileNotFoundError(
            f"demucs files.txt not found at {files_txt}; "
            "is the `demucs` package correctly installed? "
            "(pip install demucs)"
        )
    out: list[str] = []
    for raw in files_txt.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def select_lines(
    all_lines: Iterable[str], *, model: Optional[str]
) -> list[tuple[str, str, str, str]]:
    """Return ``[(line, sig, hash, ext), ...]`` for the lines we want.

    ``line`` is the original ``files.txt`` entry (used for the download
    URL), the rest is its parsed components.

    When ``model`` is set (e.g. ``"htdemucs"``) the filter keeps only
    lines whose signature exactly matches ``model`` OR starts with
    ``<model>_`` -- so ``htdemucs`` keeps the 5 htdemucs weight files
    but drops unrelated models like ``mdx_q``. The ``_<suffix>``
    allowance keeps future sibling models (e.g. ``htdemucs_ft``) in the
    selection if a user asks for the parent name.
    Without ``model`` we keep *everything*: useful for a "max-portable"
    build, wasteful if you only use htdemucs.
    """
    out: list[tuple[str, str, str, str]] = []
    for line in all_lines:
        m = _F_LINE.match(line)
        if not m:
            print(
                f"  [skip] {line!r} does not match the <sig>-<hash>.<ext> pattern",
                file=sys.stderr,
            )
            continue
        sig, hsh, ext = m["sig"], m["hash"], m["ext"]
        if model and not (sig == model or sig.startswith(model + "_")):
            continue
        out.append((line, sig, hsh, ext))
    return out


# -----------------------------------------------------------------------------
# Download one file with Range-aware resume
# -----------------------------------------------------------------------------


def _format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:6.1f} {unit}"
        n /= 1024
    return f"{n:6.1f} TB"


def _progress(label: str, done: int, total: Optional[int], t0: float, show: bool) -> None:
    if not show:
        return
    pct = ""
    if total and total > 0:
        pct = f"{(done / total) * 100:5.1f}%"
    speed = _format_bytes(done / max(time.monotonic() - t0, 0.001)) + "/s"
    msg = f"  {label:30s} {_format_bytes(done):>14s}"
    if total:
        msg += f" / {_format_bytes(total):>14s}  {pct}"
    msg += f"  {speed}"
    sys.stdout.write("\r" + msg + " " * 4)
    sys.stdout.flush()


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    quiet: bool = False,
    retries: int = MAX_RETRIES,
) -> bool:
    """Stream-download ``url`` to ``dest``, with Range-aware resume.

    Mirrors :func:`scripts.download_whisper_model.download_file` so the
    two scripts behave consistently under flaky connections / TCP-RST
    mid-stream drops. Returns True if the file is complete, False after
    exhausting retries.
    """
    try:
        expected_size = remote_file_size(url)
    except Exception as exc:
        if not quiet:
            print(f"  [HEAD] {url} -> {type(exc).__name__}: {exc}")
        expected_size = None

    if not force and dest.exists() and expected_size is not None:
        if dest.stat().st_size == expected_size:
            if not quiet:
                print(
                    f"  [skip] {dest.name} already complete "
                    f"({_format_bytes(expected_size)})"
                )
            return True

    range_supported = supports_partial_content(url) if expected_size else False

    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        resume_from = dest.stat().st_size if dest.exists() else 0
        if resume_from > 0 and not range_supported:
            if not quiet:
                print(
                    f"  [info] {dest.name}: server doesn't return 206 for "
                    "Range request -- restarting from byte 0."
                )
            dest.write_bytes(b"")
            resume_from = 0
        if (
            expected_size is not None
            and resume_from > expected_size
            and not force
        ):
            if not quiet:
                print(f"  [info] {dest.name}: local size > expected -- truncating")
            dest.write_bytes(b"")
            resume_from = 0

        extra_headers: dict[str, str] = {}
        append_mode = False
        if (
            resume_from > 0
            and range_supported
            and expected_size is not None
            and resume_from < expected_size
        ):
            extra_headers["Range"] = f"bytes={resume_from}-"
            append_mode = True

        try:
            t0 = time.monotonic()
            done = resume_from
            with _open(url, extra_headers=extra_headers) as r, dest.open(
                "ab" if append_mode else "wb"
            ) as f:
                while True:
                    chunk = r.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    _progress(dest.name, done, expected_size, t0, not quiet)
                f.flush()
            if not quiet:
                sys.stdout.write("\n")

            actual = dest.stat().st_size
            if expected_size is not None and actual != expected_size:
                raise RuntimeError(
                    f"size mismatch: got {actual}, expected {expected_size}; "
                    "server probably RST'd mid-write; will resume on next retry"
                )
            return True
        except Exception as exc:
            last_exc = exc
            if attempt == retries:
                if not quiet:
                    sys.stdout.write("\n")
                    print(f"  [FAIL] {dest.name} -> {type(exc).__name__}: {exc}")
                return False
            wait = RETRY_BACKOFF_S * attempt
            if not quiet:
                sys.stdout.write("\n")
                print(
                    f"  [retry {attempt}/{retries}] {dest.name}: "
                    f"{type(exc).__name__}; "
                    f"resuming from byte {dest.stat().st_size if dest.exists() else 0}; "
                    f"waiting {wait:.1f}s"
                )
            time.sleep(wait)

    if last_exc is not None and not quiet:
        print(f"  [FAIL] {dest.name} after {retries} retries: {last_exc}")
    return False


# -----------------------------------------------------------------------------
# Integrity verification (only the practical one: ask demucs to load the
# tree via its own LocalRepo path -- that's the schema demucs will demand)
# -----------------------------------------------------------------------------


def verify_layout(repo_dir: Path, expect_model: str) -> tuple[bool, str]:
    """Run ``get_model(<expect_model>, repo=<repo_dir>)`` to confirm the
    directory is LocalRepo-loadable.

    This is the *only* way to know we built the file layout that
    :class:`LocalRepo` accepts -- there is no public schema. The
    function is the gate the README's "Verification step" calls out;
    exposing it here lets ``build-portable.bat`` invoke it safely.
    """
    if not _ensure_demucs():
        return False, (
            "demucs package is not importable. Install with: pip install demucs"
        )
    try:
        from demucs.pretrained import get_model
        m = get_model(expect_model, repo=str(repo_dir))
    except Exception as exc:
        return False, f"get_model({expect_model!r}, repo=...) raised: {exc}"
    return True, f"OK: samplerate={getattr(m, 'samplerate', '?')} sources={getattr(m, 'sources', '?')}"


def total_size_bytes(repo_dir: Path) -> int:
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
            f"Demucs model to download (default: {DEFAULT_MODEL}). "
            "Filters files.txt to lines starting with this signature "
            "(so 'htdemucs' keeps the 5 htdemucs weight files but "
            "drops unrelated ones like mdx_q). Pass an empty string "
            "to download EVERYTHING (largest footprint)."
        ),
    )
    p.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to place the files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    p.add_argument(
        "--url",
        default=None,
        help=(
            "Override demucs's ROOT_URL (the canonical endpoint is "
            "https://dl.fbaipublicfiles.com/demucs/); use this if the "
            "canonical endpoint is unreachable on your network."
        ),
    )
    p.add_argument(
        "--verify",
        action="store_true",
        help=(
            "After download, run a verification step (calls "
            "demucs.pretrained.get_model(<model>, repo=output_dir) "
            "and prints the result). This is the gate from "
            "models/demucs/README.md."
        ),
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a file with matching size already exists.",
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
            "Print the file listing demucs would download (filtered by "
            "--model) and exit; useful for inspecting what will land on "
            "disk before committing to a real download."
        ),
    )
    args = p.parse_args(argv)

    if not _ensure_demucs():
        print(
            "  [error] demucs is not importable. Install with: pip install demucs",
            file=sys.stderr,
        )
        return 2

    files_txt, root_url = _demucs_paths()
    root_url = args.url or root_url
    print(f"demucs files.txt: {files_txt}")
    print(f"Base URL:         {root_url}")
    print(f"Output dir:       {args.output_dir}")
    if args.model:
        print(f"Model filter:     {args.model!r}")
    print()

    all_lines = list_repo_lines(files_txt)
    selected = select_lines(all_lines, model=args.model or None)
    if not selected:
        print(
            f"  [error] no files.txt lines matched the "
            f"{'--model ' + repr(args.model) if args.model else 'no-filter'} "
            "select; aborting.",
            file=sys.stderr,
        )
        return 2

    if args.list_only:
        print(f"Planned download ({len(selected)} file(s)):")
        for line, _sig, _h, _ext in selected:
            print(f"  - {line}")
        print()
        print("Use without --list-only to actually fetch.")
        return 0

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Selected {len(selected)} file(s) from files.txt")
    failed: list[str] = []
    for line, sig, _h, ext in selected:
        url = f"{root_url.rstrip('/')}/{line}"
        dest = out_dir / f"{sig}{ext}"
        ok = download_file(url, dest, force=args.force, quiet=args.quiet)
        if not ok:
            failed.append(line)

    print()
    if failed:
        print(f"FAILED for {len(failed)} file(s): {failed}", file=sys.stderr)
        for line in failed:
            print(
                f"\nDirect URL for {line!r}:\n  {root_url.rstrip('/')}/{line}",
                file=sys.stderr,
            )
        print(
            f"\nDrop the downloaded files into:\n  {out_dir}\nand re-run "
            "the script -- files with matching local sizes will be skipped.",
            file=sys.stderr,
        )
        return 1

    print(f"All {len(selected)} file(s) downloaded to {out_dir}")
    print(
        "Each weight file was saved as <sig>.<ext> with the hash suffix "
        "stripped, so demucs.pretrained.LocalRepo can read this directory "
        "directly via get_model(<sig>, repo=this_path)."
    )

    # Sanity-gate: at least the htdemucs subtree, when present, ought to be
    # >350 MB (5 sub-models x ~84 MB minus slack). We don't fail on this,
    # but a too-small result signals that something went wrong upstream
    # (e.g. internet proxy only mirrored part of the bag).
    sz = total_size_bytes(out_dir)
    if args.model == "htdemucs" and sz < MIN_HTDEMUCS_BYTES:
        print(
            f"  [warn] htdemucs total on disk is only {_format_bytes(sz)} "
            f"(< {_format_bytes(MIN_HTDEMUCS_BYTES)}). This usually means "
            "the mirror returned a partial set. Re-run with --force.",
            file=sys.stderr,
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
