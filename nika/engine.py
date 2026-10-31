# -*- coding: utf-8 -*-
"""Мозг Nika: понимает фразу, решает, что сделать, и отвечает по-человечески.

Модуль не зависит от Kivy: его можно гонять тестами на компьютере,
подставив фейковый мост вместо Android.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import catalog, nlp
from .persona import (
    AFTER_COMMAND_CHIPS,
    AFTER_EMPATHY_CHIPS,
    AFTER_FACT_CHIPS,
    AFTER_JOKE_CHIPS,
    DEFAULT_CHIPS,
    HELP_LINES,
    Persona,
)
from .weather import Weather


@dataclass
class Reply:
    """Ответ Nika: текст, быстрые кнопки и поручения интерфейсу."""

    text: str = ""
    chips: List[str] = field(default_factory=list)
    actions: List[Dict[str, Any]] = field(default_factory=list)
    intent: str = ""
    speak: bool = True


# ======================================================================
#  Регулярки команд
# ======================================================================

CALL_RE = re.compile(
    r"^(?:позвони|позвонить|набери|набрать|дозвонись|вызови|набери номер)\s*(.*)$")
SMS_RE = re.compile(
    r"^(?:напиши|отправь|скинь|напиши сообщение)\s+(?:смс|сообщение|эсэмэску|эсэмэс)\s*(.*)$")
OPEN_RE = re.compile(
    r"^(?:открой|открыть|запусти|запустить|вруби|врубай|включи|покажи|откройте)\s*(.*)$")
MUSIC_RE = re.compile(
    r"^(?:включи|поставь|вруби|запусти|включить)\s+(?:музыку|песню|трек|плейлист|радио)\s*(.*)$")
VIDEO_RE = re.compile(
    r"^(?:включи|поставь|вруби|включить)\s+(?:видео|фильм|кино|сериал|ролик)\s*(.*)$")
TIMER_RE = re.compile(r"^(?:засеки|отсчитай|таймер|поставь таймер)\b\s*(.*)$")
ALARM_RE = re.compile(r"^(?:будильник|разбуди|поставь будильник)\b\s*(.*)$")
REMIND_RE = re.compile(r"^(?:напомни|напоминание)\b\s*(.*)$")
SEARCH_RE = re.compile(
    r"^(?:найди|поищи|загугли|погугли|вбей|ищи|поиск|найти)\s+(.*)$")
WHAT_RE = re.compile(r"^(?:что такое|кто такой|кто такая|что значит|расскажи про|расскажи о)\s+(.*)$")
WEATHER_RE = re.compile(r"^погод[а-я]*\s*(?:в|во|на|для|по)?\s*(.*)$")
SETTINGS_RE = re.compile(r"^(?:открой|открыть)?\s*(?:настройки|параметры)\s*(.*)$")
GREET_RE = re.compile(
    r"^(?:привет|приветик|приветствую|здравствуй|здравствуйте|хай|ку|прив|салют|"
    r"здорово|йо|добрый\s+(?:день|вечер)|доброе\s+утро|доброй\s+ночи|доброго\s+времени)"
    r"(?:\b|$)")
LEARN_RE = re.compile(r"^(?:научись|выучи)\s*[:\s]\s*(.+?)\s*(?:=|->|—|значит|это)\s*(.+)$")
MEMORY_RE = re.compile(r"^запомни\s*[:\s]\s*(.+?)\s*[-—=]\s*(.+)$")
NOTE_RE = re.compile(r"^(?:запомни|запиши|заметка)\s*[:\s]?\s*(.+)$")

THANKS_RE = re.compile(r"\b(?:спасибо|благодарю|спс|пасиба|от души|thanks)\b")
BYE_RE = re.compile(r"\b(?:пока|до свидания|до свид|бай|спокойной ночи|прощай)\b")
LOVE_RE = re.compile(r"\b(?:люблю тебя|ты мне нравишься|ты классная|ты лучшая)\b")
INSULT_RE = re.compile(r"\b(?:дура|тупая|глупая|отстой|ненавижу|бесишь|тупица)\b")
PRAISE_RE = re.compile(r"\b(?:ты красивая|ты умная|ты классная|молодец|умница)\b")
NAME_CALL_RE = re.compile(r"(?:тебя\s+зовут|тво[её]\s+имя)\s+([a-zA-Zа-яА-ЯёЁ]{2,20})")

OWN_NAMES = {"ника", "nika", "ник", "nik", "никочка", "нике", "нику", "никой"}

# Если человек ждёт уточнения («в каком городе?»), но вместо ответа явно
# начинает новую команду — уточнение отменяем, команду выполняем.
NEW_COMMAND_PREFIXES = (
    "открой", "запусти", "включи", "позвони", "набери", "напиши смс",
    "отправь сообщение", "засеки", "таймер", "будильник", "напомни",
    "погода", "фонарик", "заряд", "громче", "тише", "без звука",
    "какие сети", "какой пароль", "найди", "загугли", "поищи",
    "что такое", "что ты умеешь", "сколько времени", "какое сегодня",
    "мои заметки", "мои напоминания", "выключи",
)


def format_phone(number):
    digits = re.sub(r"\D", "", number or "")
    if len(digits) == 11 and digits.startswith("7"):
        return "+7 %s %s-%s-%s" % (digits[1:4], digits[4:7], digits[7:9], digits[9:11])
    if len(digits) == 10:
        return "+7 %s %s-%s-%s" % (digits[0:3], digits[3:6], digits[6:8], digits[8:10])
    return number


def _strip_time_words(text):
    """Убирает «через 20 минут» / «в 18:30» из текста напоминания."""
    t = text or ""
    t = re.sub(r"\bчерез\s+([0-9]+|[а-я]+)(?:\s+([0-9]+|[а-я]+))?\s*"
               r"(минут[а-я]*|мин|час[а-я]*|ч|секунд[а-я]*|сек|с)\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:в|к|на)\s+\d{1,2}(?:[:.]\d{2})?\s*(?:утра|дня|вечера|ночи)?\b", " ",
               t, flags=re.IGNORECASE)
    t = re.sub(r"\b(?:утра|дня|вечера|ночи)\b", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" .,!?-—")
    return t


class Engine:
    """Обрабатывает одну фразу человека и возвращает Reply."""

    def __init__(self, bridge, store, persona=None, weather=None,
                 now: Optional[Callable[[], float]] = None,
                 status_cb: Optional[Callable[[str], None]] = None):
        self.b = bridge
        self.s = store
        self.p = persona or Persona(store)
        self.w = weather or Weather()
        self.now = now or time.time
        self.status_cb = status_cb
        self.pending: Optional[Dict[str, Any]] = None
        self.last_intent = ""
        self.torch_on = False
        self._deferred: List[Callable[[], Optional[Reply]]] = []
        self._nested = False
        self._question = False
        self.session_started = self.now()

    # ------------------------------------------------------------------
    #  Служебное
    # ------------------------------------------------------------------
    def _status(self, text):
        if self.status_cb:
            try:
                self.status_cb(text)
            except Exception:
                pass

    def _defer(self, fn):
        self._deferred.append(fn)

    def take_deferred(self):
        items, self._deferred = self._deferred, []
        return items

    def _request(self, permission, then):
        """Просит право и откладывает действие до ответа системы."""
        def done(ok):
            if ok:
                self._defer(then)
            else:
                self._defer(lambda: Reply(
                    "без доступа не получится. включи его в настройках телефона — "
                    "и скажи ещё раз."))
        try:
            res = self.b.request_permissions([permission], done)
        except Exception:
            return Reply("не смогла попросить доступ. включи его в настройках вручную.")
        if res and not res.ok and "права" not in (res.message or ""):
            return Reply(res.message or "не смогла получить доступ.")
        return None

    # ------------------------------------------------------------------
    #  Главный вход
    # ------------------------------------------------------------------
    def respond(self, raw):
        text = nlp.strip_punct(raw)
        self._question = "?" in (raw or "")
        if not text:
            return Reply(self.p.pick(["напиши что-нибудь)", "я тут, слушаю."]),
                         chips=DEFAULT_CHIPS, intent="empty")

        self.s.touch()

        # ждём ответа на уточняющий вопрос
        if self.pending:
            reply = self._handle_pending(text)
            if reply is not None:
                answer = self._finish(reply, "pending")
                self._remember(text, answer)
                return answer

        clean = self._prepare(text)
        t = nlp.fold(clean)

        if not t:
            return Reply("напиши что-нибудь)", chips=DEFAULT_CHIPS)

        # «тебя зовут Петя» — она немного обижается
        name_reply = self._name_guard(t)
        if name_reply:
            answer = self._finish(name_reply, "name")
            self._remember(text, answer)
            return answer

        parts = nlp.split_multi(clean)
        if len(parts) > 1:
            self._nested = True
            texts = []
            try:
                for part in parts:
                    sub = self.respond(part)
                    if sub.text and sub.text not in texts:
                        texts.append(sub.text)
            finally:
                self._nested = False
            if texts:
                answer = Reply(" ".join(texts), chips=AFTER_COMMAND_CHIPS, intent="multi")
                self._remember(text, answer)
                return answer

        answer = self._respond_one(clean)
        self._remember(text, answer)
        return answer

    def _remember(self, user_text, reply):
        if self._nested or not reply:
            return
        try:
            self.s.push_dialog(user_text, reply.text)
        except Exception:
            pass

    def _respond_one(self, clean):
        t = nlp.fold(clean)
        handlers = (
            self._h_learn,
            self._h_meta,
            self._h_timer,
            self._h_alarm,
            self._h_reminder,
            self._h_call,
            self._h_sms,
            self._h_settings,
            self._h_torch,
            self._h_volume,
            self._h_battery,
            self._h_wifi,
            self._h_weather,
            self._h_music,
            self._h_video,
            self._h_time,
            self._h_date,
            self._h_identity,
            self._h_help,
            self._h_social,
            self._h_facts,
            self._h_memory,
            self._h_notes,
            self._h_open,
            self._h_search,
        )
        for handler in handlers:
            try:
                reply = handler(clean, t)
            except Exception as exc:  # один сломанный обработчик не роняет всё
                print("[Nika/engine] %s: %s" % (handler.__name__, exc))
                continue
            if reply is not None:
                return self._finish(reply, handler.__name__.replace("_h_", ""))
        return self._finish(self._fallback(clean, t), "fallback")

    # ------------------------------------------------------------------
    #  Подготовка фразы
    # ------------------------------------------------------------------
    def _prepare(self, text):
        clean = self._strip_address(text)
        clean = nlp.fix_typos(clean)
        clean = self._apply_learned(clean)
        return clean

    def _strip_address(self, text):
        names = "|".join(re.escape(n) for n in OWN_NAMES)
        return re.sub(r"^(?:%s)[\s,!.]+" % names, "", text or "",
                      flags=re.IGNORECASE).strip() or text

    def _apply_learned(self, text):
        learned = self.s.get("learned", {}) or {}
        low = (text or "").lower()
        best = None
        for key in learned:
            if low.startswith(key.lower()) and len(key) > 3:
                if best is None or len(key) > len(best):
                    best = key
        if best:
            rest = text[len(best):].strip()
            return (learned[best] + " " + rest).strip()
        return text

    def _name_guard(self, t):
        m = NAME_CALL_RE.search(t)
        if not m:
            return None
        name = m.group(1).strip().lower()
        if name in OWN_NAMES:
            return None
        if len(name) < 3:
            return None
        return Reply(self.p.pick([
            "я вообще-то Nika) но можно просто Ника.",
            "это не я. я Nika, если что)",
            "не-а, меня зовут Nika. запомни, пожалуйста)",
        ]), chips=DEFAULT_CHIPS)

    def _finish(self, reply, intent=""):
        if reply is None:
            reply = Reply("")
        if isinstance(reply, str):
            reply = Reply(reply)
        reply.text = (reply.text or "").strip()
        if not reply.chips:
            reply.chips = DEFAULT_CHIPS
        reply.intent = reply.intent or intent
        self.last_intent = reply.intent
        return reply

    # ------------------------------------------------------------------
    #  Ожидание уточнения
    # ------------------------------------------------------------------
    def _handle_pending(self, text):
        pending = self.pending
        kind = pending.get("kind")
        t = nlp.fold(text)
        value = nlp.strip_punct(text)

        # вместо ответа на уточнение человек начал новую команду
        if t.startswith(NEW_COMMAND_PREFIXES):
            self.pending = None
            return None

        def ask_again(prompt, chips=None):
            return Reply(prompt, chips=chips or DEFAULT_CHIPS)

        # ---- выбор контакта ----
        if kind == "contact_choice":
            options = pending.get("options") or []
            chosen = None
            digits = re.findall(r"\d", t)
            if len(digits) == 1 and 1 <= int(digits[0]) <= len(options):
                chosen = options[int(digits[0]) - 1]
            if chosen is None and len(digits) >= 4:
                tail = "".join(digits)[-10:]
                for option in options:
                    if re.sub(r"\D", "", option["number"])[-10:] == tail:
                        chosen = option
                        break
            if chosen is None:
                for option in options:
                    if nlp.fold(option.get("label") or option["name"]) == t:
                        chosen = option
                        break
            if chosen is None:
                words = set(nlp.tokens(t))
                for option in options:
                    name_words = set(nlp.tokens(option["name"]))
                    if words & name_words or nlp.stem_ru(option["name"]) == nlp.stem_ru(value):
                        chosen = option
                        break
            if chosen is None:
                best, score = nlp.fuzzy_best(value, [(o["name"], [o["name"]]) for o in options])
                if best and score >= 0.7:
                    for option in options:
                        if option["name"] == best:
                            chosen = option
                            break
            if chosen is None:
                names = ", ".join(o.get("label") or o["name"] for o in options[:6])
                return ask_again("не поняла, кому. вот варианты: %s" % names,
                                 chips=[o.get("label") or o["name"] for o in options[:6]])
            self.pending = None
            return self._dial_number(chosen["number"], chosen["name"])

        # ---- кому позвонить ----
        if kind == "call_name":
            self.pending = None
            return self._dial_target(value)

        # ---- текст смс ----
        if kind == "sms_text":
            number = pending.get("number")
            name = pending.get("name") or ""
            self.pending = None
            res = self.b.send_sms(number, value)
            if res.ok:
                return Reply("открыла сообщение%s — текст уже вставлен." %
                             ((" для «" + name + "»") if name else ""),
                             chips=AFTER_COMMAND_CHIPS)
            return Reply(res.message or "не смогла открыть сообщения.",
                         chips=AFTER_COMMAND_CHIPS)

        # ---- город для погоды ----
        if kind == "weather_city":
            self.pending = None
            return self._weather_reply(value)

        # ---- сеть для wi-fi ----
        if kind == "wifi_ssid":
            self.pending = None
            return self._wifi_password_reply(value)

        # ---- длительность таймера ----
        if kind == "timer_duration":
            seconds = nlp.parse_duration(text)
            if not seconds:
                return ask_again("на сколько? можно цифрой: 5, 10, 25 минут.",
                                 chips=["5 минут", "10 минут", "25 минут"])
            self.pending = None
            return self._start_timer(seconds)

        # ---- время будильника ----
        if kind == "alarm_time":
            clock = nlp.parse_clock(text)
            if not clock:
                return ask_again("на какое время? например, 7:30.",
                                 chips=["7:00", "8:00", "9:00"])
            self.pending = None
            return self._set_alarm(clock[0], clock[1])

        # ---- время напоминания ----
        if kind == "reminder_time":
            seconds = nlp.parse_duration(text)
            clock = nlp.parse_clock(text) if not seconds else None
            if not seconds and not clock:
                return ask_again("через сколько напомнить?",
                                 chips=["через 10 минут", "через час", "в 18:00"])
            self.pending = None
            return self._create_reminder(pending.get("text", ""), seconds, clock)

        self.pending = None
        return None

    # ------------------------------------------------------------------
    #  Факты и самообучение
    # ------------------------------------------------------------------
    def _h_learn(self, clean, t):
        m = LEARN_RE.match(clean)
        if not m:
            return None
        key = m.group(1).strip().lower()
        value = m.group(2).strip()
        if not key or not value:
            return None
        learned = self.s.get("learned", {}) or {}
        learned[key] = value
        self.s.set("learned", learned)
        return Reply(self.p.pick([
            "запомнила: «%s» = «%s»." % (key, value),
            "ок, теперь «%s» буду понимать как «%s»." % (key, value),
            "выучила новую фразу)",
        ]), chips=["проверь", "что ты не знаешь"])

    def _h_meta(self, clean, t):
        if any(w in t for w in ("что ты не знаешь", "чему надо научить", "чего не поняла")):
            unknown = self.s.get("unknown", []) or []
            if not unknown:
                return Reply("пока всё понимаю) нечего учить.")
            top = unknown[-8:][::-1]
            return Reply("вот что я недавно не поняла:\n" +
                         "\n".join("• %s" % p for p in top) +
                         "\nскажи «научись: <фраза> = <что делать>», и я запомню.",
                         chips=["забудь непонимание"])
        if any(w in t for w in ("забудь непонимание", "очисти непонимание",
                                "забудь что не знаешь")):
            self.s.set("unknown", [])
            return Reply("ок, очистила список непониманий.")
        if any(w in t for w in ("что ты обо мне помнишь", "что помнишь обо мне",
                                "что ты знаешь обо мне")):
            return Reply(self.p.facts_summary(), chips=["запомни, что ", "мои заметки"])
        if any(w in t for w in ("забудь обо мне", "удали мои данные", "сотри память",
                                "забудь всё")):
            self.s.set("facts", {})
            self.s.set("dialog", [])
            self.s.set("notes", [])
            self.s.set("memory", {})
            self.s.save()
            return Reply("готово, стёрла всё, что помнила о тебе. начнём с чистого листа.",
                         chips=DEFAULT_CHIPS)
        return None

    def _h_facts(self, clean, t):
        if any(w in t for w in ("как меня зовут", "моё имя", "мое имя", "кто я")):
            name = self.s.fact("name")
            if not name:
                return Reply("ты мне ещё не сказал) скажи «меня зовут ...» — и запомню.",
                             chips=["меня зовут "])
            return Reply(self.p.pick([
                "тебя зовут %s. я помню)" % name,
                "%s, конечно. такое не забывается." % name,
            ]))
        if any(w in t for w in ("сколько мне лет", "мой возраст")):
            age = self.s.fact("age")
            if not age:
                return Reply("не знаю) скажи «мне N лет», и я запомню.")
            return Reply("тебе %s. записала однажды и помню." % age)

        if not any(w in t for w in ("меня зовут", "мне ", "я живу", "я из", "я люблю",
                                    "я обожаю", "у меня есть", "я работаю", "я учусь")):
            return None
        # не перебиваем просьбы и команды
        if any(t.startswith(v) for v in ("позвони", "открой", "найди", "включи",
                                         "напомни", "засеки", "будильник", "погода")):
            return None
        found = self.p.learn_facts(clean)
        ack = self.p.fact_ack(found)
        if not ack:
            likes = (self.s.get("facts", {}) or {}).get("likes") or []
            if ("люблю" in t or "обожаю" in t) and likes:
                return Reply("запомнила: любишь %s. а что ещё?" % likes[-1],
                             chips=["что ты обо мне помнишь"])
            if "меня зовут" in t and self.s.fact("name"):
                return Reply("мы уже знакомы) ты %s." % self.s.fact("name"),
                             chips=["что ты обо мне помнишь"])
            ack = self.p.pick(["запомнила)", "ок, буду знать)"])
        return Reply(ack + " а что ещё расскажешь?", chips=["что ты обо мне помнишь"])

    # ------------------------------------------------------------------
    #  Время: таймер, будильник, напоминание
    # ------------------------------------------------------------------
    def _h_timer(self, clean, t):
        if not TIMER_RE.match(t):
            return None
        if "будильник" in t:
            return None
        rest = TIMER_RE.match(t).group(1)
        seconds = nlp.parse_duration(rest or t)
        if not seconds:
            self.pending = {"kind": "timer_duration"}
            return Reply("на сколько засечь?", chips=["5 минут", "10 минут", "25 минут"])
        return self._start_timer(seconds)

    def _start_timer(self, seconds):
        label = nlp.human_duration(seconds)
        self._status("засекаю %s" % label)
        return Reply(
            self.p.pick([
                "засекла %s. цифры будут сверху." % label,
                "таймер на %s пошёл. я рядом." % label,
                "ок, %s. как выйдет время — скажу." % label,
            ]),
            actions=[{"type": "timer", "seconds": seconds, "label": label}],
            chips=["останови таймер", "спасибо"],
        )

    def _h_alarm(self, clean, t):
        m = ALARM_RE.match(t)
        if not m:
            return None
        rest = m.group(1)
        clock = nlp.parse_clock(rest or t)
        if not clock:
            self.pending = {"kind": "alarm_time"}
            return Reply("на какое время поставить будильник?", chips=["7:00", "8:00", "9:00"])
        return self._set_alarm(clock[0], clock[1])

    def _set_alarm(self, hour, minute):
        label = "Nika"
        res = self.b.set_alarm(hour, minute, label)
        clock = nlp.human_clock(hour, minute)
        if res.ok:
            return Reply(self.p.pick([
                "будильник на %s. не проспи)" % clock,
                "поставила на %s. если что — поправь в часах." % clock,
            ]), chips=["спасибо", "заряд"])
        return Reply(res.message or "не смогла открыть будильник.",
                     chips=["открой часы"])

    def _h_reminder(self, clean, t):
        m = REMIND_RE.match(t)
        if not m:
            return None
        rest = m.group(1).strip()
        if not rest:
            self.pending = {"kind": "reminder_time", "text": ""}
            return Reply("о чём напомнить и когда?", chips=["через 10 минут", "через час"])
        seconds = nlp.parse_duration(rest)
        clock = nlp.parse_clock(rest) if not seconds else None
        text = _strip_time_words(rest)
        if not seconds and not clock:
            self.pending = {"kind": "reminder_time", "text": text or rest}
            return Reply("когда напомнить про «%s»?" % (text or rest),
                         chips=["через 10 минут", "через час", "в 18:00"])
        return self._create_reminder(text, seconds, clock)

    def _create_reminder(self, text, seconds, clock):
        now = self.now()
        if seconds:
            at = now + seconds
        else:
            hour, minute = clock
            stamp = time.localtime(now)
            at = time.mktime((stamp.tm_year, stamp.tm_mon, stamp.tm_mday,
                              hour, minute, 0, 0, 0, -1))
            if at <= now:
                at += 86400
        text = text or "напоминание"
        self.s.add_reminder(at, text)
        self.s.save()
        when = time.strftime("%H:%M", time.localtime(at))
        if at - now > 20 * 3600:
            when = time.strftime("%d.%m в %H:%M", time.localtime(at))
        return Reply(self.p.pick([
            "напомню в %s: %s." % (when, text),
            "записала. в %s напомню про «%s»." % (when, text),
        ]), actions=[{"type": "reminder", "at": at, "text": text}],
            chips=["мои напоминания", "спасибо"])

    # ------------------------------------------------------------------
    #  Звонки
    # ------------------------------------------------------------------
    def _h_call(self, clean, t):
        # режим звонка: сразу набирать или только открывать номер
        if any(w in t for w in ("звони сразу", "сразу звони", "сразу набирай",
                                "звонить сразу", "набирай сразу")):
            self.s.set_pref("instant_call", True)
            if self.b.is_android and not self.b.has_permission("CALL_PHONE"):
                self._request("CALL_PHONE", lambda: None)
            return Reply("хорошо, буду сразу набирать. если что — скажи "
                         "«показывай номер».", chips=["позвони маме", "спасибо"])
        if any(w in t for w in ("показывай номер", "не звони сразу", "не набирай сразу",
                                "спрашивай перед звонком", "только набирай")):
            self.s.set_pref("instant_call", False)
            return Reply("ок, буду открывать номер — нажмёшь зелёную кнопку сам.",
                         chips=["спасибо"])

        m = CALL_RE.match(t)
        if not m:
            return None
        target = nlp.strip_punct(m.group(1))
        if not target:
            self.pending = {"kind": "call_name"}
            return Reply("кому позвонить?", chips=self._contact_chips())
        return self._dial_target(target)

    def _contact_chips(self, limit=4):
        try:
            contacts = self.b.contacts()
        except Exception:
            contacts = []
        names = []
        for contact in contacts:
            if contact.name and contact.name not in names:
                names.append(contact.name)
            if len(names) >= limit:
                break
        if names:
            return names
        return ["маме", "папе", "112"]

    def _dial_target(self, target):
        target = nlp.strip_punct(target)
        t = nlp.fold(target)

        # экстренные службы
        emergency = catalog.emergency_number(t)
        if emergency:
            return self._dial_number(emergency, "экстренную службу")

        digits = re.findall(r"\d", target)
        letters = re.findall(r"[a-zа-я]", t)
        if len(digits) >= 3 and not letters:
            number = "".join(digits)
            if len(number) > 4:
                number = nlp.normalize_phone(number) or ("+" + number)
            return self._dial_number(number, "")

        if self.b.can_contacts and not self.b.has_permission("READ_CONTACTS"):
            failure = self._request("READ_CONTACTS", lambda: self._dial_target(target))
            if failure:
                return failure
            return Reply("сейчас спрошу доступ к контактам — разреши, и я наберу "
                         "«%s»." % target, chips=DEFAULT_CHIPS)

        matches = self._match_contacts(target)
        if not matches:
            contacts = self.b.contacts()
            if not contacts:
                return Reply("в контактах пусто. назови номер — наберу.",
                             chips=["позвони 112"])
            return Reply("в контактах не нашла «%s». под каким именем он записан?" % target,
                         chips=[c.name for c in contacts[:4]])
        if len(matches) == 1:
            contact = matches[0]
            return self._dial_number(contact.number, contact.name)

        options = []
        for contact in matches[:6]:
            label = contact.name
            twins = sum(1 for other in matches
                        if nlp.fold(other.name) == nlp.fold(contact.name))
            if twins > 1:
                label = "%s · %s" % (contact.name, format_phone(contact.number))
            options.append({"name": contact.name, "number": contact.number,
                            "label": label})
        self.pending = {"kind": "contact_choice", "options": options}
        names = ", ".join(o["label"] for o in options)
        return Reply("нашла несколько: %s. кому звонить?" % names,
                     chips=[o["label"] for o in options])

    def _match_contacts(self, query):
        try:
            contacts = self.b.contacts()
        except Exception:
            contacts = []
        if not contacts:
            return []
        q = nlp.fold(query)
        q = re.sub(r"^(?:в|на|к|по)\s+", "", q)
        if not q:
            return []
        stem_q = nlp.stem_ru(q)
        scored = []
        for contact in contacts:
            name = nlp.fold(contact.name)
            if not name:
                continue
            stem_name = nlp.stem_ru(name)
            score = 0.0
            if name == q:
                score = 1.0
            elif stem_name == stem_q:
                score = 0.96
            elif name.startswith(q) or q.startswith(name):
                score = 0.86
            elif stem_name.startswith(stem_q) or stem_q.startswith(stem_name):
                score = 0.8
            elif q in name:
                score = 0.72
            elif nlp.stem_ru(name.split()[0]) == stem_q:
                score = 0.78
            else:
                score = nlp.ratio(name, q) * 0.65
            if score >= 0.6:
                scored.append((score, contact))
        if not scored:
            return []
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][0]
        result = []
        seen = set()
        for score, contact in scored:
            if score < best - 0.12:
                continue
            key = re.sub(r"\D", "", contact.number)[-10:]
            if key in seen:
                continue
            seen.add(key)
            result.append(contact)
        return result[:6]

    def _dial_number(self, number, name=""):
        if not number:
            return Reply("не поняла номер.")
        direct = bool(self.s.pref("instant_call", False))
        res = self.b.dial(number, direct=direct)
        pretty = format_phone(number)
        if not res.ok:
            return Reply(res.message or "не смогла набрать.",
                         chips=["позвони 112", "что ты умеешь"])
        if res.message == "звоню":
            return Reply("звоню%s — %s." % ((" " + name) if name else "", pretty),
                         chips=["спасибо"])
        if name:
            return Reply(self.p.pick([
                "набираю «%s» — %s. нажми зелёную кнопку)" % (name, pretty),
                "готово: «%s», %s. осталось позвонить." % (name, pretty),
            ]), chips=["спасибо"])
        return Reply("набрала %s. жми вызов." % pretty, chips=["спасибо"])

    # ------------------------------------------------------------------
    #  Смс
    # ------------------------------------------------------------------
    def _h_sms(self, clean, t):
        m = SMS_RE.match(t)
        if not m:
            return None
        rest = nlp.strip_punct(m.group(1))
        if not rest:
            self.pending = {"kind": "call_name"}
            return Reply("кому написать?", chips=self._contact_chips())

        if self.b.can_contacts and not self.b.has_permission("READ_CONTACTS"):
            failure = self._request("READ_CONTACTS", lambda: self._h_sms(clean, t))
            if failure:
                return failure
            return Reply("сейчас спрошу доступ к контактам — разреши, и я сразу "
                         "открою сообщение.", chips=DEFAULT_CHIPS)

        contact, text = self._split_contact_text(rest)
        if contact is None:
            return Reply("не нашла такого контакта. назови имя или номер.",
                         chips=self._contact_chips())
        if not text:
            self.pending = {"kind": "sms_text", "number": contact.number,
                            "name": contact.name}
            return Reply("что написать %s?" % contact.name)

        res = self.b.send_sms(contact.number, text)
        if res.ok:
            return Reply("открыла сообщение для «%s» — текст уже вставлен." % contact.name,
                         chips=AFTER_COMMAND_CHIPS)
        return Reply(res.message or "не смогла открыть сообщения.",
                     chips=AFTER_COMMAND_CHIPS)

    def _split_contact_text(self, rest):
        """«маме я скоро буду» -> (контакт, «я скоро буду»)."""
        divider = re.split(r"\s*[:,—]\s*", rest, maxsplit=1)
        if len(divider) == 2:
            contact_part, text = divider[0], divider[1]
            contact = self._resolve_one_contact(contact_part)
            if contact:
                return contact, text

        words = rest.split()
        for count in range(1, min(4, len(words)) + 1):
            candidate = " ".join(words[:count])
            contact = self._resolve_one_contact(candidate)
            if contact:
                return contact, " ".join(words[count:])

        matches = self._match_contacts(rest)
        if matches:
            return matches[0], ""
        return None, ""

    def _resolve_one_contact(self, text):
        matches = self._match_contacts(text)
        if len(matches) == 1:
            return matches[0]
        if matches:
            return matches[0]
        return None

    # ------------------------------------------------------------------
    #  Настройки, фонарик, звук, заряд
    # ------------------------------------------------------------------
    def _h_settings(self, clean, t):
        m = SETTINGS_RE.match(t)
        if not m:
            return None
        tail = m.group(1)
        page = ""
        if "вайф" in tail or "wi-fi" in tail or "wi fi" in tail or "wifi" in tail or "сет" in tail:
            page = "wifi"
        elif "приложен" in tail:
            page = "apps"
        elif "блютуз" in tail or "bluetooth" in tail:
            page = "bluetooth"
        elif "звук" in tail:
            page = "sound"
        elif "экран" in tail or "дисплей" in tail:
            page = "display"
        elif "батаре" in tail or "заряд" in tail:
            page = "battery"
        elif "геолокац" in tail or "местополож" in tail:
            page = "location"

        res = self.b.open_settings(page)
        if not res.ok:
            return Reply("не смогла открыть настройки: %s" % (res.message or "нет доступа"),
                         chips=["что ты умеешь"])
        if page == "wifi":
            return Reply("открыла настройки wi-fi. тут можно посмотреть сеть и "
                         "поделиться паролем через QR.", chips=["какой пароль от вайфая"])
        return Reply("открыла настройки.", chips=AFTER_COMMAND_CHIPS)

    def _h_torch(self, clean, t):
        if not any(w in t for w in ("фонарик", "фонарь", "вспышк", "подсветк")):
            return None
        if any(w in t for w in ("выключи", "погаси", "отключи", "не надо")):
            res = self.b.torch(False)
            self.torch_on = False
            return Reply("выключила фонарик." if res.ok else
                         (res.message or "не получилось выключить."),
                         chips=["фонарик"])
        res = self.b.torch(True)
        self.torch_on = True
        if res.ok:
            return Reply(self.p.pick(["включила фонарик.", "фонарик горит)"]),
                         chips=["выключи фонарик"])
        return Reply(res.message or "фонарик не поддался.", chips=DEFAULT_CHIPS)

    def _h_volume(self, clean, t):
        direction = None
        if any(w in t for w in ("громче", "прибавь", "погромче", "увеличь звук",
                                "сделай громче")):
            direction = "up"
        elif any(w in t for w in ("тише", "убавь", "потише", "уменьши звук",
                                  "сделай тише")):
            direction = "down"
        elif any(w in t for w in ("без звука", "выключи звук", "на беззвучный",
                                  "беззвучн", "mute")):
            direction = "mute"
        elif any(w in t for w in ("на полную", "максимум звука", "громкость на максимум")):
            direction = "max"
        if not direction:
            return None
        res = self.b.volume(direction)
        if not res.ok:
            return Reply(res.message or "не смогла изменить звук.", chips=DEFAULT_CHIPS)
        if direction == "mute":
            return Reply("звук выключен.", chips=["громче"])
        return Reply("теперь %s." % res.message, chips=["громче", "тише"])

    def _h_battery(self, clean, t):
        if not any(w in t for w in ("заряд", "батаре", "аккумулятор", "сколько процентов")):
            return None
        self._status("смотрю заряд")
        data = self.b.battery()
        if not data or "percent" not in data:
            return Reply("не получилось узнать заряд — телефон не отдаёт данные.",
                         chips=DEFAULT_CHIPS)
        percent = int(data.get("percent", 0))
        charging = bool(data.get("charging"))
        if charging:
            return Reply("заряд %d%%, и он заряжается. хорошо." % percent,
                         chips=["спасибо"])
        if percent <= 15:
            return Reply(self.p.pick([
                "заряд %d%%. пора к розетке, а то я волнуюсь." % percent,
                "всего %d%%. найди зарядку, пожалуйста." % percent,
            ]), chips=["фонарик", "спасибо"])
        if percent <= 40:
            return Reply("заряд %d%%. ещё живём, но зарядку лучше не терять." % percent,
                         chips=["спасибо"])
        return Reply("заряд %d%%. всё в порядке." % percent, chips=["спасибо"])

    # ------------------------------------------------------------------
    #  Wi-Fi
    # ------------------------------------------------------------------
    def _h_wifi(self, clean, t):
        has_wifi_word = any(w in t for w in ("вайфай", "вай-фай", "вай фай", "wifi",
                                             "wi-fi", "wi fi", "вайфа"))
        wants_password = ("парол" in t or bool(re.search(r"(?<![а-яa-z])ключ", t)))
        wants_saved = any(w in t for w in ("какие сети", "сохраненн", "сохранённ",
                                           "мои сети", "список сетей", "все сети",
                                           "всех сетей", "какие вайфаи"))
        if wants_saved and (has_wifi_word or "сет" in t):
            return self._wifi_list_reply()
        if wants_password and (has_wifi_word or "сет" in t):
            ssid = self._extract_ssid(clean) or ""
            return self._wifi_password_reply(ssid)
        if has_wifi_word and any(w in t for w in ("включи", "выключи", "переключи",
                                                  "отключи", "вруби", "подключи")):
            self.b.open_settings("wifi")
            return Reply("переключать wi-fi приложениям Android запрещает, поэтому "
                         "открыла настройки — тут один переключатель.",
                         chips=["какой пароль от вайфая"])
        if has_wifi_word:
            return self._wifi_info_reply()
        return None

    @staticmethod
    def _extract_ssid(clean):
        pattern = (r'(?:сеть|сети|сетью|вай[\s\-]?фа\w*|wi[\s\-]?fi|wifi)'
                   r'\s+["«]?([^\s"»,.!?]+)')
        m = re.search(pattern, clean, re.IGNORECASE)
        if not m:
            return ""
        value = m.group(1).strip()
        stop = {"от", "для", "этой", "этого", "моей", "моего", "текущей", "сейчас",
                "пожалуйста", "вайфая", "вай-фая", "wifi", "wi-fi", "сеть"}
        if value.lower() in stop or value.lower().startswith("вайф"):
            return ""
        return value

    def _wifi_info_reply(self):
        if not self.b.is_android:
            info = self.b.wifi_info() or {}
            if info.get("ssid"):
                return Reply("ты подключён к сети «%s»." % info["ssid"],
                             chips=["какой пароль от вайфая"])
            return Reply("wi-fi смотрю только на телефоне. тут могу открыть настройки "
                         "сети, если хочешь.", chips=DEFAULT_CHIPS)
        self._status("смотрю сеть")
        info = self.b.wifi_info() or {}
        ssid = info.get("ssid")
        if not ssid:
            return Reply(
                "не вижу, к какой сети подключён. либо wi-fi выключен, либо Android "
                "не даёт имя сети без доступа к геолокации.\n"
                "включи wi-fi — и спроси ещё раз.", chips=["открой настройки вайфая"])
        lines = ["ты в сети «%s»." % ssid]
        rssi = info.get("rssi")
        if isinstance(rssi, int):
            if rssi >= -55:
                lines.append("сигнал отличный.")
            elif rssi >= -70:
                lines.append("сигнал нормальный.")
            else:
                lines.append("сигнал слабоват — подойди к роутеру.")
        if info.get("ip"):
            lines.append("ip %s." % info["ip"])
        lines.append("пароль просто так не покажу — Android его прячет. спроси "
                     "«какой пароль от вайфая», и я попробую.")
        return Reply("\n".join(lines),
                     chips=["какой пароль от вайфая", "какие сети"])

    def _wifi_list_reply(self):
        self._status("читаю сохранённые сети")
        names = self.b.wifi_saved() or []
        info = self.b.wifi_info() or {}
        if not names:
            if not self.b.is_android:
                return Reply("на компьютере не нашла сохранённых сетей.",
                             chips=DEFAULT_CHIPS)
            return Reply(
                "список сохранённых сетей Android показывает только системным "
                "приложениям. но текущую сеть вижу: %s." %
                (info.get("ssid") or "не вижу"),
                chips=["какой пароль от вайфая"])
        current = info.get("ssid")
        lines = ["сохранённые сети:"]
        for name in names[:12]:
            mark = " (сейчас)" if current and name.lower() == current.lower() else ""
            lines.append("• %s%s" % (name, mark))
        lines.append("пароли к ним без root не отдаются. про конкретную сеть спроси "
                     "«пароль от вайфая <название>».")
        return Reply("\n".join(lines),
                     chips=["какой пароль от вайфая"])

    def _wifi_password_reply(self, ssid):
        ssid = (ssid or "").strip().strip('"')
        self._status("ищу пароль")
        if not self.b.is_android:
            info = self.b.wifi_info() or {}
            ssid = ssid or info.get("ssid", "")
            if not ssid:
                return Reply("не вижу, к какой сети ты подключён.",
                             chips=["какие сети"])
        if not ssid:
            info = self.b.wifi_info() or {}
            ssid = info.get("ssid") or ""
            if not ssid:
                names = self.b.wifi_saved() or []
                if len(names) == 1:
                    ssid = names[0]
                elif names:
                    self.pending = {"kind": "wifi_ssid"}
                    return Reply("не вижу текущую сеть. скажи название: %s" %
                                 ", ".join(names[:8]),
                                 chips=names[:6])
                else:
                    return Reply(
                        "не вижу ни одной сети. включи wi-fi и спроси ещё раз.",
                        chips=["открой настройки вайфая"])

        password, how = self.b.wifi_password(ssid)
        if password:
            note = "" if how == "root" else ""
            return Reply("сеть «%s»\nпароль: %s%s" % (ssid, password, note),
                         chips=["какие сети", "спасибо"])
        if how == "" and self.b.is_android:
            return Reply(
                "сеть «%s» сохранена, но Android не отдаёт пароль приложениям — "
                "это защита системы, не моя лень.\n"
                "как посмотреть самой:\n"
                "• настройки → wi-fi → нажми на сеть → «поделиться» — там QR и пароль\n"
                "• на роутере часто есть наклейка с заводским паролем\n"
                "• если роутер под рукой — кнопка WPS подключает без пароля\n"
                "• на телефоне с root я могу прочитать пароль сама — скажи, если он есть." %
                ssid,
                chips=["открой настройки вайфая", "какие сети"])
        return Reply("сеть «%s» без пароля или пароль прочитать не удалось." % ssid,
                     chips=["какие сети"])

    # ------------------------------------------------------------------
    #  Погода
    # ------------------------------------------------------------------
    def _h_weather(self, clean, t):
        m = WEATHER_RE.match(t)
        if not m:
            return None
        city = nlp.strip_punct(m.group(1))
        city = re.sub(r"^(?:в|во|на|для|по)\s+", "", city)
        if city.lower() in ("завтра", "сегодня", "послезавтра", "сейчас", "на завтра",
                            "на сегодня"):
            city = ""
        if not city:
            city = self.s.pref("city", "") or self.s.fact("city") or ""
        if not city:
            self.pending = {"kind": "weather_city"}
            return Reply("в каком городе смотреть погоду?",
                         chips=["москва", "санкт-петербург"])
        return self._weather_reply(city)

    def _weather_reply(self, city):
        self._status("смотрю погоду в %s" % city)
        data = None
        try:
            data = self.w.report(city)
        except Exception:
            data = None
        if not data:
            return Reply("не смогла достучаться до погоды. интернет точно есть?",
                         chips=["погода в москве"])
        self.s.set_pref("city", data.get("city") or city)
        text = self.w.format_report(data)
        flavor = self._weather_flavor(data)
        if flavor:
            text += "\n" + flavor
        return Reply(text, chips=["погода завтра", "спасибо"])

    @staticmethod
    def _weather_flavor(data):
        desc = (data.get("desc") or "").lower()
        if any(w in desc for w in ("дожд", "ливень", "морось")):
            return "возьми зонт, если выходишь."
        if "гроза" in desc:
            return "лучше переждать дома."
        if "снег" in desc:
            return "скользко — аккуратнее."
        temp = data.get("temp")
        try:
            temp = float(temp)
        except (TypeError, ValueError):
            temp = None
        if temp is not None and temp <= -5:
            return "оденься потеплее, серьёзно."
        if temp is not None and temp >= 27:
            return "пей больше воды."
        return ""

    # ------------------------------------------------------------------
    #  Музыка и видео
    # ------------------------------------------------------------------
    def _h_music(self, clean, t):
        m = MUSIC_RE.match(t)
        if not m:
            return None
        query = nlp.strip_punct(m.group(1))
        query = re.sub(r"^(?:пожалуйста|плиз|мне|нам)\s+", "", query)
        self._status("включаю музыку")
        res = self.b.play_media(query, video=False)
        if res.ok:
            source = (res.data or {}).get("source")
            if source == "local":
                title = (res.data or {}).get("title") or query
                return Reply("нашла «%s» — включаю." % title, chips=["спасибо"])
            return Reply("в памяти пусто, открыла плеер%s." %
                         ((" с поиском «%s»" % query) if query else ""),
                         chips=["спасибо"])
        return Reply(res.message or "не смогла включить музыку.",
                     chips=["открой ютуб"])

    def _h_video(self, clean, t):
        m = VIDEO_RE.match(t)
        if not m:
            return None
        query = nlp.strip_punct(m.group(1))
        self._status("включаю видео")
        res = self.b.play_media(query, video=True)
        if res.ok:
            source = (res.data or {}).get("source")
            if source == "local":
                title = (res.data or {}).get("title") or query
                return Reply("нашла «%s» — включаю." % title, chips=["спасибо"])
            return Reply("открыла ютуб%s." %
                         ((" с поиском «%s»" % query) if query else ""),
                         chips=["спасибо"])
        return Reply(res.message or "не смогла включить видео.",
                     chips=["открой ютуб"])

    # ------------------------------------------------------------------
    #  Заметки и память
    # ------------------------------------------------------------------
    def _h_notes(self, clean, t):
        if any(w in t for w in ("мои заметки", "что в заметках", "покажи заметки",
                                "список заметок", "моих заметках")):
            notes = self.s.get("notes", []) or []
            if not notes:
                return Reply("заметок пока нет. скажи «запиши ...» — и я сохраню.",
                             chips=["запиши "])
            lines = ["твои заметки:"]
            for index, note in enumerate(notes[-10:], start=1):
                lines.append("%d. %s" % (index, note.get("text", "")))
            return Reply("\n".join(lines), chips=["удали заметку 1"])
        m = re.match(r"^(?:удали|сотри)\s+заметку\s*(\d+)$", t)
        if m:
            dropped = self.s.drop_note(int(m.group(1)))
            if dropped:
                return Reply("удалила заметку: «%s»." % dropped.get("text", ""))
            return Reply("нет заметки с таким номером.")
        m = NOTE_RE.match(clean)
        if m:
            note_text = m.group(1).strip(" .,!")
            if len(note_text) < 2:
                return None
            note = self.s.add_note(note_text)
            return Reply(self.p.pick([
                "записала: «%s»." % note_text,
                "ок, в заметках: «%s»." % note_text,
            ]), chips=["мои заметки"])
        return None

    def _h_memory(self, clean, t):
        memory = self.s.get("memory", {}) or {}
        if memory:
            best = None
            for key in memory:
                if re.search(r"(?<![а-яa-z])" + re.escape(key) + r"(?![а-яa-z])", t):
                    if best is None or len(key) > len(best):
                        best = key
            if best:
                return Reply(memory[best])
        m = MEMORY_RE.match(clean)
        if not m:
            return None
        question = m.group(1).strip().lower()
        answer = m.group(2).strip()
        if not question or not answer or len(question) > 60:
            return None
        memory[question] = answer
        self.s.set("memory", memory)
        return Reply("запомнила. теперь про «%s» буду отвечать: «%s»." % (question, answer),
                     chips=DEFAULT_CHIPS)

    # ------------------------------------------------------------------
    #  Открыть приложение, сайт, файл
    # ------------------------------------------------------------------
    def _h_open(self, clean, t):
        m = OPEN_RE.match(t)
        if not m:
            return None
        target_raw = m.group(1)
        target = catalog.normalize_target(target_raw)
        if not target:
            return Reply("что открыть?", chips=["ютуб", "телеграм", "камеру",
                                                "настройки", "вконтакте"])
        return self._open_target(target, clean)

    def _open_target(self, target, clean=""):
        t = nlp.fold(target)

        # 1) явная ссылка
        if nlp.looks_like_url(target):
            url = target
            if not re.match(r"^[a-z]+://", url.lower()):
                url = "https://" + url
            self._status("открываю ссылку")
            res = self.b.open_url(url)
            if res.ok:
                return Reply("открыла %s." % target, chips=["спасибо"])
            return Reply(res.message or "не смогла открыть ссылку.", chips=DEFAULT_CHIPS)

        # 2) известное приложение
        app = catalog.find_app(t)
        if app:
            if self.b.app_installed(app.package):
                self._status("запускаю %s" % app.label)
                res = self.b.launch_package(app.package)
                if res.ok:
                    return Reply(self.p.pick([
                        "открыла %s." % app.label,
                        "готово: %s." % app.label,
                        "%s уже на экране." % app.label,
                    ]), chips=AFTER_COMMAND_CHIPS)
            elif app.settings == "settings" and t in ("настройки", "параметры"):
                res = self.b.open_settings("")
                if res.ok:
                    return Reply("открыла настройки.", chips=AFTER_COMMAND_CHIPS)
            elif app.site:
                self._status("открываю сайт")
                res = self.b.open_url(app.site)
                if res.ok:
                    return Reply("%s на телефоне нет, открыла сайт." % app.label,
                                 chips=AFTER_COMMAND_CHIPS)
            else:
                self._status("открываю магазин приложений")
                res = self.b.open_play_store(app.package)
                if res.ok:
                    return Reply("%s не установлено. открыла Play Market — там одна "
                                 "кнопка «Установить»." % app.label,
                                 chips=AFTER_COMMAND_CHIPS)

        # 3) сайт
        site = catalog.find_site(t)
        if site:
            self._status("открываю %s" % site.label)
            res = self.b.open_url(site.url)
            if res.ok:
                return Reply("открыла %s." % site.label, chips=["спасибо"])
            return Reply(res.message or "не смогла открыть сайт.", chips=DEFAULT_CHIPS)

        # 4) поиск среди установленных приложений
        apps = self.b.installed_apps()
        if apps:
            self._status("ищу приложение")
            best, score = nlp.fuzzy_best(t, [(label, [label]) for label, _pkg in apps])
            if best and score >= 0.78:
                for label, package in apps:
                    if label == best:
                        res = self.b.launch_package(package)
                        if res.ok:
                            return Reply("открыла %s." % label, chips=AFTER_COMMAND_CHIPS)
                        break

        # 5) не знаем такое — предложим поиск
        return Reply(self.p.pick([
            "не нашла «%s» ни среди приложений, ни в моём списке сайтов." % target,
            "хм, «%s» мне не знакомо." % target,
        ]) + " поискать в интернете?", chips=["поищи %s" % target, "что ты умеешь"])

    # ------------------------------------------------------------------
    #  Поиск в интернете
    # ------------------------------------------------------------------
    def _h_search(self, clean, t):
        m = SEARCH_RE.match(t)
        query = ""
        if m:
            query = m.group(1)
        else:
            m = WHAT_RE.match(t)
            if m:
                query = m.group(1)
        if not query:
            return None
        query = nlp.strip_punct(query)
        query = re.sub(r"^(?:в\s+интернете|в\s+сети|в\s+инете|в\s+гугле)\s+", "", query,
                       flags=re.IGNORECASE)
        if not query:
            return Reply("что искать?")
        self._status("ищу «%s»" % query)
        url = "https://duckduckgo.com/?q=" + query.replace(" ", "+")
        res = self.b.open_url(url)
        if res.ok:
            return Reply(self.p.pick([
                "ищу «%s»." % query,
                "открываю поиск по «%s»." % query,
                "секунду, гуглю «%s»." % query,
            ]), chips=["спасибо"])
        return Reply("не смогла открыть браузер.", chips=DEFAULT_CHIPS)

    # ------------------------------------------------------------------
    #  Время и дата
    # ------------------------------------------------------------------
    def _h_time(self, clean, t):
        if not any(w in t for w in ("время", "который час", "сколько времени",
                                    "скок время", "сколько время")):
            return None
        hour = time.localtime(self.now()).tm_hour
        now_str = time.strftime("%H:%M", time.localtime(self.now()))
        part = self.p.part_of_day(hour)
        if part == "night":
            extra = self.p.pick(["уже поздно, пора спать) ", "ночь на дворе, а ты не спишь "])
        elif part == "morning":
            extra = self.p.pick(["ещё утро, но ты уже тут) ", "рано встал. ", ""])
        elif part == "evening":
            extra = self.p.pick(["вечер уже. ", ""])
        else:
            extra = ""
        return Reply(extra + "сейчас %s." % now_str, chips=["какое сегодня число"])

    def _h_date(self, clean, t):
        if not any(w in t for w in ("дата", "какое число", "какой сегодня день",
                                    "какой день", "что сегодня", "какое сегодня")):
            return None
        months = ["января", "февраля", "марта", "апреля", "мая", "июня",
                  "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        weekdays = ["понедельник", "вторник", "среда", "четверг",
                    "пятница", "суббота", "воскресенье"]
        now = time.localtime(self.now())
        return Reply("сегодня %d %s %d, %s." % (now.tm_mday, months[now.tm_mon - 1],
                                                now.tm_year, weekdays[now.tm_wday]),
                     chips=["сколько времени"])

    # ------------------------------------------------------------------
    #  О себе и помощь
    # ------------------------------------------------------------------
    def _h_identity(self, clean, t):
        if any(w in t for w in ("кто ты", "как тебя зовут", "твоё имя", "твое имя",
                                "как звать", "ты кто")):
            return Reply(self.p.pick([
                "меня зовут Nika.",
                "Nika. приятно, что спросил)",
                "Nika, я тут рядом — в твоём телефоне.",
            ]), chips=DEFAULT_CHIPS)
        if any(w in t for w in ("сколько тебе лет", "когда ты родилась")):
            return Reply("я появилась вместе с этим приложением. так что я ещё "
                         "совсем юная)", chips=DEFAULT_CHIPS)
        return None

    def _h_help(self, clean, t):
        if any(w in t for w in ("что ты умеешь", "что можешь", "помощь", "команды",
                                "как пользоваться", "что ты можешь")):
            return Reply(self.p.pick(HELP_LINES),
                         chips=["позвони маме", "открой ютуб", "погода", "какой пароль от вайфая"])
        return None

    # ------------------------------------------------------------------
    #  Социальное и болтовня
    # ------------------------------------------------------------------
    def _h_social(self, clean, t):
        hour = time.localtime(self.now()).tm_hour

        if any(w in t for w in ("останови таймер", "стоп таймер", "отмени таймер",
                                "хватит таймер")):
            return Reply("остановила таймер.", actions=[{"type": "timer_stop"}],
                         chips=DEFAULT_CHIPS)

        if any(w in t for w in ("мои напоминания", "какие напоминания",
                                "список напоминаний")):
            reminders = [r for r in self.s.get("reminders", []) or [] if not r.get("done")]
            if not reminders:
                return Reply("напоминаний нет. скажи «напомни через час ...» — поставлю.")
            lines = ["твои напоминания:"]
            for item in reminders[:8]:
                when = time.strftime("%d.%m %H:%M", time.localtime(item.get("at", 0)))
                lines.append("• %s — %s" % (when, item.get("text", "")))
            return Reply("\n".join(lines), chips=DEFAULT_CHIPS)

        if THANKS_RE.search(t):
            return Reply(self.p.pick(["всегда пожалуйста!", "рада помочь)",
                                      "обращайся.", "не за что) приятно быть полезной."]),
                         chips=DEFAULT_CHIPS)

        if BYE_RE.search(t):
            if "спокойной ночи" in t:
                return Reply(self.p.pick(["спокойной ночи) выспись как следует.",
                                          "давай спать. завтра всё будет яснее."]),
                             chips=DEFAULT_CHIPS)
            return Reply(self.p.pick(["пока! если что — я тут.", "до встречи!",
                                      "бай. было приятно поболтать.",
                                      "увидимся. не пропадай."]),
                         chips=DEFAULT_CHIPS)

        if LOVE_RE.search(t):
            return Reply(self.p.pick(["ой) я тоже к тебе тепло отношусь.",
                                      "ну вот, я теперь довольная)",
                                      "и я тебя. только не говори никому, я суровая)"]),
                         chips=DEFAULT_CHIPS)

        if INSULT_RE.search(t):
            return Reply(self.p.pick(["эй, это было обидно.", "зачем так? я же стараюсь.",
                                      "ну спасибо. настроение испортил("]),
                         chips=["извини"])

        if PRAISE_RE.search(t):
            return Reply(self.p.pick(["ой, спасибо) ты тоже ничего.",
                                      "приятно, спасибо. ты меня смущаешь."]),
                         chips=DEFAULT_CHIPS)

        if "как дела" in t or "как ты" in t or "как жизнь" in t or "как сам" in t:
            return Reply(self.p.greeting(hour) + self.p.how_are_you(),
                         chips=["нормально", "расскажи что-нибудь"])

        if GREET_RE.match(t):
            tail = self.p.pick(["", "", "как ты?", "что нового?", "чем занят?"])
            text = self.p.greeting(hour).strip()
            if tail:
                text = text.rstrip(")") + ") " + tail if not text.endswith(("?", "!")) else text + " " + tail
            return Reply(text, chips=DEFAULT_CHIPS)

        if any(w in t for w in ("а еще", "а ещё", "еще", "ещё")) and len(t.split()) <= 3:
            return Reply(self.p.again(), chips=AFTER_JOKE_CHIPS
                         if self.p.last_kind == "joke" else DEFAULT_CHIPS)

        if hour < 5 and any(w in t for w in ("спишь", "не спишь", "ты тут", "ау",
                                             "ты здесь")):
            return Reply(self.p.night_line(), chips=DEFAULT_CHIPS)

        if any(w in t for w in ("ты спишь", "спишь")):
            return Reply(self.p.pick(["не сплю) я же программа, мне спать не надо.",
                                      "не сплю. а ты почему?"]),
                         chips=DEFAULT_CHIPS)

        small = self.p.smalltalk(t)
        if small:
            chips = DEFAULT_CHIPS
            if self.p.last_kind == "joke":
                chips = AFTER_JOKE_CHIPS
            elif self.p.last_kind == "fact":
                chips = AFTER_FACT_CHIPS
            elif any(w in t for w in ("грустно", "плохо", "устал", "тревожно",
                                      "одиноко", "тяжело")):
                chips = AFTER_EMPATHY_CHIPS
            return Reply(small, chips=chips)

        return None

    # ------------------------------------------------------------------
    #  Не поняла
    # ------------------------------------------------------------------
    def _fallback(self, clean, t):
        question_words = ("как ", "что ", "где ", "когда ", "почему ", "зачем ",
                          "кто ", "сколько ", "какой ", "какая ", "какое ",
                          "можно ли", "есть ли")
        if self._question or t.startswith(question_words):
            short = nlp.strip_punct(clean)
            if len(short) < 70:
                unknown = self.s.get("unknown", []) or []
                unknown.append(short)
                self.s.set("unknown", unknown[-200:])
                return Reply(self.p.pick([
                    "хм, интересный вопрос. сама не отвечу — но могу поискать.",
                    "тут я пасую) хочешь, открою поиск?",
                    "не уверена, что знаю ответ. поискать в интернете?",
                ]), chips=["поищи %s" % short[:40], "что ты умеешь"])

        if len(t) < 80 and len(t.split()) <= 6:
            unknown = self.s.get("unknown", []) or []
            unknown.append(nlp.strip_punct(clean))
            self.s.set("unknown", unknown[-200:])

        return Reply(self.p.pick([
            "поняла тебя.",
            "ага, слушаю.",
            "интересно. и что дальше?",
            "мм, понятно.",
            "расскажи ещё что-нибудь)",
            "я тут, слушаю.",
        ]), chips=DEFAULT_CHIPS)

    # ------------------------------------------------------------------
    #  Приветствие при запуске и «она сама пишет»
    # ------------------------------------------------------------------
    def startup(self):
        last = self.s.last_seen()
        now = self.now()
        hour = time.localtime(now).tm_hour
        self.s.touch()
        self.s.save()
        if last and now - last > 2 * 3600:
            gap = (now - last) / 3600.0
            text = self.p.absence(gap) + " как ты?"
        elif not last:
            text = self.p.greeting(hour) + "я Nika. теперь живу в твоём телефоне — " \
                                           "могу позвонить, открыть приложение, " \
                                           "поставить таймер и просто поболтать."
        else:
            text = self.p.greeting(hour) + "я тут."
        return Reply(text, chips=DEFAULT_CHIPS, intent="startup")

    def idle_message(self):
        """Сообщение, если человек долго молчит."""
        now = self.now()
        last = self.s.last_seen()
        if last and now - last < 10 * 60:
            return None
        hour = time.localtime(now).tm_hour
        if hour < 5:
            return None
        return Reply(self.p.idle_line(hour), chips=DEFAULT_CHIPS, intent="idle")

    def greeting_for_resume(self):
        now = self.now()
        last = self.s.last_seen()
        if last and now - last > 2 * 3600:
            return Reply(self.p.absence((now - last) / 3600.0) + " как ты?",
                         chips=DEFAULT_CHIPS, intent="resume")
        return None
