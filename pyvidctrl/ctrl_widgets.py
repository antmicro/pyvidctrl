import curses
from fcntl import ioctl

from v4l2 import *
from widgets import *

KEY_ESCAPE = "\x1b"


class CtrlWidget(Row):
    """
    Base control widget class
    Each CtrlWidget is a label with a name of
    its control and another label with text
    'Not implemented!'. Child CtrlWidgets should
    replace that with their specific widget.
    """

    show_statusline = False

    def __init__(self, device, ctrl):
        self.device = device
        self.ctrl = ctrl

        self.name = ctrl.name.decode("ascii")
        self.label = Label(self.name)
        self.widget = Label("Not implemented!", align="center")

        self._statusline = Label("Statusline")

        super().__init__(self.label, Label(""), self.widget, columns=(4, 1, 4))

    @staticmethod
    def create(device, ctrl):
        """
        Creates and returns CtrlWidget depending
        on type of the passed ctrl
        """

        return {
            V4L2_CTRL_TYPE_INTEGER: IntCtrl,
            V4L2_CTRL_TYPE_BOOLEAN: BoolCtrl,
            V4L2_CTRL_TYPE_MENU: MenuCtrl,
            V4L2_CTRL_TYPE_BUTTON: ButtonCtrl,
            V4L2_CTRL_TYPE_INTEGER64: Int64Ctrl,
            V4L2_CTRL_TYPE_CTRL_CLASS: CtrlClassCtrl,
            V4L2_CTRL_TYPE_STRING: StringCtrl,
            V4L2_CTRL_TYPE_BITMASK: BitmaskCtrl,
            V4L2_CTRL_TYPE_INTEGER_MENU: IntMenuCtrl,
        }[ctrl.type](device, ctrl)

    @property
    def value(self):
        """Returns value depending on control type"""

        ectrl = v4l2_ext_control()
        ectrls = v4l2_ext_controls()
        ectrl.id = self.ctrl.id
        if self.ctrl.type == V4L2_CTRL_TYPE_STRING:
            ectrl.size = self.ctrl.elem_size
            ectrl.string = bytes(self.ctrl.maximum + 1)
        ectrls.controls = ctypes.pointer(ectrl)
        ectrls.count = 1

        try:
            ioctl(self.device, VIDIOC_G_EXT_CTRLS, ectrls)
        except OSError:
            return None

        if self.ctrl.type == V4L2_CTRL_TYPE_INTEGER64:
            return ectrl.value64
        elif self.ctrl.type == V4L2_CTRL_TYPE_STRING:
            return ectrl.string.decode("ascii")
        else:
            return ectrl.value

    @value.setter
    def value(self, value):
        """Sets value depending on control type"""

        ectrl = v4l2_ext_control()
        ectrls = v4l2_ext_controls()

        ectrl.id = self.ctrl.id

        if self.ctrl.type == V4L2_CTRL_TYPE_INTEGER64:
            ectrl.value64 = value
        elif self.ctrl.type == V4L2_CTRL_TYPE_STRING:
            if len(value) < self.ctrl.minimum:
                value = " " * self.ctrl.minimum
            ectrl.string = value.encode("ascii")
            ectrl.size = self.ctrl.elem_size
        else:
            ectrl.value = value

        ectrls.controls = ctypes.pointer(ectrl)
        ectrls.count = 1

        try:
            ioctl(self.device, VIDIOC_S_EXT_CTRLS, ectrls)
        except OSError:
            return

    def update(self):
        """Updates child widgets with its value"""

        v = self.value
        for w in self.widgets:
            w.value = v

    @property
    def statusline(self):
        return self._statusline

    def toggle_statusline(self):
        CtrlWidget.show_statusline = not CtrlWidget.show_statusline

    def draw_statusline(self, window):
        _, w = window.getmaxyx()

        self.statusline.draw(window, w, 1, 0, 0,
                             curses.color_pair(3) | curses.A_REVERSE)

    def draw(self, window, w, h, x, y, color):
        """Updates itself and then draws"""

        self.update()
        super().draw(window, w, h, x, y, color)


class IntCtrl(CtrlWidget):
    """
    Integer type control widget
    Uses LabeledBar to display its value
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.bar = BarLabeled(ctrl.minimum, ctrl.maximum, self.value)
        self.widgets[2] = self.bar

    def inc(self, delta):
        total_span = self.ctrl.maximum - self.ctrl.minimum

        one_percent = total_span / 100.0
        value = self.value

        inc = int(delta * one_percent)

        if inc == 0:
            if delta > 0:
                inc = 1
            else:
                inc = -1
            inc *= self.ctrl.step

        value += inc

        if value < self.ctrl.minimum:
            value = self.ctrl.minimum
        elif value > self.ctrl.maximum:
            value = self.ctrl.maximum

        self.value = value

    @property
    def statusline(self):
        minimum = self.ctrl.minimum
        maximum = self.ctrl.maximum
        step = self.ctrl.step
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=Integer",
            f"{minimum=}",
            f"{maximum=}",
            f"{step=}",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))


class BoolCtrl(CtrlWidget):
    """
    Boolean type control widget
    Uses TrueFalse to display its value
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets[2] = TrueFalse(self.value)

    def true(self):
        self.value = True

    def false(self):
        self.value = False

    def neg(self):
        self.value = not self.value

    @property
    def statusline(self):
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=Boolean",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))


class MenuCtrl(CtrlWidget):
    """
    Menu type control widget
    Uses Menu to display its value
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)

        querymenu = v4l2_querymenu()
        querymenu.id = ctrl.id

        options = {}
        for i in range(ctrl.minimum, ctrl.maximum + 1):
            querymenu.index = i
            try:
                ioctl(device, VIDIOC_QUERYMENU, querymenu)
                options[i] = querymenu.name.decode("ascii")
            except OSError:
                pass

        self.menu = Menu(options)
        self.widgets[2] = self.menu

    def next(self):
        """Selects next option"""

        self.menu.next()
        self.value = self.menu.value

    def prev(self):
        """Selects previous option"""

        self.menu.prev()
        self.value = self.menu.value

    @property
    def statusline(self):
        minimum = self.ctrl.minimum
        maximum = self.ctrl.maximum
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=Menu",
            f"{minimum=}",
            f"{maximum=}",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))


class ButtonCtrl(CtrlWidget):
    """
    Button type control widget
    Uses Button with 'Click me' text
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets[2] = Button("Click me")

    def click(self):
        """
        Button type controls need to set its
        value to 1, and after a while they reset
        themselves to 0
        """

        self.value = 1

    @property
    def statusline(self):
        flags = self.ctrl.flags
        return Label(f"type=Button, {flags=}")


class Int64Ctrl(IntCtrl):
    """
    Integer64 type control widget
    Same as Integer one, except for statusline
    """
    @property
    def statusline(self):
        minimum = self.ctrl.minimum
        maximum = self.ctrl.maximum
        step = self.ctrl.step
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=Integer64",
            f"{minimum=}",
            f"{maximum=}",
            f"{step=}",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))


class CtrlClassCtrl(CtrlWidget):
    """
    Control Class control widget
    Removes second widget to show just its name,
    as it's just a category name control
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets = [Label(self.name, align="center")]
        self.columns = (1, )


class StringCtrl(CtrlWidget):
    """
    String type control widget
    Uses TextField to display its value.
    Enter key toggles edit mode and Escape aborts edit mode and
    restores previous text.

    String type controls use minimum and maximum fields to limit
    number of characters stored.
    When upper limit is reached, then further keys are ignored
    (except Enter and Escape).
    When minimum number of characters is not present, then spaces
    are appended at the end.
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.text_field = TextField(self.value)
        self.widgets[2] = self.text_field

    def on_keypress(self, key):
        in_edit = self.text_field.in_edit

        if in_edit and key == "\n":
            self.text_field.edit()
            self.value = self.text_field.buffer
        elif in_edit and ord(key) == curses.KEY_BACKSPACE:
            self.text_field.buffer = self.text_field.buffer[:-1]
        elif in_edit and key == KEY_ESCAPE:
            self.text_field.abort()
        elif in_edit:
            if len(self.text_field.buffer) < self.ctrl.maximum:
                self.text_field.buffer += key
        elif key == "\n":
            self.text_field.edit()
        else:
            return super().on_keypress(key)

    @property
    def statusline(self):
        minimum = self.ctrl.minimum
        maximum = self.ctrl.maximum
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=String",
            f"{minimum=}",
            f"{maximum=}",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))


class BitmaskCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)


class IntMenuCtrl(MenuCtrl):
    """
    IntegerMenu type control widget
    Just like MenuCtrl, but doesn't decode text representations
    of its values, as they are numbers.
    """
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)

        querymenu = v4l2_querymenu()
        querymenu.id = ctrl.id

        options = {}
        for i in range(ctrl.minimum, ctrl.maximum + 1):
            querymenu.index = i
            try:
                ioctl(device, VIDIOC_QUERYMENU, querymenu)
                options[i] = int.from_bytes(querymenu.name, "little")
            except OSError:
                pass

        self.menu = Menu(options)
        self.widgets[2] = self.menu

    @property
    def statusline(self):
        minimum = self.ctrl.minimum
        maximum = self.ctrl.maximum
        default = self.ctrl.default
        value = self.value
        flags = self.ctrl.flags
        return Label(", ".join((
            "type=IntMenu",
            f"{minimum=}",
            f"{maximum=}",
            f"{default=}",
            f"{value=}",
            f"{flags=}",
        )))
