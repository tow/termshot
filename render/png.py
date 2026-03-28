"""Render captured terminal state to PNG via kitty + window capture."""

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from render.ansi import render_ansi


def render_png(data, output_path, font_name="DejaVu Sans Mono",
               font_size=14, terminal=None):
    """Render terminal state to PNG by launching kitty and capturing the window."""
    theme = data.get("theme", {})
    bg = theme.get("background", "#1e1e2e")
    fg = theme.get("foreground", "#cdd6f4")
    ansi_content = render_ansi(data)
    cols, rows = data["cols"], data["rows"]

    kitty = _find_kitty()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".ansi", delete=False) as f:
        f.write(ansi_content)
        ansi_path = f.name

    sock_dir = tempfile.mkdtemp(prefix="termshot-")
    sock_path = os.path.join(sock_dir, "kitty.sock")

    try:
        proc = subprocess.Popen([
            kitty,
            "--listen-on", f"unix:{sock_path}",
            "-o", "allow_remote_control=yes",
            "-o", "confirm_os_window_close=0",
            "-o", "macos_quit_when_last_window_closed=yes",
            "-o", f"font_family={font_name}",
            "-o", f"font_size={font_size}",
            "-o", f"background={bg}",
            "-o", f"foreground={fg}",
            "-o", f"initial_window_width={cols}c",
            "-o", f"initial_window_height={rows}c",
            "-o", "window_padding_width=0",
            "-o", "hide_window_decorations=yes",
            "-e", "bash", "-c",
            f"printf '\\033[?25l'; cat {shlex.quote(ansi_path)}; sleep 60",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(50):
            time.sleep(0.1)
            if os.path.exists(sock_path):
                break

        time.sleep(1.5)

        import json
        result = subprocess.run(
            [kitty, "@", "--to", f"unix:{sock_path}", "ls"],
            capture_output=True, text=True,
        )
        window_id = json.loads(result.stdout)[0]["platform_window_id"]

        if sys.platform == "darwin":
            subprocess.run(
                ["screencapture", "-l", str(window_id), "-o", output_path],
                check=True,
            )
        else:
            subprocess.run(
                ["import", "-window", str(window_id), output_path],
                check=True,
            )

        proc.kill()
        proc.wait()
    finally:
        os.unlink(ansi_path)
        if os.path.exists(sock_path):
            os.unlink(sock_path)
        os.rmdir(sock_dir)


def _find_kitty():
    path = shutil.which("kitty")
    if path:
        return path
    mac_path = "/Applications/kitty.app/Contents/MacOS/kitty"
    if os.path.isfile(mac_path):
        return mac_path
    print("Error: kitty not found. Install with: brew install --cask kitty",
          file=sys.stderr)
    sys.exit(1)
