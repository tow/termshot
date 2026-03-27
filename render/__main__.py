"""CLI entry point: python3 -m render capture.json -o output.ext"""

import argparse
import json
import os
import sys

from render import render_svg, render_html, render_ansi, render_png


def render_to_file(data, output_path, title=None, font_name="DejaVu Sans Mono",
                   font_size=14, terminal=None):
    """Render capture data to a file, choosing format by extension.

    Returns the format string ("svg", "html", "png", "ansi") on success.
    Raises ValueError for unsupported formats.
    """
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".html":
        with open(output_path, "w") as f:
            f.write(render_html(data, title=title))
        return "html"
    elif ext == ".svg":
        with open(output_path, "w") as f:
            f.write(render_svg(data, title=title))
        return "svg"
    elif ext == ".png":
        render_png(data, output_path,
                   font_name=font_name, font_size=font_size,
                   terminal=terminal)
        return "png"
    elif ext == ".ansi":
        with open(output_path, "w") as f:
            f.write(render_ansi(data))
        return "ansi"
    else:
        raise ValueError(f"Unsupported format: {ext!r} (use .svg, .html, .png, or .ansi)")


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

    fmt = args.output.rsplit(".", 1)[-1].lower()
    if fmt in ("png", "ansi") and args.title:
        print(f"Note: --title is not supported for {fmt.upper()} output", file=sys.stderr)

    try:
        render_to_file(data, args.output, title=args.title,
                       font_name=args.font, font_size=args.font_size,
                       terminal=args.terminal)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"Rendered {args.output} ({len(data['cells'])} rows \u00d7 {data['cols']} cols)")


if __name__ == "__main__":
    main()
