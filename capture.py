#!/usr/bin/env python3
"""
Capture a TUI application's screen state to a JSON file.

Usage:
    python3 capture.py <command> [--cols 80] [--rows 24] [--wait 1.0] -o output.json

Examples:
    python3 capture.py "htop" -o htop.json
    python3 capture.py "ls --color=always -la" -o ls.json
    python3 capture.py "python3 my_tui.py" --cols 120 --rows 40 -o tui.json
"""

import argparse
import json
import os
import pty
import select
import signal
import subprocess
import sys
import time

import pyte


def normalize_color(color_value):
    """Store the raw pyte color value, only skipping 'default'."""
    if not color_value or color_value == "default":
        return None
    return color_value


def capture_command(command, cols, rows, wait_time, input_keys=None):
    """Run a command in a virtual terminal and capture its screen state."""
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)

    # Create a pseudo-terminal
    master_fd, slave_fd = pty.openpty()

    # Set terminal size
    import fcntl
    import struct
    import termios
    winsize = struct.pack("HHHH", rows, cols, 0, 0)
    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLUMNS"] = str(cols)
    env["LINES"] = str(rows)

    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        env=env,
        preexec_fn=os.setsid,
    )
    os.close(slave_fd)

    # Send any input keys (for interactive TUIs)
    if input_keys:
        for key_seq in input_keys:
            time.sleep(0.1)
            os.write(master_fd, key_seq.encode("utf-8"))

    # Read output until wait_time elapses with no new data
    deadline = time.time() + wait_time
    while time.time() < deadline:
        ready, _, _ = select.select([master_fd], [], [], 0.1)
        if ready:
            try:
                data = os.read(master_fd, 65536)
                if data:
                    stream.feed(data.decode("utf-8", errors="replace"))
                    deadline = time.time() + wait_time  # reset timer on new data
                else:
                    break
            except OSError:
                break

    # Kill the process
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    os.close(master_fd)

    return screen


def screen_to_dict(screen):
    """Convert a pyte Screen to a serializable dictionary."""
    rows = []
    for y in range(screen.lines):
        cells = []
        for x in range(screen.columns):
            char = screen.buffer[y][x]
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
        "cols": screen.columns,
        "rows": screen.lines,
        "cells": rows,
    }


def main():
    parser = argparse.ArgumentParser(description="Capture a TUI to JSON")
    parser.add_argument("command", help="Command to run")
    parser.add_argument("--cols", type=int, default=80, help="Terminal columns")
    parser.add_argument("--rows", type=int, default=24, help="Terminal rows")
    parser.add_argument("--wait", type=float, default=1.5,
                        help="Seconds to wait for output to settle")
    parser.add_argument("--keys", nargs="*",
                        help="Input key sequences to send (e.g. '\\n' for enter)")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file")
    args = parser.parse_args()

    # Process escape sequences in key args
    keys = None
    if args.keys:
        keys = [k.encode().decode("unicode_escape") for k in args.keys]

    print(f"Capturing: {args.command} ({args.cols}x{args.rows})")
    screen = capture_command(args.command, args.cols, args.rows, args.wait, keys)
    data = screen_to_dict(screen)

    with open(args.output, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved to {args.output}")
    print(f"Now edit the JSON, then run: python3 render.py {args.output} -o mockup.svg")


if __name__ == "__main__":
    main()
