#!/usr/bin/env python3
"""Unit tests for the termshot pipeline."""

import os
import sys
import unittest

# Add parent dir to path so we can import the modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture_data import validate, to_text, CaptureValidationError
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
        data = _make_styled_grid("AB", fg="#cd0000")
        ansi = render_ansi(data)
        self.assertFalse(ansi.startswith("\x1b[0m"))

    def test_reset_between_style_changes(self):
        data = {"cols": 2, "rows": 1, "cells": [[
            {"char": "A", "fg": "#cd0000"},
            {"char": "B", "fg": "#0000ee"},
        ]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[0m", ansi)

    def test_no_reset_for_same_style(self):
        data = _make_styled_grid("AB", fg="#cd0000")
        ansi = render_ansi(data)
        parts = ansi.split("A")
        after_a = parts[1] if len(parts) > 1 else ""
        self.assertTrue(after_a.startswith("B"))

    def test_ends_with_reset(self):
        data = _make_styled_grid("A", fg="#cd0000")
        ansi = render_ansi(data)
        self.assertTrue(ansi.endswith("\x1b[0m"))

    def test_unstyled_cells_no_escapes(self):
        data = _make_grid(["AB"])
        ansi = render_ansi(data)
        self.assertEqual(ansi, "AB\x1b[0m")


# --- Render SVG/HTML tests ---

class TestRenderSvg(unittest.TestCase):
    def test_basic_output(self):
        from render.svg import render_svg
        data = _make_styled_grid("Hello", fg="#cd0000", bold=True)
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
        data = _make_styled_grid("X", bg="#0000ee")
        svg = render_svg(data)
        # Should have a background rect with the blue color
        self.assertIn("fill=\"#0000ee\"", svg)

    def test_reverse_video(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "R", "fg": "#cd0000", "reverse": True}
        ]]}
        svg = render_svg(data)
        self.assertIn("R", svg)

    def test_underline(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "U", "fg": "#00cd00", "underline": True}
        ]]}
        svg = render_svg(data)
        self.assertIn("stroke=", svg)

    def test_italic(self):
        from render.svg import render_svg
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "I", "fg": "#00cdcd", "italic": True}
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
        data = _make_styled_grid("Hello", fg="#cd0000")
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
        data = _make_styled_grid("B", fg="#cd0000", bold=True)
        html = render_html(data)
        self.assertIn("color:#cd0000", html)
        self.assertIn("font-weight:bold", html)

    def test_background_in_span(self):
        from render.html import render_html
        data = _make_styled_grid("X", bg="#0000ee")
        html = render_html(data)
        self.assertIn("background:#0000ee", html)

    def test_reverse_video(self):
        from render.html import render_html
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "R", "fg": "#cd0000", "bg": "#0000ee", "reverse": True}
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
        data = _make_styled_grid("X", bg="#0000ee")
        ansi = render_ansi(data)
        self.assertIn("\x1b[48;2;0;0;238m", ansi)  # blue bg

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

# --- Render dispatch tests ---

class TestRenderToFile(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = tempfile.mkdtemp()
        self.data = _make_styled_grid("Hello", fg="#cd0000", bold=True)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_svg(self):
        from render import render_to_file
        path = os.path.join(self.tmpdir, "out.svg")
        fmt = render_to_file(self.data, path, title="Test")
        self.assertEqual(fmt, "svg")
        with open(path) as f:
            content = f.read()
        self.assertIn("<svg", content)
        self.assertIn("Test", content)

    def test_html(self):
        from render import render_to_file
        path = os.path.join(self.tmpdir, "out.html")
        fmt = render_to_file(self.data, path, title="Test")
        self.assertEqual(fmt, "html")
        with open(path) as f:
            content = f.read()
        self.assertIn("<!DOCTYPE html>", content)

    def test_ansi(self):
        from render import render_to_file
        path = os.path.join(self.tmpdir, "out.ansi")
        fmt = render_to_file(self.data, path)
        self.assertEqual(fmt, "ansi")
        with open(path) as f:
            content = f.read()
        self.assertIn("\x1b[", content)

    def test_unsupported_format(self):
        from render import render_to_file
        path = os.path.join(self.tmpdir, "out.pdf")
        with self.assertRaises(ValueError) as ctx:
            render_to_file(self.data, path)
        self.assertIn(".pdf", str(ctx.exception))




# =============================================================================
# TDD-style tests: categories 1-8
# =============================================================================


# --- 1. Roundtrip / contract tests ---


# --- 2. Unicode throughout the pipeline ---

class TestUnicodeRender(unittest.TestCase):
    """Unicode characters survive rendering."""

    def test_box_drawing_in_svg(self):
        from render.svg import render_svg
        data = _make_grid(["╔══╗", "║  ║", "╚══╝"])
        svg = render_svg(data)
        self.assertIn("╔", svg)
        self.assertIn("║", svg)
        self.assertIn("╚", svg)

    def test_braille_in_svg(self):
        from render.svg import render_svg
        data = _make_grid(["⣀⣤⣿"])
        svg = render_svg(data)
        self.assertIn("⣀", svg)
        self.assertIn("⣿", svg)

    def test_box_drawing_in_html(self):
        from render.html import render_html
        data = _make_grid(["╔══╗"])
        html = render_html(data)
        self.assertIn("╔", html)

    def test_unicode_in_ansi(self):
        data = _make_grid(["✓ done ✗ fail"])
        ansi = render_ansi(data)
        self.assertIn("✓", ansi)
        self.assertIn("✗", ansi)

    def test_box_drawing_styled(self):
        from render.svg import render_svg
        # Box drawing with color should render both char and color
        cells = [{"char": c, "fg": "#00cdcd"} for c in "╔══╗"]
        data = {"cols": 4, "rows": 1, "cells": [cells]}
        svg = render_svg(data)
        self.assertIn("╔", svg)
        self.assertIn("#00cdcd", svg)  # cyan


# --- 5. Renderer structural correctness ---

class TestRendererStructuralSvg(unittest.TestCase):
    """SVG renderer produces correct structural elements."""

    def test_one_bg_rect_per_colored_cell(self):
        from render.svg import render_svg
        # 3 cells with bg, should produce 3 bg rects (+ 1 main bg rect)
        cells = [
            {"char": "A", "bg": "#cd0000"},
            {"char": "B", "bg": "#0000ee"},
            {"char": "C", "bg": "#00cd00"},
        ]
        data = {"cols": 3, "rows": 1, "cells": [cells]}
        svg = render_svg(data)
        # Count <rect elements -- should be 4 (1 bg + 3 cell bgs)
        rect_count = svg.count("<rect ")
        self.assertEqual(rect_count, 4)

    def test_no_bg_rects_for_unstyled(self):
        from render.svg import render_svg
        data = _make_grid(["ABC"])
        svg = render_svg(data)
        # Only 1 rect: the main background
        rect_count = svg.count("<rect ")
        self.assertEqual(rect_count, 1)

    def test_text_elements_for_non_space(self):
        from render.svg import render_svg
        # Different styles force separate <text> elements
        cells = [
            {"char": "A", "fg": "#cd0000"},
            {"char": " "},
            {"char": "B", "fg": "#0000ee"},
        ]
        data = {"cols": 3, "rows": 1, "cells": [cells]}
        svg = render_svg(data)
        text_count = svg.count("<text ")
        # 1 for "A", 1 for "B" (different styles)
        self.assertGreaterEqual(text_count, 2)

    def test_circle_count(self):
        from render.svg import render_svg
        data = _make_grid(["x"])
        svg = render_svg(data)
        # 3 window dots
        self.assertEqual(svg.count("<circle "), 3)

    def test_line_separator_exists(self):
        from render.svg import render_svg
        data = _make_grid(["x"])
        svg = render_svg(data)
        self.assertIn("<line ", svg)


class TestRendererStructuralHtml(unittest.TestCase):
    """HTML renderer produces correct structural elements."""

    def test_span_count_matches_styled_cells(self):
        from render.html import render_html
        cells = [
            {"char": "A", "fg": "#cd0000"},
            {"char": "B"},  # unstyled -> no span
            {"char": "C", "bold": True},
        ]
        data = {"cols": 3, "rows": 1, "cells": [cells]}
        html = render_html(data)
        span_count = html.count("<span ")
        self.assertEqual(span_count, 2)  # A (fg) and C (bold)

    def test_dot_divs(self):
        from render.html import render_html
        data = _make_grid(["x"])
        html = render_html(data)
        # Each dot class appears in CSS definition + HTML element
        self.assertIn('class="dot dot-red"', html)
        self.assertIn('class="dot dot-yellow"', html)
        self.assertIn('class="dot dot-green"', html)


class TestRendererAnsiExactBytes(unittest.TestCase):
    """ANSI renderer produces exact byte sequences for known input."""

    def test_single_red_char(self):
        data = {"cols": 1, "rows": 1, "cells": [[{"char": "A", "fg": "#cd0000"}]]}
        ansi = render_ansi(data)
        self.assertEqual(ansi, "\x1b[38;2;205;0;0mA\x1b[0m")

    def test_two_same_style_chars(self):
        data = {"cols": 2, "rows": 1, "cells": [[
            {"char": "A", "fg": "#cd0000"},
            {"char": "B", "fg": "#cd0000"},
        ]]}
        ansi = render_ansi(data)
        # Same style -> no reset between A and B
        self.assertEqual(ansi, "\x1b[38;2;205;0;0mAB\x1b[0m")

    def test_two_different_style_chars(self):
        data = {"cols": 2, "rows": 1, "cells": [[
            {"char": "A", "fg": "#cd0000"},
            {"char": "B", "fg": "#0000ee"},
        ]]}
        ansi = render_ansi(data)
        self.assertEqual(ansi, "\x1b[38;2;205;0;0mA\x1b[0m\x1b[38;2;0;0;238mB\x1b[0m")

    def test_plain_no_escapes_except_reset(self):
        data = {"cols": 3, "rows": 1, "cells": [[
            {"char": "A"}, {"char": "B"}, {"char": "C"},
        ]]}
        ansi = render_ansi(data)
        self.assertEqual(ansi, "ABC\x1b[0m")

    def test_bold_and_fg(self):
        data = {"cols": 1, "rows": 1, "cells": [[
            {"char": "X", "fg": "#00cd00", "bold": True},
        ]]}
        ansi = render_ansi(data)
        self.assertIn("\x1b[38;2;0;205;0m", ansi)  # green fg
        self.assertIn("\x1b[1m", ansi)   # bold
        self.assertIn("X", ansi)
        self.assertTrue(ansi.endswith("\x1b[0m"))

    def test_two_rows(self):
        data = {"cols": 1, "rows": 2, "cells": [
            [{"char": "A", "fg": "#cd0000"}],
            [{"char": "B", "fg": "#0000ee"}],
        ]}
        ansi = render_ansi(data)
        lines = ansi.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "\x1b[38;2;205;0;0mA\x1b[0m")
        self.assertEqual(lines[1], "\x1b[38;2;0;0;238mB\x1b[0m")



if __name__ == "__main__":
    unittest.main()
