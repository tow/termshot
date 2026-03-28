"""Render captured terminal state to raw ANSI escape sequences."""


def render_ansi(data):
    """Convert captured JSON back to raw ANSI escape sequences."""
    lines = []
    for row in data["cells"]:
        parts = []
        prev_style = None
        for cell in row:
            sgr = ""
            sgr += _color_sgr(cell.get("fg"), "fg")
            sgr += _color_sgr(cell.get("bg"), "bg")
            if cell.get("bold"):
                sgr += "\x1b[1m"
            if cell.get("italic"):
                sgr += "\x1b[3m"
            if cell.get("underline"):
                sgr += "\x1b[4m"
            if cell.get("reverse"):
                sgr += "\x1b[7m"

            if sgr != prev_style:
                if prev_style is not None:
                    parts.append("\x1b[0m")
                if sgr:
                    parts.append(sgr)
                prev_style = sgr

            parts.append(cell.get("char", " "))

        parts.append("\x1b[0m")
        lines.append("".join(parts))

    return "\n".join(lines)


def _color_sgr(color, layer):
    """Convert a hex color to an ANSI truecolor SGR sequence."""
    if not color:
        return ""
    h = color.lstrip("#")
    if len(h) != 6:
        return ""
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return ""
    sgr = 38 if layer == "fg" else 48
    return f"\x1b[{sgr};2;{r};{g};{b}m"
