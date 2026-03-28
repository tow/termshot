"""Render captured terminal state to PNG via kitty + window capture."""

import os
import shlex
import tempfile
import time

from render.ansi import render_ansi
from kitty_util import KittyWindow, capture_window

_THEME_DEFAULTS = {
    "background": "#1e1e2e", "foreground": "#cdd6f4",
}


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG by launching kitty and capturing the window."""
    theme = data.get("theme", {})
    bg = theme.get("background", _THEME_DEFAULTS["background"])
    fg = theme.get("foreground", _THEME_DEFAULTS["foreground"])
    ansi_content = render_ansi(data)
    cols, rows = data["cols"], data["rows"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    try:
        kw = KittyWindow(extra_opts=[
            "-o", f"font_family={font_name}",
            "-o", f"font_size={font_size}",
            "-o", f"background={bg}",
            "-o", f"foreground={fg}",
            "-o", f"initial_window_width={cols}c",
            "-o", f"initial_window_height={rows}c",
            "-o", "window_padding_width=0",
            "-o", "hide_window_decorations=yes",
        ])
        kw.launch(cmd=[
            "bash", "-c",
            f"printf '\\033[?25l'; cat {shlex.quote(ansi_path)}; sleep 60",
        ])
        time.sleep(1.5)
        capture_window(kw.get_window_id(), output_path)
        kw.kill()
    finally:
        os.unlink(ansi_path)
