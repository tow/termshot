#!/usr/bin/env python3
"""
Terminal editor for captured screen states.

Renders directly via ANSI escape sequences (no curses), so kitty
handles all character width and rendering correctly.

Usage:
    python3 editor.py capture.json [-o edited.json]

Controls:
    Arrow keys           Move cursor
    Home / End           Jump to start/end of row
    Any printable key    Overwrite character (keeps cell style)
    Backspace            Replace with space, move left
    Ctrl+Y               Copy style from current cell
    Ctrl+P               Paste style to current cell
    Ctrl+S               Save and quit
    Ctrl+Q / Escape      Quit without saving
    Ctrl+Z               Undo last edit
"""

import argparse
import os
import select
import sys
import termios
import tty

from capture_data import load, save
from render.ansi import render_ansi


def _read_key(fd):
    """Read a single keypress from a raw terminal fd."""
    ch = os.read(fd, 1)
    if not ch:
        return ""
    b = ch[0]

    if b == 0x1b:
        if select.select([fd], [], [], 0.05)[0]:
            seq = os.read(fd, 8)
            return chr(b) + seq.decode("utf-8", errors="replace")
        return "ESC"

    if b == 0x13:
        return "SAVE"
    if b == 0x11:
        return "QUIT"
    if b == 0x1a:
        return "UNDO"
    if b == 0x19:  # Ctrl+Y
        return "YANK_STYLE"
    if b == 0x10:  # Ctrl+P
        return "PASTE_STYLE"
    if b in (0x7f, 0x08):
        return "BS"

    return ch.decode("utf-8", errors="replace")


def _parse_key(key):
    """Parse escape sequences into named keys."""
    if len(key) >= 3 and key[0] == "\x1b" and key[1] == "[":
        code = key[2:]
        return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                "H": "HOME", "F": "END"}.get(code, None)
    return None


class Editor:
    def __init__(self, data):
        self.data = data
        self.cols = data["cols"]
        self.rows = data["rows"]
        self.cells = data["cells"]
        self.cursor_y = 0
        self.cursor_x = 0
        self.undo_stack = []
        self.modified = False
        self.yanked_style = None

    def render(self):
        """Render full screen via ANSI sequences."""
        ansi = render_ansi(self.data)
        # In raw mode, \n is just LF (no carriage return), so add \r
        ansi = ansi.replace("\n", "\r\n")
        out = "\x1b[?25l"       # hide cursor during render
        out += "\x1b[H"         # cursor home
        out += ansi
        # Position cursor and show it
        out += f"\x1b[{self.cursor_y + 1};{self.cursor_x + 1}H"
        out += "\x1b[?25h"
        sys.stdout.write(out)
        sys.stdout.flush()

    def edit_cell(self, ch):
        cell = self.cells[self.cursor_y][self.cursor_x]
        old_char = cell.get("char", " ")
        if ch != old_char:
            self.undo_stack.append((self.cursor_y, self.cursor_x, {"char": old_char}))
            cell["char"] = ch
            self.modified = True

    def yank_style(self):
        """Copy the style (fg, bg, bold, etc.) from the current cell."""
        cell = self.cells[self.cursor_y][self.cursor_x]
        self.yanked_style = {}
        for key in ("fg", "bg", "bold", "italic", "underline", "reverse"):
            if cell.get(key):
                self.yanked_style[key] = cell[key]

    def paste_style(self):
        """Apply the yanked style to the current cell."""
        if self.yanked_style is None:
            return
        cell = self.cells[self.cursor_y][self.cursor_x]
        # Save full cell state for undo
        old = {k: cell.get(k) for k in ("char", "fg", "bg", "bold", "italic", "underline", "reverse")}
        self.undo_stack.append((self.cursor_y, self.cursor_x, old))
        for key in ("fg", "bg", "bold", "italic", "underline", "reverse"):
            if key in self.yanked_style:
                cell[key] = self.yanked_style[key]
            else:
                cell.pop(key, None)
        self.modified = True

    def undo(self):
        if self.undo_stack:
            entry = self.undo_stack.pop()
            y, x, old = entry[0], entry[1], entry[2]
            if isinstance(old, str):
                # Legacy: just a char
                self.cells[y][x]["char"] = old
            else:
                # Full cell state
                cell = self.cells[y][x]
                for key in ("char", "fg", "bg", "bold", "italic", "underline", "reverse"):
                    if key in old and old[key] is not None:
                        cell[key] = old[key]
                    else:
                        cell.pop(key, None)
            self.cursor_y = y
            self.cursor_x = x
            self.modified = len(self.undo_stack) > 0

    def handle_key(self, key):
        """Process a keypress. Returns 'save', 'quit', or None."""
        named = _parse_key(key)
        if named:
            key = named

        if key == "UP" and self.cursor_y > 0:
            self.cursor_y -= 1
        elif key == "DOWN" and self.cursor_y < self.rows - 1:
            self.cursor_y += 1
        elif key == "LEFT" and self.cursor_x > 0:
            self.cursor_x -= 1
        elif key == "RIGHT" and self.cursor_x < self.cols - 1:
            self.cursor_x += 1
        elif key == "HOME":
            self.cursor_x = 0
        elif key == "END":
            self.cursor_x = self.cols - 1
        elif key == "SAVE":
            return "save"
        elif key in ("QUIT", "ESC"):
            return "quit"
        elif key == "UNDO":
            self.undo()
        elif key == "YANK_STYLE":
            self.yank_style()
        elif key == "PASTE_STYLE":
            self.paste_style()
        elif key == "BS":
            self.edit_cell(" ")
            if self.cursor_x > 0:
                self.cursor_x -= 1
        elif len(key) == 1 and 32 <= ord(key) <= 126:
            self.edit_cell(key)
            if self.cursor_x < self.cols - 1:
                self.cursor_x += 1

        return None

    def to_dict(self):
        out = {
            "cols": self.cols,
            "rows": self.rows,
            "cells": self.cells,
        }
        if "theme" in self.data:
            out["theme"] = self.data["theme"]
        return out

    def render_final(self):
        """Render without cursor for screenshot."""
        ansi = render_ansi(self.data)
        ansi = ansi.replace("\n", "\r\n")
        out = "\x1b[?25l\x1b[H" + ansi + "\x1b[0m"
        sys.stdout.write(out)
        sys.stdout.flush()

    def run(self):
        """Main editor loop. Returns True if saved, False otherwise."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            sys.stdout.write("\x1b[2J")
            self.render()

            while True:
                key = _read_key(fd)
                if not key:
                    continue

                result = self.handle_key(key)
                self.render()

                if result == "save":
                    # Re-render without cursor for screenshot
                    self.render_final()
                    return True
                elif result == "quit":
                    return False
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def main():
    parser = argparse.ArgumentParser(
        description="Edit captured terminal screens")
    parser.add_argument("input", help="Input JSON file")
    parser.add_argument("-o", "--output",
                        help="Output JSON file (default: overwrite input)")
    args = parser.parse_args()

    data = load(args.input)
    output_path = args.output or args.input
    editor = Editor(data)

    should_save = editor.run()

    if should_save:
        save(editor.to_dict(), output_path)
        print(f"Saved to {output_path}")
    else:
        if editor.modified:
            print("Quit without saving (edits discarded)")
        else:
            print("No changes")


if __name__ == "__main__":
    main()
