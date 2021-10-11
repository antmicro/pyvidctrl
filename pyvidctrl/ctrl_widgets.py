from fcntl import ioctl
from v4l2 import *
from widgets import *


class CtrlWidget(Row):
    def __init__(self, device, ctrl):
        self.device = device
        self.ctrl = ctrl

        self.name = ctrl.name.decode("ascii")
        self.label = Label(self.name)
        self.widget = Label("Not implemented!", align="center")

        super().__init__(self.label, Label(""), self.widget, columns=(4, 1, 4))

    @staticmethod
    def create(device, ctrl):
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
        gctrl = v4l2_control()
        gctrl.id = self.ctrl.id

        try:
            ioctl(self.device, VIDIOC_G_CTRL, gctrl)
        except OSError:
            return None

        return gctrl.value

    @value.setter
    def value(self, value):
        sctrl = v4l2_control()

        sctrl.id = self.ctrl.id
        sctrl.value = value
        try:
            ioctl(self.device, VIDIOC_S_CTRL, sctrl)
        except OSError:
            return

    def update(self):
        v = self.value
        for w in self.widgets:
            w.value = v

    def draw(self, window, w, h, x, y, color):
        self.update()
        super().draw(window, w, h, x, y, color)


class IntCtrl(CtrlWidget):
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


class BoolCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets[2] = TrueFalse(self.value)

    def true(self):
        self.value = True

    def false(self):
        self.value = False

    def neg(self):
        self.value = not self.value


class MenuCtrl(CtrlWidget):
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
        self.menu.next()
        self.value = self.menu.value

    def prev(self):
        self.menu.prev()
        self.value = self.menu.value


class ButtonCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets[2] = Button("Click me")

    def click(self):
        self.value = 1


Int64Ctrl = IntCtrl


class CtrlClassCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)
        self.widgets = [Label(self.name, align="center")]
        self.columns = (1, )


class StringCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)


class BitmaskCtrl(CtrlWidget):
    def __init__(self, device, ctrl):
        super().__init__(device, ctrl)


class IntMenuCtrl(MenuCtrl):
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
