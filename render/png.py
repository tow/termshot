"""Render captured terminal state to PNG via kitty + window capture.

macOS: screencapture -l <window_id>
Linux: import -window <window_id> (ImageMagick)
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from render.ansi import render_ansi
from capture_data import get_theme
from kitty_util import KittyWindow


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG by launching kitty and capturing the window."""
    t = get_theme(data)
    ansi_content = render_ansi(data)
    cols = data["cols"]
    rows = data["rows"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    try:
        kw = KittyWindow(extra_opts=[
            "-o", f"font_family={font_name}",
            "-o", f"font_size={font_size}",
            "-o", f"background={t['background']}",
            "-o", f"foreground={t['foreground']}",
            "-o", f"initial_window_width={cols}c",
            "-o", f"initial_window_height={rows}c",
            "-o", "window_padding_width=0",
            "-o", "hide_window_decorations=yes",
        ])
        kw.launch(cmd=[
            "bash", "-c",
            f"printf '\\033[?25l'; cat {shlex.quote(ansi_path)}; sleep 60",
        ])

        # Give kitty time to render
        time.sleep(1.5)

        window_id = kw.get_window_id()
        _capture_window(window_id, output_path)
        kw.kill()
    finally:
        os.unlink(ansi_path)


def _capture_window(window_id, output_path):
    """Capture a window to PNG using the platform's tool."""
    if sys.platform == "darwin":
        subprocess.run(
            ["screencapture", "-l", str(window_id), "-o", output_path],
            check=True,
        )
    else:
        # Linux: ImageMagick import
        if not shutil.which("import"):
            print("Error: import (ImageMagick) not found. "
                  "Install with: apt-get install imagemagick",
                  file=sys.stderr)
            sys.exit(1)
        subprocess.run(
            ["import", "-window", str(window_id), output_path],
            check=True,
        )
