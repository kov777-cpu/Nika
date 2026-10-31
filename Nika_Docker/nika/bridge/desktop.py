# -*- coding: utf-8 -*-
"""Мост для компьютера: чтобы приложение можно было запустить и проверить на ПК.

Всё телефонное здесь честно отвечает «это на телефоне», а ссылки, погода,
чат, таймеры и даже wi-fi (через netsh) работают по-настоящему.
"""

import os
import subprocess
import webbrowser

from .base import Bridge, Contact, Res


class DesktopBridge(Bridge):
    platform_name = "компьютер"
    can_apps = False
    can_voice = False
    can_notify = False
    can_wifi_passwords = True  # на Windows netsh отдаёт пароль без root

    def ready(self):
        return True

    # ---------- ссылки ----------
    def open_url(self, url):
        try:
            webbrowser.open(url)
            return Res(True, "", url)
        except Exception as exc:
            return Res(False, "не смогла открыть браузер: %s" % exc)

    def open_play_store(self, package):
        return self.open_url("https://play.google.com/store/apps/details?id=%s" % package)

    def launch_package(self, package):
        return Res(False, "приложения запускаются на телефоне.")

    def app_installed(self, package):
        return False

    # ---------- звонки ----------
    def dial(self, number, direct=False):
        return Res(False, "позвонить могу только с телефона — тут нет сим-карты)")

    def send_sms(self, number, text):
        return Res(False, "сообщения отправляю только с телефона.")

    # ---------- wi-fi через netsh (только Windows) ----------
    def _netsh(self, args):
        if os.name != "nt":
            return ""
        try:
            out = subprocess.run(
                ["cmd", "/c", "chcp 65001>nul & netsh wlan " + args],
                capture_output=True, timeout=20,
            )
        except Exception:
            return ""
        raw = (out.stdout or b"") + (out.stderr or b"")
        for enc in ("utf-8", "cp866", "cp1251"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    def wifi_info(self):
        text = self._netsh("show interfaces")
        info = {}
        for line in (text or "").splitlines():
            low = line.lower()
            if "ssid" in low and "bssid" not in low and ":" in line:
                value = line.split(":", 1)[1].strip()
                if value:
                    info["ssid"] = value
                    break
        info["connected"] = bool(info.get("ssid"))
        if info.get("connected"):
            info["signal"] = "—"
        return info

    def wifi_saved(self):
        text = self._netsh("show profiles")
        names = []
        for line in (text or "").splitlines():
            if ":" in line and ("profile" in line.lower() or "профил" in line.lower()):
                value = line.split(":", 1)[1].strip()
                if value and value not in names:
                    names.append(value)
        return names

    def wifi_password(self, ssid):
        safe = (ssid or "").replace('"', "").strip()
        if not safe:
            return None, ""
        text = self._netsh('show profile name="%s" key=clear' % safe)
        for line in (text or "").splitlines():
            low = line.lower()
            if ":" in line and ("key content" in low or "содержимое ключа" in low or
                                "ключевое содержимое" in low):
                value = line.split(":", 1)[1].strip()
                if value:
                    return value, "netsh"
        return None, ""

    # ---------- батарея на Windows ----------
    def battery(self):
        if os.name != "nt":
            return {}
        try:
            import ctypes

            class PowerStatus(ctypes.Structure):
                _fields_ = [("ACLineStatus", ctypes.c_byte),
                            ("BatteryFlag", ctypes.c_byte),
                            ("BatteryLifePercent", ctypes.c_byte),
                            ("Reserved1", ctypes.c_byte),
                            ("BatteryLifeTime", ctypes.c_ulong),
                            ("BatteryFullLifeTime", ctypes.c_ulong)]

            status = PowerStatus()
            if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
                return {}
            percent = int(status.BatteryLifePercent)
            if percent > 100:
                return {}
            return {"percent": percent, "charging": status.ACLineStatus == 1}
        except Exception:
            return {}

    # ---------- голос и уведомления ----------
    def speak(self, text):
        print("[Nika говорит] %s" % text)
        return Res(True, "")

    def stop_speak(self):
        return Res(True, "")

    def notify(self, title, text):
        print("[Nika] %s: %s" % (title, text))
        return Res(True, "")

    def vibrate(self, ms=40):
        return Res(False, "")

    def open_settings(self, page=""):
        return Res(False, "настройки телефона — на телефоне.")
