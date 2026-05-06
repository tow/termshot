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
    Alt+B                Toggle bold
    Alt+I                Toggle italic
    Alt+U                Toggle underline
    Alt+R                Toggle reverse
    Alt+F / Alt+Shift+F  Cycle foreground color forward / backward
    Alt+G / Alt+Shift+G  Cycle background color forward / backward
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

from capture import load, save
from render.ansi import render_ansi


# Claude Code's dark theme — extracted from the installed binary by parsing
# the theme object that maps semantic tokens to rgb() values. Subset of the
# full 60-color palette covering the UI states most worth recreating in
# screenshots. The full theme is in CLAUDE_DARK_THEME below.
COLOR_PALETTE = [
    None,        # default
    "#d77757",   # claude (orange — brand, spinner, "Claude:" labels)
    "#ffffff",   # text
    "#999999",   # inactive
    "#505050",   # subtle
    "#4eba65",   # success
    "#ff6b80",   # error
    "#ffc107",   # warning
    "#225c2b",   # diffAdded (bg)
    "#7a2936",   # diffRemoved (bg)
    "#38a660",   # diffAddedWord
    "#b3596b",   # diffRemovedWord
    "#b1b9f9",   # permission / suggestion
    "#48968c",   # planMode
    "#4782c8",   # ide
    "#af87ff",   # autoAccept / merged
    "#fd5db1",   # bashBorder
    "#ff7814",   # fastMode
    "#fbbc04",   # chromeYellow
    "#eb9f7f",   # claudeShimmer
]

# Full Claude Code dark theme — every semantic token. Useful if you want to
# pick a more specific color than the cycle covers.
CLAUDE_DARK_THEME = {
    "autoAccept": "#af87ff",
    "bashBorder": "#fd5db1",
    "claude": "#d77757",
    "claudeShimmer": "#eb9f7f",
    "claudeBlue_FOR_SYSTEM_SPINNER": "#93a5ff",
    "claudeBlueShimmer_FOR_SYSTEM_SPINNER": "#b1c3ff",
    "permission": "#b1b9f9",
    "permissionShimmer": "#cfd7ff",
    "planMode": "#48968c",
    "ide": "#4782c8",
    "promptBorder": "#888888",
    "promptBorderShimmer": "#a6a6a6",
    "text": "#ffffff",
    "inverseText": "#000000",
    "inactive": "#999999",
    "inactiveShimmer": "#c1c1c1",
    "subtle": "#505050",
    "suggestion": "#b1b9f9",
    "remember": "#b1b9f9",
    "background": "#00cccc",
    "success": "#4eba65",
    "error": "#ff6b80",
    "warning": "#ffc107",
    "merged": "#af87ff",
    "warningShimmer": "#ffdf39",
    "diffAdded": "#225c2b",
    "diffRemoved": "#7a2936",
    "diffAddedDimmed": "#47584a",
    "diffRemovedDimmed": "#69484d",
    "diffAddedWord": "#38a660",
    "diffRemovedWord": "#b3596b",
    "red_FOR_SUBAGENTS_ONLY": "#dc2626",
    "blue_FOR_SUBAGENTS_ONLY": "#2563eb",
    "green_FOR_SUBAGENTS_ONLY": "#16a34a",
    "yellow_FOR_SUBAGENTS_ONLY": "#ca8a04",
    "purple_FOR_SUBAGENTS_ONLY": "#9333ea",
    "orange_FOR_SUBAGENTS_ONLY": "#ea580c",
    "pink_FOR_SUBAGENTS_ONLY": "#db2777",
    "cyan_FOR_SUBAGENTS_ONLY": "#0891b2",
    "professionalBlue": "#6a9bcc",
    "chromeYellow": "#fbbc04",
    "userMessageBackground": "#373737",
    "userMessageBackgroundHover": "#464646",
    "selectionBg": "#264f78",
    "bashMessageBackgroundColor": "#413c41",
    "memoryBackgroundColor": "#374146",
    "rate_limit_fill": "#b1b9f9",
    "rate_limit_empty": "#505370",
    "fastMode": "#ff7814",
    "fastModeShimmer": "#ffa546",
    "briefLabelYou": "#7ab4e8",
    "briefLabelClaude": "#d77757",
    "rainbow_red": "#eb5f57",
    "rainbow_orange": "#f58b57",
    "rainbow_yellow": "#fac35f",
    "rainbow_green": "#91c882",
    "rainbow_blue": "#82aadc",
    "rainbow_indigo": "#9b82c8",
    "rainbow_violet": "#c882b4",
}


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

    # Handle multi-byte UTF-8
    if b >= 0xC0:
        if b < 0xE0:
            remaining = 1
        elif b < 0xF0:
            remaining = 2
        else:
            remaining = 3
        more = os.read(fd, remaining)
        return (ch + more).decode("utf-8", errors="replace")

    return ch.decode("utf-8", errors="replace")


def _parse_key(key):
    """Parse escape sequences into named keys."""
    if len(key) >= 3 and key[0] == "\x1b" and key[1] == "[":
        code = key[2:]
        return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT",
                "H": "HOME", "F": "END"}.get(code, None)
    # Alt+key (ESC followed by a single character).
    # Color keys distinguish case so Shift cycles backwards.
    if len(key) == 2 and key[0] == "\x1b":
        ch = key[1]
        if ch == "f": return "FG_COLOR"
        if ch == "F": return "FG_COLOR_BACK"
        if ch == "g": return "BG_COLOR"
        if ch == "G": return "BG_COLOR_BACK"
        return {"b": "BOLD", "i": "ITALIC", "u": "UNDERLINE",
                "r": "REVERSE"}.get(ch.lower(), None)
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

    def _save_undo(self):
        """Save the full state of the current cell for undo."""
        cell = self.cells[self.cursor_y][self.cursor_x]
        old = {k: cell.get(k) for k in ("char", "fg", "bg", "bold", "italic", "underline", "reverse")}
        self.undo_stack.append((self.cursor_y, self.cursor_x, old))

    def edit_cell(self, ch):
        cell = self.cells[self.cursor_y][self.cursor_x]
        if ch != cell.get("char", " "):
            self._save_undo()
            cell["char"] = ch
            self.modified = True

    def toggle_attr(self, attr):
        """Toggle a boolean style attribute on the current cell."""
        cell = self.cells[self.cursor_y][self.cursor_x]
        self._save_undo()
        if cell.get(attr):
            cell.pop(attr, None)
        else:
            cell[attr] = True
        self.modified = True

    def cycle_color(self, layer, direction=1):
        """Cycle the fg or bg color through COLOR_PALETTE (direction ±1)."""
        cell = self.cells[self.cursor_y][self.cursor_x]
        current = cell.get(layer)
        try:
            idx = COLOR_PALETTE.index(current)
        except ValueError:
            idx = 0
        new_color = COLOR_PALETTE[(idx + direction) % len(COLOR_PALETTE)]
        self._save_undo()
        if new_color is None:
            cell.pop(layer, None)
        else:
            cell[layer] = new_color
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
        self._save_undo()
        for key in ("fg", "bg", "bold", "italic", "underline", "reverse"):
            if key in self.yanked_style:
                cell[key] = self.yanked_style[key]
            else:
                cell.pop(key, None)
        self.modified = True

    def undo(self):
        if self.undo_stack:
            y, x, old = self.undo_stack.pop()
            cell = self.cells[y][x]
            for key in ("char", "fg", "bg", "bold", "italic", "underline", "reverse"):
                if old.get(key) is not None:
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
        elif key in ("BOLD", "ITALIC", "UNDERLINE", "REVERSE"):
            self.toggle_attr(key.lower())
        elif key == "FG_COLOR":
            self.cycle_color("fg", 1)
        elif key == "FG_COLOR_BACK":
            self.cycle_color("fg", -1)
        elif key == "BG_COLOR":
            self.cycle_color("bg", 1)
        elif key == "BG_COLOR_BACK":
            self.cycle_color("bg", -1)
        elif key == "BS":
            self.edit_cell(" ")
            if self.cursor_x > 0:
                self.cursor_x -= 1
        elif len(key) == 1 and key.isprintable():
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
            # Bar cursor (DECSCUSR 6) so the cell beneath shows through —
            # otherwise a block cursor hides the fg/bg of the active cell.
            sys.stdout.write("\x1b[2J\x1b[6 q")
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
            sys.stdout.write("\x1b[0 q")  # restore default cursor shape
            sys.stdout.flush()
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
