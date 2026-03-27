"""Simple curses TUI for testing interact.py."""
import curses
import time

def main(stdscr):
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_CYAN, curses.COLOR_BLACK)
    stdscr.clear()
    stdscr.addstr(0, 0, "=== Test App v1.0 ===", curses.color_pair(1) | curses.A_BOLD)
    stdscr.addstr(2, 0, "Loading...", curses.color_pair(2))
    stdscr.refresh()
    time.sleep(0.5)

    stdscr.addstr(2, 0, "Ready.    ", curses.color_pair(1))
    stdscr.addstr(4, 0, "Type something> ", curses.color_pair(3))
    stdscr.refresh()
    curses.echo()
    buf = []
    while True:
        ch = stdscr.getch()
        if ch == ord('\n') or ch == ord('\r'):
            break
        buf.append(chr(ch))
    user_input = "".join(buf)

    stdscr.addstr(6, 0, f"You said: {user_input}", curses.color_pair(2) | curses.A_BOLD)
    stdscr.addstr(8, 0, "Press q to quit", curses.color_pair(3))
    stdscr.refresh()
    while stdscr.getch() != ord('q'):
        pass

curses.wrapper(main)
