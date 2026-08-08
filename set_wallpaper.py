"""Chalkboard's hand on the desktop — applies the rendered PNG as the wallpaper."""

import ctypes
import logging
import os

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02


def set_wallpaper(path):
    if os.name != "nt":  # bench preview — the PNG is the deliverable
        logging.info("Not a Windows host — wallpaper left unapplied, PNG at %s", path)
        return
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, str(path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
    )
    if not ok:
        raise OSError(f"SystemParametersInfoW refused wallpaper path: {path}")
