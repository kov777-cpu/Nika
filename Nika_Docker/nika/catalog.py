# -*- coding: utf-8 -*-
"""Каталог приложений и сайтов, чтобы «открой ютуб» работало без интернета.

Для каждого приложения: пакет Android, человеческое имя, запасной сайт
(если приложение не установлено — откроем сайт или страницу в Play Market).
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import nlp


@dataclass
class App:
    keys: Tuple[str, ...]
    package: str
    label: str
    site: str = ""
    settings: str = ""   # необязательная страница настроек


@dataclass
class Site:
    keys: Tuple[str, ...]
    url: str
    label: str


# ======================================================================
#  Приложения
# ======================================================================

APPS: List[App] = [
    # --- общение ---
    App(("телеграм", "телега", "telegram", "тг", "телеграмм"), "org.telegram.messenger",
        "Telegram", "https://web.telegram.org"),
    App(("телеграм х", "telegram x"), "org.thunderdog.challegram", "Telegram X"),
    App(("вотсап", "ватсап", "whatsapp", "вацап", "вотс"), "com.whatsapp", "WhatsApp"),
    App(("вотсап бизнес", "whatsapp business"), "com.whatsapp.w4b", "WhatsApp Business"),
    App(("вайбер", "viber"), "com.viber.voip", "Viber"),
    App(("сигнал", "signal"), "org.thoughtcrime.securesms", "Signal"),
    App(("дискорд", "discord", "дс"), "com.discord", "Discord", "https://discord.com/app"),
    App(("вк", "vk", "вконтакте", "вконтакт"), "com.vkontakte.android", "VK",
        "https://m.vk.com"),
    App(("одноклассники", "ок", "ok"), "ru.ok.android", "OK", "https://m.ok.ru"),
    App(("инстаграм", "инста", "instagram", "иг"), "com.instagram.android", "Instagram",
        "https://www.instagram.com"),
    App(("тикток", "тик ток", "tiktok"), "com.zhiliaoapp.musically", "TikTok",
        "https://www.tiktok.com"),
    App(("твиттер", "twitter", "х"), "com.twitter.android", "X", "https://x.com"),
    App(("снапчат", "snapchat"), "com.snapchat.android", "Snapchat"),
    App(("зум", "zoom"), "us.zoom.videomeetings", "Zoom"),
    App(("тимс", "teams", "майкрософт тимс"), "com.microsoft.teams", "Teams"),

    # --- музыка и видео ---
    App(("ютуб", "youtube", "ютьюб", "ютюб"), "com.google.android.youtube", "YouTube",
        "https://m.youtube.com"),
    App(("ютуб мьюзик", "youtube music", "ютуб музыка"), "com.google.android.apps.youtube.music",
        "YouTube Music", "https://music.youtube.com"),
    App(("спотифай", "spotify"), "com.spotify.music", "Spotify", "https://open.spotify.com"),
    App(("яндекс музыка", "яндексмузыка", "яндекс музыка"), "ru.yandex.music", "Яндекс Музыка",
        "https://music.yandex.ru"),
    App(("звук", "zvuk"), "com.zvuk.app", "Звук"),
    App(("кинопоиск", "kinopoisk"), "ru.kinopoisk", "Кинопоиск", "https://www.kinopoisk.ru"),
    App(("иви", "ivi"), "ru.ivi.client", "IVI", "https://www.ivi.ru"),
    App(("нетфликс", "netflix"), "com.netflix.mediaclient", "Netflix", "https://www.netflix.com"),
    App(("влц", "vlc", "влс"), "org.videolan.vlc", "VLC"),
    App(("рутуб", "rutube"), "ru.rutube.app", "RUTUBE", "https://rutube.ru"),
    App(("твич", "twitch"), "tv.twitch.android.app", "Twitch", "https://m.twitch.tv"),
    App(("шейзам", "shazam"), "com.shazam.android", "Shazam"),

    # --- карты и транспорт ---
    App(("карты", "гугл карты", "google maps", "maps"), "com.google.android.apps.maps",
        "Google Карты", "https://maps.google.com"),
    App(("яндекс карты", "яндекс навигатор", "навигатор"), "ru.yandex.yandexmaps",
        "Яндекс Карты"),
    App(("2гис", "2 гис", "два гис", "2gis"), "ru.dublgis.dgismobile", "2ГИС"),
    App(("яндекс го", "яндекс такси", "такси", "yandex go"), "ru.yandex.taxi", "Яндекс Go"),
    App((("ситимобил", "сити мобил")), "com.citymobil", "Ситимобил"),
    App(("метро", "метро москвы"), "ru.metro", "Метро"),

    # --- покупки и деньги ---
    App(("авито", "avito"), "com.avito.android", "Авито", "https://m.avito.ru"),
    App(("озон", "ozon"), "ru.ozon.app.android", "Ozon", "https://m.ozon.ru"),
    App(("вайлдберриз", "вайлдберрис", "wildberries", "вб"), "com.wildberries.ru",
        "Wildberries", "https://www.wildberries.ru"),
    App(("алиэкспресс", "aliexpress", "али"), "com.alibaba.aliexpresshd", "AliExpress",
        "https://m.aliexpress.ru"),
    App(("яндекс маркет", "маркет"), "ru.yandex.market", "Яндекс Маркет",
        "https://market.yandex.ru"),
    App(("сбер", "сбербанк", "сбер онлайн"), "ru.sberbankmobile", "СберБанк Онлайн",
        "https://online.sberbank.ru"),
    App(("тинькофф", "т банк", "tinkoff", "тбанк"), "com.idamob.tinkoff.android", "Т-Банк",
        "https://www.tbank.ru"),
    App(("газпромбанк",), "ru.gazprombank.android.mobilebank", "Газпромбанк"),
    App(("альфа банк", "альфабанк"), "ru.alfabank.mobile.android", "Альфа-Банк"),
    App(("сбп", "платежи"), "ru.nspk.mirpay", "СБПэй"),

    # --- учёба, работа, госуслуги ---
    App(("госуслуги", "госы", "gosuslugi"), "ru.rostel", "Госуслуги",
        "https://www.gosuslugi.ru"),
    App(("налоги", "фнс", "лк фнс"), "ru.taxcom.nalog", "Налоги ФЛ"),
    App(("почта", "почта россии"), "ru.russianpost", "Почта России"),
    App(("яндекс почта", "почта яндекса"), "ru.yandex.mail", "Яндекс Почта",
        "https://mail.yandex.ru"),
    App(("джимейл", "gmail", "гмейл"), "com.google.android.gm", "Gmail",
        "https://mail.google.com"),
    App(("мейл ру", "mail ru", "mailru"), "ru.mail.mailapp", "Mail.ru", "https://mail.ru"),
    App(("ворд", "word"), "com.microsoft.office.word", "Word"),
    App(("эксель", "excel"), "com.microsoft.office.excel", "Excel"),
    App(("поинт", "powerpoint"), "com.microsoft.office.powerpoint", "PowerPoint"),
    App(("офис", "office"), "com.microsoft.office.officehubrow", "Office"),
    App(("ноут", "notion"), "notion.id", "Notion", "https://www.notion.so"),
    App(("обсидиан", "obsidian"), "md.obsidian", "Obsidian"),
    App(("телеграм стикер",), "org.telegram.messenger.web", "Telegram Web"),
    App(("зум конференция",), "us.zoom.videomeetings", "Zoom"),

    # --- разработка ---
    App(("гитхаб", "github"), "com.github.android", "GitHub", "https://github.com"),
    App(("термукс", "termux"), "com.termux", "Termux"),
    App(("питон", "python"), "ru.iiec.pydroid3", "Pydroid 3"),

    # --- нейросети ---
    App(("чатгпт", "chatgpt", "чат гпт"), "com.openai.chatgpt", "ChatGPT", "https://chatgpt.com"),
    App(("дипсик", "deepseek"), "com.deepseek.chat", "DeepSeek", "https://chat.deepseek.com"),
    App(("алиса", "яндекс", "яндекс браузер"), "ru.yandex.searchplugin", "Яндекс с Алисой",
        "https://yandex.ru"),

    # --- системное ---
    App(("камера", "camera", "фотик"), "com.google.android.GoogleCamera", "Камера"),
    App(("камера самсунг",), "com.sec.android.app.camera", "Камера"),
    App(("камера сяоми",), "com.android.camera", "Камера"),
    App(("галерея", "фото", "фотографии", "gallery"), "com.google.android.apps.photos",
        "Фото"),
    App(("часы", "будильник", "clock"), "com.google.android.deskclock", "Часы"),
    App(("калькулятор", "calculator"), "com.google.android.calculator", "Калькулятор"),
    App(("заметки", "notes", "keep"), "com.google.android.keep", "Заметки"),
    App(("календарь", "calendar"), "com.google.android.calendar", "Календарь"),
    App(("контакты", "contacts"), "com.google.android.contacts", "Контакты"),
    App(("телефон", "звонилка", "dialer"), "com.google.android.dialer", "Телефон"),
    App(("смс", "сообщения", "messages"), "com.google.android.apps.messaging", "Сообщения"),
    App(("настройки", "settings", "параметры"), "com.android.settings", "Настройки",
        settings="settings"),
    App(("файлы", "проводник", "files"), "com.google.android.documentsui", "Файлы"),
    App(("плей маркет", "play market", "маркет приложений", "google play"),
        "com.android.vending", "Google Play"),
    App(("хром", "chrome", "браузер"), "com.android.chrome", "Chrome",
        "https://www.google.com"),
    App(("яндекс браузер", "yandex browser"), "com.yandex.browser", "Яндекс Браузер",
        "https://yandex.ru"),
    App(("стим", "steam"), "com.valvesoftware.android.steam.community", "Steam",
        "https://store.steampowered.com"),
    App(("ютуб студио", "youtube studio"), "com.google.android.apps.youtube.creator",
        "YouTube Studio"),
    App(("фитнес", "fit", "здоровье"), "com.google.android.apps.fitness", "Fit"),
    App(("погода", "weather"), "com.google.android.apps.weather", "Погода",
        "https://yandex.ru/pogoda"),

    # --- прочее ---
    App(("переводчик", "translate"), "com.google.android.apps.translate", "Переводчик",
        "https://translate.google.com"),
    App(("книги", "books"), "com.google.android.apps.books", "Google Книги"),
    App(("подкасты", "podcasts"), "com.google.android.apps.podcasts", "Подкасты"),
    App(("диктофон", "recorder"), "com.google.android.apps.recorder", "Диктофон"),
    App(("фонарик", "flashlight"), "com.google.android.apps.flashlight", "Фонарик"),
]


# ======================================================================
#  Сайты
# ======================================================================

SITES: List[Site] = [
    Site(("ютуб", "youtube", "ютьюб"), "https://m.youtube.com", "YouTube"),
    Site(("вк", "vk", "вконтакте"), "https://m.vk.com", "ВКонтакте"),
    Site(("телеграм веб", "телеграм", "telegram", "web telegram"), "https://web.telegram.org",
         "Telegram Web"),
    Site(("одноклассники", "ок"), "https://m.ok.ru", "Одноклассники"),
    Site(("инстаграм", "instagram"), "https://www.instagram.com", "Instagram"),
    Site(("тикток", "tiktok"), "https://www.tiktok.com", "TikTok"),
    Site(("госуслуги", "gosuslugi"), "https://www.gosuslugi.ru", "Госуслуги"),
    Site(("почта яндекса", "яндекс почта", "яндекс почту", "почту"), "https://mail.yandex.ru",
         "Яндекс Почта"),
    Site(("джимейл", "gmail", "гмейл"), "https://mail.google.com", "Gmail"),
    Site(("мейл", "mail ru", "mailru"), "https://mail.ru", "Mail.ru"),
    Site(("сбер", "сбербанк", "сбер онлайн"), "https://online.sberbank.ru", "СберБанк"),
    Site(("тинькофф", "т банк", "tbank"), "https://www.tbank.ru", "Т-Банк"),
    Site(("авито", "avito"), "https://m.avito.ru", "Авито"),
    Site(("озон", "ozon"), "https://m.ozon.ru", "Ozon"),
    Site(("вайлдберриз", "wildberries"), "https://www.wildberries.ru", "Wildberries"),
    Site(("алиэкспресс", "aliexpress"), "https://m.aliexpress.ru", "AliExpress"),
    Site(("яндекс маркет", "маркет"), "https://market.yandex.ru", "Яндекс Маркет"),
    Site(("кинопоиск", "kinopoisk"), "https://www.kinopoisk.ru", "Кинопоиск"),
    Site(("иви", "ivi"), "https://www.ivi.ru", "IVI"),
    Site(("рутуб", "rutube"), "https://rutube.ru", "RUTUBE"),
    Site(("твич", "twitch"), "https://m.twitch.tv", "Twitch"),
    Site(("спотифай", "spotify"), "https://open.spotify.com", "Spotify"),
    Site(("яндекс музыка", "музыка"), "https://music.yandex.ru", "Яндекс Музыка"),
    Site(("гитхаб", "github"), "https://github.com", "GitHub"),
    Site(("стек оверфлоу", "stackoverflow"), "https://stackoverflow.com", "Stack Overflow"),
    Site(("хабр", "habr"), "https://habr.com", "Хабр"),
    Site(("википедия", "wikipedia", "вики"), "https://ru.m.wikipedia.org", "Википедия"),
    Site(("яндекс", "yandex"), "https://yandex.ru", "Яндекс"),
    Site(("гугл", "google"), "https://www.google.com", "Google"),
    Site(("дудак", "duckduckgo"), "https://duckduckgo.com", "DuckDuckGo"),
    Site(("яндекс погода", "погода"), "https://yandex.ru/pogoda", "Погода"),
    Site(("новости", "лента"), "https://lenta.ru", "Лента"),
    Site(("рик", "ria"), "https://ria.ru", "РИА Новости"),
    Site(("пикабу", "pikabu"), "https://pikabu.ru", "Пикабу"),
    Site(("джой", "joyreactor"), "https://joyreactor.cc", "JoyReactor"),
    Site(("эйчач", "hh", "хедхантер"), "https://hh.ru", "hh.ru"),
    Site(("авито работа",), "https://www.avito.ru/rossiya/vakansii", "Авито Работа"),
    Site(("карты", "гугл карты"), "https://maps.google.com", "Google Карты"),
    Site(("яндекс карты",), "https://yandex.ru/maps", "Яндекс Карты"),
    Site(("2гис", "2gis"), "https://2gis.ru", "2ГИС"),
    Site(("переводчик", "translate"), "https://translate.google.com", "Переводчик"),
    Site(("дипсик", "deepseek"), "https://chat.deepseek.com", "DeepSeek"),
    Site(("чатгпт", "chatgpt"), "https://chatgpt.com", "ChatGPT"),
]


# ======================================================================
#  Экстренные номера
# ======================================================================

EMERGENCY = [
    (("скорую", "скорая", "скорой", "неотложку", "неотложка", "врача"), "103"),
    (("полицию", "полиция", "полиции", "ментам", "менты", "полицейского"), "102"),
    (("пожарным", "пожарные", "пожарная", "пожарных"), "101"),
    (("мчс", "спасателей", "спасатели"), "112"),
    (("газ", "газовую"), "104"),
    (("единый", "экстренный", "112"), "112"),
    (("справку", "справка", "регистратуру"), "003"),
]


# ======================================================================
#  Поиск
# ======================================================================

def _best(query, items):
    """Ищет по ключам. Возвращает (объект, оценка)."""
    q = nlp.fold(query)
    if not q:
        return None, 0.0
    # точное совпадение ключа — приоритет
    for item in items:
        for key in item.keys:
            if nlp.fold(key) == q:
                return item, 1.0
    pair, score = nlp.fuzzy_best(
        q, [(item, list(item.keys)) for item in items])
    return pair, score


def find_app(query, threshold=0.74):
    app, score = _best(query, APPS)
    return app if score >= threshold else None


def find_site(query, threshold=0.74):
    site, score = _best(query, SITES)
    return site if score >= threshold else None


def emergency_number(query):
    q = nlp.fold(query)
    if not q:
        return None
    for keys, number in EMERGENCY:
        for key in keys:
            if q == key or q.startswith(key + " ") or (" " + key + " ") in (" " + q + " "):
                return number
    if q.isdigit() and len(q) in (3,) and q.startswith("1"):
        return q
    return None


def app_by_package(package):
    for app in APPS:
        if app.package == package:
            return app
    return None


def normalize_target(text):
    """«в ютубе», «ютуб», «на ютубе» -> «ютуб»."""
    t = nlp.strip_punct(text or "")
    t = re.sub(r"^(?:в|на|во|по)\s+", "", t, flags=re.IGNORECASE)
    t = re.sub(r"^(?:приложение|прогу|программу|сайт)\s+", "", t, flags=re.IGNORECASE)
    return nlp.strip_punct(t)
