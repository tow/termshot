"""CLI entry point: python3 -m render capture.json -o output.ext"""

import argparse
import json
import os
import sys

from render import render_svg, render_html, render_ansi, render_png


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
