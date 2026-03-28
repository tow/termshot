"""Parse ANSI-formatted text (from kitty get-text --ansi) into cell data.

This replaces pyte for the capture path. The input is clean SGR-only ANSI
from `kitten @ get-text --ansi --extent=screen`, not raw terminal protocol.
"""

import re

# Matches any CSI sequence: ESC [ <params> <final byte>
# Params may use semicolons (standard) or colons (kitty/modern sub-parameters)
_CSI_RE = re.compile(r'\x1b\[([0-9;:]*)([A-Za-z])')
# Matches OSC sequences: ESC ] ... (BEL | ESC \)
_OSC_RE = re.compile(r'\x1b\].*?(?:\x07|\x1b\\)')


def parse_ansi_to_cells(text, cols, rows):
    """Parse ANSI text into a cells grid (list of rows, each a list of cell dicts).

    Only handles SGR (Select Graphic Rendition) sequences — the kind that
    `kitten @ get-text --ansi` produces. Other CSI/OSC sequences are ignored.
    """
    # Current style state
    fg = None
    bg = None
    bold = False
    italic = False
    underline = False
    reverse = False

    # Initialize grid with spaces
    grid = [[{"char": " "} for _ in range(cols)] for _ in range(rows)]

    # With --add-wrap-markers, \r marks a line wrap and \n marks a real
    # newline. Both mean "advance to the next screen row".
    screen_rows = re.split(r"\r|\n", text)

    for y, line in enumerate(screen_rows):
        if y >= rows:
            break

        x = 0
        i = 0
        while i < len(line) and x < cols:
            ch = line[i]

            if ch == "\x1b" and i + 1 < len(line):
                # Try CSI sequence
                m = _CSI_RE.match(line, i)
                if m:
                    if m.group(2) == "m":
                        _apply_sgr(m.group(1), locals_ref := {
                            "fg": fg, "bg": bg, "bold": bold,
                            "italic": italic, "underline": underline,
                            "reverse": reverse,
                        })
                        fg = locals_ref["fg"]
                        bg = locals_ref["bg"]
                        bold = locals_ref["bold"]
                        italic = locals_ref["italic"]
                        underline = locals_ref["underline"]
                        reverse = locals_ref["reverse"]
                    i = m.end()
                    continue

                # Try OSC sequence
                m = _OSC_RE.match(line, i)
                if m:
                    i = m.end()
                    continue

                # Unknown escape — skip ESC and next char
                i += 2
                continue

            # Regular character
            cell = {"char": ch}
            if fg:
                cell["fg"] = fg
            if bg:
                cell["bg"] = bg
            if bold:
                cell["bold"] = True
            if italic:
                cell["italic"] = True
            if underline:
                cell["underline"] = True
            if reverse:
                cell["reverse"] = True

            grid[y][x] = cell
            x += 1
            i += 1

    return grid


def _apply_sgr(params_str, state):
    """Apply SGR parameters to the style state dict.

    Handles both semicolon-separated params (38;2;r;g;b) and
    colon-separated sub-params (38:2:r:g:b) as used by kitty.
    """
    if not params_str:
        state["fg"] = None
        state["bg"] = None
        state["bold"] = False
        state["italic"] = False
        state["underline"] = False
        state["reverse"] = False
        return

    # Split on semicolons into groups. Each group may have colon sub-params.
    groups = params_str.split(";")
    i = 0
    while i < len(groups):
        parts = groups[i].split(":")
        try:
            p = int(parts[0])
        except ValueError:
            i += 1
            continue

        if p == 0:
            state["fg"] = None
            state["bg"] = None
            state["bold"] = False
            state["italic"] = False
            state["underline"] = False
            state["reverse"] = False
        elif p == 1:
            state["bold"] = True
        elif p == 3:
            state["italic"] = True
        elif p == 4:
            state["underline"] = True
        elif p == 7:
            state["reverse"] = True
        elif p == 22:
            state["bold"] = False
        elif p == 23:
            state["italic"] = False
        elif p == 24:
            state["underline"] = False
        elif p == 27:
            state["reverse"] = False
        elif 30 <= p <= 37:
            state["fg"] = _sgr_to_name(p - 30)
        elif p in (38, 48):
            key = "fg" if p == 38 else "bg"
            if len(parts) > 1:
                # Colon style: 38:2:r:g:b or 38:5:n
                color = _parse_color_subparams(parts[1:])
            else:
                # Semicolon style: 38;2;r;g;b — consume following groups
                remaining = [g for g in groups[i+1:]]
                color = _parse_color_subparams(remaining)
                if remaining and remaining[0] == "2":
                    i += 4  # skip 2;r;g;b
                elif remaining and remaining[0] == "5":
                    i += 2  # skip 5;n
            if color:
                state[key] = color
        elif p == 39:
            state["fg"] = None
        elif p == 49:
            state["bg"] = None
        elif 40 <= p <= 47:
            state["bg"] = _sgr_to_name(p - 40)
        elif 90 <= p <= 97:
            state["fg"] = _sgr_to_name(p - 90 + 8)
        elif 100 <= p <= 107:
            state["bg"] = _sgr_to_name(p - 100 + 8)

        i += 1


_ANSI_NAMES = [
    "black", "red", "green", "brown", "blue", "magenta", "cyan", "white",
    "brightblack", "brightred", "brightgreen", "brightyellow",
    "brightblue", "brightmagenta", "brightcyan", "brightwhite",
]


def _sgr_to_name(index):
    """Convert SGR color index (0-15) to color name."""
    if 0 <= index < len(_ANSI_NAMES):
        return _ANSI_NAMES[index]
    return None


def _parse_color_subparams(parts):
    """Parse color sub-parameters: [2, r, g, b] or [5, n].

    Works for both colon style (38:2:r:g:b) and semicolon style
    (where parts come from splitting on ;).
    """
    if not parts:
        return None
    try:
        mode = int(parts[0])
    except ValueError:
        return None

    if mode == 2 and len(parts) >= 4:
        try:
            r = int(parts[1])
            g = int(parts[2])
            b = int(parts[3])
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return None
    elif mode == 5 and len(parts) >= 2:
        try:
            n = int(parts[1])
            return _color256_to_hex(n)
        except ValueError:
            return None
    return None


def _color256_to_hex(n):
    """Convert 256-color index to hex string."""
    if n < 16:
        return _sgr_to_name(n)
    elif n < 232:
        # 6x6x6 color cube
        n -= 16
        b = (n % 6) * 51
        g = ((n // 6) % 6) * 51
        r = (n // 36) * 51
        return f"#{r:02x}{g:02x}{b:02x}"
    else:
        # Grayscale ramp
        v = (n - 232) * 10 + 8
        return f"#{v:02x}{v:02x}{v:02x}"
