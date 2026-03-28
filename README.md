# termshot

Capture, edit, and render terminal screenshots with pixel-perfect accuracy.

termshot uses [kitty](https://sw.kovidgoyal.net/kitty/) as a real terminal renderer, so what you see in the screenshot is exactly what a user would see -- correct fonts, Unicode, box-drawing characters, truecolor, and all.

## How it works

```
python3 capture.py -o screenshot.png
```

1. Opens a kitty terminal -- set up whatever you want to screenshot
2. Press **Enter** in the controlling terminal to capture
3. Opens an editor in a new kitty window -- make any text or style changes
4. Press **Ctrl+S** to save, then **Enter** in the controlling terminal
5. Screenshots the kitty window to PNG (or renders to SVG/HTML)

## Requirements

- Python 3.8+
- [kitty](https://sw.kovidgoyal.net/kitty/) (`brew install --cask kitty` on macOS)
- `screencapture` (macOS, built-in) or ImageMagick `import` (Linux)

## Editor

The editor runs inside kitty for pixel-perfect rendering.

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

Supports pasting Unicode characters via Cmd+V.

## Rendering

Render a saved JSON capture to various formats:

```bash
python3 -m render capture.json -o output.png
python3 -m render capture.json -o output.svg --title "My Terminal"
python3 -m render capture.json -o output.html --title "My Terminal"
```

| Format | Notes |
|--------|-------|
| PNG | Screenshots a real kitty window |
| SVG | Self-contained, scalable |
| HTML | Selectable text |

## JSON format

```json
{
  "cols": 80,
  "rows": 24,
  "cells": [
    [{"char": "H", "fg": "#ff0000", "bold": true}, ...]
  ]
}
```

Each cell has a `char` and optional style properties: `fg`, `bg` (hex colors), `bold`, `italic`, `underline`, `reverse`.

## Files

```
capture.py      Main workflow, kitty control, ANSI parser, JSON I/O
editor.py       Interactive editor (runs in kitty)
render/         SVG, HTML, PNG, ANSI renderers
```
