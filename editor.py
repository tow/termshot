#!/usr/bin/env python3
"""
In-place terminal editor for captured screen states.

Opens a terminal sized exactly to the capture, renders it with full colors,
and lets you edit text directly. Styles (colors, bold, etc.) are preserved
from the original cell — you're just changing the characters.

Usage:
    python3 editor.py capture.json -o edited.json

Controls:
    Arrow keys           Move cursor
    Home / End           Jump to start/end of row
    Any printable key    Overwrite character (keeps cell style)
    Backspace            Replace with space, move left
    Ctrl+S               Save and quit
    Ctrl+Q / Escape      Quit without saving
    Ctrl+Z               Undo last edit
    Tab                  Toggle status bar
"""

import argparse
import curses
import json
import sys


def color_to_curses(raw):
    """Convert a raw pyte color to curses color init args.

    Returns (r, g, b) scaled to 0-1000 for curses, or None for default.
    """
    if not raw or raw == "default":
        return None

    # Named ANSI colors
    ANSI_NAMES = {
        "black": (0, 0, 0), "red": (205, 0, 0), "green": (0, 205, 0),
        "brown": (205, 205, 0), "yellow": (205, 205, 0),
        "blue": (0, 0, 238), "magenta": (205, 0, 205),
        "cyan": (0, 205, 205), "white": (229, 229, 229),
        "brightblack": (127, 127, 127), "brightred": (255, 0, 0),
        "brightgreen": (0, 255, 0), "brightyellow": (255, 255, 0),
        "brightblue": (92, 92, 255), "brightmagenta": (255, 0, 255),
        "brightcyan": (0, 255, 255), "brightwhite": (255, 255, 255),
    }

    if isinstance(raw, str) and raw.lower() in ANSI_NAMES:
        r, g, b = ANSI_NAMES[raw.lower()]
        return (r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)

    # Bare hex or #hex
    if isinstance(raw, str):
        h = raw.lstrip("#")
        if len(h) == 6:
            try:
                int(h, 16)
                r = int(h[0:2], 16)
                g = int(h[2:4], 16)
                b = int(h[4:6], 16)
                return (r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)
            except ValueError:
                pass

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
        self.show_status = True
        self.message = ""
        # Color pair cache: (fg_raw, bg_raw) -> pair_number
        self._color_pairs = {}
        self._next_pair = 1
        self._next_color = 16  # start custom colors after the 16 basics

    def _get_color_pair(self, fg_raw, bg_raw):
        """Get or create a curses color pair for this fg/bg combination."""
        key = (fg_raw, bg_raw)
        if key in self._color_pairs:
            return self._color_pairs[key]

        if self._next_pair >= curses.COLOR_PAIRS - 1:
            return 0  # fallback to default

        fg_id = self._alloc_color(fg_raw, fallback=curses.COLOR_WHITE)
        bg_id = self._alloc_color(bg_raw, fallback=-1)  # -1 = default bg

        pair_num = self._next_pair
        self._next_pair += 1

        try:
            curses.init_pair(pair_num, fg_id, bg_id)
        except curses.error:
            return 0

        self._color_pairs[key] = pair_num
        return pair_num

    def _alloc_color(self, raw, fallback=curses.COLOR_WHITE):
        """Allocate a curses color from a raw pyte value."""
        rgb = color_to_curses(raw)
        if rgb is None:
            return fallback

        if not curses.can_change_color():
            # Can't define custom colors, map to nearest basic
            return self._nearest_basic(rgb)

        color_id = self._next_color
        if color_id >= curses.COLORS:
            return self._nearest_basic(rgb)

        self._next_color += 1
        try:
            curses.init_color(color_id, rgb[0], rgb[1], rgb[2])
        except curses.error:
            return self._nearest_basic(rgb)

        return color_id

    def _nearest_basic(self, rgb):
        """Map an RGB tuple to the nearest basic curses color."""
        basics = [
            (curses.COLOR_BLACK, (0, 0, 0)),
            (curses.COLOR_RED, (804, 0, 0)),
            (curses.COLOR_GREEN, (0, 804, 0)),
            (curses.COLOR_YELLOW, (804, 804, 0)),
            (curses.COLOR_BLUE, (0, 0, 933)),
            (curses.COLOR_MAGENTA, (804, 0, 804)),
            (curses.COLOR_CYAN, (0, 804, 804)),
            (curses.COLOR_WHITE, (898, 898, 898)),
        ]
        best = curses.COLOR_WHITE
        best_dist = float("inf")
        for cid, (r, g, b) in basics:
            d = (rgb[0] - r) ** 2 + (rgb[1] - g) ** 2 + (rgb[2] - b) ** 2
            if d < best_dist:
                best_dist = d
                best = cid
        return best

    def draw(self, stdscr):
        """Draw the full screen."""
        for y in range(min(self.rows, curses.LINES - (1 if self.show_status else 0))):
            for x in range(min(self.cols, curses.COLS)):
                cell = self.cells[y][x]
                ch = cell.get("char", " ")
                if not ch:
                    ch = " "

                fg_raw = cell.get("fg")
                bg_raw = cell.get("bg")

                is_reverse = cell.get("reverse", False)
                if is_reverse:
                    fg_raw, bg_raw = bg_raw, fg_raw

                pair = self._get_color_pair(fg_raw, bg_raw)
                attrs = curses.color_pair(pair)
                if cell.get("bold"):
                    attrs |= curses.A_BOLD
                if cell.get("italic"):
                    attrs |= curses.A_ITALIC
                if cell.get("underline"):
                    attrs |= curses.A_UNDERLINE
                if is_reverse and pair == 0:
                    attrs |= curses.A_REVERSE

                try:
                    stdscr.addstr(y, x, ch, attrs)
                except curses.error:
                    pass  # bottom-right corner

        # Status bar
        if self.show_status:
            status_y = min(self.rows, curses.LINES - 1)
            if status_y < curses.LINES:
                cell = self.cells[self.cursor_y][self.cursor_x]
                pos = f" ({self.cursor_y},{self.cursor_x}) "
                char_info = f"'{cell.get('char', ' ')}'"
                fg_info = f" fg={cell.get('fg', '-')}"
                bg_info = f" bg={cell.get('bg', '-')}" if cell.get('bg') else ""
                style = ""
                for s in ["bold", "italic", "underline", "reverse"]:
                    if cell.get(s):
                        style += f" {s}"

                status = f"{pos}{char_info}{fg_info}{bg_info}{style}"
                if self.modified:
                    status += "  [modified]"
                if self.message:
                    status += f"  {self.message}"

                status = status[:curses.COLS - 1]
                try:
                    stdscr.addstr(status_y, 0, status.ljust(curses.COLS - 1),
                                  curses.A_REVERSE)
                except curses.error:
                    pass

    def edit_cell(self, ch):
        """Replace the character at cursor position, preserving style."""
        cell = self.cells[self.cursor_y][self.cursor_x]
        old_char = cell.get("char", " ")
        if ch != old_char:
            self.undo_stack.append((self.cursor_y, self.cursor_x, old_char))
            cell["char"] = ch
            self.modified = True

    def undo(self):
        """Undo the last edit."""
        if self.undo_stack:
            y, x, old_char = self.undo_stack.pop()
            self.cells[y][x]["char"] = old_char
            self.cursor_y = y
            self.cursor_x = x
            self.message = "undo"
            self.modified = len(self.undo_stack) > 0

    def run(self, stdscr):
        """Main editor loop."""
        curses.start_color()
        curses.use_default_colors()
        curses.curs_set(1)
        stdscr.clear()

        # Resize terminal hint
        need_rows = self.rows + (1 if self.show_status else 0)
        if curses.LINES < need_rows or curses.COLS < self.cols:
            stdscr.addstr(0, 0,
                          f"Resize terminal to at least {self.cols}x{need_rows} "
                          f"(currently {curses.COLS}x{curses.LINES})")
            stdscr.addstr(1, 0, "Press any key to continue anyway, or q to quit")
            stdscr.refresh()
            if stdscr.getch() == ord('q'):
                return False

        while True:
            self.draw(stdscr)
            stdscr.move(self.cursor_y, self.cursor_x)
            stdscr.refresh()
            self.message = ""

            key = stdscr.getch()

            # Navigation (arrow keys only — all printable keys type)
            if key == curses.KEY_UP and self.cursor_y > 0:
                self.cursor_y -= 1
            elif key == curses.KEY_DOWN and self.cursor_y < self.rows - 1:
                self.cursor_y += 1
            elif key == curses.KEY_LEFT and self.cursor_x > 0:
                self.cursor_x -= 1
            elif key == curses.KEY_RIGHT and self.cursor_x < self.cols - 1:
                self.cursor_x += 1
            elif key == curses.KEY_HOME:
                self.cursor_x = 0
            elif key == curses.KEY_END:
                self.cursor_x = self.cols - 1

            # Ctrl+S = save and quit
            elif key == 19:  # Ctrl+S
                return True

            # Ctrl+Q or Escape = quit without saving
            elif key in (17, 27):  # Ctrl+Q, Escape
                return False

            # Ctrl+Z = undo
            elif key == 26:
                self.undo()

            # Tab = toggle status bar
            elif key == 9:
                self.show_status = not self.show_status

            # Backspace = replace with space, move left
            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.edit_cell(" ")
                if self.cursor_x > 0:
                    self.cursor_x -= 1

            # Printable character = edit
            elif 32 <= key <= 126:
                self.edit_cell(chr(key))
                # Advance cursor
                if self.cursor_x < self.cols - 1:
                    self.cursor_x += 1

    def save(self, path):
        """Save the edited state to JSON."""
        out = {
            "cols": self.cols,
            "rows": self.rows,
            "cells": self.cells,
        }
        # Preserve theme if present
        if "theme" in self.data:
            out["theme"] = self.data["theme"]
        with open(path, "w") as f:
            json.dump(out, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="In-place terminal editor for captured screens")
    parser.add_argument("input", help="Input JSON file from capture.py")
    parser.add_argument("-o", "--output", help="Output JSON file (default: overwrite input)")
    args = parser.parse_args()

    with open(args.input) as f:
        data = json.load(f)

    output_path = args.output or args.input
    editor = Editor(data)

    def wrapped(stdscr):
        return editor.run(stdscr)

    should_save = curses.wrapper(wrapped)

    if should_save:
        editor.save(output_path)
        print(f"Saved to {output_path}")
    else:
        if editor.modified:
            print("Quit without saving (edits discarded)")
        else:
            print("No changes")


if __name__ == "__main__":
    main()
