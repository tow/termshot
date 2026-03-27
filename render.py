#!/usr/bin/env python3
"""
Render a captured (and optionally edited) terminal state to SVG or HTML.

Usage:
    python3 render.py capture.json -o mockup.svg
    python3 render.py capture.json -o mockup.html
    python3 render.py capture.json -o mockup.svg --title "My App v2.0"
"""

import argparse
import html
import json
import sys


def render_svg(data, title=None):
    """Render terminal state to SVG string."""
    theme = data.get("theme", {})
    cols = data["cols"]
    rows = data["rows"]
    cells = data["cells"]

    font_family = theme.get("font_family", "JetBrains Mono, Menlo, monospace")
    font_size = theme.get("font_size", 14)
    line_height = theme.get("line_height", 1.4)
    padding = theme.get("padding", 16)
    border_radius = theme.get("border_radius", 10)
    bg = theme.get("background", "#1e1e2e")
    fg = theme.get("foreground", "#cdd6f4")

    char_width = font_size * 0.6
    row_height = font_size * line_height

    # Title bar height
    title_bar_h = 40 if title is not None else 36  # always show dots
    content_y = title_bar_h + padding

    canvas_w = padding * 2 + cols * char_width
    canvas_h = content_y + rows * row_height + padding

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{canvas_w}" height="{canvas_h}" '
                 f'viewBox="0 0 {canvas_w} {canvas_h}">')

    # Background with rounded corners
    parts.append(f'<rect width="{canvas_w}" height="{canvas_h}" rx="{border_radius}" '
                 f'fill="{bg}" />')

    # Window title bar (macOS-style dots)
    dot_y = 18
    dot_colors = ["#ff5f57", "#febc2e", "#28c840"]
    for i, color in enumerate(dot_colors):
        cx = padding + i * 20
        parts.append(f'<circle cx="{cx}" cy="{dot_y}" r="6" fill="{color}" />')

    if title:
        title_x = canvas_w / 2
        parts.append(f'<text x="{title_x}" y="{dot_y + 5}" '
                     f'text-anchor="middle" '
                     f'font-family="{font_family}" font-size="{font_size - 1}" '
                     f'fill="{fg}" opacity="0.6">{html.escape(title)}</text>')

    # Separator line
    sep_y = title_bar_h - 2
    parts.append(f'<line x1="0" y1="{sep_y}" x2="{canvas_w}" y2="{sep_y}" '
                 f'stroke="{fg}" stroke-opacity="0.1" />')

    # Render cells
    for y_idx, row in enumerate(cells):
        # First pass: background rectangles
        for x_idx, cell in enumerate(row):
            cell_bg = cell.get("bg")
            is_reverse = cell.get("reverse", False)
            cell_fg = cell.get("fg", fg)

            if is_reverse:
                # Swap fg/bg for reverse video
                rect_color = cell_fg
            elif cell_bg:
                rect_color = cell_bg
            else:
                rect_color = None

            if rect_color:
                rx = padding + x_idx * char_width
                ry = content_y + y_idx * row_height
                parts.append(f'<rect x="{rx}" y="{ry}" '
                             f'width="{char_width}" height="{row_height}" '
                             f'fill="{rect_color}" />')

        # Second pass: text spans — group consecutive same-style chars
        x = 0
        while x < len(row):
            cell = row[x]
            ch = cell.get("char", " ")
            if ch == " " and not cell.get("bg") and not cell.get("reverse"):
                x += 1
                continue

            # Collect run of same style
            style = _cell_style(cell, fg)
            run_start = x
            run_chars = [ch]
            x += 1
            while x < len(row):
                next_cell = row[x]
                if _cell_style(next_cell, fg) == style:
                    run_chars.append(next_cell.get("char", " "))
                    x += 1
                else:
                    break

            text = "".join(run_chars)
            if not text.strip():
                continue

            tx = padding + run_start * char_width
            ty = content_y + y_idx * row_height + font_size

            is_reverse = cell.get("reverse", False)
            if is_reverse:
                text_color = cell.get("bg", bg)
            else:
                text_color = cell.get("fg", fg)

            attrs = [
                f'x="{tx}"',
                f'y="{ty}"',
                f'font-family="{font_family}"',
                f'font-size="{font_size}"',
                f'fill="{text_color}"',
            ]
            if cell.get("bold"):
                attrs.append('font-weight="bold"')
            if cell.get("italic"):
                attrs.append('font-style="italic"')

            text_escaped = html.escape(text)
            # Use xml:space to preserve whitespace in mixed runs
            parts.append(f'<text {" ".join(attrs)} xml:space="preserve">{text_escaped}</text>')

            if cell.get("underline"):
                uy = ty + 2
                uw = len(run_chars) * char_width
                parts.append(f'<line x1="{tx}" y1="{uy}" x2="{tx + uw}" y2="{uy}" '
                             f'stroke="{text_color}" stroke-width="1" />')

    parts.append('</svg>')
    return "\n".join(parts)


def _cell_style(cell, default_fg):
    """Return a hashable style key for grouping consecutive cells."""
    return (
        cell.get("fg", default_fg),
        cell.get("bg"),
        cell.get("bold", False),
        cell.get("italic", False),
        cell.get("underline", False),
        cell.get("reverse", False),
    )


def render_html(data, title=None):
    """Render terminal state to a standalone HTML file."""
    theme = data.get("theme", {})
    cols = data["cols"]
    cells = data["cells"]

    font_family = theme.get("font_family", "JetBrains Mono, Menlo, monospace")
    font_size = theme.get("font_size", 14)
    line_height = theme.get("line_height", 1.4)
    padding = theme.get("padding", 16)
    border_radius = theme.get("border_radius", 10)
    bg = theme.get("background", "#1e1e2e")
    fg = theme.get("foreground", "#cdd6f4")

    title_text = html.escape(title) if title else "Terminal"

    lines_html = []
    for row in cells:
        spans = []
        for cell in row:
            ch = cell.get("char", " ")
            styles = []
            if cell.get("fg"):
                styles.append(f"color:{cell['fg']}")
            if cell.get("bg"):
                styles.append(f"background:{cell['bg']}")
            if cell.get("bold"):
                styles.append("font-weight:bold")
            if cell.get("italic"):
                styles.append("font-style:italic")
            if cell.get("underline"):
                styles.append("text-decoration:underline")
            if cell.get("reverse"):
                fg_c = cell.get("fg", fg)
                bg_c = cell.get("bg", bg)
                styles.append(f"color:{bg_c};background:{fg_c}")

            if styles:
                spans.append(f'<span style="{";".join(styles)}">{html.escape(ch)}</span>')
            else:
                spans.append(html.escape(ch))
        lines_html.append("".join(spans))

    body = "\n".join(lines_html)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title_text}</title>
<style>
body {{ margin: 0; padding: 40px; background: #0e0e16; display: flex; justify-content: center; }}
.window {{
    background: {bg}; color: {fg};
    font-family: {font_family}; font-size: {font_size}px;
    line-height: {line_height};
    border-radius: {border_radius}px;
    overflow: hidden;
    box-shadow: 0 20px 60px rgba(0,0,0,0.5);
}}
.titlebar {{
    padding: 10px {padding}px;
    display: flex; align-items: center; gap: 8px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}}
.dot {{ width: 12px; height: 12px; border-radius: 50%; }}
.dot-red {{ background: #ff5f57; }}
.dot-yellow {{ background: #febc2e; }}
.dot-green {{ background: #28c840; }}
.titlebar .title {{ flex: 1; text-align: center; opacity: 0.5; font-size: {font_size - 1}px; }}
pre {{
    margin: 0; padding: {padding}px;
    white-space: pre; overflow-x: auto;
}}
</style>
</head>
<body>
<div class="window">
  <div class="titlebar">
    <div class="dot dot-red"></div>
    <div class="dot dot-yellow"></div>
    <div class="dot dot-green"></div>
    <div class="title">{title_text}</div>
  </div>
  <pre>{body}</pre>
</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Render terminal JSON to SVG/HTML")
    parser.add_argument("input", help="Input JSON file from capture.py")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.svg or .html)")
    parser.add_argument("--title", help="Window title text")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    if args.output.endswith(".html"):
        result = render_html(data, title=args.title)
    elif args.output.endswith(".svg"):
        result = render_svg(data, title=args.title)
    else:
        print("Output must be .svg or .html", file=sys.stderr)
        sys.exit(1)

    with open(args.output, "w") as f:
        f.write(result)
    print(f"Rendered {args.output} ({len(data['cells'])} rows × {data['cols']} cols)")


if __name__ == "__main__":
    main()
