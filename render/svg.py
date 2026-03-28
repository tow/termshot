"""Render captured terminal state to SVG."""

import html as html_mod
import re

_THEME_DEFAULTS = {
    "font_family": "JetBrains Mono, Fira Code, Menlo, monospace",
    "font_size": 14, "line_height": 1.4, "padding": 16,
    "border_radius": 10, "background": "#1e1e2e", "foreground": "#cdd6f4",
}

_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3,8}$')
_SAFE_FONT_RE = re.compile(r'^[a-zA-Z0-9 ,\-]+$')


def _safe_color(val, default):
    """Validate a color is a hex value, return default if not."""
    if isinstance(val, str) and _HEX_COLOR_RE.match(val):
        return val
    return default


def _safe_font(val, default):
    """Validate a font family string, return default if not safe."""
    if isinstance(val, str) and _SAFE_FONT_RE.match(val):
        return val
    return default


def _safe_num(val, default):
    """Validate a numeric value."""
    if isinstance(val, (int, float)) and val > 0:
        return val
    return default


def _theme(data):
    t = data.get("theme", {})
    d = _THEME_DEFAULTS
    return {
        "font_family": _safe_font(t.get("font_family"), d["font_family"]),
        "font_size": _safe_num(t.get("font_size"), d["font_size"]),
        "line_height": _safe_num(t.get("line_height"), d["line_height"]),
        "padding": _safe_num(t.get("padding"), d["padding"]),
        "border_radius": _safe_num(t.get("border_radius"), d["border_radius"]),
        "background": _safe_color(t.get("background"), d["background"]),
        "foreground": _safe_color(t.get("foreground"), d["foreground"]),
    }


def _cell_style(cell):
    return (
        cell.get("fg"), cell.get("bg"),
        cell.get("bold", False), cell.get("italic", False),
        cell.get("underline", False), cell.get("reverse", False),
    )


def render_svg(data, title=None):
    """Render terminal state to SVG string."""
    t = _theme(data)
    cols, rows, cells = data["cols"], data["rows"], data["cells"]

    font_family = t["font_family"]
    font_size = t["font_size"]
    padding = t["padding"]
    bg, fg = t["background"], t["foreground"]

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

    dot_y = 18
    for i, color in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        cx = padding + i * 20
        parts.append(f'<circle cx="{cx}" cy="{dot_y}" r="6" fill="{color}" />')

    if title:
        title_x = canvas_w / 2
        parts.append(f'<text x="{title_x}" y="{dot_y + 5}" '
                     f'text-anchor="middle" '
                     f'font-family="{font_family}" font-size="{font_size - 1}" '
                     f'fill="{fg}" opacity="0.6">{html_mod.escape(title)}</text>')

    sep_y = title_bar_h - 2
    parts.append(f'<line x1="0" y1="{sep_y}" x2="{canvas_w}" y2="{sep_y}" '
                 f'stroke="{fg}" stroke-opacity="0.1" />')

    for y_idx, row in enumerate(cells):
        for x_idx, cell in enumerate(row):
            cell_bg = _safe_color(cell.get("bg"), None)
            cell_fg = _safe_color(cell.get("fg"), None) or fg
            is_reverse = cell.get("reverse", False)

            rect_color = cell_fg if is_reverse else cell_bg
            if rect_color:
                rx = padding + x_idx * char_width
                ry = content_y + y_idx * row_height
                parts.append(f'<rect x="{rx}" y="{ry}" '
                             f'width="{char_width}" height="{row_height}" '
                             f'fill="{rect_color}" />')

        x = 0
        while x < len(row):
            cell = row[x]
            ch = cell.get("char", " ")
            if ch == " " and not cell.get("bg") and not cell.get("reverse"):
                x += 1
                continue

            style = _cell_style(cell)
            run_chars = [ch]
            x += 1
            while x < len(row) and _cell_style(row[x]) == style:
                run_chars.append(row[x].get("char", " "))
                x += 1

            text = "".join(run_chars)
            if not text.strip():
                continue

            tx = padding + (x - len(run_chars)) * char_width
            ty = content_y + y_idx * row_height + font_size

            is_reverse = cell.get("reverse", False)
            text_color = (_safe_color(cell.get("bg"), None) or bg) if is_reverse else (_safe_color(cell.get("fg"), None) or fg)

            attrs = [
                f'x="{tx}"', f'y="{ty}"',
                f'font-family="{font_family}"', f'font-size="{font_size}"',
                f'fill="{text_color}"',
            ]
            if cell.get("bold"):
                attrs.append('font-weight="bold"')
            if cell.get("italic"):
                attrs.append('font-style="italic"')

            parts.append(f'<text {" ".join(attrs)} xml:space="preserve">{html_mod.escape(text)}</text>')

            if cell.get("underline"):
                uy = ty + 2
                uw = len(run_chars) * char_width
                parts.append(f'<line x1="{tx}" y1="{uy}" x2="{tx + uw}" y2="{uy}" '
                             f'stroke="{text_color}" stroke-width="1" />')

    parts.append('</svg>')
    return "\n".join(parts)
