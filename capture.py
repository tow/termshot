#!/usr/bin/env python3
"""
Interactive terminal capture and edit workflow using kitty.

Launches a kitty terminal for you to set up content, captures the screen,
opens an editor for modifications, then takes the final screenshot.

Usage:
    python3 capture.py -o output.png
    python3 capture.py -o output.svg
    python3 capture.py -o output.json
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time


# ── JSON I/O ──────────────────────────────────────────────────────────────────

class CaptureValidationError(ValueError):
    pass


def validate(data):
    """Validate a capture data dict."""
    if not isinstance(data, dict):
        raise CaptureValidationError("Capture data must be a dict")
    for key in ("cols", "rows", "cells"):
        if key not in data:
            raise CaptureValidationError(f"Missing required key: {key!r}")
    cols, rows, cells = data["cols"], data["rows"], data["cells"]
    if not isinstance(cols, int) or cols <= 0:
        raise CaptureValidationError(f"'cols' must be a positive int, got {cols!r}")
    if not isinstance(rows, int) or rows <= 0:
        raise CaptureValidationError(f"'rows' must be a positive int, got {rows!r}")
    if not isinstance(cells, list) or len(cells) != rows:
        raise CaptureValidationError(f"'cells' has {len(cells) if isinstance(cells, list) else '?'} rows, expected {rows}")
    for y, row in enumerate(cells):
        if not isinstance(row, list) or len(row) != cols:
            raise CaptureValidationError(f"Row {y} has wrong length")
        for x, cell in enumerate(row):
            if not isinstance(cell, dict) or "char" not in cell:
                raise CaptureValidationError(f"Cell ({y},{x}) invalid")


def load(path):
    """Load and validate a capture JSON file."""
    with open(path) as f:
        data = json.load(f)
    validate(data)
    return data


def save(data, path):
    """Save capture data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def to_text(data):
    """Convert capture to plain text."""
    return "\n".join(
        "".join(cell.get("char", " ") for cell in row).rstrip()
        for row in data["cells"]
    )


# ── Kitty remote control ─────────────────────────────────────────────────────

def _find_kitty():
    """Find the kitty binary."""
    path = shutil.which("kitty")
    if path:
        return path
    mac_path = "/Applications/kitty.app/Contents/MacOS/kitty"
    if os.path.isfile(mac_path):
        return mac_path
    print("Error: kitty not found. Install with: brew install --cask kitty",
          file=sys.stderr)
    sys.exit(1)


class KittyWindow:
    """A kitty terminal window with remote control."""

    def __init__(self, extra_opts=None):
        self.kitty = _find_kitty()
        self._sock_dir = tempfile.mkdtemp(prefix="termshot-")
        self.sock_path = os.path.join(self._sock_dir, "kitty.sock")
        self.proc = None
        self._extra_opts = extra_opts or []

    def launch(self, cmd=None):
        args = [
            self.kitty,
            "--listen-on", f"unix:{self.sock_path}",
            "-o", "allow_remote_control=yes",
            "-o", "confirm_os_window_close=0",
            "-o", "macos_quit_when_last_window_closed=yes",
        ]
        args.extend(self._extra_opts)
        if cmd:
            args.extend(["-e"] + cmd)
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(50):
            time.sleep(0.1)
            if os.path.exists(self.sock_path):
                return
        raise RuntimeError("kitty did not start (socket not created)")

    def remote(self, *cmd_args):
        return subprocess.run(
            [self.kitty, "@", "--to", f"unix:{self.sock_path}"] + list(cmd_args),
            capture_output=True, text=True,
        )

    def get_text(self, ansi=True):
        args = ["get-text", "--extent=screen", "--add-wrap-markers"]
        if ansi:
            args.append("--ansi")
        result = self.remote(*args)
        if result.returncode != 0:
            raise RuntimeError(f"get-text failed: {result.stderr}")
        return result.stdout

    def get_dimensions(self):
        result = self.remote("ls")
        if result.returncode != 0:
            raise RuntimeError(f"ls failed: {result.stderr}")
        ls_data = json.loads(result.stdout)
        for os_win in ls_data:
            for tab in os_win.get("tabs", []):
                for win in tab.get("windows", []):
                    return win["columns"], win["lines"]
        raise RuntimeError("no kitty window found")

    def get_window_id(self):
        result = self.remote("ls")
        if result.returncode != 0:
            raise RuntimeError(f"ls failed: {result.stderr}")
        return json.loads(result.stdout)[0]["platform_window_id"]

    def kill(self):
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc = None
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        if os.path.exists(self._sock_dir):
            os.rmdir(self._sock_dir)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kill()


def capture_window(window_id, output_path):
    """Capture a window to PNG using the platform's tool."""
    if sys.platform == "darwin":
        subprocess.run(
            ["screencapture", "-l", str(window_id), "-o", output_path],
            check=True,
        )
    else:
        if not shutil.which("import"):
            print("Error: import (ImageMagick) not found.", file=sys.stderr)
            sys.exit(1)
        subprocess.run(
            ["import", "-window", str(window_id), output_path],
            check=True,
        )


# ── ANSI parser ───────────────────────────────────────────────────────────────

_CSI_RE = re.compile(r'\x1b\[([0-9;:]*)([A-Za-z])')
_OSC_RE = re.compile(r'\x1b\].*?(?:\x07|\x1b\\)')

_ANSI_16_HEX = [
    "#000000", "#cd0000", "#00cd00", "#cdcd00",
    "#0000ee", "#cd00cd", "#00cdcd", "#e5e5e5",
    "#7f7f7f", "#ff0000", "#00ff00", "#ffff00",
    "#5c5cff", "#ff00ff", "#00ffff", "#ffffff",
]


def parse_ansi_to_cells(text, cols, rows):
    """Parse ANSI text (from kitty get-text --ansi) into a cells grid."""
    fg = bg = None
    bold = italic = underline = reverse = False

    grid = [[{"char": " "} for _ in range(cols)] for _ in range(rows)]
    screen_rows = re.split(r"\r|\n", text)

    for y, line in enumerate(screen_rows):
        if y >= rows:
            break
        x = i = 0
        while i < len(line) and x < cols:
            ch = line[i]
            if ch == "\x1b" and i + 1 < len(line):
                m = _CSI_RE.match(line, i)
                if m:
                    if m.group(2) == "m":
                        st = {"fg": fg, "bg": bg, "bold": bold, "italic": italic,
                              "underline": underline, "reverse": reverse}
                        _apply_sgr(m.group(1), st)
                        fg, bg = st["fg"], st["bg"]
                        bold, italic = st["bold"], st["italic"]
                        underline, reverse = st["underline"], st["reverse"]
                    i = m.end()
                    continue
                m = _OSC_RE.match(line, i)
                if m:
                    i = m.end()
                    continue
                i += 2
                continue

            cell = {"char": ch}
            if fg: cell["fg"] = fg
            if bg: cell["bg"] = bg
            if bold: cell["bold"] = True
            if italic: cell["italic"] = True
            if underline: cell["underline"] = True
            if reverse: cell["reverse"] = True
            grid[y][x] = cell
            x += 1
            i += 1

    return grid


def _apply_sgr(params_str, state):
    if not params_str:
        state.update(fg=None, bg=None, bold=False, italic=False,
                     underline=False, reverse=False)
        return

    groups = params_str.split(";")
    i = 0
    while i < len(groups):
        parts = groups[i].split(":")
        try:
            p = int(parts[0])
        except ValueError:
            i += 1
            continue

        if p == 0:
            state.update(fg=None, bg=None, bold=False, italic=False,
                         underline=False, reverse=False)
        elif p == 1: state["bold"] = True
        elif p == 3: state["italic"] = True
        elif p == 4: state["underline"] = True
        elif p == 7: state["reverse"] = True
        elif p == 22: state["bold"] = False
        elif p == 23: state["italic"] = False
        elif p == 24: state["underline"] = False
        elif p == 27: state["reverse"] = False
        elif 30 <= p <= 37: state["fg"] = _ANSI_16_HEX[p - 30]
        elif p in (38, 48):
            key = "fg" if p == 38 else "bg"
            if len(parts) > 1:
                color = _parse_color_subparams(parts[1:])
            else:
                remaining = groups[i+1:]
                color = _parse_color_subparams(remaining)
                if remaining and remaining[0] == "2": i += 4
                elif remaining and remaining[0] == "5": i += 2
            if color:
                state[key] = color
        elif p == 39: state["fg"] = None
        elif p == 49: state["bg"] = None
        elif 40 <= p <= 47: state["bg"] = _ANSI_16_HEX[p - 40]
        elif 90 <= p <= 97: state["fg"] = _ANSI_16_HEX[p - 90 + 8]
        elif 100 <= p <= 107: state["bg"] = _ANSI_16_HEX[p - 100 + 8]
        i += 1


def _parse_color_subparams(parts):
    if not parts:
        return None
    try:
        mode = int(parts[0])
    except ValueError:
        return None
    if mode == 2 and len(parts) >= 4:
        try:
            r, g, b = int(parts[1]), int(parts[2]), int(parts[3])
            return f"#{r:02x}{g:02x}{b:02x}"
        except ValueError:
            return None
    elif mode == 5 and len(parts) >= 2:
        try:
            return _color256_to_hex(int(parts[1]))
        except ValueError:
            return None
    return None


def _color256_to_hex(n):
    if n < 16:
        return _ANSI_16_HEX[n]
    elif n < 232:
        n -= 16
        return f"#{(n//36)*51:02x}{((n//6)%6)*51:02x}{(n%6)*51:02x}"
    else:
        v = (n - 232) * 10 + 8
        return f"#{v:02x}{v:02x}{v:02x}"


# ── Main workflow ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Capture, edit, and render terminal screenshots via kitty")
    parser.add_argument("-o", "--output", required=True,
                        help="Output file (.png, .svg, .html, or .json)")
    args = parser.parse_args()

    # Step 1: Launch kitty for content setup
    print("Launching kitty terminal...")
    print("Set up whatever you want to screenshot in the kitty window.")
    print()

    kw = KittyWindow()
    kw.launch()
    input("Press Enter here when the kitty window is ready to capture...")

    # Step 2: Capture screen content
    cols, rows = kw.get_dimensions()
    ansi_text = kw.get_text(ansi=True)
    kw.kill()

    cells = parse_ansi_to_cells(ansi_text, cols, rows)
    data = {"cols": cols, "rows": rows, "cells": cells}

    json_path = args.output + ".edit.json"
    save(data, json_path)
    print(f"Captured {cols}x{rows} terminal.")

    # Step 3: Launch editor in kitty
    print("Opening editor in kitty. Ctrl+S to save, Escape to cancel.")
    editor_script = (
        f"{sys.executable} {os.path.join(os.path.dirname(__file__), 'editor.py')}"
        f" {json_path}; sleep infinity"
    )
    editor_kw = KittyWindow(extra_opts=[
        "-o", f"initial_window_width={cols}c",
        "-o", f"initial_window_height={rows}c",
        "-o", r"map cmd+b send_text all \x1bb",
        "-o", r"map cmd+i send_text all \x1bi",
        "-o", r"map cmd+u send_text all \x1bu",
        "-o", r"map cmd+r send_text all \x1br",
        "-o", r"map cmd+s send_text all \x13",
        "-o", r"map cmd+z send_text all \x1a",
    ])
    editor_kw.launch(cmd=["bash", "-c", editor_script])
    input("Press Enter here when you're done editing to take the screenshot...")

    # Step 4: Render output
    ext = os.path.splitext(args.output)[1].lower()

    if ext == ".png":
        capture_window(editor_kw.get_window_id(), args.output)
        print(f"Saved {args.output}")
    elif ext == ".json":
        os.rename(json_path, args.output)
        print(f"Saved {args.output}")
    else:
        from render import render_to_file
        render_to_file(load(json_path), args.output)
        print(f"Saved {args.output}")

    editor_kw.kill()
    if os.path.exists(json_path) and ext != ".json":
        os.unlink(json_path)


if __name__ == "__main__":
    main()
