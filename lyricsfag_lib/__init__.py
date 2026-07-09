"""LyricsFAG library: audio metadata extraction, lyrics fetching, LRC formatting.

Versioning
----------
``__version__`` is the single source of truth for the ``[tool:LyricsFAG X.Y.Z]``
stamp written into every :func:`lyricsfag_lib.lrc.write_lrc` call.  It is
also the version printed by ``build.bat``'s end-of-run summary and the
version displayed in the GUI titlebar.  When adding a new feature,
update this BEFORE bumping the corresponding subsection in
``RELEASE_NOTES.md`` so the version is consistent across git history.
"""

__version__ = "1.2.1"
