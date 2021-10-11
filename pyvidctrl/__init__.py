#!/usr/bin/env python3

import v4l2
import fcntl
import curses
from curses import (
    KEY_UP,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
)
import signal
import sys
import json
import argparse
import errno

from widgets import *
from ctrl_widgets import *
from video_controller import VideoController


def query_v4l2_ctrls(dev):
    ctrls = []

    ctrl = v4l2.v4l2_queryctrl()
    ctrl.id = v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

    while True:
        try:
            fcntl.ioctl(dev, v4l2.VIDIOC_QUERYCTRL, ctrl)
        except OSError:
            return ctrls

        if not ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED:
            ctrls.append(ctrl)

            ctrl = v4l2.v4l2_queryctrl()
            ctrl.id = ctrls[-1].id

        ctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

    return ctrls


def query_tegra_ctrls(dev):
    # This function supports deprecated TEGRA_CAMERA_CID_* API
    ctrls = []

    ctrlid = TEGRA_CAMERA_CID_BASE

    ctrl = v4l2_queryctrl()
    ctrl.id = ctrlid

    while ctrl.id < TEGRA_CAMERA_CID_LASTP1:
        try:
            ioctl(dev, VIDIOC_QUERYCTRL, ctrl)
        except IOError as e:
            if e.errno != errno.EINVAL:
                return ctrls
            ctrl = v4l2_queryctrl()
            ctrlid += 1
            ctrl.id = ctrlid
            continue

        if not ctrl.flags & V4L2_CTRL_FLAG_DISABLED:
            ctrls.append(ctrl)

        ctrl = v4l2_queryctrl()
        ctrlid += 1
        ctrl.id = ctrlid

    return ctrls


def query_ctrls(dev):
    ctrls_v4l2 = query_v4l2_ctrls(dev)
    ctrls_tegra = query_tegra_ctrls(dev)

    ctrls = ctrls_v4l2 + ctrls_tegra
    return ctrls


def query_driver(dev):
    try:
        cp = v4l2.v4l2_capability()
        fcntl.ioctl(dev, v4l2.VIDIOC_QUERYCAP, cp)
        return cp.driver
    except Exception:
        return "unknown"


class App(Widget):
    def __init__(self, device):
        self.win = curses.initscr()

        curses.start_color()
        curses.noecho()
        curses.cbreak()
        curses.curs_set(False)
        self.win.keypad(True)

        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, 236)
        curses.init_pair(8, curses.COLOR_YELLOW, 236)

        self.device = device
        self.ctrls = query_ctrls(device)

        widgets = [CtrlWidget.create(device, ctrl) for ctrl in self.ctrls]
        self.video_controller = VideoController(device, widgets)

        self.in_help = False

    def getch(self):
        return self.win.getch()

    def help(self):
        self.in_help = not self.in_help

    def draw_help(self, window, w, h, x, y, color):
        keys = {}
        for kb in KeyBind.KEYBINDS:
            help_texts = keys.setdefault(kb.display, [])
            if kb.help_text not in help_texts:
                help_texts.append(kb.help_text)

        for i, (key, help_texts) in enumerate(keys.items(), y):
            Label(key + " - " + " / ".join(help_texts)).draw(
                window, w, h, x, i, color)

    def draw(self):
        h, w = self.win.getmaxyx()

        self.win.erase()

        title = Label("pyVidController - press ? for help")
        title.draw(self.win, w, 1, 0, 0,
                   curses.color_pair(2) | curses.A_REVERSE)

        if self.in_help:
            self.draw_help(self.win, w - 6, h - 2, 3, 2, curses.color_pair(0))
            return

        if len(self.ctrls) == 0:
            self.win.addstr(2, 0, "There are no controls available for camera")
        else:
            self.video_controller.draw(self.win, w - 6, h - 2, 3, 2)

    def on_keypress(self, key):
        should_continue = self.video_controller.on_keypress(key)
        if should_continue:
            return super().on_keypress(key)

    def end(self):
        curses.nocbreak()
        self.win.keypad(False)
        curses.echo()
        curses.endwin()
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "-s",
        "--store",
        action="store_true",
        help="Store current parameter values",
    )
    parser.add_argument(
        "-r",
        "--restore",
        action="store_true",
        help="Restore current parameter values",
    )
    parser.add_argument(
        "-d",
        "--device",
        help="Path to the camera device node or its ID",
        default="/dev/video0",
    )

    args = parser.parse_args()

    if args.device.isdigit():
        args.device = "/dev/video" + args.device

    def store_ctrls(dev):
        ctrls = query_ctrls(dev)
        driver = query_driver(dev)

        config = {}

        for c in ctrls:
            pname = c.name.decode("ascii")

            try:
                config[pname] = int(get_ctrl(dev, c))
            except Exception:
                continue

        fname = ".pyvidctrl-" + driver.decode("ascii")

        with open(fname, "w+") as f:
            json.dump(config, f, indent=4)

    def restore_ctrls(dev):
        ctrls = query_ctrls(dev)
        driver = query_driver(dev)

        config = {}

        fname = ".pyvidctrl-" + driver.decode("ascii")

        try:
            with open(fname, "r") as f:
                config = json.load(f)
        except Exception:
            print("Unable to read the config file!")
            return

        for c in ctrls:
            pname = c.name.decode("ascii")

            if pname not in config.keys():
                continue

            try:
                new_value = int(config[pname])
                set_ctrl(dev, c, new_value)
            except Exception:
                print("Unable to restore", pname)

    device = open(args.device, "r")

    if args.store and args.restore:
        print("Cannot store and restore values at the same time!")
        sys.exit(1)
    elif args.store:
        print("Storing...")
        store_ctrls(device)
        sys.exit(0)
    elif args.restore:
        print("Restoring...")
        restore_ctrls(device)
        sys.exit(0)

    app = App(device)

    signal.signal(signal.SIGINT, lambda s, f: app.end())

    while True:
        app.draw()
        try:
            c = chr(app.getch())
        except Exception:
            continue

        app.on_keypress(c)


if __name__ == "__main__":
    KeyBind(App, "q", App.end, "quit app")
    KeyBind(App, "?", App.help, "toggle help")
    KeyBind(VideoController, "k", VideoController.prev,
            "select previous control")
    KeyBind(
        VideoController,
        KEY_UP,
        VideoController.prev,
        "select previous control",
        "↑",
    )
    KeyBind(VideoController, "j", VideoController.next, "select next control")
    KeyBind(
        VideoController,
        KEY_DOWN,
        VideoController.next,
        "select next control",
        "↓",
    )
    KeyBind(IntCtrl, "h", lambda s: s.inc(-1), "decrease value")
    KeyBind(IntCtrl, KEY_LEFT, lambda s: s.inc(-1), "decrease value", "←")
    KeyBind(IntCtrl, "l", lambda s: s.inc(1), "increase value")
    KeyBind(IntCtrl, KEY_RIGHT, lambda s: s.inc(1), "increase value", "→")
    KeyBind(BoolCtrl, "h", BoolCtrl.false, "set value false")
    KeyBind(BoolCtrl, KEY_LEFT, BoolCtrl.false, "set value false", "←")
    KeyBind(BoolCtrl, "l", BoolCtrl.true, "set value true")
    KeyBind(BoolCtrl, KEY_RIGHT, BoolCtrl.true, "set value true", "→")
    KeyBind(BoolCtrl, "\n", BoolCtrl.neg, "negate value", "⏎")
    KeyBind(ButtonCtrl, "\n", ButtonCtrl.click, "click button", "⏎")
    KeyBind(MenuCtrl, "h", MenuCtrl.prev, "previous choice")
    KeyBind(MenuCtrl, KEY_LEFT, MenuCtrl.prev, "previous choice", "←")
    KeyBind(MenuCtrl, "l", MenuCtrl.next, "next choice")
    KeyBind(MenuCtrl, KEY_RIGHT, MenuCtrl.next, "next choice", "→")
    KeyBind(IntMenuCtrl, "h", IntMenuCtrl.prev, "previous choice")
    KeyBind(IntMenuCtrl, KEY_LEFT, IntMenuCtrl.prev, "previous choice", "←")
    KeyBind(IntMenuCtrl, "l", IntMenuCtrl.next, "next choice")
    KeyBind(IntMenuCtrl, KEY_RIGHT, IntMenuCtrl.next, "next choice", "→")

    main()
