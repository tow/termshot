"""Render captured terminal state to PNG via a real terminal emulator.

macOS: launches kitty minimized, captures via screencapture.
Linux: launches Xvfb + urxvt/xterm, captures via ImageMagick.
"""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from render.ansi import render_ansi
from capture_data import get_theme
from kitty_util import find_kitty


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG via a headless terminal.

    On macOS, uses kitty + screencapture.
    On Linux, uses Xvfb + urxvt/xterm + ImageMagick.
    """
    if sys.platform == "darwin":
        _render_png_kitty(data, output_path, font_name, font_size)
    else:
        _render_png_xvfb(data, output_path, font_name, font_size, terminal)


# ── macOS: kitty + screencapture ──────────────────────────────────────────────

def _render_png_kitty(data, output_path, font_name, font_size):
    """Render via kitty terminal on macOS.

    Launches kitty minimized with remote control, cats the ANSI output,
    retrieves the OS window ID, and uses screencapture to grab the window.
    """
    kitty = find_kitty()
    if not shutil.which("screencapture"):
        print("Error: screencapture not found", file=sys.stderr)
        sys.exit(1)

    t = get_theme(data)
    ansi_content = render_ansi(data)
    cols = data["cols"]
    rows = data["rows"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    sock_dir = tempfile.mkdtemp(prefix="termshot-")
    sock_path = os.path.join(sock_dir, "kitty.sock")

    kitty_proc = None
    try:
        kitty_proc = subprocess.Popen([
            kitty,
            "--start-as=minimized",
            "--listen-on", f"unix:{sock_path}",
            "-o", "allow_remote_control=yes",
            "-o", f"font_family={font_name}",
            "-o", f"font_size={font_size}",
            "-o", f"background={t['background']}",
            "-o", f"foreground={t['foreground']}",
            "-o", f"initial_window_width={cols}c",
            "-o", f"initial_window_height={rows}c",
            "-o", "window_padding_width=0",
            "-o", "hide_window_decorations=yes",
            "-o", "confirm_os_window_close=0",
            "-o", "macos_quit_when_last_window_closed=yes",
            "-e", "bash", "-c",
            f"printf '\\033[?25l'; cat {shlex.quote(ansi_path)}; sleep 60",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Wait for the socket to appear (kitty is ready)
        for _ in range(50):
            time.sleep(0.1)
            if os.path.exists(sock_path):
                break
        else:
            print("Error: kitty did not start (socket not created)",
                  file=sys.stderr)
            sys.exit(1)

        # Give kitty time to render the content
        time.sleep(1.5)

        # Get the macOS window ID via kitty remote control
        result = subprocess.run(
            [kitty, "@", "--to", f"unix:{sock_path}", "ls"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"Error: kitty remote control failed: {result.stderr}",
                  file=sys.stderr)
            sys.exit(1)

        ls_data = json.loads(result.stdout)
        window_id = ls_data[0].get("platform_window_id")
        if not window_id:
            print("Error: could not get kitty window ID", file=sys.stderr)
            sys.exit(1)

        # screencapture -l captures by CGWindowID, works even when minimized
        # -o removes the drop shadow
        subprocess.run(
            ["screencapture", "-l", str(window_id), "-o", output_path],
            check=True,
        )
    finally:
        if kitty_proc:
            kitty_proc.kill()
            kitty_proc.wait()
        os.unlink(ansi_path)
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        os.rmdir(sock_dir)


# ── Linux: Xvfb + terminal + ImageMagick ─────────────────────────────────────

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


def _render_png_xvfb(data, output_path, font_name, font_size, terminal):
    """Render via Xvfb + terminal emulator on Linux."""
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
