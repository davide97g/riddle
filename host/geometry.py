"""Digitizer and screen geometry for the reMarkable 2.

The Wacom layer is rotated relative to the panel: its X axis runs down the
tall side of the screen and is inverted, its Y axis runs across the short
side. These constants were measured on the device by tapping the two opposite
corners of a page and reading the raw samples back.
"""

WACOM_X_MAX = 20966
WACOM_Y_MAX = 15725
PRESSURE_MAX = 4095

SCREEN_W = 1404
SCREEN_H = 1872


def wacom_to_screen(wx: int, wy: int) -> tuple[float, float]:
    x = wy * SCREEN_W / WACOM_Y_MAX
    y = (WACOM_X_MAX - wx) * SCREEN_H / WACOM_X_MAX
    return x, y


def screen_to_wacom(x: float, y: float) -> tuple[int, int]:
    wx = WACOM_X_MAX - y * WACOM_X_MAX / SCREEN_H
    wy = x * WACOM_Y_MAX / SCREEN_W
    return (
        max(0, min(WACOM_X_MAX, round(wx))),
        max(0, min(WACOM_Y_MAX, round(wy))),
    )
