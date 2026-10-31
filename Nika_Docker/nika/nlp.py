# -*- coding: utf-8 -*-
"""Разбор человеческой речи: числа словами, длительности, время, телефоны, опечатки.

Модуль не зависит от Kivy и Android — его можно тестировать на компьютере.
"""

import re
from difflib import SequenceMatcher

# ======================================================================
#  Нормализация
# ======================================================================

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[\"'«»„“”`]")


def fold(text):
    """Нижний регистр, ё->е, без кавычек, один пробел. Для сравнения, не для показа."""
    t = (text or "").lower().replace("ё", "е")
    t = _PUNCT.sub(" ", t)
    return _WS.sub(" ", t).strip()


def strip_punct(text):
    return (text or "").strip(" \t\n.,!?;:—-")


def tokens(text):
    return re.findall(r"[a-zа-я0-9]+", fold(text))


def has_digit(text):
    return bool(re.search(r"\d", text or ""))


def looks_like_url(text):
    """«youtube.com», «https://...», «www.сайт.рф/путь» — значит открывать браузер."""
    raw = strip_punct(text).strip()
    if not raw or " " in raw:
        return False
    if re.match(r"^[a-z][a-z0-9+.-]*://", raw.lower()):
        return True
    return bool(re.match(
        r"^(?:www\.)?[a-zа-я0-9-]+(?:\.[a-zа-я0-9-]+)*\.[a-zа-я]{2,10}(?:/[^\s]*)?$",
        raw.lower()))


def normalize_phone(text):
    """Приводит номер к виду +7XXXXXXXXXX (для России) или +<цифры>."""
    digits = re.sub(r"\D", "", text or "")
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8"):
        return "+7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return "+" + digits
    if len(digits) == 10:
        return "+7" + digits
    if len(digits) < 3:
        return ""
    return "+" + digits


# ======================================================================
#  Числа словами
# ======================================================================

_WORD_NUM = {
    "ноль": 0, "один": 1, "одна": 1, "одну": 1, "два": 2, "две": 2, "три": 3,
    "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13,
    "четырнадцать": 14, "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17,
    "восемнадцать": 18, "девятнадцать": 19, "двадцать": 20, "тридцать": 30,
    "сорок": 40, "пятьдесят": 50, "шестьдесят": 60, "семьдесят": 70,
    "восемьдесят": 80, "девяносто": 90, "сто": 100,
}

_HOURS = {"час", "часа", "часов", "ч"}
_MINUTES = {"минута", "минуты", "минуту", "минут", "мин", "м"}
_SECONDS = {"секунда", "секунды", "секунду", "секунд", "сек", "с"}
_DAYS = {"сутки", "суток", "день", "дня", "дней"}

_FIXED = {
    "полчаса": 1800,
    "полминуты": 30,
    "полторы минуты": 90,
    "полтора часа": 5400,
    "полтора часа ровно": 5400,
    "четверть часа": 900,
    "час": 3600,
    "минуту": 60,
    "минутку": 60,
    "секунду": 1,
    "сутки": 86400,
}


def _read_number(tokens_list, start):
    """Читает «двадцать пять» начиная с позиции start. Возвращает (число, сдвиг)."""
    total = 0
    used = 0
    for token in tokens_list[start:start + 3]:
        if token in _WORD_NUM:
            total += _WORD_NUM[token]
            used += 1
        else:
            break
    return (total if used else None), used


def parse_duration(text):
    """«10 минут», «полчаса», «через двадцать пять минут», «1 ч 30 мин» -> секунды."""
    t = fold(text)
    if not t:
        return None
    for phrase, secs in _FIXED.items():
        # границы слова: иначе «час» съедает «2 часа»
        if re.search(r"(?<![а-я])" + re.escape(phrase) + r"(?![а-я])", t):
            return secs

    words = re.findall(r"[a-zа-я0-9]+", t)
    total = 0
    i = 0
    while i < len(words):
        word = words[i]
        value = None
        step = 1
        if word.isdigit():
            value = int(word)
        elif word in _WORD_NUM:
            value, used = _read_number(words, i)
            step = max(1, used)
        if value is None:
            i += 1
            continue
        unit = words[i + step] if i + step < len(words) else ""
        if unit in _HOURS:
            total += value * 3600
        elif unit in _MINUTES:
            total += value * 60
        elif unit in _SECONDS:
            total += value
        elif unit in _DAYS:
            total += value * 86400
        else:
            i += 1
            continue
        i += step + 1

    return total or None


# ======================================================================
#  Время суток
# ======================================================================

_DAY_PARTS = {
    "утра": "am", "утром": "am", "ночи": "night",
    "дня": "pm", "днем": "pm", "вечера": "pm", "вечером": "pm",
}


def parse_clock(text):
    """«в 7:30», «на 7 утра», «в 23 00», «в полдень» -> (часы, минуты)."""
    t = fold(text)
    if not t:
        return None
    if "полночь" in t:
        return (0, 0)
    if "полдень" in t:
        return (12, 0)

    hour = minute = None
    m = re.search(r"\b(\d{1,2})\s*[:.]\s*(\d{1,2})\b", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(?:в|на|к|до)\s+(\d{1,2})(?:\s+(\d{2}))?\b", t)
        if m:
            hour = int(m.group(1))
            minute = int(m.group(2)) if m.group(2) else 0
        else:
            m = re.search(r"\b(\d{1,2})\s+(?:час|часа|часов)\b", t)
            if m:
                hour, minute = int(m.group(1)), 0

    if hour is None or not (0 <= hour <= 24):
        return None
    if minute is None:
        minute = 0
    if not (0 <= minute <= 59):
        minute = 0

    part = None
    for word, kind in _DAY_PARTS.items():
        if re.search(r"\b" + word + r"\b", t):
            part = kind
            break

    if part == "pm" and hour < 12:
        hour += 12
    elif part == "am" and hour == 12:
        hour = 0
    elif part == "night" and hour == 12:
        hour = 0

    if hour == 24:
        hour = 0
    return (hour, minute)


def human_duration(seconds):
    seconds = max(0, int(seconds))
    if seconds < 60:
        return "%d сек" % seconds
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        if secs:
            return "%d мин %d сек" % (minutes, secs)
        return "%d мин" % minutes
    hours, minutes = divmod(minutes, 60)
    if minutes:
        return "%d ч %d мин" % (hours, minutes)
    return "%d ч" % hours


def human_clock(hour, minute):
    return "%02d:%02d" % (int(hour) % 24, int(minute) % 60)


# ======================================================================
#  Похожесть и опечатки
# ======================================================================

_STEM_ENDINGS = (
    "ами", "ями", "ыми", "ими", "ого", "его", "ому", "ему", "ах", "ях",
    "ам", "ям", "ов", "ев", "ей", "ой", "ый", "ая", "ое", "ые", "ом", "ем",
    "а", "я", "ы", "и", "у", "ю", "е", "о", "ь",
)


def stem_ru(word):
    """Грубая основа слова: «маме»/«мама»/«маму» -> «мам»."""
    w = fold(word)
    if len(w) <= 3:
        return w
    for ending in _STEM_ENDINGS:
        if w.endswith(ending) and len(w) - len(ending) >= 3:
            return w[:-len(ending)]
    return w


def ratio(a, b):
    return SequenceMatcher(None, fold(a), fold(b)).ratio()


def fuzzy_best(query, candidates):
    """Возвращает лучшую пару (значение, оценка) из candidates.

    candidates — список значений или список пар (значение, ключи).
    """
    q = fold(query)
    if not q:
        return None, 0.0
    best, best_score = None, 0.0
    for item in candidates:
        keys = item[1] if isinstance(item, tuple) else [item]
        for key in keys:
            k = fold(key)
            if not k:
                continue
            score = 0.0
            if k == q:
                score = 1.0
            elif k.startswith(q) or q.startswith(k):
                score = 0.9 - abs(len(k) - len(q)) * 0.01
            elif q in k:
                score = 0.82
            elif stem_ru(k) and stem_ru(k) == stem_ru(q):
                score = 0.88
            elif stem_ru(k) and (stem_ru(k).startswith(stem_ru(q)) or
                                 stem_ru(q).startswith(stem_ru(k))):
                score = 0.78
            else:
                score = ratio(k, q) * 0.75
            if score > best_score:
                best, best_score = (item[0] if isinstance(item, tuple) else item), score
    return best, best_score


COMMAND_VERBS = [
    "открой", "открыть", "запусти", "запустить", "включи", "вруби", "включить",
    "позвони", "позвонить", "набери", "набрать", "дозвонись", "вызови",
    "напиши", "отправь", "найди", "поищи", "загугли", "погугли", "вбей",
    "засеки", "таймер", "отсчитай", "будильник", "разбуди", "напомни",
    "погода", "фонарик", "заряд", "громче", "тише", "запиши", "запомни",
    "научись", "покажи", "переключи", "выключи", "поставь", "вайфай",
    "пароль", "смс", "сколько", "который", "что", "как", "где", "кто",
    "когда", "почему", "расскажи", "пошути", "привет", "спасибо", "пока",
    "какие", "какой", "какая", "удали", "забудь", "откройте",
]

# слова, которые нельзя «чинить» как опечатку: они уже правильные
_SAFE_WORDS = set(COMMAND_VERBS) | {
    "какое", "какую", "каком", "какои", "какия", "чем", "кем", "чей", "чья",
    "куда", "откуда", "можно", "надо", "нужно", "давай", "дайте", "плиз",
    "пожалуйста", "есть", "будет", "было", "это", "этот", "эта", "моя", "мой",
    "мои", "твой", "твоя", "твои", "мне", "меня", "тебе", "тебя", "она", "они",
    "мы", "вы", "ты", "все", "всё", "уже", "ещё", "еще", "или", "но", "а",
    "и", "в", "на", "с", "к", "по", "из", "от", "до", "за", "для",
}


def fix_typos(text, vocabulary=None):
    """Правит опечатки в первом слове команды: «аткрой ютуб» -> «открой ютуб»."""
    words = (text or "").split()
    if not words:
        return text
    vocabulary = vocabulary or COMMAND_VERBS
    first = fold(words[0])
    if first in _SAFE_WORDS:
        return text
    folded = {fold(v): v for v in vocabulary}
    if first in folded:
        return text
    best, best_score = None, 0.0
    for key, original in folded.items():
        if abs(len(key) - len(first)) > 2:
            continue
        score = SequenceMatcher(None, first, key).ratio()
        if score > best_score:
            best, best_score = original, score
    if best and 0.78 <= best_score < 1.0:
        words[0] = best
        return " ".join(words)
    return text


# ======================================================================
#  Склейка нескольких команд
# ======================================================================

_SPLITTERS = re.compile(r"\s*;\s*|\s+затем\s+|\s+потом\s+", re.IGNORECASE)


def _is_command_start(part):
    words = fold(part).split()
    if not words:
        return False
    return stem_ru(words[0]) in [stem_ru(v) for v in COMMAND_VERBS]


def split_multi(text):
    """«открой ютуб и позвони маме» -> две команды. Болтовню не разрывает."""
    parts = [p.strip() for p in _SPLITTERS.split(text or "") if p.strip()]
    if len(parts) == 1:
        # запятая и «и» — только если обе половины явно команды
        for sep in (r"\s*,\s*", r"\s+и\s+"):
            chunks = [c.strip() for c in re.split(sep, text or "", maxsplit=1)]
            if len(chunks) == 2 and _is_command_start(chunks[0]) and _is_command_start(chunks[1]):
                parts = chunks
                break
    return parts if parts else [text]


# ======================================================================
#  Для озвучки
# ======================================================================

def clean_for_speech(text, limit=350):
    """Убирает то, что TTS читает некрасиво: списки, скобки-смайлы, ссылки."""
    t = text or ""
    t = re.sub(r"https?://\S+", " ссылка ", t)
    t = t.replace("wi-fi", "вай-фай").replace("wifi", "вай-фай").replace("Wi-Fi", "вай-фай")
    t = re.sub(r"\bNika\b", "Ника", t)
    t = t.replace("•", ". ").replace("\n", ". ")
    t = re.sub(r"\)+", ".", t)
    t = re.sub(r"[()]", "", t)
    t = _WS.sub(" ", t).strip(" .")
    if len(t) > limit:
        cut = t[:limit]
        dot = cut.rfind(". ")
        t = cut[:dot + 1] if dot > 60 else cut + "…"
    return t
