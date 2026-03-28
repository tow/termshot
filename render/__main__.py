"""CLI entry point: python3 -m render capture.json -o output.ext"""

import argparse
import json
import sys

from render import render_to_file


def main():
    parser = argparse.ArgumentParser(description="Render terminal JSON to SVG/HTML/PNG/ANSI")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.svg, .html, .png, or .ansi)")
    parser.add_argument("--title", help="Window title text (SVG/HTML only)")
    parser.add_argument("--font", default="DejaVu Sans Mono",
                        help="Font name for PNG rendering (default: DejaVu Sans Mono)")
    parser.add_argument("--font-size", type=int, default=14,
                        help="Font size for PNG rendering (default: 14)")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    try:
        render_to_file(data, args.output, title=args.title,
                       font_name=args.font, font_size=args.font_size)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"Rendered {args.output} ({len(data['cells'])} rows × {data['cols']} cols)")


if __name__ == "__main__":
    main()
