# -*- coding: utf-8 -*-
"""Nika для Android — интерфейс.

Палитра и настроение перенесены из Windows-версии:
тёмный фон #0d0d0f, бордовый акцент #c81e3a, приглушённый #7a4a52,
тонкая рамка в два цвета вокруг всего окна.

Запуск на телефоне: buildozer android debug
Проверка на компьютере: pip install kivy certifi && python main.py
"""

import os
import random
import threading
import time

from kivy.app import App
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.text import Label as CoreLabel
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle, RoundedRectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import ButtonBehavior
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform

from nika import Engine, Reply, Store, nlp, theme
from nika.bridge import get_bridge

IS_ANDROID = platform == "android"

# кэш измерений текста: (текст, ширина) -> (ширина, высота)
_MEASURE_CACHE = {}


def measure_text(text, font_size, text_width=None):
    """Честно измеряет текст тем же шрифтом.

    Label.texture_size сразу после смены text_size отдаёт старое значение,
    поэтому считаем через CoreLabel — он обновляется синхронно.
    """
    key = (text, round(float(text_width or 0), 1), round(float(font_size), 2))
    if key in _MEASURE_CACHE:
        return _MEASURE_CACHE[key]
    core = CoreLabel(text=text, font_name=theme.FONT, font_size=font_size,
                     halign="left", valign="top",
                     text_size=(text_width, None) if text_width else (None, None))
    core.refresh()
    size = tuple(core.texture.size)
    _MEASURE_CACHE[key] = size
    return size


# ======================================================================
#  Мелкие помощники
# ======================================================================

class AlignLabel(Label):
    """Label с выравниванием, которое работает по фактическому размеру."""

    def __init__(self, **kwargs):
        kwargs.setdefault("halign", "left")
        kwargs.setdefault("valign", "middle")
        kwargs.setdefault("markup", False)
        super().__init__(**kwargs)
        self.bind(size=self._sync_text_size)

    def _sync_text_size(self, *_args):
        self.text_size = self.size


class FlatChip(ButtonBehavior, Label):
    """Маленькая кнопка-таблетка (подсказка, «голос», «стоп»)."""

    def __init__(self, text, on_choice=None, active=False, **kwargs):
        kwargs.setdefault("font_size", sp(12.5))
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("height", dp(30))
        super().__init__(text=text, **kwargs)
        self.on_choice = on_choice
        self.active = active
        with self.canvas.before:
            self._bg_color = Color(*(theme.ACCENT if active else theme.BG_CHIP))
            self._bg = RoundedRectangle(radius=[dp(15)])
            self._border_color = Color(*(theme.ACCENT if active else theme.LINE))
            self._border = Line(width=1)
        self.bind(pos=self._redraw, size=self._redraw, texture_size=self._fit)
        self._fit()

    def _fit(self, *_args):
        # только ширина: text_size не трогаем, иначе получается петля пересчёта
        self.width = self.texture_size[0] + dp(26)

    def _redraw(self, *_args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._border.rounded_rectangle = (self.x, self.y, self.width, self.height, dp(15))

    def set_active(self, active):
        self.active = active
        self._bg_color.rgba = theme.ACCENT if active else theme.BG_CHIP
        self._border_color.rgba = theme.ACCENT if active else theme.LINE
        self.color = theme.BG if active else theme.MUTED_LIGHT

    def on_release(self):
        if self.on_choice:
            self.on_choice(self.text)


# ======================================================================
#  Пузыри сообщений
# ======================================================================

class Bubble(Label):
    def __init__(self, text, mine=False, **kwargs):
        super().__init__(
            text=text,
            markup=False,
            halign="left",
            valign="top",
            font_name=theme.FONT,
            font_size=sp(15.5),
            color=theme.USER_TEXT if mine else theme.ACCENT,
            size_hint=(None, None),
            **kwargs
        )
        self.mine = mine
        with self.canvas.before:
            self._bg_color = Color(*(theme.BG_BUBBLE_MINE if mine else theme.BG_BUBBLE))
            self._bg = RoundedRectangle(radius=[dp(13)])
            if not mine:
                self._bar_color = Color(*theme.ACCENT)
                self._bar = RoundedRectangle(radius=[dp(1.5)])
        self.bind(pos=self._redraw, size=self._redraw)

    def _redraw(self, *_args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        if not self.mine:
            self._bar.pos = (self.x + dp(1), self.y + dp(7))
            self._bar.size = (dp(2.5), max(dp(4), self.height - dp(14)))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and touch.is_double_tap:
            try:
                Clipboard.copy(self.text)
            except Exception:
                pass
            return True
        return super().on_touch_down(touch)


class BubbleRow(BoxLayout):
    def __init__(self, text, mine=False, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         spacing=dp(4), **kwargs)
        self.mine = mine
        self.label = Bubble(text, mine=mine)
        if mine:
            self.add_widget(Widget(size_hint_x=1))
            self.add_widget(self.label)
            self.add_widget(Widget(size_hint_x=None, width=dp(4)))
        else:
            self.add_widget(Widget(size_hint_x=None, width=dp(4)))
            self.add_widget(self.label)
            self.add_widget(Widget(size_hint_x=1))
        self._last = (0, 0)
        self._natural = None
        self.bind(width=self._layout)
        self.label.bind(texture_size=self._layout)
        Clock.schedule_once(self._layout, 0)

    def _measure(self):
        """Натуральный размер текста в одну строку (кэшируется)."""
        if self._natural is None:
            self._natural = measure_text(self.label.text, sp(15.5))
        return self._natural

    def _layout(self, *_args):
        row_width = self.width or (Window.width - dp(26))
        max_width = max(dp(90), row_width * 0.84)
        text_width = max(dp(40), max_width - dp(26))
        natural_w, natural_h = self._measure()

        if natural_w <= text_width:
            text_size = (None, None)
            width = min(max_width, natural_w + dp(26))
            height = natural_h + dp(18)
        else:
            _w, wrapped_h = measure_text(self.label.text, sp(15.5), text_width)
            text_size = (text_width, None)
            width = max_width
            height = wrapped_h + dp(18)

        label = self.label
        if list(label.text_size) != list(text_size):
            label.text_size = text_size
        if (abs(width - self._last[0]) < 0.5 and abs(height - self._last[1]) < 0.5):
            return
        self._last = (width, height)
        label.size = (width, height)
        self.height = height + dp(2)


class TypingRow(BoxLayout):
    """«печатает…» с живыми точками."""

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint=(None, None),
                         height=dp(34), **kwargs)
        with self.canvas.before:
            self._bg_color = Color(*theme.BG_BUBBLE)
            self._bg = RoundedRectangle(radius=[dp(13)])
        self.label = Label(text="печатает", font_name=theme.FONT, font_size=sp(13),
                           color=theme.MUTED_LIGHT, size_hint=(None, 1),
                           padding=(dp(14), 0))
        self.label.bind(texture_size=self._fit)
        self.add_widget(self.label)
        self.bind(pos=self._redraw, size=self._redraw)
        self._dots = 0
        self._event = Clock.schedule_interval(self._tick, 0.45)

    def _fit(self, *_args):
        self.width = self.label.texture_size[0] + dp(28)

    def _tick(self, _dt):
        self._dots = (self._dots + 1) % 3
        self.label.text = "печатает" + "." * (self._dots + 1)

    def _redraw(self, *_args):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def stop(self):
        try:
            self._event.cancel()
        except Exception:
            pass


# ======================================================================
#  Кнопки с нарисованными иконками (без зависимости от шрифтов)
# ======================================================================

class IconButton(ButtonBehavior, Widget):
    def __init__(self, kind="send", on_press=None, filled=True, **kwargs):
        size = kwargs.pop("size", dp(46))
        super().__init__(size_hint=(None, None), size=(size, size), **kwargs)
        self.kind = kind
        self._callback = on_press
        self._filled = filled
        self._base = theme.ACCENT if filled else theme.BG_CHIP
        with self.canvas.before:
            self._bg_color = Color(*self._base)
            self._bg = RoundedRectangle(radius=[size / 2])
        with self.canvas.after:
            self._fg_color = Color(*(theme.BG if filled else theme.ACCENT))
            if kind == "send":
                self._icon = Triangle(points=[])
            elif kind == "stop":
                self._shape = RoundedRectangle(radius=[dp(2)])
            else:  # mic
                self._shape = RoundedRectangle(radius=[dp(4)])
                self._arc = Line(width=1.4, cap="round")
                self._stem = Line(width=1.4, cap="round")
        self.bind(pos=self._redraw, size=self._redraw, state=self._on_state)
        Clock.schedule_once(self._redraw, 0)

    def _on_state(self, *_args):
        if self._filled:
            self._bg_color.rgba = theme.ACCENT_PRESS if self.state == "down" else theme.ACCENT

    def _redraw(self, *_args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        cx, cy = self.center
        s = self.width
        if self.kind == "send":
            self._icon.points = [cx - s * 0.11, cy + s * 0.17,
                                 cx - s * 0.11, cy - s * 0.17,
                                 cx + s * 0.19, cy]
        elif self.kind == "stop":
            half = s * 0.13
            self._shape.pos = (cx - half, cy - half)
            self._shape.size = (half * 2, half * 2)
        else:
            body_w, body_h = s * 0.24, s * 0.34
            self._shape.pos = (cx - body_w / 2, cy - body_h * 0.15)
            self._shape.size = (body_w, body_h)
            radius = s * 0.19
            self._arc.circle = (cx, cy - s * 0.02, radius, 200, 340)
            self._stem.points = [cx, cy - s * 0.02 - radius, cx, cy - s * 0.30]
            self._arc.width = 1.4
            self._stem.width = 1.4

    def on_release(self):
        if self._callback:
            self._callback()


# ======================================================================
#  Поле ввода
# ======================================================================

class InputBar(BoxLayout):
    def __init__(self, on_send, on_mic, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(64), padding=(dp(10), dp(9)),
                         spacing=dp(8), **kwargs)
        holder = BoxLayout(size_hint=(1, 1))
        with holder.canvas.before:
            self._field_color = Color(*theme.BG_INPUT)
            self._field_bg = RoundedRectangle(radius=[dp(18)])
            self._field_border_color = Color(*theme.LINE)
            self._field_border = Line(width=1)

        def _sync(*_a):
            self._field_bg.pos = holder.pos
            self._field_bg.size = holder.size
            self._field_border.rounded_rectangle = (
                holder.x, holder.y, holder.width, holder.height, dp(18))

        holder.bind(pos=_sync, size=_sync)
        Clock.schedule_once(_sync, 0)

        self.field = TextInput(
            multiline=False,
            write_tab=False,
            hint_text="напиши или нажми на микрофон",
            font_name=theme.FONT,
            font_size=sp(15),
            foreground_color=theme.ACCENT,
            hint_text_color=theme.MUTED,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            padding=(dp(14), dp(12)),
            cursor_blink=True,
        )
        try:
            self.field.cursor_color = theme.ACCENT
            self.field.cursor_width = dp(1.4)
        except Exception:
            pass
        self.field.bind(on_text_validate=lambda *_: on_send(self.field.text))
        self.field.bind(focus=self._on_focus)
        holder.add_widget(self.field)
        self.add_widget(holder)
        self.add_widget(IconButton("mic", on_press=on_mic, filled=False, size=dp(44)))
        self.add_widget(IconButton("send", on_press=lambda: on_send(self.field.text),
                                   filled=True, size=dp(46)))

    def _on_focus(self, _inst, focused):
        self._field_border_color.rgba = theme.ACCENT if focused else theme.LINE


# ======================================================================
#  Список сообщений
# ======================================================================

class Chat(ScrollView):
    def __init__(self, **kwargs):
        super().__init__(do_scroll_x=False, bar_width=dp(2),
                         bar_color=theme.MUTED, bar_inactive_color=theme.LINE, **kwargs)
        self.box = BoxLayout(orientation="vertical", size_hint_y=None,
                             padding=(dp(10), dp(8)), spacing=dp(6))
        self.box.bind(minimum_height=self.box.setter("height"))
        # пружина сверху: пока сообщений мало, они прижаты к низу, как в мессенджере
        self._spring = Widget(size_hint_y=None, height=0)
        self.box.add_widget(self._spring)
        self.add_widget(self.box)
        self.typing = None
        self.bind(size=self._relayout)
        Clock.schedule_once(self._relayout, 0)

    def _relayout(self, *_args):
        rows = [w for w in self.box.children if w is not self._spring]
        content = sum(w.height for w in rows)
        content += self.box.spacing * max(0, len(rows) - 1)
        content += self.box.padding[1] * 2
        target = max(0, self.height - content)
        if abs(self._spring.height - target) > 0.5:
            self._spring.height = target

    def add(self, text, mine=False):
        row = BubbleRow(text, mine=mine)
        self.box.add_widget(row)
        Clock.schedule_once(lambda _dt: self._relayout(), 0)
        self.to_bottom()
        return row

    def show_typing(self):
        if self.typing is None:
            self.typing = TypingRow()
            self.box.add_widget(self.typing)
            Clock.schedule_once(lambda _dt: self._relayout(), 0)
            self.to_bottom()

    def hide_typing(self):
        if self.typing is not None:
            self.typing.stop()
            try:
                self.box.remove_widget(self.typing)
            except Exception:
                pass
            self.typing = None
            self._relayout()

    def clear(self):
        self.hide_typing()
        self.box.clear_widgets()
        self.box.add_widget(self._spring)
        self._relayout()

    def to_bottom(self):
        Clock.schedule_once(lambda _dt: setattr(self, "scroll_y", 0), 0.03)


# ======================================================================
#  Подсказки
# ======================================================================

class Chips(ScrollView):
    def __init__(self, on_choice, **kwargs):
        super().__init__(do_scroll_x=True, do_scroll_y=False,
                         size_hint_y=None, height=dp(38), bar_width=0, **kwargs)
        self.box = BoxLayout(orientation="horizontal", size_hint=(None, 1),
                             spacing=dp(8), padding=(dp(10), dp(2)))
        self.box.bind(minimum_width=self.box.setter("width"))
        self.add_widget(self.box)
        self.on_choice = on_choice

    def set(self, items):
        self.box.clear_widgets()
        for item in list(items)[:6]:
            if not item:
                continue
            chip = FlatChip(item, on_choice=self.on_choice)
            self.box.add_widget(chip)
        self.scroll_x = 0


# ======================================================================
#  Верхняя полоса
# ======================================================================

class Header(BoxLayout):
    def __init__(self, on_voice, on_help, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None,
                         height=dp(58), padding=(dp(14), dp(7)),
                         spacing=dp(6), **kwargs)
        left = BoxLayout(orientation="vertical", spacing=0, size_hint_x=1)
        self.title = AlignLabel(text="Nika", color=theme.ACCENT, bold=True,
                                font_size=sp(22), size_hint_y=None, height=dp(28))
        self.status = AlignLabel(text=theme.TAGLINE, color=theme.MUTED,
                                 font_size=sp(11), size_hint_y=None, height=dp(16))
        left.add_widget(self.title)
        left.add_widget(self.status)
        self.add_widget(left)
        self.voice_chip = FlatChip("голос", on_choice=lambda _t: on_voice(), active=True,
                                   color=theme.BG)
        self.help_chip = FlatChip("?", on_choice=lambda _t: on_help(),
                                  color=theme.MUTED_LIGHT)
        self.help_chip.width = dp(38)
        self.add_widget(self.voice_chip)
        self.add_widget(self.help_chip)

    def set_status(self, text):
        self.status.text = text

    def set_voice(self, enabled):
        self.voice_chip.set_active(enabled)
        self.voice_chip.text = "голос" if enabled else "тихо"


class TimerBar(BoxLayout):
    def __init__(self, on_stop, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=0,
                         padding=(dp(14), 0), spacing=dp(8), **kwargs)
        with self.canvas.before:
            self._bg_color = Color(*theme.BG_BUBBLE)
            self._bg = Rectangle()
            self._edge_color = Color(*theme.ACCENT)
            self._edge = Rectangle()
        self.bind(pos=self._redraw, size=self._redraw)
        self.label = AlignLabel(text="таймер", color=theme.ACCENT, font_size=sp(13),
                                size_hint_y=None, height=dp(30))
        self.add_widget(self.label)
        self.add_widget(Widget(size_hint_x=1))
        self.stop_chip = FlatChip("стоп", on_choice=lambda _t: on_stop(),
                                  color=theme.MUTED_LIGHT)
        self.stop_chip.height = dp(26)
        self.add_widget(self.stop_chip)

    def _redraw(self, *_args):
        self._bg.pos = self.pos
        self._bg.size = self.size
        self._edge.pos = (self.x, self.y)
        self._edge.size = (dp(2), self.height)

    def show(self, visible):
        self.height = dp(34) if visible else 0
        self.opacity = 1 if visible else 0


# ======================================================================
#  Корень
# ======================================================================

class NikaRoot(BoxLayout):
    def __init__(self, app, **kwargs):
        super().__init__(orientation="vertical", padding=(dp(4), dp(4)),
                         spacing=0, **kwargs)
        self.app = app
        with self.canvas.before:
            self._frame_accent = Color(*theme.ACCENT)
            self._rect_accent = Rectangle()
            self._frame_black = Color(*theme.BLACK)
            self._rect_black = Rectangle()
            self._frame_bg = Color(*theme.BG)
            self._rect_bg = Rectangle()
        self.bind(pos=self._draw_frame, size=self._draw_frame)

        self.header = Header(on_voice=app.toggle_voice, on_help=app.show_help)
        self.timer_bar = TimerBar(on_stop=app.stop_timers)
        self.chat = Chat()
        self.chips = Chips(on_choice=app.send)
        self.input = InputBar(on_send=app.send, on_mic=app.listen)
        self.add_widget(self.header)
        self.add_widget(self.timer_bar)
        self.add_widget(self.chat)
        self.add_widget(self.chips)
        self.add_widget(self.input)

    def _draw_frame(self, *_args):
        width, height = self.size
        self._rect_accent.pos = self.pos
        self._rect_accent.size = (width, height)
        self._rect_black.pos = (self.x + dp(1), self.y + dp(1))
        self._rect_black.size = (max(0, width - dp(2)), max(0, height - dp(2)))
        self._rect_bg.pos = (self.x + dp(2), self.y + dp(2))
        self._rect_bg.size = (max(0, width - dp(4)), max(0, height - dp(4)))

    # ---------- удобные обёртки ----------
    def add_nika(self, text):
        return self.chat.add(text, mine=False)

    def add_user(self, text):
        return self.chat.add(text, mine=True)

    def set_status(self, text):
        self.header.set_status(text)

    def set_chips(self, items):
        self.chips.set(items)

    def set_timer(self, text):
        self.timer_bar.show(bool(text))
        if text:
            self.timer_bar.label.text = text


# ======================================================================
#  Приложение
# ======================================================================

class NikaApp(App):
    title = "Nika"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.store = None
        self.bridge = None
        self.engine = None
        self.root_ui = None
        self.timers = []
        self._busy = 0
        self._last_status = ""

    # ---------- запуск ----------
    def build(self):
        Window.clearcolor = theme.BG
        if not IS_ANDROID:
            Window.size = (420, 840)
        try:
            Window.softinput_mode = "below_target"
        except Exception:
            pass

        data_dir = self.user_data_dir or os.getcwd()
        try:
            if not os.path.isdir(data_dir):
                os.makedirs(data_dir)
        except Exception:
            pass
        self.store = Store(os.path.join(data_dir, "nika_memory.json"))
        self.bridge, note = get_bridge(verbose=True)
        self.engine = Engine(self.bridge, self.store, status_cb=self._status_from_thread)
        self.root_ui = NikaRoot(self)
        return self.root_ui

    def on_start(self):
        Window.bind(on_keyboard=self._on_key)
        self.root_ui.header.set_voice(bool(self.store.pref("voice", True)))
        if IS_ANDROID:
            self._ask_notifications()
        Clock.schedule_once(lambda _dt: self._startup_message(), 0.7)
        Clock.schedule_interval(self._tick, 1.0)
        self._schedule_idle()

    def on_pause(self):
        self._save()
        return True

    def on_resume(self):
        Clock.schedule_once(lambda _dt: self._check_reminders(), 0.3)
        Clock.schedule_once(lambda _dt: self._resume_greeting(), 0.6)

    def on_stop(self):
        self._save()

    def _save(self):
        try:
            self.store.save()
        except Exception:
            pass

    def _ask_notifications(self):
        try:
            from android.permissions import Permission, check_permission, request_permissions
            if not check_permission(Permission.POST_NOTIFICATIONS):
                request_permissions([Permission.POST_NOTIFICATIONS])
        except Exception:
            pass

    # ---------- приветствие ----------
    def _startup_message(self):
        try:
            reply = self.engine.startup()
        except Exception as exc:
            self.root_ui.add_nika("не смогла запуститься: %s" % exc)
            return
        self.root_ui.add_nika(reply.text)
        self.root_ui.set_chips(reply.chips)
        self._save()

    def _resume_greeting(self):
        try:
            reply = self.engine.greeting_for_resume()
        except Exception:
            reply = None
        if reply:
            self.root_ui.add_nika(reply.text)

    # ---------- отправка ----------
    def send(self, text=None):
        text = (text if text is not None else self.root_ui.input.field.text)
        text = (text or "").strip()
        if not text:
            return
        field = self.root_ui.input.field
        field.text = ""
        field.focus = False
        self.root_ui.add_user(text)
        self.root_ui.set_chips([])
        self._busy += 1
        self.root_ui.chat.show_typing()
        self.root_ui.set_status("думает…")
        Clock.schedule_once(lambda _dt: self._save(), 0.1)
        threading.Thread(target=self._work, args=(text,), daemon=True).start()

    def _work(self, text):
        try:
            reply = self.engine.respond(text)
        except Exception as exc:  # noqa: BLE001
            reply = Reply("что-то сломалось: %s" % exc)
        # небольшая пауза, чтобы ответ не «вылетал» мгновенно
        delay = 0.25 if len(reply.text) < 60 else 0.45
        time.sleep(delay)
        Clock.schedule_once(lambda _dt: self._deliver(reply), 0)

    def _deliver(self, reply):
        self._busy = max(0, self._busy - 1)
        if self._busy == 0:
            self.root_ui.chat.hide_typing()
            self.root_ui.set_status(theme.TAGLINE)
        if reply.text:
            self.root_ui.add_nika(reply.text)
        if reply.chips:
            self.root_ui.set_chips(reply.chips)
        self._run_actions(reply.actions)
        if reply.speak and reply.text and self.store.pref("voice", True):
            self._speak(reply.text)
        self._save()

    def _run_actions(self, actions):
        for action in actions or []:
            kind = action.get("type")
            if kind == "timer":
                self._add_timer(action.get("seconds", 60), action.get("label", "таймер"))
            elif kind == "timer_stop":
                self.stop_timers(announce=False)
            elif kind == "reminder":
                self._check_reminders()

    # ---------- голос ----------
    def _speak(self, text):
        if not self.bridge.can_voice:
            return
        phrase = nlp.clean_for_speech(text)
        if phrase:
            try:
                self.bridge.speak(phrase)
            except Exception:
                pass

    def toggle_voice(self):
        enabled = not bool(self.store.pref("voice", True))
        self.store.set_pref("voice", enabled)
        self._save()
        self.root_ui.header.set_voice(enabled)
        if not enabled:
            try:
                self.bridge.stop_speak()
            except Exception:
                pass
        self.root_ui.add_nika(
            "ок, буду молчать. пиши — я отвечу текстом)" if not enabled
            else "снова говорю вслух)")

    def listen(self):
        if not self.bridge.can_voice:
            self.root_ui.add_nika("голосовой ввод работает на телефоне.")
            return
        self.root_ui.set_status("слушаю…")
        try:
            res = self.bridge.listen(self._speech_result)
        except Exception as exc:
            res = None
            self.root_ui.set_status(theme.TAGLINE)
            self.root_ui.add_nika("микрофон не отвечает: %s" % exc)
            return
        if res is not None and not res.ok:
            self.root_ui.set_status(theme.TAGLINE)
            self.root_ui.add_nika(res.message or "не смогла включить микрофон.")

    def _speech_result(self, text):
        Clock.schedule_once(lambda _dt: self._handle_speech(text), 0)

    def _handle_speech(self, text):
        self.root_ui.set_status(theme.TAGLINE)
        if not text:
            self.root_ui.add_nika(self.engine.p.pick([
                "не расслышала. повтори, пожалуйста.",
                "тихо как-то. скажи ещё раз?",
            ]))
            return
        self.root_ui.input.field.text = text
        self.send(text)

    # ---------- статус из фонового потока ----------
    def _status_from_thread(self, text):
        Clock.schedule_once(lambda _dt: self.root_ui.set_status(text), 0)

    # ---------- таймеры ----------
    def _add_timer(self, seconds, label):
        self.timers.append({"label": label, "end": time.time() + max(1, seconds)})
        self._update_timer_bar()

    def stop_timers(self, announce=True):
        had = bool(self.timers)
        self.timers = []
        self._update_timer_bar()
        if had and announce:
            self.root_ui.add_nika("остановила таймер.")

    def _update_timer_bar(self):
        if not self.timers:
            self.root_ui.set_timer("")
            return
        left = min(item["end"] for item in self.timers) - time.time()
        left = max(0, int(left))
        self.root_ui.set_timer("таймер  %02d:%02d" % (left // 60, left % 60))

    def _fire_timer(self, item):
        label = item.get("label", "таймер")
        self.root_ui.add_nika(self.engine.p.pick([
            "время вышло)",
            "всё, таймер закончился.",
            "дзынь! время вышло.",
        ]))
        try:
            self.bridge.notify("Nika — таймер", label + ": время вышло")
            self.bridge.vibrate(120)
        except Exception:
            pass
        self._speak("Время вышло")

    # ---------- напоминания ----------
    def _check_reminders(self):
        try:
            due = self.store.due_reminders()
        except Exception:
            return
        for reminder in due:
            text = reminder.get("text", "напоминание")
            self.root_ui.add_nika(self.engine.p.pick([
                "напоминаю: %s" % text,
                "не забыть: %s" % text,
            ]))
            try:
                self.bridge.notify("Nika напоминает", text)
                self.bridge.vibrate(150)
            except Exception:
                pass
            self._speak("Напоминаю: " + text)
            self.store.mark_reminder_done(reminder)
        if due:
            self._save()

    # ---------- ежесекундный тик ----------
    def _tick(self, _dt):
        now = time.time()
        if self.timers:
            alive = []
            for item in self.timers:
                if item["end"] <= now:
                    self._fire_timer(item)
                else:
                    alive.append(item)
            if len(alive) != len(self.timers):
                self.timers = alive
            self._update_timer_bar()
        self._flush_deferred()
        self._check_reminders()

    def _flush_deferred(self):
        try:
            items = self.engine.take_deferred()
        except Exception:
            return
        for item in items:
            threading.Thread(target=self._run_deferred, args=(item,), daemon=True).start()

    def _run_deferred(self, item):
        reply = None
        try:
            reply = item()
        except Exception as exc:
            reply = Reply("не получилось: %s" % exc)
        if isinstance(reply, Reply):
            Clock.schedule_once(lambda _dt: self._deliver(reply), 0)

    # ---------- «она сама пишет» ----------
    def _schedule_idle(self):
        delay = random.randint(20 * 60, 40 * 60)
        Clock.schedule_once(self._idle_tick, delay)

    def _idle_tick(self, _dt):
        try:
            if self.engine and self._busy == 0:
                reply = self.engine.idle_message()
                if reply and self.store.pref("notify", True):
                    self.root_ui.add_nika(reply.text)
                    self._save()
        finally:
            self._schedule_idle()

    # ---------- справка ----------
    def show_help(self):
        reply = self.engine.respond("что ты умеешь")
        self.root_ui.add_nika(reply.text)
        self.root_ui.set_chips(reply.chips)
        self._save()

    # ---------- кнопка «назад» ----------
    def _on_key(self, _window, key, *_args):
        if key == 27:  # аппаратная «назад» на Android и Esc на ПК
            field = self.root_ui.input.field
            if field.focus:
                field.focus = False
                return True
            return False
        return False


if __name__ == "__main__":
    NikaApp().run()
