"""
Render captured terminal state to SVG, HTML, PNG, or ANSI.

Usage:
    python3 -m render capture.json -o mockup.svg
    python3 -m render capture.json -o mockup.html --title "My App v2.0"
    python3 -m render capture.json -o mockup.png --font "DejaVu Sans Mono"
    python3 -m render capture.json -o mockup.ansi
"""

import os

from render.svg import render_svg
from render.html import render_html
from render.ansi import render_ansi
from render.png import render_png

__all__ = ["render_svg", "render_html", "render_ansi", "render_png", "render_to_file"]


def render_to_file(data, output_path, title=None, font_name="DejaVu Sans Mono",
                   font_size=14, terminal=None):
    """Render capture data to a file, choosing format by extension."""
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".html":
        with open(output_path, "w") as f:
            f.write(render_html(data, title=title))
        return "html"
    elif ext == ".svg":
        with open(output_path, "w") as f:
            f.write(render_svg(data, title=title))
        return "svg"
    elif ext == ".png":
        render_png(data, output_path, font_name=font_name, font_size=font_size,
                   terminal=terminal)
        return "png"
    elif ext == ".ansi":
        with open(output_path, "w") as f:
            f.write(render_ansi(data))
        return "ansi"
    else:
        raise ValueError(f"Unsupported format: {ext!r} (use .svg, .html, .png, or .ansi)")
