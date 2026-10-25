#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Terminal key tester for the QMK MK Typist, drawn from its own layout.

Reads every /dev/input/event* whose name contains the keyboard_name from
keyboard.json ("MK Typist"), so desktop key
bindings and window focus do not hide anything (PrtSc and media keys included).
The board comes from keyboard.json and the default keymap, so every one of the
108 positions is shown, including the 4 media keys. A key turns green once it
has been pressed and is highlighted while held. Needs read access to the event
nodes (run with sudo). Ctrl-C quits (typed keys also reach the terminal, so
no letter key is used to quit).

Usage: keytest.py <qmk_firmware/keyboards/mk/typist> [log.txt]
       (presses are appended to the log, if given)
"""
import curses
import glob
import json
import os
import re
import select
import struct
import sys
import textwrap

EVENT = struct.Struct("llHHi")  # struct input_event on 64-bit Linux
EV_KEY = 1

# QMK keycode suffix -> Linux evdev name, for codes in the default keymap
QMK_TO_EVDEV = {
    "ESC": "ESC", "GRV": "GRAVE", "MINS": "MINUS", "EQL": "EQUAL", "BSPC": "BACKSPACE",
    "TAB": "TAB", "LBRC": "LEFTBRACE", "RBRC": "RIGHTBRACE", "BSLS": "BACKSLASH",
    "CAPS": "CAPSLOCK", "SCLN": "SEMICOLON", "QUOT": "APOSTROPHE", "ENT": "ENTER",
    "LSFT": "LEFTSHIFT", "COMM": "COMMA", "DOT": "DOT", "SLSH": "SLASH", "RSFT": "RIGHTSHIFT",
    "LCTL": "LEFTCTRL", "LGUI": "LEFTMETA", "LALT": "LEFTALT", "SPC": "SPACE",
    "RALT": "RIGHTALT", "RGUI": "RIGHTMETA", "APP": "COMPOSE", "RCTL": "RIGHTCTRL",
    "PSCR": "SYSRQ", "SCRL": "SCROLLLOCK", "PAUS": "PAUSE", "INS": "INSERT", "HOME": "HOME",
    "PGUP": "PAGEUP", "DEL": "DELETE", "END": "END", "PGDN": "PAGEDOWN", "UP": "UP",
    "DOWN": "DOWN", "LEFT": "LEFT", "RGHT": "RIGHT", "NUM": "NUMLOCK", "PSLS": "KPSLASH",
    "PAST": "KPASTERISK", "PMNS": "KPMINUS", "PPLS": "KPPLUS", "PENT": "KPENTER",
    "PDOT": "KPDOT", "CALC": "CALC", "MUTE": "MUTE", "VOLD": "VOLUMEDOWN", "VOLU": "VOLUMEUP",
}


def evdev_codes():
    names = {}
    text = open("/usr/include/linux/input-event-codes.h").read()
    for name, value in re.findall(r"#define\s+(KEY_\w+)\s+(0x[0-9a-fA-F]+|\d+)", text):
        names.setdefault(name, int(value, 0))
    return names


def to_evdev(keycode):
    """Linux key name for a basic keycode, or None for keys that send nothing (e.g. MO(1))."""
    if not keycode.startswith("KC_"):
        return None
    k = keycode.removeprefix("KC_")
    if re.fullmatch(r"[A-Z0-9]|F\d+", k):
        return k
    if re.fullmatch(r"P\d", k):
        return "KP" + k[1]
    return QMK_TO_EVDEV[k]


def load_board(keyboard):
    """Return [(label, x, y, w, matrix, evdev_code)] for layer 0 of the default keymap."""
    layout = json.load(open(f"{keyboard}/keyboard.json"))["layouts"]["LAYOUT"]["layout"]
    keymap = open(f"{keyboard}/keymaps/default/keymap.c").read()
    body = re.search(r"\[0\]\s*=\s*LAYOUT\((.*?)\n\s*\)", keymap, re.S).group(1)
    keycodes = re.findall(r"[A-Z_][A-Z0-9_]*(?:\(\d+\))?", body)
    assert len(keycodes) == len(layout), (len(keycodes), len(layout))
    codes = evdev_codes()
    board = []
    for k, kc in zip(layout, keycodes):
        name = to_evdev(kc)
        board.append((k.get("label", kc), k["x"], k["y"], k.get("w", 1), k["matrix"], codes["KEY_" + name] if name else None))
    return board


def open_devices(name):
    fds = {}
    for node in sorted(glob.glob("/sys/class/input/event*")):
        if name in open(f"{node}/device/name").read():
            fds[os.open(f"/dev/input/{os.path.basename(node)}", os.O_RDONLY)] = node
    if not fds:
        sys.exit(f"no input devices named {name!r} found")
    return fds


def run(screen, board, fds, log):
    curses.curs_set(0)
    screen.nodelay(True)
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_GREEN)   # tested
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_YELLOW)  # held
    names = {v: k for k, v in evdev_codes().items()}
    by_code = {}
    for i, key in enumerate(board):
        if key[5] is not None:
            by_code.setdefault(key[5], []).append(i)
    testable = [i for i, key in enumerate(board) if key[5] is not None]
    tested, held, recent, unmapped = set(), set(), [], []
    width = max(x + w for _, x, _, w, _, _ in board)

    while True:
        rows, cols = screen.getmaxyx()
        unit = max(3, min(6, int((cols - 2) // width)))
        screen.erase()
        for i, (label, x, y, w, matrix, _) in enumerate(board):
            cell_w = max(2, int(w * unit) - 1)
            text = label[:cell_w].center(cell_w)
            attr = curses.color_pair(2) if i in held else curses.color_pair(1) if i in tested else curses.A_DIM
            try:
                screen.addstr(1 + int(y) * 2, 1 + int(x * unit), text, attr | curses.A_BOLD)
            except curses.error:
                pass
        status = 13
        lines = [f"tested {len(tested)}/{len(testable)}   Ctrl-C quits   last: " + "  ".join(recent[-6:])]
        if unmapped:
            lines.append("not on the layout: " + ", ".join(unmapped[-8:]))
        lines += textwrap.wrap("untested: " + ", ".join(
            f"{board[i][0]}{board[i][4]}" for i in testable if i not in tested), cols - 2)
        for n, line in enumerate(lines):
            try:
                screen.addstr(status + n, 1, line[:cols - 2])
            except curses.error:
                pass
        screen.refresh()

        ready = select.select(list(fds) + [sys.stdin], [], [])[0]
        if sys.stdin in ready:
            while screen.getch() != -1:  # discard the keys the terminal also received
                pass
        for fd in ready:
            if fd is sys.stdin:
                continue
            data = os.read(fd, EVENT.size * 64)
            for off in range(0, len(data), EVENT.size):
                _, _, etype, code, value = EVENT.unpack_from(data, off)
                if etype != EV_KEY or value == 2:
                    continue
                name = names.get(code, str(code))
                idx = by_code.get(code)
                if value == 1:
                    recent.append(name.removeprefix("KEY_"))
                    if idx:
                        tested.update(idx)
                        held.update(idx)
                    elif name not in unmapped:
                        unmapped.append(name)
                    if log:
                        where = ", ".join(f"{board[i][0]} {board[i][4]}" for i in idx) if idx else "not on layout"
                        log.write(f"{name} ({code}) -> {where}\n")
                        log.flush()
                elif idx:
                    held.difference_update(idx)


def main(keyboard=None, log_path=None):
    if not keyboard:
        sys.exit(__doc__)
    board = load_board(keyboard)
    fds = open_devices(json.load(open(f"{keyboard}/keyboard.json"))["keyboard_name"])
    log = open(log_path, "a") if log_path else None
    try:
        curses.wrapper(run, board, fds, log)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(*sys.argv[1:])
