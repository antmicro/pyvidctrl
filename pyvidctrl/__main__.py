#!/usr/bin/env python3

from v4l2 import *
from fcntl import ioctl

from itertools import chain
import signal
import sys
import json
import argparse
import errno

from .widgets import *
from .ctrl_widgets import *
from .video_controller import VideoController

import curses
from curses import (
    KEY_UP,
    KEY_DOWN,
    KEY_LEFT,
    KEY_RIGHT,
    KEY_SLEFT,
    KEY_SRIGHT,
    KEY_HOME,
    KEY_END,
)

KEY_TAB = "\t"
KEY_STAB = 353


def is_valid_device(device):
    ctrl = v4l2_queryctrl()
    ctrl.id = V4L2_CTRL_FLAG_NEXT_CTRL
    try:
        ioctl(device, VIDIOC_QUERYCTRL, ctrl)
    except OSError as e:
        return e.errno != errno.ENODEV

    return True


def query_v4l2_ctrls(dev):
    ctrl_id = V4L2_CTRL_FLAG_NEXT_CTRL
    current_class = "User Controls"
    controls = {current_class: []}

    while True:
        ctrl = v4l2_query_ext_ctrl()
        ctrl.id = ctrl_id
        try:
            ioctl(dev, VIDIOC_QUERY_EXT_CTRL, ctrl)
        except OSError:
            break

        if ctrl.type == V4L2_CTRL_TYPE_CTRL_CLASS:
            current_class = ctrl.name.decode("ascii")
            controls[current_class] = []

        controls[current_class].append(ctrl)

        ctrl_id = ctrl.id | V4L2_CTRL_FLAG_NEXT_CTRL

    return controls


def query_tegra_ctrls(dev):
    """This function supports deprecated TEGRA_CAMERA_CID_* API"""
    ctrls = []

    ctrlid = TEGRA_CAMERA_CID_BASE

    ctrl = v4l2_queryctrl()
    ctrl.id = ctrlid

    while ctrl.id < TEGRA_CAMERA_CID_LASTP1:
        try:
            ioctl(dev, VIDIOC_QUERYCTRL, ctrl)
        except IOError as e:
            if e.errno != errno.EINVAL:
                break
            ctrl = v4l2_queryctrl()
            ctrlid += 1
            ctrl.id = ctrlid
            continue

        if not ctrl.flags & V4L2_CTRL_FLAG_DISABLED:
            ctrls.append(ctrl)

        ctrl = v4l2_queryctrl()
        ctrlid += 1
        ctrl.id = ctrlid

    return {"Tegra Controls": ctrls}


def query_ctrls(dev):
    ctrls_v4l2 = query_v4l2_ctrls(dev)
    ctrls_tegra = query_tegra_ctrls(dev)

    return {**ctrls_v4l2, **ctrls_tegra}


def query_driver(dev):
    try:
        cp = v4l2.v4l2_capability()
        fcntl.ioctl(dev, v4l2.VIDIOC_QUERYCAP, cp)
        return cp.driver
    except Exception:
        return "unknown"


class App(Widget):
    def __init__(self, device):
        self.running = True
        self.win = curses.initscr()

        curses.start_color()
        curses.noecho()
        curses.curs_set(False)
        self.win.keypad(True)
        curses.halfdelay(10)

        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, 236)
        curses.init_pair(8, curses.COLOR_YELLOW, 236)

        self.in_help = False

        self.device = device
        self.ctrls = query_ctrls(device)

        if len(sum(self.ctrls.values(), start=[])) == 0:
            return

        tab_titles = []
        video_controllers = []
        for name, ctrls in self.ctrls.items():
            ctrl_widgets = []
            for ctrl in ctrls:
                ctrl_widgets.append(CtrlWidget.create(device, ctrl))
            if 0 < len(ctrl_widgets):
                video_controllers.append(VideoController(device, ctrl_widgets))
                tab_titles.append(name)

        self.video_controller_tabs = TabbedView(video_controllers, tab_titles)

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
            Label(f"{key:^3} - {' / '.join(help_texts)}").draw(
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

        if len(sum(self.ctrls.values(), start=[])) == 0:
            Label("There are no controls available for camera").draw(
                self.win, w, 1, 2, 2, curses.color_pair(2))
            return

        self.video_controller_tabs.draw(self.win, w - 6, h - 2, 3, 2)

    def on_keypress(self, key):
        should_continue = True
        if hasattr(self, "video_controller_tabs"):
            should_continue = self.video_controller_tabs.on_keypress(key)

        if should_continue:
            return super().on_keypress(key)

    def store_ctrls(self):
        driver = query_driver(self.device)
        fname = ".pyvidctrl-" + driver.decode("ascii")

        if not hasattr(self, "video_controller_tabs"):
            print(f"WARNING: Device {driver.decode('ascii')} has no controls")
            with open(fname, "w") as fd:
                json.dump([], fd, indent=4)
            return 0

        flattened_cw = chain.from_iterable(
            vc.ctrls for vc in self.video_controller_tabs.widgets)

        config = [{
            "id": cw.ctrl.id,
            "name": cw.name,
            "type": cw.ctrl.type,
            "value": cw.value,
        } for cw in flattened_cw]

        with open(fname, "w") as fd:
            json.dump(config, fd, indent=4)

        return 0

    def restore_ctrls(self):
        driver = query_driver(self.device)
        fname = ".pyvidctrl-" + driver.decode("ascii")

        try:
            with open(fname, "r") as fd:
                config = json.load(fd)
        except FileNotFoundError:
            print("No", fname, "file in current directory!")
            return 1
        except Exception as e:
            print("Unable to read the config file!")
            print(e)
            return 1

        if not hasattr(self, "video_controller_tabs"):
            print(f"WARNING: Device {driver.decode('ascii')} has no controls.")
            return 0

        flattened_cw = chain.from_iterable(
            vc.ctrls for vc in self.video_controller_tabs.widgets)

        id_cw_mapping = {cw.ctrl.id: cw for cw in flattened_cw}

        for c in config:
            cw = id_cw_mapping.get(c["id"], None)
            if cw is not None:
                cw.value = c["value"]
            else:
                print(
                    "Couldn't restore value of",
                    c["name"],
                    f"control (id: {c['id']})",
                )

        return 0

    def end(self):
        self.running = False
        curses.nocbreak()
        self.win.keypad(False)
        curses.echo()
        curses.endwin()


KeyBind(App, "q", App.end, "quit app")
KeyBind(App, "?", App.help, "toggle help")
KeyBind(App, "s", CtrlWidget.toggle_statusline, "toggle statusline")

KeyBind(TabbedView, KEY_STAB, TabbedView.prev, "select previous tab", "⇧ ⇆")
KeyBind(TabbedView, KEY_TAB, TabbedView.next, "select next tab", "⇆")

KeyBind(
    VideoController,
    "d",
    VideoController.set_default_selected,
    "reset to default",
)
KeyBind(
    VideoController,
    "D",
    VideoController.set_default_all,
    "reset all to default",
)
KeyBind(VideoController, "k", VideoController.prev, "select previous control")
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

KeyBind(IntCtrl, "u", lambda s: s.change_step(-1), "decrease value by step")
KeyBind(IntCtrl, ",", lambda s: s.change_step(-1), "decrease value by step")
KeyBind(IntCtrl, "p", lambda s: s.change_step(+1), "increase value by step")
KeyBind(IntCtrl, ".", lambda s: s.change_step(+1), "increase value by step")

KeyBind(
    IntCtrl,
    "U",
    lambda s: s.change_step(-10),
    "decrease value by 10 steps",
)
KeyBind(
    IntCtrl,
    "<",
    lambda s: s.change_step(-10),
    "decrease value by 10 steps",
)
KeyBind(
    IntCtrl,
    "P",
    lambda s: s.change_step(+10),
    "increase value by 10 steps",
)
KeyBind(
    IntCtrl,
    ">",
    lambda s: s.change_step(+10),
    "increase value by 10 steps",
)

KeyBind(IntCtrl, "h", lambda s: s.change_percent(-1), "decrease value by 1%")
KeyBind(
    IntCtrl,
    KEY_LEFT,
    lambda s: s.change_percent(-1),
    "decrease value by 1%",
    "←",
)
KeyBind(IntCtrl, "l", lambda s: s.change_percent(+1), "increase value by 1%")
KeyBind(
    IntCtrl,
    KEY_RIGHT,
    lambda s: s.change_percent(+1),
    "increase value by 1%",
    "→",
)

KeyBind(IntCtrl, "H", lambda s: s.change_percent(-10), "decrease value by 10%")
KeyBind(
    IntCtrl,
    KEY_SLEFT,
    lambda s: s.change_percent(-10),
    "decrease value by 10%",
    "⇧ ←",
)
KeyBind(IntCtrl, "L", lambda s: s.change_percent(+10), "increase value by 10%")
KeyBind(
    IntCtrl,
    KEY_SRIGHT,
    lambda s: s.change_percent(+10),
    "increase value by 10%",
    "⇧ →",
)

KeyBind(
    IntCtrl,
    "^",
    lambda s: s.set_value(float("-inf")),
    "set value to minimum",
)
KeyBind(
    IntCtrl,
    KEY_HOME,
    lambda s: s.set_value(float("-inf")),
    "set value to minimum",
    "⇤",
)
KeyBind(
    IntCtrl,
    "$",
    lambda s: s.set_value(float("inf")),
    "set value to maximum",
)
KeyBind(
    IntCtrl,
    KEY_END,
    lambda s: s.set_value(float("inf")),
    "set value to maximum",
    "⇥",
)

KeyBind(Int64Ctrl, "u", lambda s: s.change_step(-1), "decrease value by step")
KeyBind(Int64Ctrl, ",", lambda s: s.change_step(-1), "decrease value by step")
KeyBind(Int64Ctrl, "p", lambda s: s.change_step(+1), "increase value by step")
KeyBind(Int64Ctrl, ".", lambda s: s.change_step(+1), "increase value by step")

KeyBind(
    Int64Ctrl,
    "U",
    lambda s: s.change_step(-10),
    "decrease value by 10 steps",
)
KeyBind(
    Int64Ctrl,
    "<",
    lambda s: s.change_step(-10),
    "decrease value by 10 steps",
)
KeyBind(
    Int64Ctrl,
    "P",
    lambda s: s.change_step(+10),
    "increase value by 10 steps",
)
KeyBind(
    Int64Ctrl,
    ">",
    lambda s: s.change_step(+10),
    "increase value by 10 steps",
)

KeyBind(Int64Ctrl, "h", lambda s: s.change_percent(-1), "decrease value by 1%")
KeyBind(
    Int64Ctrl,
    KEY_LEFT,
    lambda s: s.change_percent(-1),
    "decrease value by 1%",
    "←",
)
KeyBind(Int64Ctrl, "l", lambda s: s.change_percent(+1), "increase value by 1%")
KeyBind(
    Int64Ctrl,
    KEY_RIGHT,
    lambda s: s.change_percent(+1),
    "increase value by 1%",
    "→",
)

KeyBind(
    Int64Ctrl,
    "H",
    lambda s: s.change_percent(-10),
    "decrease value by 10%",
)
KeyBind(
    Int64Ctrl,
    KEY_SLEFT,
    lambda s: s.change_percent(-10),
    "decrease value by 10%",
    "⇧ ←",
)
KeyBind(
    Int64Ctrl,
    "L",
    lambda s: s.change_percent(+10),
    "increase value by 10%",
)
KeyBind(
    Int64Ctrl,
    KEY_SRIGHT,
    lambda s: s.change_percent(+10),
    "increase value by 10%",
    "⇧ →",
)

KeyBind(
    Int64Ctrl,
    "^",
    lambda s: s.set_value(float("-inf")),
    "set value to minimum",
)
KeyBind(
    Int64Ctrl,
    KEY_HOME,
    lambda s: s.set_value(float("-inf")),
    "set value to minimum",
    "⇤",
)
KeyBind(
    Int64Ctrl,
    "$",
    lambda s: s.set_value(float("inf")),
    "set value to maximum",
)
KeyBind(
    Int64Ctrl,
    KEY_END,
    lambda s: s.set_value(float("inf")),
    "set value to maximum",
    "⇥",
)

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

KeyBind(BitmaskCtrl, "h", BitmaskCtrl.prev, "previous nibble")
KeyBind(BitmaskCtrl, KEY_LEFT, BitmaskCtrl.prev, "previous nibble", "←")
KeyBind(BitmaskCtrl, "l", BitmaskCtrl.next, "next nibble")
KeyBind(BitmaskCtrl, KEY_RIGHT, BitmaskCtrl.next, "next nibble", "→")
KeyBind(BitmaskCtrl, "k", BitmaskCtrl.inc, "increment nibble")
KeyBind(BitmaskCtrl, KEY_UP, BitmaskCtrl.inc, "increment nibble", "↑")
KeyBind(BitmaskCtrl, "j", BitmaskCtrl.dec, "decrement nibble")
KeyBind(BitmaskCtrl, KEY_DOWN, BitmaskCtrl.dec, "decrement nibble", "↓")

KeyBind(IntMenuCtrl, "h", IntMenuCtrl.prev, "previous choice")
KeyBind(IntMenuCtrl, KEY_LEFT, IntMenuCtrl.prev, "previous choice", "←")
KeyBind(IntMenuCtrl, "l", IntMenuCtrl.next, "next choice")
KeyBind(IntMenuCtrl, KEY_RIGHT, IntMenuCtrl.next, "next choice", "→")


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

    try:
        device = open(args.device, "r")
    except FileNotFoundError:
        print(f"There is no '{args.device}' device")
        return 1

    app = App(device)

    if args.store and args.restore:
        app.end()
        print("Cannot store and restore values at the same time!")
        return 1
    elif args.store:
        app.end()
        print("Storing...")
        return app.store_ctrls()
    elif args.restore:
        app.end()
        print("Restoring...")
        return app.restore_ctrls()

    signal.signal(signal.SIGINT, lambda s, f: app.end())

    while app.running:
        app.draw()

        c = app.getch()
        if 0 < c:
            app.on_keypress(chr(c))

        if not is_valid_device(device):
            app.end()
            print("Disconnected")
            break


if __name__ == "__main__":
    sys.exit(main())
