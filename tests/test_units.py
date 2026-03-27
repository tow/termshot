#!/usr/bin/env python3
"""Unit tests for the termshot pipeline."""

import json
import os
import sys
import unittest

# Add parent dir to path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from colors import (
    ANSI_16, ANSI_FG_CODES, ANSI_BG_CODES,
    is_bare_hex, normalize_color, resolve_color, color_to_ansi, color_to_curses,
)
from capture_data import validate, to_text, CaptureValidationError
from edit import replace_in_row, replace_all, set_text, clear_row
from render.ansi import render_ansi


def _make_grid(text_lines):
    """Helper: create a minimal JSON data dict from plain text lines."""
    rows = []
    max_cols = max(len(line) for line in text_lines) if text_lines else 0
    for line in text_lines:
        padded = line.ljust(max_cols)
        rows.append([{"char": ch} for ch in padded])
    return {"cols": max_cols, "rows": len(rows), "cells": rows}


def _make_styled_grid(text, fg=None, bg=None, bold=False):
    """Helper: create a single-row grid with uniform style."""
    cells = []
    for ch in text:
        cell = {"char": ch}
        if fg:
            cell["fg"] = fg
        if bg:
            cell["bg"] = bg
        if bold:
            cell["bold"] = True
        cells.append(cell)
    return {"cols": len(text), "rows": 1, "cells": [cells]}


# --- Color tests ---

class TestResolveColor(unittest.TestCase):
    def test_default_returns_none(self):
        self.assertIsNone(resolve_color(None))
        self.assertIsNone(resolve_color("default"))
        self.assertIsNone(resolve_color(""))

    def test_hash_prefixed_hex_passthrough(self):
        self.assertEqual(resolve_color("#ff0000"), "#ff0000")
        self.assertEqual(resolve_color("#1e1e2e"), "#1e1e2e")

    def test_bare_hex_gets_hash(self):
        self.assertEqual(resolve_color("ff8c00"), "#ff8c00")
        self.assertEqual(resolve_color("000000"), "#000000")
        self.assertEqual(resolve_color("ffffff"), "#ffffff")

    def test_named_ansi_colors(self):
        self.assertEqual(resolve_color("red"), "#cd0000")
        self.assertEqual(resolve_color("blue"), "#0000ee")
        self.assertEqual(resolve_color("brown"), "#cdcd00")
        self.assertEqual(resolve_color("brightwhite"), "#ffffff")

    def test_named_case_insensitive(self):
        self.assertEqual(resolve_color("Red"), "#cd0000")
        self.assertEqual(resolve_color("BLUE"), "#0000ee")

    def test_unknown_returns_none(self):
        self.assertIsNone(resolve_color("notacolor"))
        self.assertIsNone(resolve_color("abc"))  # 3 chars, not 6


class TestIsBareHex(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(is_bare_hex("ff8c00"))
        self.assertTrue(is_bare_hex("000000"))
        self.assertTrue(is_bare_hex("abcdef"))

    def test_invalid(self):
        self.assertFalse(is_bare_hex("red"))
        self.assertFalse(is_bare_hex("#ff8c00"))
        self.assertFalse(is_bare_hex("gg0000"))
        self.assertFalse(is_bare_hex("fff"))


class TestColorToAnsi(unittest.TestCase):
    def test_named_fg(self):
        self.assertEqual(color_to_ansi("red", "fg"), "\x1b[31m")
        self.assertEqual(color_to_ansi("green", "fg"), "\x1b[32m")
        self.assertEqual(color_to_ansi("brightred", "fg"), "\x1b[91m")

    def test_named_bg(self):
        self.assertEqual(color_to_ansi("red", "bg"), "\x1b[41m")
        self.assertEqual(color_to_ansi("brightblue", "bg"), "\x1b[104m")

    def test_truecolor_fg(self):
        self.assertEqual(color_to_ansi("ff8c00", "fg"), "\x1b[38;2;255;140;0m")

    def test_truecolor_bg(self):
        self.assertEqual(color_to_ansi("1e1e2e", "bg"), "\x1b[48;2;30;30;46m")

    def test_hash_hex(self):
        self.assertEqual(color_to_ansi("#ff0000", "fg"), "\x1b[38;2;255;0;0m")

    def test_default_empty(self):
        self.assertEqual(color_to_ansi(None, "fg"), "")
        self.assertEqual(color_to_ansi("default", "bg"), "")

    def test_yellow_alias(self):
        self.assertEqual(color_to_ansi("yellow", "fg"), color_to_ansi("brown", "fg"))


class TestAnsiSgrCodeConsistency(unittest.TestCase):
    def test_fg_codes(self):
        self.assertEqual(ANSI_FG_CODES["black"], "30")
        self.assertEqual(ANSI_FG_CODES["red"], "31")
        self.assertEqual(ANSI_FG_CODES["white"], "37")
        self.assertEqual(ANSI_FG_CODES["brightblack"], "90")
        self.assertEqual(ANSI_FG_CODES["brightwhite"], "97")

    def test_bg_codes(self):
        self.assertEqual(ANSI_BG_CODES["black"], "40")
        self.assertEqual(ANSI_BG_CODES["cyan"], "46")
        self.assertEqual(ANSI_BG_CODES["brightcyan"], "106")


class TestColorToCurses(unittest.TestCase):
    def test_default_returns_none(self):
        self.assertIsNone(color_to_curses(None))
        self.assertIsNone(color_to_curses("default"))

    def test_named_color(self):
        result = color_to_curses("red")
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 3)
        self.assertEqual(result, (803, 0, 0))  # 205 * 1000 // 255

    def test_bare_hex(self):
        result = color_to_curses("ff0000")
        self.assertEqual(result, (1000, 0, 0))

    def test_hash_hex(self):
        result = color_to_curses("#00ff00")
        self.assertEqual(result, (0, 1000, 0))

    def test_unknown_returns_none(self):
        self.assertIsNone(color_to_curses("notacolor"))


class TestNormalizeColor(unittest.TestCase):
    def test_default_none(self):
        self.assertIsNone(normalize_color(None))
        self.assertIsNone(normalize_color("default"))

    def test_passthrough(self):
        self.assertEqual(normalize_color("red"), "red")
        self.assertEqual(normalize_color("ff8c00"), "ff8c00")


# --- Capture data validation tests ---

class TestValidate(unittest.TestCase):
    def test_valid(self):
        data = _make_grid(["hello"])
        validate(data)  # should not raise

    def test_missing_cols(self):
        with self.assertRaises(CaptureValidationError):
            validate({"rows": 1, "cells": [[{"char": "a"}]]})

    def test_wrong_row_count(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": 2, "cells": [[{"char": "a"}]]})

    def test_wrong_col_count(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 3, "rows": 1, "cells": [[{"char": "a"}]]})

    def test_missing_char(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": 1, "cells": [[{"fg": "red"}]]})


# --- Render tests ---

class TestRenderAnsi(unittest.TestCase):
    def test_no_spurious_leading_reset(self):
        data = _make_styled_grid("AB", fg="red")
        ansi = render_ansi(data)
        self.assertFalse(ansi.startswith("\x1b[0m"))

    def test_reset_between_style_changes(self):
        data = {"cols": 2, "rows": 1, "cells": [[
            {"char": "A", "fg": "red"},
            {"char": "B", "fg": "blue"},
        ]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[0m", ansi)

    def test_no_reset_for_same_style(self):
        data = _make_styled_grid("AB", fg="red")
        ansi = render_ansi(data)
        parts = ansi.split("A")
        after_a = parts[1] if len(parts) > 1 else ""
        self.assertTrue(after_a.startswith("B"))

    def test_ends_with_reset(self):
        data = _make_styled_grid("A", fg="red")
        ansi = render_ansi(data)
        self.assertTrue(ansi.endswith("\x1b[0m"))

    def test_unstyled_cells_no_escapes(self):
        data = _make_grid(["AB"])
        ansi = render_ansi(data)
        self.assertEqual(ansi, "AB\x1b[0m")


# --- Edit tests ---

class TestReplaceInRow(unittest.TestCase):
    def test_basic_replace(self):
        data = _make_grid(["hello world"])
        result = replace_in_row(data, 0, "world", "earth")
        self.assertGreaterEqual(result, 0)
        self.assertEqual(to_text(data), "hello earth")

    def test_shorter_replacement_pads_spaces(self):
        data = _make_grid(["hello world"])
        replace_in_row(data, 0, "world", "hi")
        row = data["cells"][0]
        raw = "".join(cell["char"] for cell in row)
        self.assertEqual(raw, "hello hi   ")
        self.assertEqual(to_text(data), "hello hi")

    def test_longer_replacement_truncates(self):
        data = _make_grid(["hello world"])
        replace_in_row(data, 0, "world", "universe!!")
        self.assertEqual(to_text(data), "hello unive")

    def test_not_found_returns_negative(self):
        data = _make_grid(["hello world"])
        result = replace_in_row(data, 0, "xyz", "abc")
        self.assertEqual(result, -1)

    def test_preserves_style(self):
        data = _make_styled_grid("hello", fg="red", bold=True)
        replace_in_row(data, 0, "ell", "ELL")
        cell = data["cells"][0][1]
        self.assertEqual(cell["char"], "E")
        self.assertEqual(cell["fg"], "red")
        self.assertTrue(cell["bold"])


class TestReplaceAll(unittest.TestCase):
    def test_multiple_rows(self):
        data = _make_grid(["foo bar", "baz foo"])
        count = replace_all(data, "foo", "FOO")
        self.assertEqual(count, 2)
        text = to_text(data)
        self.assertIn("FOO bar", text)
        self.assertIn("baz FOO", text)

    def test_new_contains_old_no_infinite_loop(self):
        data = _make_grid(["version v1 release"])
        count = replace_all(data, "v1", "v1")
        self.assertGreaterEqual(count, 1)

    def test_new_contains_old_different(self):
        data = _make_grid(["v1 and v1"])
        count = replace_all(data, "v1", "v2")
        self.assertEqual(count, 2)


class TestSetText(unittest.TestCase):
    def test_basic(self):
        data = _make_grid(["hello world"])
        set_text(data, 0, 6, "WORLD")
        self.assertEqual(to_text(data), "hello WORLD")

    def test_inherits_style(self):
        data = _make_styled_grid("hello", fg="green")
        set_text(data, 0, 0, "HI")
        self.assertEqual(data["cells"][0][0]["char"], "H")
        self.assertEqual(data["cells"][0][0]["fg"], "green")

    def test_truncates_at_row_end(self):
        data = _make_grid(["abc"])
        set_text(data, 0, 1, "XYZW")
        self.assertEqual(to_text(data), "aXY")

    def test_out_of_bounds_col(self):
        data = _make_grid(["abc"])
        set_text(data, 0, 99, "X")  # should not crash


class TestClearRow(unittest.TestCase):
    def test_clears_to_spaces(self):
        data = _make_grid(["hello"])
        clear_row(data, 0)
        self.assertEqual(to_text(data), "")

    def test_preserves_style(self):
        data = _make_styled_grid("hello", bg="blue")
        clear_row(data, 0)
        self.assertEqual(data["cells"][0][0]["char"], " ")
        self.assertEqual(data["cells"][0][0]["bg"], "blue")


# --- Editor tests ---

class TestEditorUndo(unittest.TestCase):
    def test_undo_restores_char(self):
        from editor import Editor
        data = _make_grid(["abc"])
        editor = Editor(data)
        editor.cursor_x = 1
        editor.edit_cell("X")
        self.assertEqual(editor.cells[0][1]["char"], "X")
        self.assertTrue(editor.modified)
        editor.undo()
        self.assertEqual(editor.cells[0][1]["char"], "b")
        self.assertFalse(editor.modified)

    def test_undo_multiple(self):
        from editor import Editor
        data = _make_grid(["abc"])
        editor = Editor(data)
        editor.cursor_x = 0
        editor.edit_cell("X")
        editor.cursor_x = 1
        editor.edit_cell("Y")
        self.assertTrue(editor.modified)
        editor.undo()
        self.assertTrue(editor.modified)
        self.assertEqual(editor.cells[0][1]["char"], "b")
        editor.undo()
        self.assertFalse(editor.modified)
        self.assertEqual(editor.cells[0][0]["char"], "a")

    def test_undo_empty_stack(self):
        from editor import Editor
        data = _make_grid(["abc"])
        editor = Editor(data)
        editor.undo()
        self.assertFalse(editor.modified)

    def test_edit_preserves_style(self):
        from editor import Editor
        data = _make_styled_grid("abc", fg="red", bold=True)
        editor = Editor(data)
        editor.cursor_x = 1
        editor.edit_cell("X")
        cell = editor.cells[0][1]
        self.assertEqual(cell["char"], "X")
        self.assertEqual(cell["fg"], "red")
        self.assertTrue(cell["bold"])

    def test_same_char_no_undo_entry(self):
        from editor import Editor
        data = _make_grid(["abc"])
        editor = Editor(data)
        editor.cursor_x = 1
        editor.edit_cell("b")
        self.assertFalse(editor.modified)
        self.assertEqual(len(editor.undo_stack), 0)


# --- Session tests ---

class TestSessionSendGuard(unittest.TestCase):
    def test_send_after_kill_raises(self):
        from session import Session
        sess = Session("true", cols=10, rows=5)
        sess.kill()
        with self.assertRaises(RuntimeError):
            sess.send("hello")


if __name__ == "__main__":
    unittest.main()
