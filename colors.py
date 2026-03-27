"""
Shared color definitions and resolution for the termshot pipeline.

Single source of truth for:
- The 16 ANSI named colors (xterm defaults)
- SGR escape code mapping (fg 30-37/90-97, bg 40-47/100-107)
- Resolving raw pyte color values to CSS hex
- Converting raw pyte colors to ANSI SGR escape sequences
- Converting raw pyte colors to curses init_color args
"""


# The 16 basic ANSI named colors in SGR order (black=0 .. white=7,
# brightblack=8 .. brightwhite=15). "yellow" is an alias for "brown"
# (pyte's name for SGR color 3) and is added separately so it doesn't
# shift the SGR index enumeration.
_ANSI_16_ORDERED = [
    ("black",         "#000000",  (0,   0,   0)),
    ("red",           "#cd0000",  (205, 0,   0)),
    ("green",         "#00cd00",  (0,   205, 0)),
    ("brown",         "#cdcd00",  (205, 205, 0)),
    ("blue",          "#0000ee",  (0,   0,   238)),
    ("magenta",       "#cd00cd",  (205, 0,   205)),
    ("cyan",          "#00cdcd",  (0,   205, 205)),
    ("white",         "#e5e5e5",  (229, 229, 229)),
    ("brightblack",   "#7f7f7f",  (127, 127, 127)),
    ("brightred",     "#ff0000",  (255, 0,   0)),
    ("brightgreen",   "#00ff00",  (0,   255, 0)),
    ("brightyellow",  "#ffff00",  (255, 255, 0)),
    ("brightblue",    "#5c5cff",  (92,  92,  255)),
    ("brightmagenta", "#ff00ff",  (255, 0,   255)),
    ("brightcyan",    "#00ffff",  (0,   255, 255)),
    ("brightwhite",   "#ffffff",  (255, 255, 255)),
]

# Name -> CSS hex
ANSI_16 = {name: hex_val for name, hex_val, _ in _ANSI_16_ORDERED}
ANSI_16["yellow"] = ANSI_16["brown"]

# Name -> (R, G, B) in 0-255
ANSI_16_RGB = {name: rgb for name, _, rgb in _ANSI_16_ORDERED}
ANSI_16_RGB["yellow"] = ANSI_16_RGB["brown"]

# SGR codes for foreground/background.
# Normal colors: fg 30-37 / bg 40-47. Bright: fg 90-97 / bg 100-107.
ANSI_FG_CODES = {}
ANSI_BG_CODES = {}
for _i, (_name, _, _) in enumerate(_ANSI_16_ORDERED):
    if _i >= 8:
        ANSI_FG_CODES[_name] = str(90 + _i - 8)
        ANSI_BG_CODES[_name] = str(100 + _i - 8)
    else:
        ANSI_FG_CODES[_name] = str(30 + _i)
        ANSI_BG_CODES[_name] = str(40 + _i)
ANSI_FG_CODES["yellow"] = ANSI_FG_CODES["brown"]
ANSI_BG_CODES["yellow"] = ANSI_BG_CODES["brown"]


def is_bare_hex(s):
    """Check if string is a bare hex color (6 hex digits, no # prefix)."""
    if not isinstance(s, str) or len(s) != 6:
        return False
    try:
        int(s, 16)
        return True
    except ValueError:
        return False


def normalize_color(color_value):
    """Store the raw pyte color value, only skipping 'default'.

    Used at capture time to decide what goes into the JSON.
    """
    if not color_value or color_value == "default":
        return None
    return color_value


def resolve_color(raw):
    """Resolve a pyte color value to a CSS hex color, or None for 'default'.

    pyte stores colors in three formats:
    - True color (24-bit RGB): bare hex like 'ff8c00'
    - 256-color: also resolved to bare hex by pyte (e.g. 'ff8700')
    - Basic 16 ANSI: a name like 'red', 'blue', 'brown'

    True color and 256-color values pass through exactly -- the TUI's own
    colors are preserved. Only the 16 named ANSI colors need mapping, and
    those are terminal-theme-dependent (we use xterm defaults).
    """
    if not raw or raw == "default":
        return None
    if isinstance(raw, str) and raw.startswith("#"):
        return raw
    if isinstance(raw, str) and is_bare_hex(raw):
        return f"#{raw}"
    if isinstance(raw, str) and raw.lower() in ANSI_16:
        return ANSI_16[raw.lower()]
    return None


def color_to_ansi(raw, layer="fg"):
    """Convert a raw pyte color to an ANSI SGR escape sequence.

    layer: "fg" for foreground (SGR 38), "bg" for background (SGR 48).
    """
    if not raw or raw == "default":
        return ""
    codes = ANSI_FG_CODES if layer == "fg" else ANSI_BG_CODES
    if isinstance(raw, str) and raw.lower() in codes:
        return f"\x1b[{codes[raw.lower()]}m"
    hex_val = raw.lstrip("#") if isinstance(raw, str) else raw
    if isinstance(hex_val, str) and len(hex_val) == 6 and is_bare_hex(hex_val):
        r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
        sgr = 38 if layer == "fg" else 48
        return f"\x1b[{sgr};2;{r};{g};{b}m"
    return ""


def color_to_curses(raw):
    """Convert a raw pyte color to curses init_color args.

    Returns (r, g, b) scaled to 0-1000, or None for default.
    """
    if not raw or raw == "default":
        return None

    if isinstance(raw, str) and raw.lower() in ANSI_16_RGB:
        r, g, b = ANSI_16_RGB[raw.lower()]
        return (r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)

    if isinstance(raw, str):
        h = raw.lstrip("#")
        if len(h) == 6 and is_bare_hex(h):
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            return (r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)

    return None
