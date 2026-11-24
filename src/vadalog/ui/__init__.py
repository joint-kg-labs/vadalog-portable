"""The local web front end (optional).

    vadalog ui                      # or:  python3 -m vadalog.ui

It ships inside the package so that a single-file build (`make pyz`) carries
the page with it.  It imports the engine, never the other way round.
"""

from .server import build, main, serve          # noqa: F401

__all__ = ["build", "main", "serve"]
