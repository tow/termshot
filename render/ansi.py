"""Render captured terminal state to raw ANSI escape sequences."""

from colors import color_to_ansi


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
            sgr = ""
            sgr += color_to_ansi(cell.get("fg"), "fg")
            sgr += color_to_ansi(cell.get("bg"), "bg")
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
