import curses

from widgets import *
from ctrl_widgets import *


class VideoController(Widget):
    """Aggregates multiple CtrlWigets, manages and draws them."""
    def __init__(self, device, ctrls):
        self.ctrls = ctrls
        self.device = device
        self.visible_ctrls = slice(0, len(ctrls))
        self.selected_ctrl = -1
        for i, c in enumerate(self.ctrls):
            if not isinstance(c, CtrlClassCtrl):
                self.selected_ctrl = i
                break

    def draw(self, window, w, h, x, y):
        """Draws each widget on every other line."""

        assert 0 <= self.selected_ctrl < len(self.ctrls)
        self.visible_ctrls = slice(self.visible_ctrls.start,
                                   self.visible_ctrls.start + h // 2)

        for i, c in enumerate(self.ctrls[self.visible_ctrls],
                              self.visible_ctrls.start):
            f = self.get_format(c)

            if self.selected_ctrl == i:
                f |= curses.color_pair(3) | curses.A_BOLD

            c.draw(window, w, 1, x, y, f)

            y += 1
            if y < h:
                window.addstr(y, x, "\n")
                y += 1

    def next(self):
        """Selects next CtrlWidget"""

        self.selected_ctrl = sc = (self.selected_ctrl + 1) % len(self.ctrls)
        vcs = self.visible_ctrls

        if sc < vcs.start:
            self.visible_ctrls = slice(0, vcs.stop - vcs.start)
        elif sc >= vcs.stop:
            self.visible_ctrls = slice(vcs.start + 1, vcs.stop + 1)

        if isinstance(self.ctrls[self.selected_ctrl], CtrlClassCtrl):
            self.next()

    def prev(self):
        """Selects previous CtrlWidget"""

        self.selected_ctrl = sc = (self.selected_ctrl - 1) % len(self.ctrls)
        vcs = self.visible_ctrls

        if sc > vcs.stop:
            self.visible_ctrls = slice(sc - (vcs.stop - vcs.start) + 1, sc + 1)
        elif sc < vcs.start:
            self.visible_ctrls = slice(vcs.start - 1, vcs.stop - 1)

        if isinstance(self.ctrls[self.selected_ctrl], CtrlClassCtrl):
            self.prev()

    def on_keypress(self, key):
        """
        First lets selected widget resolve the keypress.
        If it isn't marked as resolved preforms default
        on_kepress action.
        """

        should_continue = self.ctrls[self.selected_ctrl].on_keypress(key)

        if should_continue:
            return super().on_keypress(key)

    def get_format(self, ctrl):
        """Returns format specific to the CtrlWidget class."""

        return {
            CtrlClassCtrl: curses.color_pair(1) | curses.A_UNDERLINE,
        }.get(type(ctrl), curses.A_NORMAL)
