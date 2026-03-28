"""CLI entry point: python3 -m render capture.json -o output.ext"""

import argparse
import sys

from render import render_to_file


def main():
    parser = argparse.ArgumentParser(description="Render terminal JSON to SVG/HTML/PNG/ANSI")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.svg, .html, .png, or .ansi)")
    parser.add_argument("--title", help="Window title text (SVG/HTML only)")
    args = parser.parse_args()

    from capture import load, CaptureValidationError
    try:
        data = load(args.input)
    except CaptureValidationError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        render_to_file(data, args.output, title=args.title)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print(f"Rendered {args.output} ({len(data['cells'])} rows × {data['cols']} cols)")


if __name__ == "__main__":
    main()
