#!/usr/bin/env python3
"""
Interactive terminal capture and edit workflow using kitty.

Launches a kitty terminal for you to set up content, captures the screen,
opens an editor for modifications, then takes the final screenshot.

Usage:
    python3 capture.py -o output.png
    python3 capture.py -o output.svg
    python3 capture.py -o output.json   # just save the edited JSON
"""

import argparse
import os
import sys

from kitty_util import KittyWindow
from ansi_parse import parse_ansi_to_cells
from capture_data import save


def main():
    parser = argparse.ArgumentParser(
        description="Capture, edit, and render terminal screenshots via kitty")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.png, .svg, .html, or .json)")
    args = parser.parse_args()

    # ── Step 1: Launch kitty for content setup ──
    print("Launching kitty terminal...")
    print("Set up whatever you want to screenshot in the kitty window.")
    print()

    kw = KittyWindow()
    kw.launch()

    input("Press Enter here when the kitty window is ready to capture...")

    # ── Step 2: Capture screen content ──
    cols, rows = kw.get_dimensions()
    ansi_text = kw.get_text(ansi=True)
    kw.kill()

    cells = parse_ansi_to_cells(ansi_text, cols, rows)
    data = {"cols": cols, "rows": rows, "cells": cells}

    # Save intermediate JSON for the editor
    json_path = args.output + ".edit.json"
    save(data, json_path)
    print(f"Captured {cols}x{rows} terminal to {json_path}")

    # ── Step 3: Launch editor in kitty ──
    # Editor saves JSON on Ctrl+S, then sleeps so kitty stays open for screenshot.
    # Escape quits without saving.
    print("Opening editor in kitty. Ctrl+S to save, Escape to cancel.")

    editor_script = (
        f"{sys.executable} {os.path.join(os.path.dirname(__file__), 'editor.py')}"
        f" {json_path}; sleep infinity"
    )
    editor_kw = KittyWindow(extra_opts=[
        "-o", f"initial_window_width={cols}c",
        "-o", f"initial_window_height={rows}c",
        # Map Cmd+key to Alt+key so Cmd+B/I/U/R work for formatting
        "-o", r"map cmd+b send_text all \x1bb",
        "-o", r"map cmd+i send_text all \x1bi",
        "-o", r"map cmd+u send_text all \x1bu",
        "-o", r"map cmd+r send_text all \x1br",
        "-o", r"map cmd+s send_text all \x13",
        "-o", r"map cmd+z send_text all \x1a",
    ])
    editor_kw.launch(cmd=["bash", "-c", editor_script])

    input("Press Enter here when you're done editing to take the screenshot...")

    # ── Step 4: Render output ──
    ext = os.path.splitext(args.output)[1].lower()

    if ext == ".png":
        from kitty_util import capture_window
        window_id = editor_kw.get_window_id()
        capture_window(window_id, args.output)
        print(f"Saved {args.output}")
    elif ext == ".json":
        os.rename(json_path, args.output)
        print(f"Saved {args.output}")
    else:
        # SVG/HTML: render from the edited JSON
        from capture_data import load
        from render import render_to_file
        data = load(json_path)
        render_to_file(data, args.output)
        print(f"Saved {args.output}")

    editor_kw.kill()

    # Clean up intermediate JSON
    if os.path.exists(json_path) and ext != ".json":
        os.unlink(json_path)


if __name__ == "__main__":
    main()
