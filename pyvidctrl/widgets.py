import curses


class KeyBind:
    KEYBINDS = []

    def __init__(self, cls, key, handler, help_text, display=None):
        assert callable(handler)
        assert isinstance(key, str) or display is not None

        if isinstance(key, int):
            key = chr(key)

        self.cls = cls
        self.key = key
        self.handler = handler
        self.help_text = help_text
        self.display = display or key

        KeyBind.KEYBINDS.append(self)

    @staticmethod
    def get_handler(cls, key):
        """Search and return key handler registered for `cls` and `key`"""

        try:
            return next(
                filter(lambda k: k.cls == cls and k.key == key,
                       KeyBind.KEYBINDS))
        except StopIteration:
            return None

    def __call__(self, other):
        return self.handler(other)


class Widget:
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value

    def draw(self, window, w, h, x, y, color):
        pass

    def on_keypress(self, key):
        handler = KeyBind.get_handler(self.__class__, key)

        if handler is not None:
            return handler(self)
        else:
            return True


class Row(Widget):
    def __init__(self, *widgets, columns=None):
        self.widgets = list(widgets)
        self.columns = columns or [1 for _ in widgets]
        assert len(self.columns) == len(self.widgets)

    def draw(self, window, w, h, x, y, color):
        total = 0
        for i, (widget, col) in enumerate(zip(self.widgets, self.columns)):
            if i == len(self.widgets) - 1:
                widget_w = w - total
            else:
                widget_w = round(w * col / sum(self.columns))
            if widget_w > 0:
                widget.draw(window, widget_w, h, x + total, y, color)
                total += widget_w


class Label(Widget):
    def __init__(self, text="", align="left"):
        assert align in ["left", "center", "right"]
        self.text = str(text)
        self.align = align

    def update(self, value):
        self.text = str(value)

    def draw(self, window, w, h, x, y, color):
        render = ""
        if len(self.text) > w:
            render = self.text[:w - 1] + "…"
        elif self.align == "left":
            render = self.text.ljust(w)
        elif self.align == "center":
            render = self.text.center(w)
        elif self.align == "right":
            render = self.text.rjust(w)

        window.addstr(y, x, render, color)


class TextField(Widget):
    def __init__(self, value="", align="left"):
        assert align in ["left", "center", "right"]
        self.value = str(value)
        self.align = align
        self.in_edit = False

    def draw(self, window, w, h, x, y, color):
        self.value = str(self.value)
        render = self.buffer if self.in_edit else self.value
        if len(render) > w:
            render = render[:w - 1] + "…"
        elif self.align == "left":
            render = render.ljust(w)
        elif self.align == "center":
            render = render.center(w)
        elif self.align == "right":
            render = render.rjust(w)

        f = color | curses.A_ITALIC

        if self.in_edit:
            window.addstr(y, x, render, f | curses.A_REVERSE)
        else:
            window.addstr(y, x, render, f)

    def edit(self):
        if not self.in_edit:
            self.buffer = self.value
            self.in_edit = True
        else:
            self.value = self.buffer
            self.in_edit = False

    def abort(self):
        self.in_edit = False


class Checkbox(Widget):
    def __init__(self, value=False):
        self.value = value

    def draw(self, window, w, h, x, y, color):
        render = ("[x]" if self.value else "[ ]").center(w)
        window.addstr(y, x, render, color)


class TrueFalse(Widget):
    def __init__(self, value=False):
        self.value = value

    def draw(self, window, w, h, x, y, color):
        fbox, tbox = "[ ]", "[x]"

        if not self.value:
            fbox, tbox = tbox, fbox

        Label(fbox + " False", align="center").draw(window, w // 2, h, x, y,
                                                    color)
        Label(tbox + " True", align="center").draw(window, w - w // 2, h,
                                                   x + w // 2, y, color)


class Menu(Widget):
    def __init__(self, options={}, selected=None):
        self.options = options
        self.keys = list(options.keys())
        assert 0 < len(self.keys)

        if selected is not None:
            assert selected in options.keys()
            self.selected = self.keys.index(selected)
        else:
            self.selected = 0

    @property
    def value(self):
        return self.keys[self.selected]

    @value.setter
    def value(self, value):
        if value is not None and value in self.options.keys():
            self.selected = self.keys.index(value)

    def next(self):
        if self.selected + 1 <= len(self.keys) - 1:
            self.selected = self.selected + 1

    def prev(self):
        if self.selected - 1 >= 0:
            self.selected = self.selected - 1

    def draw(self, window, w, h, x, y, color):
        pre = "<" if self.selected > 0 else " "
        post = ">" if self.selected < len(self.keys) - 1 else " "
        middle = str(self.options[self.value])
        if w < len(middle) + 2:
            middle = middle[:w - 3] + "…"
        render = pre + middle.center(w - 2) + post
        window.addstr(y, x, render, color)


class Bar(Widget):
    def __init__(self, min, max, value=None):
        self.value = value if value is not None else min
        self.min = min
        self.max = max

    def draw(self, window, w, h, x, y, color):
        filled_w = round(w * (self.value - self.min) / (self.max - self.min))
        empty_w = w - filled_w

        window.addstr(y, x, " " * filled_w, color | curses.A_REVERSE)
        window.addstr(y, x + filled_w, " " * empty_w, curses.color_pair(7))


class BarLabeled(Bar):
    def __init__(self, min, max, value=None, label_position="left"):
        super().__init__(min, max, value)

        assert label_position in ["left", "right"]
        self.label_position = label_position

    def draw(self, window, w, h, x, y, color):
        text = str(self.value)
        if len(text) > w:
            render = "…" + text[len(text) - w + 1:]
        else:
            render = text.center(w)

        filled_w = round(w * (self.value - self.min) / (self.max - self.min))

        # if widget is selected
        if color == curses.color_pair(3) | curses.A_BOLD:
            empty_color = curses.color_pair(8) | curses.A_BOLD
        else:
            empty_color = curses.color_pair(7)

        window.addstr(y, x, render[:filled_w], color | curses.A_REVERSE)
        window.addstr(y, x + filled_w, render[filled_w:], empty_color)


class Button(Widget):
    def __init__(self, text):
        self.text = text

    def draw(self, window, w, h, x, y, color):
        render = "[" + self.text.center(w - 2) + "]"
        window.addstr(y, x, render, color)
