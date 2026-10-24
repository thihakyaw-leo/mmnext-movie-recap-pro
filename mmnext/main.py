"""Entry point for MMNext Movie Recap Pro Milestone 1.

The heavy lifting lives in :mod:`mmnext.bootstrap`; this module only wires
the console script to it.
"""

from __future__ import annotations

import sys

from .bootstrap import bootstrap


def main() -> int:
    """Run the desktop application."""
    return bootstrap(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
