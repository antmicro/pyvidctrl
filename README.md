# pyVidController

A small python utility for controlling video4linux cameras.
It queries user-controls from the v4l2 devices and creates a TUI to display and adjust their values.

Features vi-like keybindings.

![](img/shot.png)

## Keybindings

| Key | Function                       |
|-----|--------------------------------|
| q   | exit                           |
| j   | next entry                     |
| k   | previous entry                 |
| u   | decrease current value by 0.1% |
| U   | decrease current value by 0.5% |
| h   | decrease current value by 1%   |
| H   | decrease current value by 10%  |
| p   | increase current value by 0.1% |
| P   | increase current value by 0.5% |
| l   | increase current value by 1%   |
| L   | increase current value by 10%  |

## Installation

    pip install git+https://github.com/antmicro/pyvidctrl

(c) 2018-2019 [Antmicro](https://antmicro.com)
