# -*- coding: utf-8 -*-
"""Общий интерфейс «телефонных» возможностей.

Логика Nika не знает, Android под ней или компьютер: она зовёт методы моста.
На ПК часть методов честно отвечает «это умею только на телефоне».
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class Res:
    """Результат действия: получилось ли и что сказать человеку."""

    ok: bool
    message: str = ""
    data: Any = None

    def __bool__(self):
        return bool(self.ok)


@dataclass
class Contact:
    name: str
    number: str
    raw_number: str = ""

    def __str__(self):
        return "%s — %s" % (self.name, self.number)


class Bridge:
    """Базовый мост. Всё, что не переопределено, недоступно."""

    is_android = False
    platform_name = "компьютер"
    can_call = False
    can_contacts = False
    can_apps = False
    can_wifi_passwords = False
    can_voice = False
    can_notify = False

    def __init__(self):
        self._contacts_cache: Optional[List[Contact]] = None
        self._contacts_ts = 0.0
        self._apps_cache: Optional[List[Tuple[str, str]]] = None
        self._apps_ts = 0.0

    # ---------- инфо ----------
    def info(self) -> Dict[str, Any]:
        return {"platform": self.platform_name, "android": self.is_android}

    def ready(self) -> bool:
        return True

    # ---------- ссылки и приложения ----------
    def open_url(self, url: str) -> Res:
        return Res(False, "ссылки умею открывать только на телефоне.")

    def launch_package(self, package: str) -> Res:
        return Res(False, "приложения живут на телефоне.")

    def app_installed(self, package: str) -> bool:
        return False

    def installed_apps(self) -> List[Tuple[str, str]]:
        return []

    def open_play_store(self, package: str) -> Res:
        return Res(False, "магазин приложений есть только на телефоне.")

    # ---------- звонки и сообщения ----------
    def contacts(self) -> List[Contact]:
        return []

    def dial(self, number: str, direct: bool = False) -> Res:
        return Res(False, "позвонить могу только с телефона.")

    def send_sms(self, number: str, text: str) -> Res:
        return Res(False, "сообщения отправляю только с телефона.")

    # ---------- медиа ----------
    def play_media(self, query: str = "", video: bool = False) -> Res:
        return Res(False, "музыку и видео включаю на телефоне.")

    # ---------- системное ----------
    def set_alarm(self, hour: int, minute: int, label: str = "") -> Res:
        return Res(False, "будильник поставлю на телефоне.")

    def torch(self, on: bool) -> Res:
        return Res(False, "фонарик есть только на телефоне.")

    def battery(self) -> Dict[str, Any]:
        return {}

    def volume(self, direction: str) -> Res:
        return Res(False, "звук регулирую на телефоне.")

    def open_settings(self, page: str = "") -> Res:
        return Res(False, "настройки открою на телефоне.")

    def notify(self, title: str, text: str) -> Res:
        return Res(False, "")

    def vibrate(self, ms: int = 40) -> Res:
        return Res(False, "")

    # ---------- голос ----------
    def speak(self, text: str) -> Res:
        return Res(False, "")

    def stop_speak(self) -> Res:
        return Res(False, "")

    def listen(self, callback: Callable[[Optional[str]], None]) -> Res:
        return Res(False, "голосовой ввод работает на телефоне.")

    # ---------- wi-fi ----------
    def wifi_info(self) -> Dict[str, Any]:
        return {}

    def wifi_saved(self) -> List[str]:
        return []

    def wifi_password(self, ssid: str) -> Tuple[Optional[str], str]:
        """(пароль, способ). Пароль достаётся только с root — иначе (None, '')."""
        return None, ""

    # ---------- права ----------
    def has_permission(self, name: str) -> bool:
        return False

    def request_permissions(self, names: List[str],
                            callback: Callable[[bool], None]) -> Res:
        return Res(False, "права выдаются на телефоне.")

    # ---------- утилиты ----------
    def touch_contacts_cache(self, contacts: List[Contact]):
        self._contacts_cache = contacts
        self._contacts_ts = time.time()

    def cached_contacts(self) -> Optional[List[Contact]]:
        if self._contacts_cache is not None and time.time() - self._contacts_ts < 120:
            return self._contacts_cache
        return None

    def touch_apps_cache(self, apps: List[Tuple[str, str]]):
        self._apps_cache = apps
        self._apps_ts = time.time()

    def cached_apps(self) -> Optional[List[Tuple[str, str]]]:
        if self._apps_cache is not None and time.time() - self._apps_ts < 180:
            return self._apps_cache
        return None
