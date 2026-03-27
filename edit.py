#!/usr/bin/env python3
"""
Quick text edits on a captured terminal JSON without hand-editing cells.

Usage:
    # Replace text in a specific row (0-indexed)
    python3 edit.py capture.json --replace 0 "old text" "new text" -o edited.json

    # Replace text anywhere in the capture
    python3 edit.py capture.json --replace-all "old text" "new text" -o edited.json

    # Set text at a specific position (row, col), inheriting style from that position
    python3 edit.py capture.json --set 5 10 "Hello World" -o edited.json

    # Clear a row
    python3 edit.py capture.json --clear-row 3 -o edited.json

    # Multiple edits (applied in order)
    python3 edit.py capture.json \
        --replace-all "v1.0" "v2.0" \
        --set 0 30 "MOCKUP" \
        -o edited.json

    # Print the capture as plain text (for quick inspection)
    python3 edit.py capture.json --print
"""

import argparse
import json
import sys


def load(path):
    with open(path) as f:
        return json.load(f)


def save(data, path):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def to_text(data):
    """Convert capture to plain text for inspection."""
    lines = []
    for row in data["cells"]:
        lines.append("".join(cell.get("char", " ") for cell in row).rstrip())
    return "\n".join(lines)


def replace_in_row(data, row_idx, old, new):
    """Replace first occurrence of text in a specific row, preserving cell styles.

    If new is shorter than old, fills remainder with spaces.
    If new is longer than old, truncates to fit the original span.
    Returns the column index after the replacement (for chained calls), or -1 if not found.
    """
    row = data["cells"][row_idx]
    line = "".join(cell.get("char", " ") for cell in row)
    start = line.find(old)
    if start == -1:
        return -1

    span = len(old)
    for i in range(span):
        col = start + i
        if col < len(row):
            row[col]["char"] = new[i] if i < len(new) else " "

    return start + span


def replace_all(data, old, new):
    """Replace text in all rows."""
    count = 0
    for row_idx in range(len(data["cells"])):
        while True:
            row = data["cells"][row_idx]
            line = "".join(cell.get("char", " ") for cell in row)
            pos = line.find(old)
            if pos == -1:
                break
            end = replace_in_row(data, row_idx, old, new)
            if end == -1:
                break
            count += 1
            # If new contains old, we'd loop forever — check remaining text only
            remaining = line[end:]
            if old in new and old not in remaining:
                break
    return count


def set_text(data, row_idx, col_idx, text):
    """Set text at a position, inheriting the style of the first cell."""
    row = data["cells"][row_idx]
    if col_idx >= len(row):
        return
    # Get style from the target position
    ref_cell = row[col_idx]
    style = {k: v for k, v in ref_cell.items() if k != "char"}

    for i, ch in enumerate(text):
        col = col_idx + i
        if col >= len(row):
            break
        # Keep existing style if present, otherwise use reference style
        existing_style = {k: v for k, v in row[col].items() if k != "char"}
        row[col] = {**style, **existing_style, "char": ch}


def clear_row(data, row_idx):
    """Clear a row to spaces, preserving background styles."""
    for cell in data["cells"][row_idx]:
        cell["char"] = " "


def main():
    parser = argparse.ArgumentParser(description="Edit captured terminal JSON")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output", help="Output JSON file")
    parser.add_argument("--print", action="store_true", help="Print as plain text")
    parser.add_argument("--replace", nargs=3, action="append",
                        metavar=("ROW", "OLD", "NEW"),
                        help="Replace text in a specific row")
    parser.add_argument("--replace-all", nargs=2, action="append",
                        metavar=("OLD", "NEW"),
                        help="Replace text in all rows")
    parser.add_argument("--set", nargs=3, action="append",
                        metavar=("ROW", "COL", "TEXT"),
                        help="Set text at position")
    parser.add_argument("--clear-row", type=int, action="append",
                        metavar="ROW",
                        help="Clear a row")
    args = parser.parse_args()

    data = load(args.input)

    if args.print:
        print(to_text(data))
        return

    modified = False

    if args.replace_all:
        for old, new in args.replace_all:
            n = replace_all(data, old, new)
            if n:
                print(f"Replaced {n} occurrence(s) of '{old}' → '{new}'")
                modified = True
            else:
                print(f"Warning: '{old}' not found", file=sys.stderr)

    if args.replace:
        for row_s, old, new in args.replace:
            row_idx = int(row_s)
            if replace_in_row(data, row_idx, old, new) >= 0:
                print(f"Row {row_idx}: '{old}' → '{new}'")
                modified = True
            else:
                print(f"Warning: '{old}' not found in row {row_idx}", file=sys.stderr)

    if args.set:
        for row_s, col_s, text in args.set:
            set_text(data, int(row_s), int(col_s), text)
            print(f"Set ({row_s},{col_s}): '{text}'")
            modified = True

    if args.clear_row:
        for row_idx in args.clear_row:
            clear_row(data, row_idx)
            print(f"Cleared row {row_idx}")
            modified = True

    if modified:
        if not args.output:
            print("Error: -o/--output required when making edits", file=sys.stderr)
            sys.exit(1)
        save(data, args.output)
        print(f"Saved to {args.output}")
    elif not args.print:
        print("No edits specified. Use --print to inspect, or --replace-all/--set to edit.")


if __name__ == "__main__":
    main()
