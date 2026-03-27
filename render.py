#!/usr/bin/env python3
"""
Render a captured (and optionally edited) terminal state to SVG, HTML, PNG, or ANSI.

Usage:
    python3 render.py capture.json -o mockup.svg
    python3 render.py capture.json -o mockup.html --title "My App v2.0"
    python3 render.py capture.json -o mockup.png --font "DejaVu Sans Mono"
    python3 render.py capture.json -o mockup.ansi

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


# The 16 basic ANSI named colors — the ONLY colors that are
# terminal-theme-dependent. Apps that care about exact colors use
# truecolor or 256-color indices instead, which pyte resolves to
# exact hex values that pass through without any mapping.
#
# This table is the single source of truth for named ANSI color mapping.
# The hex values are standard xterm defaults. The SGR code mapping
# derives from the key order (black=0, red=1, ...).
# The 16 basic ANSI named colors in SGR order (black=0 .. white=7,
# brightblack=8 .. brightwhite=15). "yellow" is an alias for "brown"
# (pyte's name for SGR color 3) and is added separately so it doesn't
# shift the SGR index enumeration.
_ANSI_16_ORDERED = [
    ("black",         "#000000"),
    ("red",           "#cd0000"),
    ("green",         "#00cd00"),
    ("brown",         "#cdcd00"),   # pyte calls SGR yellow "brown"
    ("blue",          "#0000ee"),
    ("magenta",       "#cd00cd"),
    ("cyan",          "#00cdcd"),
    ("white",         "#e5e5e5"),
    ("brightblack",   "#7f7f7f"),
    ("brightred",     "#ff0000"),
    ("brightgreen",   "#00ff00"),
    ("brightyellow",  "#ffff00"),
    ("brightblue",    "#5c5cff"),
    ("brightmagenta", "#ff00ff"),
    ("brightcyan",    "#00ffff"),
    ("brightwhite",   "#ffffff"),
]

ANSI_16 = {name: hex_val for name, hex_val in _ANSI_16_ORDERED}
ANSI_16["yellow"] = ANSI_16["brown"]  # alias

# SGR codes for foreground/background, derived from the ordered list.
# Normal colors: fg 30-37 / bg 40-47. Bright: fg 90-97 / bg 100-107.
_ANSI_FG_CODES = {}
_ANSI_BG_CODES = {}
for _i, (_name, _) in enumerate(_ANSI_16_ORDERED):
    if _i >= 8:
        _ANSI_FG_CODES[_name] = str(90 + _i - 8)
        _ANSI_BG_CODES[_name] = str(100 + _i - 8)
    else:
        _ANSI_FG_CODES[_name] = str(30 + _i)
        _ANSI_BG_CODES[_name] = str(40 + _i)
_ANSI_FG_CODES["yellow"] = _ANSI_FG_CODES["brown"]
_ANSI_BG_CODES["yellow"] = _ANSI_BG_CODES["brown"]


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


def _color_to_ansi(raw, layer="fg"):
    """Convert a raw pyte color to an ANSI escape sequence.

    layer: "fg" for foreground (SGR 38), "bg" for background (SGR 48).
    """
    if not raw or raw == "default":
        return ""
    codes = _ANSI_FG_CODES if layer == "fg" else _ANSI_BG_CODES
    if isinstance(raw, str) and raw.lower() in codes:
        return f"\x1b[{codes[raw.lower()]}m"
    # Bare hex (truecolor from pyte) or #hex
    hex_val = raw.lstrip("#") if isinstance(raw, str) else raw
    if isinstance(hex_val, str) and len(hex_val) == 6 and _is_bare_hex(hex_val):
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        sgr = 38 if layer == "fg" else 48
        return f"\x1b[{sgr};2;{r};{g};{b}m"
    return ""


def render_ansi(data):
    """Convert captured JSON back to raw ANSI escape sequences.

    Output can be cat'd in any terminal for pixel-perfect rendering,
    then screenshotted with the terminal's own font and theme.
    """
    lines = []
    for row in data["cells"]:
        parts = []
        prev_style = None
        for cell in row:
            # Build style string for this cell
            sgr = ""
            sgr += _color_to_ansi(cell.get("fg"), "fg")
            sgr += _color_to_ansi(cell.get("bg"), "bg")
            if cell.get("bold"):
                sgr += "\x1b[1m"
            if cell.get("italic"):
                sgr += "\x1b[3m"
            if cell.get("underline"):
                sgr += "\x1b[4m"
            if cell.get("reverse"):
                sgr += "\x1b[7m"

            # Only emit reset + new style when style changes
            if sgr != prev_style:
                if prev_style is not None:
                    parts.append("\x1b[0m")
                if sgr:
                    parts.append(sgr)
                prev_style = sgr

            parts.append(cell.get("char", " "))

        parts.append("\x1b[0m")  # reset at end of line
        lines.append("".join(parts))

    return "\n".join(lines)


def _build_terminal_cmd(terminal, font_name, font_size, bg, fg, cols, rows, ansi_path):
    """Build the command to launch a terminal displaying the ANSI file."""
    from shlex import quote
    shell_cmd = f"printf '\\033[?25l'; cat {quote(ansi_path)}; sleep 10"

    if terminal == "urxvt":
        return [
            "urxvt",
            "-fn", f"xft:{font_name}:size={font_size}",
            "-bg", bg,
            "-fg", fg,
            "-geometry", f"{cols + 2}x{rows + 1}",
            "-b", "0",
            "-bl",
            "+sb",
            "-e", "bash", "-c", shell_cmd,
        ]
    else:  # xterm
        return [
            "xterm",
            "-fa", font_name,
            "-fs", str(font_size),
            "-bg", bg,
            "-fg", fg,
            "-geometry", f"{cols + 2}x{rows + 1}",
            "+sb",
            "-b", "0",
            "-bw", "0",
            "-e", shell_cmd,
        ]


def _detect_terminal():
    """Pick the best available terminal for headless rendering."""
    import shutil
    for term in ["urxvt", "xterm"]:
        if shutil.which(term):
            return term
    return None


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG via a headless terminal.

    Launches Xvfb + a real terminal emulator, cats the ANSI output, and
    screenshots the window with ImageMagick. The terminal handles all font
    rendering, Unicode, colors, and character alignment.

    Prefers urxvt (better Unicode/box-drawing) over xterm.
    """
    import shutil
    import subprocess
    import tempfile
    import time

    for tool in ["Xvfb", "xdotool", "import"]:
        if not shutil.which(tool):
            print(f"Error: {tool} not found. Install with: apt-get install xvfb xdotool imagemagick",
                  file=sys.stderr)
            sys.exit(1)

    if terminal is None:
        terminal = _detect_terminal()
    if terminal is None or not shutil.which(terminal):
        print(f"Error: no terminal found. Install urxvt or xterm.", file=sys.stderr)
        sys.exit(1)

    t = _get_theme(data)
    ansi_content = render_ansi(data)
    cols = data["cols"]
    rows = data["rows"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    # Find a free display number by checking lock files
    display_num = None
    for candidate in range(10, 100):
        if not os.path.exists(f"/tmp/.X{candidate}-lock"):
            display_num = candidate
            break
    if display_num is None:
        print("Error: no free X display number found", file=sys.stderr)
        sys.exit(1)

    xvfb = None
    term_proc = None
    try:
        xvfb = subprocess.Popen(
            ["Xvfb", f":{display_num}", "-screen", "0", "1920x1080x24"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(0.5)

        env = os.environ.copy()
        env["DISPLAY"] = f":{display_num}"
        env["LC_ALL"] = "C.utf8"
        env["LANG"] = "C.utf8"

        cmd = _build_terminal_cmd(
            terminal, font_name, font_size,
            t["background"], t["foreground"],
            cols, rows, ansi_path,
        )
        term_proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        result = subprocess.run(
            ["xdotool", "search", "--pid", str(term_proc.pid)],
            env=env, capture_output=True, text=True,
        )
        window_ids = result.stdout.strip().split("\n")
        window_id = window_ids[0] if window_ids[0] else ""

        if not window_id:
            print(f"Error: {terminal} window not found (process may have crashed)",
                  file=sys.stderr)
            sys.exit(1)

        subprocess.run(
            ["import", "-window", window_id, output_path],
            env=env, check=True,
        )
    finally:
        if term_proc:
            term_proc.kill()
        if xvfb:
            xvfb.kill()
        os.unlink(ansi_path)


def main():
    parser = argparse.ArgumentParser(description="Render terminal JSON to SVG/HTML/PNG/ANSI")
    parser.add_argument("input", help="Input JSON file from capture.py")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.svg, .html, .png, or .ansi)")
    parser.add_argument("--title", help="Window title text (SVG/HTML only)")
    parser.add_argument("--font", default="DejaVu Sans Mono",
                        help="Font name for PNG rendering (default: DejaVu Sans Mono)")
    parser.add_argument("--font-size", type=int, default=14,
                        help="Font size for PNG rendering (default: 14)")
    parser.add_argument("--terminal", choices=["urxvt", "xterm"],
                        help="Terminal for PNG rendering (default: auto-detect, prefers urxvt)")
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
        if args.title:
            print("Note: --title is not supported for PNG output", file=sys.stderr)
        render_png(data, args.output,
                   font_name=args.font, font_size=args.font_size,
                   terminal=args.terminal)
    elif ext == ".ansi":
        if args.title:
            print("Note: --title is not supported for ANSI output", file=sys.stderr)
        result = render_ansi(data)
        with open(args.output, "w") as f:
            f.write(result)
    else:
        print("Output must be .svg, .html, .png, or .ansi", file=sys.stderr)
        sys.exit(1)

    print(f"Rendered {args.output} ({len(data['cells'])} rows × {data['cols']} cols)")


if __name__ == "__main__":
    main()
