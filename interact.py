#!/usr/bin/env python3
"""
Drive a TUI through a scripted interaction, then capture the result.

Takes a YAML script that defines a sequence of wait-for / send / snapshot
steps. Each step waits for the screen to be ready before acting.

Usage:
    python3 interact.py script.yaml -o final.json

Script format (YAML):
    command: "python3 my_tui.py"
    cols: 120
    rows: 40
    steps:
      - wait_for: "Welcome"          # wait until screen contains this text
        timeout: 5                    # optional, seconds (default 10)

      - send: "hello world"          # send keystrokes

      - send: "\\n"                   # send enter (escape sequences supported)

      - send: "\\x1b[A"              # send up arrow (raw escape)

      - wait_for: "Results"
        send: "q"                    # combined: wait, then send

      - wait_for_stable: 2.0         # wait until screen stops changing for N seconds

      - snapshot: "step3.json"       # save screen state at this point

    # The final screen state is always saved to the -o output file.

Named keys shorthand (use in send values):
    {enter}     → \\r
    {tab}       → \\t
    {escape}    → \\x1b
    {up}        → \\x1b[A
    {down}      → \\x1b[B
    {right}     → \\x1b[C
    {left}      → \\x1b[D
    {backspace} → \\x7f
    {delete}    → \\x1b[3~
    {home}      → \\x1b[H
    {end}       → \\x1b[F
    {ctrl+c}    → \\x03
    {ctrl+d}    → \\x04
    {ctrl+z}    → \\x1a
"""

import argparse
import json
import re
import sys

import yaml

from session import Session


NAMED_KEYS = {
    "{enter}":     "\r",
    "{tab}":       "\t",
    "{escape}":    "\x1b",
    "{up}":        "\x1b[A",
    "{down}":      "\x1b[B",
    "{right}":     "\x1b[C",
    "{left}":      "\x1b[D",
    "{backspace}": "\x7f",
    "{delete}":    "\x1b[3~",
    "{home}":      "\x1b[H",
    "{end}":       "\x1b[F",
    "{ctrl+c}":    "\x03",
    "{ctrl+d}":    "\x04",
    "{ctrl+z}":    "\x1a",
}


def expand_keys(text):
    """Replace {enter}, {up}, etc. with actual escape sequences, then process \\n-style escapes."""
    for name, value in NAMED_KEYS.items():
        text = text.replace(name, value)
    # Process Python-style escape sequences (\\n, \\t, \\x1b, etc.)
    # but only for sequences that haven't already been expanded
    text = re.sub(
        r'\\(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|n|r|t|\\)',
        lambda m: m.group(0).encode().decode("unicode_escape"),
        text,
    )
    return text


def save_snapshot(sess, path):
    """Save current screen state to a JSON file."""
    data = sess.to_dict()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  snapshot → {path}")


def run_script(script_path, output_path):
    with open(script_path) as f:
        script = yaml.safe_load(f)

    command = script["command"]
    cols = script.get("cols", 80)
    rows = script.get("rows", 24)
    steps = script.get("steps", [])

    print(f"Running: {command} ({cols}x{rows}), {len(steps)} steps")

    with Session(command, cols=cols, rows=rows) as sess:
        # Let the TUI start up
        sess.drain(settle_time=0.5)

        for i, step in enumerate(steps):
            step_num = i + 1

            # Wait for specific text
            if "wait_for" in step:
                target = step["wait_for"]
                timeout = step.get("timeout", 10)
                print(f"  [{step_num}] waiting for {target!r} (timeout {timeout}s)...")
                found = sess.wait_for(target, timeout=timeout)
                if not found:
                    print(f"  [{step_num}] TIMEOUT waiting for {target!r}", file=sys.stderr)
                    # Dump what's on screen for debugging
                    print("  Current screen:", file=sys.stderr)
                    for line in sess.screen_text():
                        rstripped = line.rstrip()
                        if rstripped:
                            print(f"    {rstripped}", file=sys.stderr)
                    if step.get("required", True):
                        print(f"  Aborting. Set 'required: false' to continue past timeouts.",
                              file=sys.stderr)
                        break
                else:
                    print(f"  [{step_num}] found {target!r}")

            # Wait for screen to stabilize
            if "wait_for_stable" in step:
                settle = step["wait_for_stable"]
                print(f"  [{step_num}] waiting for stable ({settle}s)...")
                sess.wait_for_stable(settle_time=settle)
                print(f"  [{step_num}] stable")

            # Send input
            if "send" in step:
                raw = step["send"]
                expanded = expand_keys(raw)
                print(f"  [{step_num}] send {raw!r}")
                sess.send(expanded)
                # Brief drain after sending to let TUI process the input
                sess.drain(settle_time=0.3)

            # Intermediate snapshot
            if "snapshot" in step:
                save_snapshot(sess, step["snapshot"])

        # Final drain and save
        sess.wait_for_stable(settle_time=0.5)
        data = sess.to_dict()

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Saved final state to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Script-driven TUI interaction + capture")
    parser.add_argument("script", help="YAML interaction script")
    parser.add_argument("-o", "--output", required=True, help="Output JSON file (final state)")
    args = parser.parse_args()
    run_script(args.script, args.output)


if __name__ == "__main__":
    main()
