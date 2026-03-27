"""
Render captured terminal state to SVG, HTML, PNG, or ANSI.

Usage:
    python3 -m render capture.json -o mockup.svg
    python3 -m render capture.json -o mockup.html --title "My App v2.0"
    python3 -m render capture.json -o mockup.png --font "DejaVu Sans Mono"
    python3 -m render capture.json -o mockup.ansi
"""

from render.svg import render_svg
from render.html import render_html
from render.ansi import render_ansi
from render.png import render_png

__all__ = ["render_svg", "render_html", "render_ansi", "render_png"]
