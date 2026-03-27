"""
Shared data model for captured terminal state.

The JSON contract between all termshot modules:
    {
        "cols": int,
        "rows": int,
        "cells": [[{"char": str, "fg"?: str, "bg"?: str,
                     "bold"?: bool, "italic"?: bool,
                     "underline"?: bool, "reverse"?: bool}, ...], ...],
        "theme"?: { ... }
    }
"""

import json


class CaptureValidationError(ValueError):
    pass


def validate(data):
    """Validate a capture data dict. Raises CaptureValidationError on problems."""
    if not isinstance(data, dict):
        raise CaptureValidationError("Capture data must be a dict")

    for key in ("cols", "rows", "cells"):
        if key not in data:
            raise CaptureValidationError(f"Missing required key: {key!r}")

    cols = data["cols"]
    rows = data["rows"]
    cells = data["cells"]

    if not isinstance(cols, int) or cols <= 0:
        raise CaptureValidationError(f"'cols' must be a positive int, got {cols!r}")
    if not isinstance(rows, int) or rows <= 0:
        raise CaptureValidationError(f"'rows' must be a positive int, got {rows!r}")
    if not isinstance(cells, list):
        raise CaptureValidationError("'cells' must be a list")
    if len(cells) != rows:
        raise CaptureValidationError(
            f"'cells' has {len(cells)} rows, expected {rows}")

    for y, row in enumerate(cells):
        if not isinstance(row, list):
            raise CaptureValidationError(f"Row {y} is not a list")
        if len(row) != cols:
            raise CaptureValidationError(
                f"Row {y} has {len(row)} cells, expected {cols}")
        for x, cell in enumerate(row):
            if not isinstance(cell, dict):
                raise CaptureValidationError(
                    f"Cell ({y},{x}) is not a dict")
            if "char" not in cell:
                raise CaptureValidationError(
                    f"Cell ({y},{x}) missing 'char' key")


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
    """Convert capture to plain text for inspection."""
    lines = []
    for row in data["cells"]:
        lines.append("".join(cell.get("char", " ") for cell in row).rstrip())
    return "\n".join(lines)


def get_theme(data):
    """Extract rendering theme with defaults. Only affects window chrome, not cell colors."""
    theme = data.get("theme", {})
    return {
        "font_family": theme.get("font_family", "JetBrains Mono, Fira Code, Menlo, monospace"),
        "font_size": theme.get("font_size", 14),
        "line_height": theme.get("line_height", 1.4),
        "padding": theme.get("padding", 16),
        "border_radius": theme.get("border_radius", 10),
        "background": theme.get("background", "#1e1e2e"),
        "foreground": theme.get("foreground", "#cdd6f4"),
    }
