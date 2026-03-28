# termshot

Capture, edit, and render terminal screenshots with pixel-perfect accuracy.

termshot uses [kitty](https://sw.kovidgoyal.net/kitty/) as a real terminal renderer, so what you see in the screenshot is exactly what a user would see -- correct fonts, Unicode, box-drawing characters, truecolor, and all.

## How it works

1. **Capture** -- launch a kitty terminal window, set up whatever you want to screenshot
2. **Edit** -- modify text while preserving styles (colors, bold, etc.)
3. **Render** -- take a screenshot of the kitty window, or export to SVG/HTML

```
python3 capture.py -o screenshot.png
```

This single command runs the full workflow:

- Opens a kitty terminal for you to set up content
- Press **Enter** in the controlling terminal when ready
- Opens an interactive editor in a new kitty window
- Press **Ctrl+S** to save edits, then **Enter** in the controlling terminal
- Captures the kitty window to PNG

## Requirements

- Python 3.8+
- [kitty terminal](https://sw.kovidgoyal.net/kitty/) (`brew install --cask kitty` on macOS)
- `screencapture` (macOS, built-in) or `import` from ImageMagick (Linux)

## Interactive editor

The editor runs inside kitty so rendering is pixel-perfect. Your keystrokes go directly to the editor.

| Key | Action |
|-----|--------|
| Arrow keys | Move cursor |
| Home / End | Jump to start/end of row |
| Any character | Overwrite (keeps cell style) |
| Backspace | Replace with space, move left |
| Cmd+B / Alt+B | Toggle bold |
| Cmd+I / Alt+I | Toggle italic |
| Cmd+U / Alt+U | Toggle underline |
| Cmd+R / Alt+R | Toggle reverse |
| Ctrl+Y | Copy style from current cell |
| Ctrl+P | Paste style to current cell |
| Cmd+Z / Ctrl+Z | Undo |
| Cmd+S / Ctrl+S | Save and quit |
| Escape | Quit without saving |

Supports pasting Unicode characters (Cmd+V / Ctrl+Shift+V). Cmd shortcuts work on macOS via kitty key mappings applied automatically to the editor window.

## Rendering

Render a captured JSON to various formats:

```bash
python3 -m render capture.json -o output.png
python3 -m render capture.json -o output.svg --title "My Terminal"
python3 -m render capture.json -o output.html --title "My Terminal"
```

| Format | Notes |
|--------|-------|
| PNG | Screenshots a real kitty window -- pixel-perfect |
| SVG | Fully self-contained, scalable |
| HTML | Interactive, selectable text |

## JSON format

The intermediate format is a simple JSON structure:

```json
{
  "cols": 80,
  "rows": 24,
  "cells": [
    [{"char": "H", "fg": "#ff0000", "bold": true}, ...]
  ]
}
```

Each cell has a `char` and optional style properties: `fg`, `bg`, `bold`, `italic`, `underline`, `reverse`.

## Architecture

```
capture.py          Interactive workflow: capture -> edit -> render
editor.py           ANSI-based editor running in kitty
render/             SVG, HTML, PNG, ANSI renderers
kitty_util.py       Kitty remote control wrapper
ansi_parse.py       ANSI escape sequence parser
capture_data.py     JSON data model and validation
colors.py           Color definitions and conversion
```
