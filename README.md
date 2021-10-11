# pyVidController

Copyright (c) 2018-2021 [Antmicro](https://www.antmicro.com)

A small python utility for controlling video4linux cameras.
It queries user-controls from the v4l2 devices and creates a TUI to display and adjust their values.

Features vi-like keybindings.

![](img/shot.png)

## Keybindings

|  Key  | Function                                                 |
|-------|----------------------------------------------------------|
|   q   | quit app                                                 |
|   ?   | toggle help                                              |
|   s   | toggle statusline                                        |
|  ⇧ ⇆  | select previous tab                                      |
|   ⇆   | select next tab                                          |
|   d   | reset to default                                         |
|   D   | reset all to default                                     |
| k / ↑ | select previous control                                  |
| j / ↓ | select next control                                      |
| u / , | decrease value by step                                   |
| p / . | increase value by step                                   |
| U / < | decrease value by 10 steps                               |
| P / > | increase value by 10 steps                               |
| h / ← | decrease value by 1% / set value false / previous choice |
| l / → | increase value by 1% / set value true / next choice      |
|H / ⇧ ←| decrease value by 10%                                    |
|L / ⇧ →| increase value by 10%                                    |
| ^ / ⇤ | set value to minimum                                     |
| $ / ⇥ | set value to maximum                                     |
|   ⏎   | negate value / click button                              |


## Installation

    pip install git+https://github.com/antmicro/pyvidctrl
