"""Stress-test TUI with box drawing, block chars, truecolor, and Unicode."""
import sys
import time

def csi(code):
    sys.stdout.write(f"\x1b[{code}")

def fg_rgb(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m"

def bg_rgb(r, g, b):
    return f"\x1b[48;2;{r};{g};{b}m"

def reset():
    return "\x1b[0m"

def main():
    # Clear screen, hide cursor
    csi("2J")
    csi("?25l")
    csi("H")

    out = sys.stdout

    # ── Box-drawing border ──
    top    = "╔" + "═" * 48 + "╗"
    bottom = "╚" + "═" * 48 + "╝"
    side   = "║"
    divider = "╠" + "═" * 48 + "╣"

    # Position and draw box
    csi("1;1H")
    out.write(fg_rgb(100, 180, 255) + top + reset())

    csi("2;1H")
    title = "  Dashboard — Status Overview  "
    padding = 48 - len(title)
    out.write(fg_rgb(100, 180, 255) + side + reset()
              + fg_rgb(255, 200, 60) + "\x1b[1m" + title + reset()
              + " " * padding
              + fg_rgb(100, 180, 255) + side + reset())

    csi("3;1H")
    out.write(fg_rgb(100, 180, 255) + divider + reset())

    # ── Block character gradient bar ──
    csi("4;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  CPU ")
    blocks = "▏▎▍▌▋▊▉█"
    for i, block in enumerate(blocks):
        r = int(50 + i * 25)
        g = int(200 - i * 15)
        out.write(fg_rgb(r, g, 80) + block)
    out.write(reset() + "█████" + fg_rgb(255, 80, 80) + "▊" + reset())
    out.write("  72%")
    out.write(" " * 15)
    out.write(fg_rgb(100, 180, 255) + side + reset())

    # ── Truecolor gradient line ──
    csi("5;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  MEM ")
    for i in range(30):
        r = int(i * 8.5)
        g = int(255 - i * 5)
        b = 100
        out.write(bg_rgb(r, g, b) + " ")
    out.write(reset() + "  63%")
    out.write(" " * 5)
    out.write(fg_rgb(100, 180, 255) + side + reset())

    # ── Unicode symbols + styling ──
    csi("6;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  " + fg_rgb(80, 255, 120) + "✓" + reset() + " api-server    "
              + fg_rgb(80, 255, 120) + "● running" + reset() + "     "
              + fg_rgb(150, 150, 150) + "pid 4821" + reset()
              + " " * 4
              + fg_rgb(100, 180, 255) + side + reset())

    csi("7;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  " + fg_rgb(255, 80, 80) + "✗" + reset() + " worker-3      "
              + fg_rgb(255, 80, 80) + "● crashed" + reset() + "     "
              + fg_rgb(150, 150, 150) + "exit 137" + reset()
              + " " * 3
              + fg_rgb(100, 180, 255) + side + reset())

    csi("8;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  " + fg_rgb(255, 200, 60) + "⟳" + reset() + " scheduler     "
              + fg_rgb(255, 200, 60) + "● starting" + reset() + "    "
              + fg_rgb(150, 150, 150) + "───────" + reset()
              + " " * 4
              + fg_rgb(100, 180, 255) + side + reset())

    # ── Sparkline with braille ──
    csi("9;1H")
    out.write(fg_rgb(100, 180, 255) + divider + reset())

    csi("10;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    sparkline = "  ⣀⣤⣶⣿⣿⣷⣶⣤⣀⣀⣤⣶⣿⣿⣷⣶⣤⣄⣀⣠⣴⣶⣿⣿⣶⣦⣄  "
    out.write(fg_rgb(120, 200, 255) + sparkline + reset())
    out.write(" " * (48 - len(sparkline)))
    out.write(fg_rgb(100, 180, 255) + side + reset())

    # ── Half-block art ──
    csi("11;1H")
    out.write(fg_rgb(100, 180, 255) + side + reset())
    out.write("  ")
    # Small bar chart with half blocks
    bars = [3, 5, 8, 6, 9, 7, 4, 6, 8, 5]
    for val in bars:
        full = val // 2
        half = val % 2
        out.write(fg_rgb(100, 200, 150) + "█" * full)
        if half:
            out.write("▄")
        out.write(reset() + " ")
    out.write(" " * 12)
    out.write(fg_rgb(100, 180, 255) + side + reset())

    # ── Bottom border ──
    csi("12;1H")
    out.write(fg_rgb(100, 180, 255) + bottom + reset())

    # ── Status bar with reverse video ──
    csi("14;1H")
    out.write("\x1b[7m" + " Ready " + reset() + "  "
              + fg_rgb(150, 150, 150) + "Press " + reset()
              + "\x1b[1m" + "q" + reset()
              + fg_rgb(150, 150, 150) + " to quit" + reset())

    out.flush()

    # Wait for 'q'
    import tty, termios, os
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1)
            if ch == b'q':
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    # Show cursor, clear
    csi("?25h")
    csi("2J")
    csi("H")

main()
