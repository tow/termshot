#!/usr/bin/env python3
"""
Render a captured (and optionally edited) terminal state to SVG or HTML.

Usage:
    python3 render.py capture.json -o mockup.svg
    python3 render.py capture.json -o mockup.html
    python3 render.py capture.json -o mockup.svg --title "My App v2.0"

The renderer resolves raw ANSI color names/indices from pyte into hex values
using the standard xterm-256color palette. The TUI's own colors are preserved
faithfully — no custom theme is imposed on the captured content.

Rendering options (font, padding, window chrome) can be overridden via a
"theme" key in the JSON if present, but these only affect the surrounding
window — never the cell colors.
"""

import argparse
import html
import json
import os
import sys


# Fallback for the 16 basic ANSI named colors.
# These are the ONLY colors that are terminal-theme-dependent — the actual
# shade of "blue" or "red" varies by terminal emulator and color scheme.
# We use xterm defaults here. Apps that care about exact colors use
# truecolor (24-bit RGB) or 256-color indices instead, both of which pyte
# resolves to exact hex values that pass through without any mapping.
ANSI_16 = {
    "black":         "#000000",
    "red":           "#cd0000",
    "green":         "#00cd00",
    "brown":         "#cdcd00",  # pyte calls SGR yellow "brown"
    "yellow":        "#cdcd00",
    "blue":          "#0000ee",
    "magenta":       "#cd00cd",
    "cyan":          "#00cdcd",
    "white":         "#e5e5e5",
    "brightblack":   "#7f7f7f",
    "brightred":     "#ff0000",
    "brightgreen":   "#00ff00",
    "brightyellow":  "#ffff00",
    "brightblue":    "#5c5cff",
    "brightmagenta": "#ff00ff",
    "brightcyan":    "#00ffff",
    "brightwhite":   "#ffffff",
}


def _is_bare_hex(s):
    """Check if string is a bare hex color (6 hex digits, no # prefix)."""
    if len(s) != 6:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def resolve_color(raw):
    """Resolve a pyte color value to a CSS hex color, or None for 'default'.

    pyte stores colors in three formats:
    - True color (24-bit RGB): bare hex like 'ff8c00'
    - 256-color: also resolved to bare hex by pyte (e.g. 'ff8700')
    - Basic 16 ANSI: a name like 'red', 'blue', 'brown'

    True color and 256-color values pass through exactly — the TUI's own
    colors are preserved. Only the 16 named ANSI colors need mapping, and
    those are terminal-theme-dependent (we use xterm defaults).
    """
    if not raw or raw == "default":
        return None
    if isinstance(raw, str) and raw.startswith("#"):
        return raw
    # Bare hex from pyte (truecolor and 256-color both arrive this way)
    if isinstance(raw, str) and _is_bare_hex(raw):
        return f"#{raw}"
    # Named ANSI color (the only theme-dependent case)
    if isinstance(raw, str) and raw.lower() in ANSI_16:
        return ANSI_16[raw.lower()]
    return None


def _get_theme(data):
    """Extract rendering theme with defaults. Only affects window chrome, not cell colors."""
    theme = data.get("theme", {})
    return {
        "font_family": theme.get("font_family", "JetBrains Mono, Fira Code, Menlo, monospace"),
        "font_size": theme.get("font_size", 14),
        "line_height": theme.get("line_height", 1.4),
        "padding": theme.get("padding", 16),
        "border_radius": theme.get("border_radius", 10),
        "background": theme.get("background", "#1e1e2e"),
        "foreground": theme.get("foreground", "#cdd6f4"),
    }


def render_svg(data, title=None):
    """Render terminal state to SVG string."""
    t = _get_theme(data)
    cols = data["cols"]
    rows = data["rows"]
    cells = data["cells"]

    font_family = t["font_family"]
    font_size = t["font_size"]
    padding = t["padding"]
    bg = t["background"]
    fg = t["foreground"]

    char_width = font_size * 0.6
    row_height = font_size * t["line_height"]

    title_bar_h = 40 if title is not None else 36
    content_y = title_bar_h + padding

    canvas_w = padding * 2 + cols * char_width
    canvas_h = content_y + rows * row_height + padding

    parts = []
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'width="{canvas_w}" height="{canvas_h}" '
                 f'viewBox="0 0 {canvas_w} {canvas_h}">')

    parts.append(f'<rect width="{canvas_w}" height="{canvas_h}" rx="{t["border_radius"]}" '
                 f'fill="{bg}" />')

    # Window dots
    dot_y = 18
    for i, color in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        cx = padding + i * 20
        parts.append(f'<circle cx="{cx}" cy="{dot_y}" r="6" fill="{color}" />')

    if title:
        title_x = canvas_w / 2
        parts.append(f'<text x="{title_x}" y="{dot_y + 5}" '
                     f'text-anchor="middle" '
                     f'font-family="{font_family}" font-size="{font_size - 1}" '
                     f'fill="{fg}" opacity="0.6">{html.escape(title)}</text>')

    sep_y = title_bar_h - 2
    parts.append(f'<line x1="0" y1="{sep_y}" x2="{canvas_w}" y2="{sep_y}" '
                 f'stroke="{fg}" stroke-opacity="0.1" />')

    for y_idx, row in enumerate(cells):
        # Background rectangles
        for x_idx, cell in enumerate(row):
            cell_bg = resolve_color(cell.get("bg"))
            is_reverse = cell.get("reverse", False)
            cell_fg = resolve_color(cell.get("fg")) or fg

            if is_reverse:
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

        # Text spans — group consecutive same-style chars
        x = 0
        while x < len(row):
            cell = row[x]
            ch = cell.get("char", " ")
            if ch == " " and not cell.get("bg") and not cell.get("reverse"):
                x += 1
                continue

            style = _cell_style(cell)
            run_start = x
            run_chars = [ch]
            x += 1
            while x < len(row):
                if _cell_style(row[x]) == style:
                    run_chars.append(row[x].get("char", " "))
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
                text_color = resolve_color(cell.get("bg")) or bg
            else:
                text_color = resolve_color(cell.get("fg")) or fg

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

            parts.append(f'<text {" ".join(attrs)} xml:space="preserve">{html.escape(text)}</text>')

            if cell.get("underline"):
                uy = ty + 2
                uw = len(run_chars) * char_width
                parts.append(f'<line x1="{tx}" y1="{uy}" x2="{tx + uw}" y2="{uy}" '
                             f'stroke="{text_color}" stroke-width="1" />')

    parts.append('</svg>')
    return "\n".join(parts)


def _cell_style(cell):
    """Return a hashable style key for grouping consecutive cells."""
    return (
        cell.get("fg"),
        cell.get("bg"),
        cell.get("bold", False),
        cell.get("italic", False),
        cell.get("underline", False),
        cell.get("reverse", False),
    )


def render_html(data, title=None):
    """Render terminal state to a standalone HTML file."""
    t = _get_theme(data)
    cells = data["cells"]

    font_family = t["font_family"]
    font_size = t["font_size"]
    line_height = t["line_height"]
    padding = t["padding"]
    border_radius = t["border_radius"]
    bg = t["background"]
    fg = t["foreground"]

    title_text = html.escape(title) if title else "Terminal"

    lines_html = []
    for row in cells:
        spans = []
        for cell in row:
            ch = cell.get("char", " ")
            styles = []
            resolved_fg = resolve_color(cell.get("fg"))
            resolved_bg = resolve_color(cell.get("bg"))

            if cell.get("reverse"):
                styles.append(f"color:{resolved_bg or bg};background:{resolved_fg or fg}")
            else:
                if resolved_fg:
                    styles.append(f"color:{resolved_fg}")
                if resolved_bg:
                    styles.append(f"background:{resolved_bg}")

            if cell.get("bold"):
                styles.append("font-weight:bold")
            if cell.get("italic"):
                styles.append("font-style:italic")
            if cell.get("underline"):
                styles.append("text-decoration:underline")

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


def _find_font(bold=False):
    """Find a monospace TTF font with good Unicode coverage."""
    candidates = [
        # Prefer DejaVu — excellent Unicode coverage (box drawing, braille, symbols)
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def render_png(data, output_path, title=None, scale=2):
    """Render terminal state to PNG with Pillow.

    Draws each character cell directly using a monospace font.
    Scale factor controls resolution (2 = retina).
    """
    from PIL import Image, ImageDraw, ImageFont

    t = _get_theme(data)
    cols = data["cols"]
    rows = data["rows"]
    cells = data["cells"]

    font_size = t["font_size"] * scale
    padding = t["padding"] * scale
    bg = t["background"]
    fg = t["foreground"]
    border_radius = t["border_radius"] * scale

    font_path = _find_font(bold=False)
    bold_font_path = _find_font(bold=True)

    if font_path:
        font = ImageFont.truetype(font_path, font_size)
        bold_font = ImageFont.truetype(bold_font_path or font_path, font_size)
    else:
        font = ImageFont.load_default()
        bold_font = font

    # Measure character cell size from the font
    bbox = font.getbbox("M")
    char_w = bbox[2] - bbox[0]
    char_h = int(font_size * t["line_height"])

    # Title bar
    title_bar_h = int(40 * scale) if title else int(36 * scale)
    content_y = title_bar_h + padding

    canvas_w = padding * 2 + cols * char_w
    canvas_h = content_y + rows * char_h + padding

    img = Image.new("RGB", (canvas_w, canvas_h), bg)
    draw = ImageDraw.Draw(img)

    # Round corners — draw rounded rect background
    draw.rounded_rectangle(
        [(0, 0), (canvas_w - 1, canvas_h - 1)],
        radius=border_radius,
        fill=bg,
    )

    # Window dots
    dot_r = 6 * scale
    dot_y = 18 * scale
    for i, color in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        cx = padding + i * 20 * scale
        draw.ellipse(
            [cx - dot_r, dot_y - dot_r, cx + dot_r, dot_y + dot_r],
            fill=color,
        )

    # Title text
    if title:
        title_font = ImageFont.truetype(font_path, int(font_size * 0.9)) if font_path else font
        tb = title_font.getbbox(title)
        tw = tb[2] - tb[0]
        draw.text(
            ((canvas_w - tw) // 2, dot_y - int(font_size * 0.35)),
            title,
            fill=fg + "99",  # slight transparency via alpha hex
            font=title_font,
        )

    # Separator line
    sep_y = title_bar_h - 2 * scale
    draw.line([(0, sep_y), (canvas_w, sep_y)], fill=fg + "1a", width=1)

    # Draw cells
    for y_idx, row in enumerate(cells):
        for x_idx, cell in enumerate(row):
            px = padding + x_idx * char_w
            py = content_y + y_idx * char_h

            # Background
            cell_bg = resolve_color(cell.get("bg"))
            cell_fg_color = resolve_color(cell.get("fg")) or fg
            is_reverse = cell.get("reverse", False)

            if is_reverse:
                rect_color = cell_fg_color
                text_color = resolve_color(cell.get("bg")) or bg
            else:
                rect_color = cell_bg
                text_color = cell_fg_color

            if rect_color:
                draw.rectangle([px, py, px + char_w, py + char_h], fill=rect_color)

            # Character
            ch = cell.get("char", " ")
            if ch and ch != " ":
                use_font = bold_font if cell.get("bold") else font
                draw.text((px, py), ch, fill=text_color, font=use_font)

                # Underline
                if cell.get("underline"):
                    uy = py + char_h - 2 * scale
                    draw.line([(px, uy), (px + char_w, uy)], fill=text_color, width=scale)

    img.save(output_path)


def main():
    parser = argparse.ArgumentParser(description="Render terminal JSON to SVG/HTML/PNG")
    parser.add_argument("input", help="Input JSON file from capture.py")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.svg, .html, or .png)")
    parser.add_argument("--title", help="Window title text")
    parser.add_argument("--scale", type=int, default=2,
                        help="PNG pixel scale factor (default 2 for retina)")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    ext = os.path.splitext(args.output)[1].lower()
    if ext == ".html":
        result = render_html(data, title=args.title)
        with open(args.output, "w") as f:
            f.write(result)
    elif ext == ".svg":
        result = render_svg(data, title=args.title)
        with open(args.output, "w") as f:
            f.write(result)
    elif ext == ".png":
        render_png(data, args.output, title=args.title, scale=args.scale)
    else:
        print("Output must be .svg, .html, or .png", file=sys.stderr)
        sys.exit(1)

    print(f"Rendered {args.output} ({len(data['cells'])} rows × {data['cols']} cols)")


if __name__ == "__main__":
    main()
