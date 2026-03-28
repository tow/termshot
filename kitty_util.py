"""Shared utilities for interacting with the kitty terminal."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time


def find_kitty():
    """Find the kitty binary, checking PATH and standard macOS location."""
    path = shutil.which("kitty")
    if path:
        return path
    mac_path = "/Applications/kitty.app/Contents/MacOS/kitty"
    if os.path.isfile(mac_path):
        return mac_path
    print("Error: kitty not found. Install with: brew install --cask kitty",
          file=sys.stderr)
    sys.exit(1)


class KittyWindow:
    """A kitty terminal window with remote control."""

    def __init__(self, kitty=None, extra_opts=None):
        self.kitty = kitty or find_kitty()
        self._sock_dir = tempfile.mkdtemp(prefix="termshot-")
        self.sock_path = os.path.join(self._sock_dir, "kitty.sock")
        self.proc = None
        self._extra_opts = extra_opts or []

    def launch(self, cmd=None):
        """Launch kitty with remote control enabled.

        If cmd is given, kitty runs that command; otherwise opens a shell.
        """
        args = [
            self.kitty,
            "--listen-on", f"unix:{self.sock_path}",
            "-o", "allow_remote_control=yes",
            "-o", "confirm_os_window_close=0",
            "-o", "macos_quit_when_last_window_closed=yes",
        ]
        args.extend(self._extra_opts)
        if cmd:
            args.extend(["-e"] + cmd)
        self.proc = subprocess.Popen(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Wait for socket
        for _ in range(50):
            time.sleep(0.1)
            if os.path.exists(self.sock_path):
                return
        raise RuntimeError("kitty did not start (socket not created)")

    def remote(self, *cmd_args, **kwargs):
        """Run a kitty @ remote control command. Returns CompletedProcess."""
        return subprocess.run(
            [self.kitty, "@", "--to", f"unix:{self.sock_path}"] + list(cmd_args),
            capture_output=True, text=True, **kwargs,
        )

    def get_text(self, ansi=True):
        """Get the screen text via remote control.

        Uses --add-wrap-markers so that \\r indicates a line wrap (next screen
        row, same logical line) and \\n indicates a real newline. Both mean
        "advance to the next screen row" for our purposes.
        """
        args = ["get-text", "--extent=screen", "--add-wrap-markers"]
        if ansi:
            args.append("--ansi")
        result = self.remote(*args)
        if result.returncode != 0:
            raise RuntimeError(f"get-text failed: {result.stderr}")
        return result.stdout

    def get_dimensions(self):
        """Get the terminal dimensions (cols, rows) from kitty."""
        result = self.remote("ls")
        if result.returncode != 0:
            raise RuntimeError(f"ls failed: {result.stderr}")
        ls_data = json.loads(result.stdout)
        # Find the active window
        for os_win in ls_data:
            for tab in os_win.get("tabs", []):
                for win in tab.get("windows", []):
                    return win["columns"], win["lines"]
        raise RuntimeError("no kitty window found")

    def get_window_id(self):
        """Get the platform window ID for screencapture."""
        result = self.remote("ls")
        if result.returncode != 0:
            raise RuntimeError(f"ls failed: {result.stderr}")
        ls_data = json.loads(result.stdout)
        return ls_data[0]["platform_window_id"]

    def kill(self):
        """Kill the kitty process and clean up."""
        if self.proc:
            self.proc.kill()
            self.proc.wait()
            self.proc = None
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)
        if os.path.exists(self._sock_dir):
            os.rmdir(self._sock_dir)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kill()


def capture_window(window_id, output_path):
    """Capture a window to PNG using the platform's tool."""
    if sys.platform == "darwin":
        subprocess.run(
            ["screencapture", "-l", str(window_id), "-o", output_path],
            check=True,
        )
    else:
        if not shutil.which("import"):
            print("Error: import (ImageMagick) not found. "
                  "Install with: apt-get install imagemagick",
                  file=sys.stderr)
            sys.exit(1)
        subprocess.run(
            ["import", "-window", str(window_id), output_path],
            check=True,
        )
