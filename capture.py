#!/usr/bin/env python3
"""
Capture a TUI application's screen state to a JSON file.

Usage:
    python3 capture.py <command> [--cols 80] [--rows 24] [--wait 1.0] -o output.json

Examples:
    python3 capture.py "htop" -o htop.json
    python3 capture.py "ls --color=always -la" -o ls.json
    python3 capture.py "python3 my_tui.py" --cols 120 --rows 40 -o tui.json
"""

import argparse
import json

from session import Session


def main():
    parser = argparse.ArgumentParser(description="Capture a TUI to JSON")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("--cols", type=int, default=80, help="Terminal columns")
    parser.add_argument("--rows", type=int, default=24, help="Terminal rows")
    parser.add_argument("--wait", type=float, default=1.5,
                        help="Seconds to wait for output to settle")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    args = parser.parse_args()

    print(f"Capturing: {args.command} ({args.cols}x{args.rows})")
    with Session(args.command, cols=args.cols, rows=args.rows) as sess:
        sess.wait_for_stable(settle_time=args.wait)
        data = sess.to_dict()

    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {args.output}")
    print(f"Now edit the JSON, then run: python3 render.py {args.output} -o mockup.png")


if __name__ == "__main__":
    main()
