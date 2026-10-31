# -*- coding: utf-8 -*-
"""Память Nika: один JSON-файл рядом с приложением (в приватной папке Android)."""

import json
import os
import tempfile
import threading
import time

DEFAULTS = {
    "version": 1,
    "facts": {},          # {"name": "Егор", "city": "Москва", "likes": [...]}
    "notes": [],          # [{"id":1,"text":"...","ts":...}]
    "reminders": [],      # [{"at": 1700000000, "text": "...", "done": false}]
    "memory": {},         # старые пары «вопрос -> ответ» (запомни: X - Y)
    "learned": {},        # синонимы команд: {"вруби ютуб": "открой ютуб"}
    "unknown": [],        # фразы, которые не поняла
    "dialog": [],         # последние реплики (для памяти и продолжения)
    "prefs": {
        "voice": True,        # говорить вслух
        "notify": True,       # системные уведомления
        "instant_call": False,  # звонить сразу, а не открывать номеронабиратель
        "city": "",           # город по умолчанию для погоды
        "theme_contrast": False,
    },
    "stats": {
        "first_seen": 0,
        "last_seen": 0,
        "msg_count": 0,
        "greeted_day": "",
    },
}


def _deep_merge(base, extra):
    """Аккуратно дополняет сохранённые данные новыми полями из DEFAULTS."""
    out = dict(base)
    for key, value in extra.items():
        if key not in out:
            out[key] = value
        elif isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
    return out


class Store:
    """Потокобезопасное хранилище. Пишет атомарно, чтобы не терять память."""

    def __init__(self, path):
        self.path = path
        self._lock = threading.RLock()
        self.data = json.loads(json.dumps(DEFAULTS))
        self._load()

    # ---------- диск ----------
    def _load(self):
        try:
            if not os.path.exists(self.path):
                return
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.data = _deep_merge(raw, DEFAULTS)
        except Exception:
            # повреждённый файл не должен ронять приложение
            try:
                os.replace(self.path, self.path + ".broken")
            except OSError:
                pass

    def save(self):
        with self._lock:
            try:
                folder = os.path.dirname(os.path.abspath(self.path))
                if folder and not os.path.isdir(folder):
                    os.makedirs(folder)
                fd, tmp = tempfile.mkstemp(prefix=".nika_", dir=folder or ".")
                os.close(fd)
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception:
                pass

    # ---------- доступ ----------
    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self._lock:
            self.data[key] = value

    def pref(self, name, default=None):
        with self._lock:
            return self.data.get("prefs", {}).get(name, default)

    def set_pref(self, name, value):
        with self._lock:
            self.data.setdefault("prefs", {})[name] = value

    # ---------- факты ----------
    def fact(self, name, value=None):
        with self._lock:
            facts = self.data.setdefault("facts", {})
            if value is None:
                return facts.get(name)
            facts[name] = value
            return value

    def add_like(self, thing):
        thing = (thing or "").strip(" .,!")
        if not thing or len(thing) > 60:
            return
        with self._lock:
            facts = self.data.setdefault("facts", {})
            likes = facts.setdefault("likes", [])
            if thing.lower() not in [x.lower() for x in likes]:
                likes.append(thing)
                del likes[:-20]

    # ---------- диалог ----------
    def push_dialog(self, user, nika, limit=200):
        with self._lock:
            dialog = self.data.setdefault("dialog", [])
            dialog.append({"t": int(time.time()), "u": user, "n": nika})
            del dialog[:-limit]

    def dialog_tail(self, n=6):
        with self._lock:
            return list(self.data.get("dialog", [])[-n:])

    # ---------- заметки ----------
    def add_note(self, text):
        with self._lock:
            notes = self.data.setdefault("notes", [])
            note = {"id": (notes[-1]["id"] + 1) if notes else 1,
                    "text": text.strip(), "ts": int(time.time())}
            notes.append(note)
            return note

    def drop_note(self, index_one_based):
        with self._lock:
            notes = self.data.setdefault("notes", [])
            if 1 <= index_one_based <= len(notes):
                return notes.pop(index_one_based - 1)
            return None

    # ---------- напоминания ----------
    def add_reminder(self, at, text):
        with self._lock:
            items = self.data.setdefault("reminders", [])
            items.append({"at": float(at), "text": text.strip(), "done": False})
            return items[-1]

    def due_reminders(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            return [r for r in self.data.get("reminders", [])
                    if not r.get("done") and r.get("at", 0) <= now]

    def mark_reminder_done(self, reminder):
        with self._lock:
            reminder["done"] = True
            items = self.data.get("reminders", [])
            self.data["reminders"] = [r for r in items if not r.get("done")][-30:]

    # ---------- время ----------
    def touch(self):
        with self._lock:
            stats = self.data.setdefault("stats", {})
            if not stats.get("first_seen"):
                stats["first_seen"] = int(time.time())
            stats["last_seen"] = int(time.time())
            stats["msg_count"] = int(stats.get("msg_count", 0)) + 1

    def last_seen(self):
        return int(self.data.get("stats", {}).get("last_seen", 0))

    def msg_count(self):
        return int(self.data.get("stats", {}).get("msg_count", 0))
