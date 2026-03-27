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


# --- Render SVG/HTML tests ---

class TestRenderSvg(unittest.TestCase):
    def test_basic_output(self):
        from render.svg import render_svg
        data = _make_styled_grid("Hello", fg="red", bold=True)
        svg = render_svg(data)
        self.assertIn("<svg", svg)
        self.assertIn("</svg>", svg)
        self.assertIn("Hello", svg)

    def test_title(self):
        from render.svg import render_svg
        data = _make_grid(["test"])
        svg = render_svg(data, title="My Title")
        self.assertIn("My Title", svg)

    def test_no_title(self):
        from render.svg import render_svg
        data = _make_grid(["test"])
        svg = render_svg(data)
        self.assertIn("<svg", svg)

    def test_background_color(self):
        from render.svg import render_svg
        data = _make_styled_grid("X", bg="blue")
        svg = render_svg(data)
        # Should have a background rect with the resolved blue color
        self.assertIn("fill=\"#0000ee\"", svg)

    def test_reverse_video(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "R", "fg": "red", "reverse": True}
        ]]}
        svg = render_svg(data)
        self.assertIn("R", svg)

    def test_underline(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "U", "fg": "green", "underline": True}
        ]]}
        svg = render_svg(data)
        self.assertIn("stroke=", svg)

    def test_italic(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "I", "fg": "cyan", "italic": True}
        ]]}
        svg = render_svg(data)
        self.assertIn("font-style=\"italic\"", svg)

    def test_html_escaping(self):
        from render.svg import render_svg
        data = {"cols": 3, "rows": 1, "cells": [[
            {"char": "<"}, {"char": "&"}, {"char": ">"}
        ]]}
        svg = render_svg(data)
        self.assertIn("&lt;", svg)
        self.assertIn("&amp;", svg)
        self.assertIn("&gt;", svg)

    def test_window_dots(self):
        from render.svg import render_svg
        data = _make_grid(["x"])
        svg = render_svg(data)
        self.assertIn("#ff5f57", svg)  # red dot
        self.assertIn("#febc2e", svg)  # yellow dot
        self.assertIn("#28c840", svg)  # green dot


class TestRenderHtml(unittest.TestCase):
    def test_basic_output(self):
        from render.html import render_html
        data = _make_styled_grid("Hello", fg="red")
        html = render_html(data)
        self.assertIn("<!DOCTYPE html>", html)
        # Each char is in its own span, so check individual chars
        self.assertIn(">H<", html)
        self.assertIn(">o<", html)

    def test_title(self):
        from render.html import render_html
        data = _make_grid(["test"])
        html = render_html(data, title="My App")
        self.assertIn("My App", html)

    def test_default_title(self):
        from render.html import render_html
        data = _make_grid(["test"])
        html = render_html(data)
        self.assertIn("Terminal", html)

    def test_styled_spans(self):
        from render.html import render_html
        data = _make_styled_grid("B", fg="red", bold=True)
        html = render_html(data)
        self.assertIn("color:#cd0000", html)
        self.assertIn("font-weight:bold", html)

    def test_background_in_span(self):
        from render.html import render_html
        data = _make_styled_grid("X", bg="blue")
        html = render_html(data)
        self.assertIn("background:#0000ee", html)

    def test_reverse_video(self):
        from render.html import render_html
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "R", "fg": "red", "bg": "blue", "reverse": True}
        ]]}
        html = render_html(data)
        # Reverse swaps fg/bg
        self.assertIn("color:#0000ee", html)
        self.assertIn("background:#cd0000", html)

    def test_unstyled_no_span(self):
        from render.html import render_html
        data = _make_grid(["A"])
        html = render_html(data)
        # Unstyled char should NOT be wrapped in a span
        self.assertIn(">A<", html)

    def test_html_escaping(self):
        from render.html import render_html
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "<"}]]}
        html = render_html(data)
        self.assertIn("&lt;", html)


# --- ANSI render additional tests ---

class TestRenderAnsiStyles(unittest.TestCase):
    def test_bold(self):
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "B", "bold": True}]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[1m", ansi)

    def test_italic(self):
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "I", "italic": True}]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[3m", ansi)

    def test_underline(self):
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "U", "underline": True}]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[4m", ansi)

    def test_reverse(self):
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "R", "reverse": True}]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[7m", ansi)

    def test_bg_color(self):
        data = _make_styled_grid("X", bg="blue")
        ansi = render_ansi(data)
        self.assertIn("\x1b[44m", ansi)  # blue bg

    def test_multi_row(self):
        data = {"cols": 2, "rows": 2, "cells": [
            [{"char": "A"}, {"char": "B"}],
            [{"char": "C"}, {"char": "D"}],
        ]}
        ansi = render_ansi(data)
        lines = ansi.split("\n")
        self.assertEqual(len(lines), 2)


# --- Capture data tests ---

class TestCaptureDataLoadSave(unittest.TestCase):
    def test_save_and_load(self):
        import tempfile
        from capture_data import load, save
        data = _make_grid(["hello world"])
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            save(data, path)
            loaded = load(path)
            self.assertEqual(loaded["cols"], data["cols"])
            self.assertEqual(loaded["rows"], data["rows"])
            self.assertEqual(to_text(loaded), "hello world")
        finally:
            os.unlink(path)

    def test_load_invalid_file(self):
        import tempfile
        from capture_data import load
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"not": "valid"}')
            path = f.name
        try:
            with self.assertRaises(CaptureValidationError):
                load(path)
        finally:
            os.unlink(path)


class TestGetTheme(unittest.TestCase):
    def test_defaults(self):
        from capture_data import get_theme
        data = _make_grid(["x"])
        t = get_theme(data)
        self.assertEqual(t["background"], "#1e1e2e")
        self.assertEqual(t["foreground"], "#cdd6f4")
        self.assertIn("font_family", t)

    def test_custom_theme(self):
        from capture_data import get_theme
        data = _make_grid(["x"])
        data["theme"] = {"background": "#000000", "font_size": 18}
        t = get_theme(data)
        self.assertEqual(t["background"], "#000000")
        self.assertEqual(t["font_size"], 18)
        # Non-overridden fields use defaults
        self.assertEqual(t["foreground"], "#cdd6f4")


class TestValidateEdgeCases(unittest.TestCase):
    def test_not_a_dict(self):
        with self.assertRaises(CaptureValidationError):
            validate([1, 2, 3])

    def test_non_positive_cols(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 0, "rows": 1, "cells": [[]]})

    def test_non_positive_rows(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": -1, "cells": []})

    def test_cells_not_list(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": 1, "cells": "bad"})

    def test_row_not_list(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": 1, "cells": ["bad"]})

    def test_cell_not_dict(self):
        with self.assertRaises(CaptureValidationError):
            validate({"cols": 1, "rows": 1, "cells": [["bad"]]})


# --- Editor additional tests ---

class TestEditorToDict(unittest.TestCase):
    def test_roundtrip(self):
        from editor import Editor
        data = _make_styled_grid("abc", fg="red")
        editor = Editor(data)
        editor.edit_cell("X")  # modify cursor_y=0, cursor_x=0
        out = editor.to_dict()
        self.assertEqual(out["cols"], 3)
        self.assertEqual(out["rows"], 1)
        self.assertEqual(out["cells"][0][0]["char"], "X")
        self.assertEqual(out["cells"][0][0]["fg"], "red")

    def test_preserves_theme(self):
        from editor import Editor
        data = _make_grid(["abc"])
        data["theme"] = {"background": "#000"}
        editor = Editor(data)
        out = editor.to_dict()
        self.assertEqual(out["theme"]["background"], "#000")

    def test_no_theme_key_when_absent(self):
        from editor import Editor
        data = _make_grid(["abc"])
        editor = Editor(data)
        out = editor.to_dict()
        self.assertNotIn("theme", out)


class TestEditorColorPair(unittest.TestCase):
    def test_nearest_basic_black(self):
        from editor import Editor
        data = _make_grid(["a"])
        editor = Editor(data)
        import curses
        result = editor._nearest_basic((0, 0, 0))
        self.assertEqual(result, curses.COLOR_BLACK)

    def test_nearest_basic_white(self):
        from editor import Editor
        data = _make_grid(["a"])
        editor = Editor(data)
        import curses
        result = editor._nearest_basic((1000, 1000, 1000))
        self.assertEqual(result, curses.COLOR_WHITE)

    def test_nearest_basic_red(self):
        from editor import Editor
        data = _make_grid(["a"])
        editor = Editor(data)
        import curses
        result = editor._nearest_basic((800, 0, 0))
        self.assertEqual(result, curses.COLOR_RED)


# --- Edit apply_ops tests ---

class TestApplyOps(unittest.TestCase):
    def test_replace_all(self):
        from edit import apply_ops
        data = _make_grid(["foo bar foo"])
        count = apply_ops(data, [("replace_all", ("foo", "FOO"))])
        self.assertEqual(count, 1)
        self.assertIn("FOO", to_text(data))

    def test_replace(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [("replace", ("0", "world", "earth"))])
        self.assertEqual(count, 1)
        self.assertEqual(to_text(data), "hello earth")

    def test_set(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [("set", ("0", "6", "WORLD"))])
        self.assertEqual(count, 1)
        self.assertEqual(to_text(data), "hello WORLD")

    def test_clear_row(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [("clear_row", [0])])
        self.assertEqual(count, 1)
        self.assertEqual(to_text(data), "")

    def test_ordered_clear_then_set(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [
            ("clear_row", [0]),
            ("set", ("0", "0", "HI")),
        ])
        self.assertEqual(count, 2)
        self.assertEqual(to_text(data), "HI")

    def test_ordered_set_then_clear(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [
            ("set", ("0", "0", "HI")),
            ("clear_row", [0]),
        ])
        self.assertEqual(count, 2)
        self.assertEqual(to_text(data), "")

    def test_replace_all_not_found(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [("replace_all", ("xyz", "abc"))])
        self.assertEqual(count, 0)

    def test_replace_not_found(self):
        from edit import apply_ops
        data = _make_grid(["hello world"])
        count = apply_ops(data, [("replace", ("0", "xyz", "abc"))])
        self.assertEqual(count, 0)

    def test_multiple_mixed_ops(self):
        from edit import apply_ops
        data = _make_grid(["aaa bbb", "ccc ddd"])
        count = apply_ops(data, [
            ("replace_all", ("aaa", "AAA")),
            ("replace", ("1", "ccc", "CCC")),
            ("set", ("0", "4", "BBB")),
        ])
        self.assertEqual(count, 3)
        text = to_text(data)
        self.assertIn("AAA", text)
        self.assertIn("BBB", text)
        self.assertIn("CCC", text)

    def test_empty_ops(self):
        from edit import apply_ops
        data = _make_grid(["hello"])
        count = apply_ops(data, [])
        self.assertEqual(count, 0)
        self.assertEqual(to_text(data), "hello")


# --- Render dispatch tests ---

class TestRenderToFile(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.data = _make_styled_grid("Hello", fg="red", bold=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_svg(self):
        from render.__main__ import render_to_file
        path = os.path.join(self.tmpdir, "out.svg")
        fmt = render_to_file(self.data, path, title="Test")
        self.assertEqual(fmt, "svg")
        with open(path) as f:
            content = f.read()
        self.assertIn("<svg", content)
        self.assertIn("Test", content)

    def test_html(self):
        from render.__main__ import render_to_file
        path = os.path.join(self.tmpdir, "out.html")
        fmt = render_to_file(self.data, path, title="Test")
        self.assertEqual(fmt, "html")
        with open(path) as f:
            content = f.read()
        self.assertIn("<!DOCTYPE html>", content)

    def test_ansi(self):
        from render.__main__ import render_to_file
        path = os.path.join(self.tmpdir, "out.ansi")
        fmt = render_to_file(self.data, path)
        self.assertEqual(fmt, "ansi")
        with open(path) as f:
            content = f.read()
        self.assertIn("\x1b[", content)

    def test_unsupported_format(self):
        from render.__main__ import render_to_file
        path = os.path.join(self.tmpdir, "out.pdf")
        with self.assertRaises(ValueError) as ctx:
            render_to_file(self.data, path)
        self.assertIn(".pdf", str(ctx.exception))


# --- Session tests ---

class TestSessionBasic(unittest.TestCase):
    def test_capture_echo(self):
        from session import Session
        with Session("echo hello", cols=40, rows=5) as sess:
            sess.wait_for("hello", timeout=5)
            self.assertTrue(sess.screen_contains("hello"))
            text = sess.screen_text()
            self.assertEqual(len(text), 5)
            found = any("hello" in line for line in text)
            self.assertTrue(found)

    def test_to_dict(self):
        from session import Session
        with Session("echo test123", cols=20, rows=3) as sess:
            sess.wait_for("test123", timeout=5)
            data = sess.to_dict()
            self.assertEqual(data["cols"], 20)
            self.assertEqual(data["rows"], 3)
            self.assertEqual(len(data["cells"]), 3)
            self.assertEqual(len(data["cells"][0]), 20)
            # Every cell has a "char" key
            for row in data["cells"]:
                for cell in row:
                    self.assertIn("char", cell)

    def test_wait_for_timeout(self):
        from session import Session
        with Session("echo hello", cols=20, rows=3) as sess:
            sess.drain(settle_time=0.5)
            result = sess.wait_for("NONEXISTENT", timeout=0.5)
            self.assertFalse(result)

    def test_context_manager_kills(self):
        from session import Session
        sess = Session("sleep 60", cols=10, rows=3)
        sess.__enter__()
        pid = sess.proc.pid
        sess.__exit__(None, None, None)
        # Process should be dead
        import signal
        try:
            os.kill(pid, 0)
            self.fail("Process should have been killed")
        except ProcessLookupError:
            pass  # expected

    def test_list_command(self):
        from session import Session
        with Session(["echo", "list_cmd"], cols=30, rows=3) as sess:
            found = sess.wait_for("list_cmd", timeout=5)
            self.assertTrue(found)


# --- Interact key expansion tests ---

class TestExpandKeys(unittest.TestCase):
    def test_enter(self):
        from interact import expand_keys
        self.assertEqual(expand_keys("{enter}"), "\r")

    def test_ctrl_c(self):
        from interact import expand_keys
        self.assertEqual(expand_keys("{ctrl+c}"), "\x03")

    def test_arrow_keys(self):
        from interact import expand_keys
        self.assertEqual(expand_keys("{up}"), "\x1b[A")
        self.assertEqual(expand_keys("{down}"), "\x1b[B")

    def test_mixed(self):
        from interact import expand_keys
        result = expand_keys("hello{enter}")
        self.assertEqual(result, "hello\r")

    def test_escape_sequences(self):
        from interact import expand_keys
        result = expand_keys("\\n")
        self.assertEqual(result, "\n")

    def test_unknown_braces_unchanged(self):
        from interact import expand_keys
        result = expand_keys("{unknown}")
        self.assertEqual(result, "{unknown}")


if __name__ == "__main__":
    unittest.main()
