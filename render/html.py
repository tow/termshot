"""Render captured terminal state to a standalone HTML file."""

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
    if isinstance(val, str) and _HEX_COLOR_RE.match(val):
        return val
    return default


def _safe_font(val, default):
    if isinstance(val, str) and _SAFE_FONT_RE.match(val):
        return val
    return default


def _safe_num(val, default):
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


def render_html(data, title=None):
    """Render terminal state to a standalone HTML file."""
    t = _theme(data)
    cells = data["cells"]

    font_family = t["font_family"]
    font_size = t["font_size"]
    line_height = t["line_height"]
    padding = t["padding"]
    border_radius = t["border_radius"]
    bg, fg = t["background"], t["foreground"]

    title_text = html_mod.escape(title) if title else "Terminal"

    lines_html = []
    for row in cells:
        spans = []
        for cell in row:
            ch = cell.get("char", " ")
            styles = []
            cell_fg = _safe_color(cell.get("fg"), None)
            cell_bg = _safe_color(cell.get("bg"), None)

            if cell.get("reverse"):
                styles.append(f"color:{cell_bg or bg};background:{cell_fg or fg}")
            else:
                if cell_fg:
                    styles.append(f"color:{cell_fg}")
                if cell_bg:
                    styles.append(f"background:{cell_bg}")

            if cell.get("bold"):
                styles.append("font-weight:bold")
            if cell.get("italic"):
                styles.append("font-style:italic")
            if cell.get("underline"):
                styles.append("text-decoration:underline")

            if styles:
                spans.append(f'<span style="{";".join(styles)}">{html_mod.escape(ch)}</span>')
            else:
                spans.append(html_mod.escape(ch))
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
