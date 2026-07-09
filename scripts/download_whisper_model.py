#!/usr/bin/env python3
"""Download a faster-whisper model checkpoint via raw HTTP, with resume.

Why this exists
---------------
The ``huggingface_hub`` library normalises download URLs and rejects responses
served from mirrors -- even when the mirror is otherwise reachable. On
networks where ``cdn-lfs.huggingface.co`` is unreachable but ``hf-mirror.com``
(or ``huggingface.co``) is, the library fails with::

    huggingface_hub.errors.FileMetadataError:
        Distant resource does not seem to be on huggingface.co.

This script bypasses that layer by issuing raw ``GET`` requests straight at
the mirror URL pattern ``https://<mirror>/<repo>/resolve/main/`` that HF
itself uses.

The second obstacle is **TCP RST mid-stream** on the heavy binary
(``model.bin``, ~140 MB): firewalls, proxies, or DPI appliances drop the
connection once it crosses some byte-count or time threshold. A naive
``GET`` loop catches the exception and has to restart from byte 0 every
retry -- which wastes minutes and frequently triggers the same drop on
the next attempt. The fix: probe ``Accept-Ranges`` / 206 Partial Content,
then issue ``Range: bytes={local_size}-`` on retries so the server only
ships the bytes we don't already have.

Default usage ::

    python scripts/download_whisper_model.py

Drops the ``small`` checkpoint into ``models/whisper-small/`` next to
the project so ``--audio-model-path models/whisper-small`` and the
PyInstaller bundle work offline.  The ``small`` size was picked as the
v1.2.1 default because the portable build bakes whichever
``models/whisper-{small,base}`` directory it finds, and ``small``
(``Systran/faster-whisper-small``) gives noticeably cleaner LRC
timestamps than ``base`` at the cost of ~500 MB instead of ~150 MB.
Pass ``--size base`` explicitly if you want the smaller footprint.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

# Map UI-friendly model name -> HF repo id.  Keep in sync with
# `lyricsfag_lib/audio_analysis.SUPPORTED_MODELS`.
REPO_ID_FOR_SIZE = {
    "tiny":     "Systran/faster-whisper-tiny",
    "base":     "Systran/faster-whisper-base",
    "small":    "Systran/faster-whisper-small",
    "medium":   "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
}

# Default mirror that serves `resolve/main/...` files directly (i.e. without
# redirecting through cdn-lfs.huggingface.co).
DEFAULT_MIRROR = "https://hf-mirror.com"

# HuggingFace metadata endpoint -- lists sibling files for the model repo.
HF_API = "https://huggingface.co/api/models/{repo_id}"

DEFAULT_OUTPUT_DIR = "models/whisper-small"
DEFAULT_SIZE = "small"

EXPECTED_FILES = (
    "config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.txt",
)

CHUNK_BYTES = 64 * 1024
HTTP_TIMEOUT = 60
MAX_RETRIES = 6       # larger than 3 because resume makes retries cheap.
RETRY_BACKOFF_S = 2.0
USER_AGENT = "lyricsfag-downloader/1.1"


# -----------------------------------------------------------------------------
# Networking helpers
# -----------------------------------------------------------------------------


def _open(url: str, *, method: str = "GET", extra_headers: dict | None = None):
    headers = {"User-Agent": USER_AGENT}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, method=method, headers=headers)
    return urllib.request.urlopen(req, timeout=HTTP_TIMEOUT)


def remote_file_size(url: str) -> int | None:
    """Return Content-Length of the URL (HEAD), or None if unavailable."""
    try:
        with _open(url, method="HEAD") as r:
            cl = r.headers.get("Content-Length")
            return int(cl) if cl and cl.isdigit() else None
    except urllib.error.HTTPError as exc:
        # Some mirrors return 405 for HEAD -- fall through (download still works).
        if exc.code == 405:
            return None
        raise


def supports_partial_content(url: str) -> bool:
    """Best-effort: does the server respond 206 to ``Range: bytes=0-0``?."""
    try:
        with _open(url, extra_headers={"Range": "bytes=0-0"}) as r:
            return r.status == 206
    except urllib.error.HTTPError as exc:
        # 416 happens when the file is already counted as fully received;
        # leaves the door open to plain GETs.
        if exc.code == 416:
            return True
        return False
    except Exception:
        return False


def list_repo_files(repo_id: str) -> list[str]:
    """Hit the HF models API and return the sibling filenames."""
    url = HF_API.format(repo_id=repo_id)
    with _open(url) as r:
        data = json.loads(r.read().decode("utf-8"))
    siblings = data.get("siblings") or []
    return [str(s.get("rfilename") or "") for s in siblings if s.get("rfilename")]


# -----------------------------------------------------------------------------
# Progress rendering
# -----------------------------------------------------------------------------


def _format_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:6.1f} {unit}"
        n /= 1024
    return f"{n:6.1f} TB"


def _progress(label: str, done: int, total: int | None, t0: float, show: bool) -> None:
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


# -----------------------------------------------------------------------------
# Download one file with Range-aware resume
# -----------------------------------------------------------------------------


def download_file(
    url: str,
    dest: Path,
    *,
    force: bool = False,
    quiet: bool = False,
    retries: int = MAX_RETRIES,
) -> bool:
    """Stream-download ``url`` to ``dest`` with Range-header resume.

    Behavior:
      * Probes ``Content-Length`` via HEAD (skips download if local already matches).
      * Probes ``Range`` support (server returns ``206 Partial Content`` on
        ``Range: bytes=0-0``) -- when supported, retries resume from the
        partial local size instead of re-downloading from byte 0.
      * Appends (``"ab"``) on resume; truncates only on the first attempt.
      * Final size vs Content-Length cross-check; if it mismatches because
        the server RST'd mid-write, the next retry will resume from the
        actual partial size.

    Returns True if the file is complete, False after exhausting retries.
    """
    # 1. Probe expected size.
    try:
        expected_size = remote_file_size(url)
    except Exception as exc:
        if not quiet:
            print(f"  [HEAD] {url} -> {type(exc).__name__}: {exc}")
        expected_size = None

    # 2. Skip if local is already complete.
    if not force and dest.exists() and expected_size is not None:
        if dest.stat().st_size == expected_size:
            if not quiet:
                print(f"  [skip] {dest.name} already complete "
                      f"({_format_bytes(expected_size)})")
            return True

    # 3. Probe Range support.
    range_supported = supports_partial_content(url) if expected_size else False
    # If we don't know the total size, Range is unreliable -- skip it.

    # 4. Loop with resume.
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        if dest.exists():
            resume_from = dest.stat().st_size
        else:
            resume_from = 0

        # If Range unsupported and we have a partial file, restart from scratch.
        if resume_from > 0 and not range_supported:
            if not quiet:
                print(f"  [info] {dest.name}: server doesn't return 206 for "
                      "Range request -- restarting from byte 0.")
            dest.write_bytes(b"")
            resume_from = 0

        # If previous attempts got further than expected (shouldn't happen),
        # truncate to expected to avoid perpetual weirdness.
        if (expected_size is not None and resume_from > expected_size
                and not force):
            if not quiet:
                print(f"  [info] {dest.name}: local size > expected -- truncating")
            dest.write_bytes(b"")
            resume_from = 0

        extra_headers: dict[str, str] = {}
        append_mode = False
        if (resume_from > 0
                and range_supported
                and expected_size is not None
                and resume_from < expected_size):
            extra_headers["Range"] = f"bytes={resume_from}-"
            append_mode = True

        try:
            t0 = time.monotonic()
            done = resume_from
            with _open(url, extra_headers=extra_headers) as r, \
                    dest.open("ab" if append_mode else "wb") as f:
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
                print(f"  [retry {attempt}/{retries}] {dest.name}: "
                      f"{type(exc).__name__}; "
                      f"resuming from byte {dest.stat().st_size if dest.exists() else 0}; "
                      f"waiting {wait:.1f}s")
            time.sleep(wait)
            # File is left at its current size; next iteration's `resume_from`
            # picks it up automatically.
    return False  # pragma: no cover


# -----------------------------------------------------------------------------
# Orchestration
# -----------------------------------------------------------------------------


def resolve_files(repo_id: str, want: Iterable[str]) -> list[str]:
    """Return the subset of ``want`` actually present in the repo."""
    try:
        siblings = set(list_repo_files(repo_id))
    except Exception as exc:
        print(f"  [warn] Could not list repo files: {exc}; "
              "falling back to defaults list.", file=sys.stderr)
        return list(want)
    available: list[str] = []
    for fn in want:
        if fn in siblings:
            available.append(fn)
        else:
            print(f"  [skip] {fn} not present in {repo_id} "
                  "(will not download)", file=sys.stderr)
    return available


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="download_whisper_model",
        description=(
            "Download a faster-whisper model checkpoint via raw HTTP "
            "(handles networks where the official LFS CDN is unreachable "
            "and resumes through TCP RST drops)."
        ),
    )
    p.add_argument(
        "--size",
        choices=sorted(REPO_ID_FOR_SIZE),
        default=DEFAULT_SIZE,
        help=f"faster-whisper model size (default: {DEFAULT_SIZE}).",
    )
    p.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Where to place the files (default: {DEFAULT_OUTPUT_DIR}).",
    )
    p.add_argument(
        "--mirror",
        default=DEFAULT_MIRROR,
        help=(
            f"Base URL of the mirror serving files directly "
            f"(default: {DEFAULT_MIRROR}). Set to https://huggingface.co "
            "to fall back to the canonical endpoint if the mirror blocks your IP."
        ),
    )
    p.add_argument(
        "--files",
        nargs="*",
        default=list(EXPECTED_FILES),
        help="Specific filenames to download (default: known faster-whisper files).",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a file with matching size already exists.",
    )
    p.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress per-file progress lines.",
    )
    args = p.parse_args(argv)

    repo_id = REPO_ID_FOR_SIZE[args.size]
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Repo:    {repo_id}")
    print(f"Mirror:  {args.mirror}")
    print(f"Output:  {out_dir}")
    print()

    files = resolve_files(repo_id, args.files)
    if not files:
        print("  [error] No files to download; aborting.", file=sys.stderr)
        return 2

    failed: list[str] = []
    for fn in files:
        url = f"{args.mirror.rstrip('/')}/{repo_id}/resolve/main/{fn}"
        dest = out_dir / fn
        ok = download_file(url, dest, force=args.force, quiet=args.quiet)
        if not ok:
            failed.append(fn)

    print()
    if failed:
        # Strong, print-the-URL-once guidance so the user can copy-paste into
        # a browser that doesn't carry the same network restrictions this
        # script just hit. Also note the proven last-resort workaround via
        # git-lfs in case the mirror is the blocker rather than cdn-lfs.
        print(
            f"FAILED for {len(failed)} file(s): {failed}", file=sys.stderr,
        )
        for fn in failed:
            mirror_url = f"{args.mirror.rstrip('/')}/{repo_id}/resolve/main/{fn}"
            canonical_url = f"https://huggingface.co/{repo_id}/resolve/main/{fn}"
            print(
                f"\nDirect URL for '{fn}' (paste in a browser):\n"
                f"  canonical: {canonical_url}\n"
                f"  mirror:    {mirror_url}",
                file=sys.stderr,
            )
        print(
            "Drop the downloaded files into the directory shown below, then "
            "rerun the script -- if the local sizes already match Content-Length "
            "(HEAD), downloads will skip automatically.\n"
            f"  {out_dir}\n",
            file=sys.stderr,
        )
        print(
            "If your network blocks the LFS storage layer outright, you can also\n"
            f"use: git lfs clone https://huggingface.co/{repo_id} tmp_dir\n"
            f"and then copy tmp_dir/.git/lfs/objects/<oid>/<files> into {out_dir}.\n",
            file=sys.stderr,
        )
        print(
            "Use --mirror https://huggingface.co to bypass the mirror if the "
            "mirror itself is down, or set LYRICSFAG_AUDIO=1 when running "
            "build.bat to attempt the download again during the build.",
            file=sys.stderr,
        )
        return 1
    print(f"All {len(files)} file(s) downloaded to {out_dir}")
    print("LyricsFAG will pick this up via --audio-model-path or via the "
          "bundled-model path resolve next to the package.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
