#!/usr/bin/env python3

import v4l2
import fcntl
import collections
import curses
import curses.textpad
import signal
import sys
import json
import argparse
import errno

SUPPORTED_CTRL_TYPES = (
    v4l2.V4L2_CTRL_TYPE_INTEGER,
    v4l2.V4L2_CTRL_TYPE_INTEGER64,
    v4l2.V4L2_CTRL_TYPE_BOOLEAN,
)


def query_v4l2_ctrls(dev):
    ctrls = []

    ctrl = v4l2.v4l2_queryctrl()
    ctrl.id = v4l2.V4L2_CID_BASE

    while True:
        try:
            fcntl.ioctl(dev, v4l2.VIDIOC_QUERYCTRL, ctrl)
        except Exception:
            return ctrls

        if not ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED and \
                ctrl.type in \
                SUPPORTED_CTRL_TYPES:
            ctrls.append(ctrl)

            ctrl = v4l2.v4l2_queryctrl()
            ctrl.id = ctrls[-1].id

        ctrl.id |= v4l2.V4L2_CTRL_FLAG_NEXT_CTRL

    return ctrls


def query_tegra_ctrls(dev):
    # This function supports deprecated TEGRA_CAMERA_CID_* API
    ctrls = []

    ctrlid = v4l2.TEGRA_CAMERA_CID_BASE

    ctrl = v4l2.v4l2_queryctrl()
    ctrl.id = ctrlid

    while ctrl.id < v4l2.TEGRA_CAMERA_CID_LASTP1:
        try:
            fcntl.ioctl(dev, v4l2.VIDIOC_QUERYCTRL, ctrl)
        except IOError as e:
            if e.errno != errno.EINVAL:
                return ctrls
            ctrl = v4l2.v4l2_queryctrl()
            ctrlid += 1
            ctrl.id = ctrlid
            continue

        if not ctrl.flags & v4l2.V4L2_CTRL_FLAG_DISABLED and \
                ctrl.type in \
                SUPPORTED_CTRL_TYPES:
            ctrls.append(ctrl)

        ctrl = v4l2.v4l2_queryctrl()
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


def get_ctrl(dev, ctrl):
    gctrl = v4l2.v4l2_control()

    gctrl.id = ctrl.id

    try:
        fcntl.ioctl(dev, v4l2.VIDIOC_G_CTRL, gctrl)
        return gctrl.value
    except Exception:
        return None


def set_ctrl(dev, ctrl, value):
    sctrl = v4l2.v4l2_control()

    sctrl.id = ctrl.id
    sctrl.value = value
    try:
        fcntl.ioctl(dev, v4l2.VIDIOC_S_CTRL, sctrl)
    except Exception:
        pass


class KeyHandler:
    def __init__(self, help_msg, callback):
        self.help_msg = help_msg
        self.callback = callback


class VidController:
    def __init__(self, dev):
        self.win = curses.initscr()
        curses.start_color()

        curses.init_pair(1, curses.COLOR_BLUE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_WHITE, curses.COLOR_CYAN)

        curses.init_pair(3, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)

        curses.noecho()
        curses.cbreak()
        curses.curs_set(False)
        self.win.keypad(True)
        self.h, self.w = self.win.getmaxyx()

        self.check_term_size()

        self.dev = dev
        self.ctrls = query_ctrls(dev)

        self.selected = 0
        self.selected_max = 0
        self.selected_ctrl = None

        self.displayed_from = 0
        self.last_visible = 0

        self.in_help = False

        self.key_handlers = collections.OrderedDict()

        self.parameterdrawers = {
            v4l2.V4L2_CTRL_TYPE_INTEGER: self.drawIntegerParameter,
            v4l2.V4L2_CTRL_TYPE_INTEGER64: self.drawIntegerParameter,
            v4l2.V4L2_CTRL_TYPE_BOOLEAN: self.drawBooleanParameter,
        }

        self.parametermodificators = {
            v4l2.V4L2_CTRL_TYPE_INTEGER: self.incInteger,
            v4l2.V4L2_CTRL_TYPE_INTEGER64: self.incInteger,
            v4l2.V4L2_CTRL_TYPE_BOOLEAN: self.incBoolean,
        }

    def check_term_size(self):
        # assume minimal terminal width
        if self.w < 50:
            self.end()
            print("Terminal too narrow")
            sys.exit(1)

    def getch(self):
        return self.win.getch()

    def toggle_help(self):
        self.in_help = not self.in_help

    def draw_help(self):
        pos = 2
        try:
            for k in self.key_handlers.keys():
                self.win.addstr(pos, 3, k, curses.color_pair(2))
                self.win.addstr(pos, 5,
                                self.key_handlers[k].help_msg,
                                curses.color_pair(3))
                pos += 1
        except Exception:
            self.end()
            print("Terminal too small to display help")
            sys.exit(1)

    def drawBooleanParameter(self, c, i, j, maxl, color):
        pname = c.name.decode('ascii')
        printvalue = "T"
        try:
            value = get_ctrl(self.dev, c)
            if value == 0:
                printvalue = "F"
        except Exception:
            return (0, i, j)

        pos = (j + 1) * 2
        self.selected_max = i
        i += 1
        j += 1

        if pos >= self.h:
            return (1, i, j)

        self.last_visible = self.selected_max

        nlen = (maxl - len(pname) - len(printvalue) - 3)
        name = pname + " " * nlen + printvalue

        self.win.addstr(pos,
                        3,
                        name[:maxl],
                        curses.color_pair(color))

        return (0, i, j)

    def drawIntegerParameter(self, c, i, j, maxl, color):
        pname = c.name.decode('ascii')
        try:
            value = get_ctrl(self.dev, c)
            total_value = c.maximum - c.minimum
            barWidth = (self.w - 2 - (3 + maxl))

            percent = (value - c.minimum) * 100 / total_value

            barFilledWidth = int((percent / 100.0) * barWidth)
            barFilled = " " * barFilledWidth
            barPadding = " " * (barWidth - barFilledWidth)
        except Exception:
            return (0, i, j)

        pos = (j + 1) * 2
        self.selected_max = i
        i += 1
        j += 1

        if pos >= self.h:
            return (1, i, j)

        self.last_visible = self.selected_max

        nlen = (maxl - len(pname) - len(str(value)) - 3)
        name = pname + " " * nlen + str(value)

        self.win.addstr(pos,
                        3,
                        name[:maxl],
                        curses.color_pair(color))

        self.win.addstr(pos,
                        3 + maxl,
                        barFilled,
                        curses.color_pair(1))

        self.win.addstr(pos,
                        3 + maxl + barFilledWidth,
                        barPadding,
                        curses.color_pair(2))
        return (0, i, j)

    def draw(self):
        self.h, self.w = self.win.getmaxyx()

        self.check_term_size()

        self.win.clear()
        self.win.addstr(0, 0, "pyVidController - press ? for help")

        if self.in_help:
            self.draw_help()
            return

        maxl = 20

        if len(self.ctrls) == 0:
            self.win.addstr(2, 0, "There are no controls available for camera")

        for c in self.ctrls:
            pname = c.name.decode('ascii')
            maxl = max(maxl, len(pname) + len(str(c.maximum)) + 3)

        if self.w < maxl + 14:
            maxl = self.w - 14

        i = 0
        j = 0

        for c in self.ctrls:
            if self.displayed_from > i:
                i += 1
                continue

            if self.selected == i:
                self.selected_ctrl = c
                color = 3
            else:
                color = 4

            ret = 0
            ret, i, j = self.parameterdrawers[c.type](c, i, j, maxl, color)
            if ret:
                return False

    def __selected_limit__(self):
        if self.selected < 0:
            self.selected = self.selected_max
            self.displayed_from = self.selected_max - self.last_visible
        elif self.selected > self.selected_max:
            self.selected = 0
            self.displayed_from = 0

    def next(self):
        if self.in_help:
            return

        self.selected += 1
        self.__selected_limit__()

        if self.last_visible < self.selected:
            self.displayed_from += 1

    def prev(self):
        if self.in_help:
            return

        self.selected -= 1
        self.__selected_limit__()

        if self.selected < self.displayed_from:
            self.displayed_from -= 1

    def incInteger(self, delta):
        if self.in_help:
            return

        value = get_ctrl(self.dev, self.selected_ctrl)

        total_span = (self.selected_ctrl.maximum - self.selected_ctrl.minimum)

        one_percent = total_span / 100.0

        inc = int(delta * one_percent)

        if inc == 0:
            if delta > 0:
                inc = 1
            else:
                inc = -1
            inc *= self.selected_ctrl.step

        value += inc

        while (value - self.selected_ctrl.minimum) % self.selected_ctrl.step:
            value += 1

        if value < self.selected_ctrl.minimum:
            value = self.selected_ctrl.minimum
        elif value > self.selected_ctrl.maximum:
            value = self.selected_ctrl.maximum

        set_ctrl(self.dev, self.selected_ctrl, value)

    def incBoolean(self, delta):
        if self.in_help:
            return
        if delta > 0:
            set_ctrl(self.dev, self.selected_ctrl, 1)
        else:
            set_ctrl(self.dev, self.selected_ctrl, 0)

    def inc(self, delta):
        self.parametermodificators[self.selected_ctrl.type](delta)

    def end(self):
        curses.nocbreak()
        self.win.keypad(False)
        curses.echo()
        curses.endwin()

    def add_key(self, key, msg, action):
        self.key_handlers[key] = KeyHandler(msg, action)


def main():
    parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("-s", "--store",
                        action="store_true",
                        help="Store current parameter values")
    parser.add_argument("-r", "--restore",
                        action="store_true",
                        help="Restore current parameter values")
    parser.add_argument("-d", "--device",
                        help="Path to the camera device node or its ID",
                        default="/dev/video0")

    args = parser.parse_args()

    if args.device.isdigit():
        args.device = "/dev/video" + args.device

    def store_ctrls(dev):
        ctrls = query_ctrls(dev)
        driver = query_driver(dev)

        config = {}

        for c in ctrls:
            pname = c.name.decode('ascii')

            try:
                config[pname] = int(get_ctrl(dev, c))
            except Exception:
                continue

        fname = ".pyvidctrl-" + driver

        with open(fname, "w+") as f:
            json.dump(config, f, indent=4)

    def restore_ctrls(dev):
        ctrls = query_ctrls(dev)
        driver = query_driver(dev)

        config = {}

        fname = ".pyvidctrl-" + driver

        try:
            with open(fname, "r") as f:
                config = json.load(f)
        except Exception:
            print("Unable to read the config file!")
            return

        for c in ctrls:
            pname = c.name.decode('ascii')

            if pname not in config.keys():
                continue

            try:
                new_value = int(config[pname])
                set_ctrl(dev, c, new_value)
            except Exception:
                print("Unable to restore", pname)

    dev = open(args.device, 'r')

    if args.store and args.restore:
        print("Cannot store and restore values at the same time!")
        sys.exit(1)
    elif args.store:
        print("Storing...")
        store_ctrls(dev)
        sys.exit(0)
    elif args.restore:
        print("Restoring...")
        restore_ctrls(dev)
        sys.exit(0)
    vctrl = VidController(dev)

    def vidctrl_exit():
        vctrl.end()
        sys.exit(0)

    def sigint_handler(sig, f):
        vidctrl_exit()

    signal.signal(signal.SIGINT, sigint_handler)

    vctrl.add_key('q', "Exit the program", lambda: vidctrl_exit())
    vctrl.add_key('?', "Enter/Exit help", lambda: vctrl.toggle_help())
    vctrl.add_key('j', "Next entry", lambda: vctrl.next())
    vctrl.add_key('k', "Previous entry", lambda: vctrl.prev())
    vctrl.add_key('u', "Decrease by 0.1%", lambda: vctrl.inc(-0.1))
    vctrl.add_key('U', "Decrease by 0.5%", lambda: vctrl.inc(-0.5))
    vctrl.add_key('h', "Decrease by 1%", lambda: vctrl.inc(-1))
    vctrl.add_key('H', "Decrease by 10%", lambda: vctrl.inc(-10))
    vctrl.add_key('p', "Increase by 0.1%", lambda: vctrl.inc(0.1))
    vctrl.add_key('P', "Increase by 0.5%", lambda: vctrl.inc(0.5))
    vctrl.add_key('l', "Increase by 1%", lambda: vctrl.inc(1))
    vctrl.add_key('L', "Increase by 10%", lambda: vctrl.inc(10))
    vctrl.add_key('s', "Save changes", lambda: store_ctrls(dev))
    vctrl.add_key('r', "Load stored", lambda: restore_ctrls(dev))

    while True:
        vctrl.draw()
        try:
            c = chr(vctrl.getch())
        except Exception:
            continue

        if c in vctrl.key_handlers.keys():
            vctrl.key_handlers[c].callback()


if __name__ == "__main__":
    main()
