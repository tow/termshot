"""
Shared pty session management for capture and interact.
"""

import fcntl
import os
import pty
import select
import shlex
import signal
import struct
import subprocess
import termios
import time

import pyte

from colors import normalize_color


class Session:
    """A virtual terminal session running a command in a pty."""

    def __init__(self, command, cols=80, rows=24):
        self.cols = cols
        self.rows = rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.master_fd = None
        self.proc = None

        master_fd, slave_fd = pty.openpty()
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLUMNS"] = str(cols)
        env["LINES"] = str(rows)

        argv = shlex.split(command) if isinstance(command, str) else list(command)
        self.proc = subprocess.Popen(
            argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            preexec_fn=os.setsid,
        )
        os.close(slave_fd)
        self.master_fd = master_fd

    def drain(self, settle_time=0.5):
        """Read all available output until no new data arrives for settle_time seconds."""
        deadline = time.time() + settle_time
        while time.time() < deadline:
            ready, _, _ = select.select([self.master_fd], [], [], 0.05)
            if ready:
                try:
                    data = os.read(self.master_fd, 65536)
                    if data:
                        self.stream.feed(data.decode("utf-8", errors="replace"))
                        deadline = time.time() + settle_time
                    else:
                        break
                except OSError:
                    break

    def send(self, text):
        """Send raw text/keystrokes to the pty."""
        if self.master_fd is None:
            raise RuntimeError("Session is closed")
        os.write(self.master_fd, text.encode("utf-8"))

    def screen_text(self):
        """Return current screen content as a list of strings (one per row)."""
        lines = []
        for y in range(self.screen.lines):
            line = "".join(self.screen.buffer[y][x].data
                           for x in range(self.screen.columns))
            lines.append(line)
        return lines

    def screen_contains(self, text):
        """Check if any screen row contains the given text."""
        for line in self.screen_text():
            if text in line:
                return True
        return False

    def wait_for(self, text, timeout=10.0, poll_interval=0.1):
        """Wait until the screen contains the given text, draining output continuously.

        Returns True if found, False if timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            # Drain any pending output (short settle)
            self.drain(settle_time=poll_interval)
            if self.screen_contains(text):
                return True
        return False

    def wait_for_stable(self, settle_time=1.0):
        """Wait until the screen stops changing for settle_time seconds."""
        self.drain(settle_time=settle_time)

    def to_dict(self):
        """Convert current screen state to a serializable dictionary."""
        rows = []
        for y in range(self.screen.lines):
            cells = []
            for x in range(self.screen.columns):
                char = self.screen.buffer[y][x]
                cell = {"char": char.data}
                fg = normalize_color(char.fg)
                bg = normalize_color(char.bg)
                if fg:
                    cell["fg"] = fg
                if bg:
                    cell["bg"] = bg
                if char.bold:
                    cell["bold"] = True
                if char.italics:
                    cell["italic"] = True
                if char.underscore:
                    cell["underline"] = True
                if char.reverse:
                    cell["reverse"] = True
                cells.append(cell)
            rows.append(cells)

        return {
            "cols": self.screen.columns,
            "rows": self.screen.lines,
            "cells": rows,
        }

    def kill(self):
        """Terminate the subprocess."""
        if self.proc:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                pass
            self.master_fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.kill()
