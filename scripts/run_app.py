"""Launch MMNext Movie Recap Pro.

A thin wrapper around :mod:`mmnext.main` so the application can be started
with ``python scripts\\run_app.py`` without installing the package first.

The repository root is put on ``sys.path`` first, which makes the script
work from a plain checkout as well as from an installed package.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmnext.main import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
