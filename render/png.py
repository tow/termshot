"""Render captured terminal state to PNG via a headless terminal.

Launches Xvfb + a real terminal emulator, cats the ANSI output, and
screenshots the window with ImageMagick. Prefers urxvt over xterm.
"""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from render.ansi import render_ansi
from capture_data import get_theme


def _build_terminal_cmd(terminal, font_name, font_size, bg, fg, cols, rows, ansi_path):
    """Build the command to launch a terminal displaying the ANSI file."""
    shell_cmd = f"printf '\\033[?25l'; cat {shlex.quote(ansi_path)}; sleep 10"

    if terminal == "urxvt":
        return [
            "urxvt",
            "-fn", f"xft:{font_name}:size={font_size}",
            "-bg", bg,
            "-fg", fg,
            "-geometry", f"{cols + 2}x{rows + 1}",
            "-b", "0",
            "-bl",
            "+sb",
            "-e", "bash", "-c", shell_cmd,
        ]
    else:  # xterm
        return [
            "xterm",
            "-fa", font_name,
            "-fs", str(font_size),
            "-bg", bg,
            "-fg", fg,
            "-geometry", f"{cols + 2}x{rows + 1}",
            "+sb",
            "-b", "0",
            "-bw", "0",
            "-e", shell_cmd,
        ]


def _detect_terminal():
    """Pick the best available terminal for headless rendering."""
    for term in ["urxvt", "xterm"]:
        if shutil.which(term):
            return term
    return None


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG via a headless terminal.

    Launches Xvfb + a real terminal emulator, cats the ANSI output, and
    screenshots the window with ImageMagick. The terminal handles all font
    rendering, Unicode, colors, and character alignment.

    Prefers urxvt (better Unicode/box-drawing) over xterm.
    """
    for tool in ["Xvfb", "xdotool", "import"]:
        if not shutil.which(tool):
            print(f"Error: {tool} not found. Install with: "
                  f"apt-get install xvfb xdotool imagemagick",
                  file=sys.stderr)
            sys.exit(1)

    if terminal is None:
        terminal = _detect_terminal()
    if terminal is None or not shutil.which(terminal):
        print("Error: no terminal found. Install urxvt or xterm.",
              file=sys.stderr)
        sys.exit(1)

    t = get_theme(data)
    ansi_content = render_ansi(data)
    cols = data["cols"]
    rows = data["rows"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    xvfb = None
    term_proc = None
    try:
        # Launch Xvfb on a free display, retrying on collision
        for candidate in range(10, 100):
            if os.path.exists(f"/tmp/.X{candidate}-lock"):
                continue
            proc = subprocess.Popen(
                ["Xvfb", f":{candidate}", "-screen", "0", "1920x1080x24"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(0.3)
            if proc.poll() is not None:
                continue
            xvfb = proc
            display_num = candidate
            break
        if xvfb is None:
            print("Error: could not start Xvfb on any display :10-:99",
                  file=sys.stderr)
            sys.exit(1)

        env = os.environ.copy()
        env["DISPLAY"] = f":{display_num}"
        env["LC_ALL"] = "C.utf8"
        env["LANG"] = "C.utf8"

        cmd = _build_terminal_cmd(
            terminal, font_name, font_size,
            t["background"], t["foreground"],
            cols, rows, ansi_path,
        )
        term_proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

        result = subprocess.run(
            ["xdotool", "search", "--pid", str(term_proc.pid)],
            env=env, capture_output=True, text=True,
        )
        window_ids = result.stdout.strip().split("\n")
        window_id = window_ids[0] if window_ids[0] else ""

        if not window_id:
            print(f"Error: {terminal} window not found (process may have crashed)",
                  file=sys.stderr)
            sys.exit(1)

        subprocess.run(
            ["import", "-window", window_id, output_path],
            env=env, check=True,
        )
    finally:
        if term_proc:
            term_proc.kill()
        if xvfb:
            xvfb.kill()
        os.unlink(ansi_path)
