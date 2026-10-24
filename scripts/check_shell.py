"""Manual smoke check for the shell. Run with QT_QPA_PLATFORM=offscreen."""

from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Allow running from a plain checkout, without installing the package.
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mmnext.bootstrap import create_application, create_main_window  # noqa: E402


def main() -> int:
    app = create_application([])
    window = create_main_window(app)
    window.show()
    print("MainWindow OK")
    print("screens:", list(window._screens.keys()))
    print("nav active:", window.nav.active_key)
    print("title:", window.windowTitle())
    print("save chip:", window.save_chip.text())
    print("source chip:", window.source_chip.text())
    print("ffmpeg chip:", window.ffmpeg_chip.text())
    print("gpu chip:", window.gpu_chip.text())
    print("language chip:", window.language_chip.text())
    print("worker running:", window._worker.isRunning())
    print("mode:", window.context.mode)
    print("session source:", window.context.session.source.name)
    print("drawer expanded:", window.log_drawer.expanded)
    window.close()
    print("closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
