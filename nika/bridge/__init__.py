# -*- coding: utf-8 -*-
"""Выбор моста: Android, если мы на телефоне, иначе — настольный."""

import os

from .base import Bridge, Contact, Res


def get_bridge(verbose=False):
    """Возвращает (bridge, note). note — почему не Android, если так вышло."""
    note = ""
    try:
        from kivy.utils import platform as kivy_platform
    except Exception:
        kivy_platform = None

    if kivy_platform == "android" or "ANDROID_ARGUMENT" in os.environ:
        try:
            from .android import AndroidBridge
            bridge = AndroidBridge()
            if bridge.ready():
                return bridge, ""
            note = "android-мост не инициализировался"
        except Exception as exc:  # noqa: BLE001
            note = "android-мост недоступен: %s" % exc
            if verbose:
                print("[Nika]", note)

    from .desktop import DesktopBridge
    return DesktopBridge(), note
