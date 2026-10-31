# -*- coding: utf-8 -*-
"""Мост Android: Intent'ы, контакты, звонки, TTS/STT, wi-fi, уведомления.

Всё обёрнуто в try/except: если на конкретном телефоне что-то недоступно,
Nika не падает, а честно говорит, что не получилось.
"""

import os
import re
import subprocess
import time

from .base import Bridge, Contact, Res
from ..wifi_parse import find_password, parse_wifi_config, parse_wpa_supplicant

try:
    from jnius import PythonJavaClass, autoclass, cast, java_method
    _JNIUS = True
except Exception:  # на ПК pyjnius нет
    _JNIUS = False

    class PythonJavaClass:  # заглушка, чтобы модуль импортировался
        pass

    def java_method(*_a, **_kw):
        def deco(fn):
            return fn
        return deco

    def autoclass(name):
        raise ImportError("pyjnius недоступен")

    def cast(name, obj):
        return obj


WIFI_CONFIG_PATHS = [
    "/data/misc/apexdata/com.android.wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml",
    "/data/misc/wifi/WifiConfigStore.xml.bak",
    "/data/misc/wifi/wpa_supplicant.conf",
    "/data/wifi/bcm_supp.conf",
]

# Индексы, которые нужны из Java
REQ_SPEECH = 0x4E4B


class _TTSListener(PythonJavaClass):
    __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
    __javacontext__ = "app"

    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    @java_method("(I)V")
    def onInit(self, status):
        try:
            self._callback(int(status) == 0)
        except Exception:
            pass


class AndroidBridge(Bridge):
    is_android = True
    platform_name = "android"
    can_call = True
    can_contacts = True
    can_apps = True
    can_wifi_passwords = True
    can_voice = True
    can_notify = True

    NOTIF_CHANNEL = "nika_messages"
    NOTIF_ID = 4101

    def __init__(self):
        super().__init__()
        self._ok = _JNIUS
        self._ctx = None
        self._tts = None
        self._tts_ready = False
        self._listen_cb = None
        self._torch_id = None
        self._torch_on = False
        self._bound = False
        if not _JNIUS:
            return
        self._init_context()
        self._emit("init", "ctx=%s" % bool(self._ctx))
        self._init_tts()
        self._bind_activity_result()

    # ------------------------------------------------------------------
    #  Служебное
    # ------------------------------------------------------------------
    @staticmethod
    def _emit(tag, message):
        try:
            print("[Nika/android] %s: %s" % (tag, message))
        except Exception:
            pass

    def _init_context(self):
        try:
            from android import mActivity
            if mActivity is not None:
                self._ctx = mActivity
        except Exception:
            self._ctx = None
        if self._ctx is None:
            try:
                self._ctx = autoclass("org.kivy.android.PythonActivity").mActivity
            except Exception:
                self._ctx = None

    def ready(self):
        return bool(self._ok and self._ctx is not None)

    def info(self):
        model = ""
        version = ""
        try:
            Build = autoclass("android.os.Build")
            model = "%s %s" % (str(Build.MANUFACTURER), str(Build.MODEL))
            version = "Android %s" % str(autoclass("android.os.Build$VERSION").RELEASE)
        except Exception:
            pass
        return {"platform": self.platform_name, "android": True,
                "model": model.strip(), "version": version}

    def _intent(self, action):
        Intent = autoclass("android.content.Intent")
        return Intent(action)

    def _start(self, intent):
        Intent = autoclass("android.content.Intent")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        self._ctx.startActivity(intent)

    @staticmethod
    def _is_missing_intent(exc):
        text = str(exc)
        return "ActivityNotFound" in text or "ActivityNotFound" in repr(exc)

    # ------------------------------------------------------------------
    #  Ссылки, приложения, магазин
    # ------------------------------------------------------------------
    def open_url(self, url):
        try:
            from urllib.parse import quote
            safe_url = quote(url, safe=":/?&=#%+@!$'()*,;[]~")
            Uri = autoclass("android.net.Uri")
            Intent = autoclass("android.content.Intent")
            self._start(Intent(Intent.ACTION_VIEW, Uri.parse(safe_url)))
            return Res(True, "", url)
        except Exception as exc:
            return Res(False, "не смогла открыть ссылку: %s" % exc)

    def app_installed(self, package):
        if not package:
            return False
        try:
            self._ctx.getPackageManager().getPackageInfo(package, 0)
            return True
        except Exception:
            return False

    def installed_apps(self):
        cached = self.cached_apps()
        if cached is not None:
            return cached
        apps = []
        try:
            pm = self._ctx.getPackageManager()
            infos = pm.getInstalledApplications(0)
            count = infos.size() if infos is not None else 0
            for i in range(count):
                info = infos.get(i)
                try:
                    label = str(pm.getApplicationLabel(info))
                except Exception:
                    label = ""
                try:
                    package = str(info.packageName)
                except Exception:
                    package = ""
                if label and package:
                    apps.append((label, package))
        except Exception as exc:
            self._emit("apps", exc)
        self.touch_apps_cache(apps)
        return apps

    def launch_package(self, package):
        try:
            intent = self._ctx.getPackageManager().getLaunchIntentForPackage(package)
            if intent is None:
                return Res(False, "не установлено")
            self._start(intent)
            return Res(True)
        except Exception as exc:
            return Res(False, str(exc))

    def open_play_store(self, package):
        try:
            Uri = autoclass("android.net.Uri")
            Intent = autoclass("android.content.Intent")
            self._start(Intent(Intent.ACTION_VIEW,
                               Uri.parse("market://details?id=%s" % package)))
            return Res(True)
        except Exception:
            return self.open_url("https://play.google.com/store/apps/details?id=%s" % package)

    # ------------------------------------------------------------------
    #  Контакты и звонки
    # ------------------------------------------------------------------
    def contacts(self):
        cached = self.cached_contacts()
        if cached is not None:
            return cached
        if not self.has_permission("READ_CONTACTS"):
            return []
        result = []
        seen = set()
        try:
            Phone = autoclass(
                "android.provider.ContactsContract$CommonDataKinds$Phone")
            resolver = self._ctx.getContentResolver()
            cursor = resolver.query(Phone.CONTENT_URI, None, None, None, None)
            if cursor is not None:
                idx_name = cursor.getColumnIndex("display_name")
                idx_number = cursor.getColumnIndex("data1")
                while cursor.moveToNext():
                    name = cursor.getString(idx_name) if idx_name >= 0 else ""
                    number = cursor.getString(idx_number) if idx_number >= 0 else ""
                    name = (name or "").strip()
                    number = (number or "").strip()
                    if not number:
                        continue
                    digits = re.sub(r"\D", "", number)
                    key = (name.lower(), digits[-10:])
                    if key in seen:
                        continue
                    seen.add(key)
                    from .. import nlp
                    result.append(Contact(name=name or number,
                                          number=nlp.normalize_phone(number) or number,
                                          raw_number=number))
                cursor.close()
        except Exception as exc:
            self._emit("contacts", exc)
        self.touch_contacts_cache(result)
        return result

    def dial(self, number, direct=False):
        if not number:
            return Res(False, "не поняла номер.")
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        if direct and self.has_permission("CALL_PHONE"):
            try:
                self._start(Intent(Intent.ACTION_CALL, Uri.parse("tel:" + number)))
                return Res(True, "звоню")
            except Exception:
                pass
        try:
            self._start(Intent(Intent.ACTION_DIAL, Uri.parse("tel:" + number)))
            return Res(True, "набираю")
        except Exception as exc:
            return Res(False, "не смогла открыть номеронабиратель: %s" % exc)

    def send_sms(self, number, text):
        try:
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            intent = Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:" + number))
            if text:
                intent.putExtra("sms_body", text)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть сообщения: %s" % exc)

    # ------------------------------------------------------------------
    #  Медиа
    # ------------------------------------------------------------------
    def _media_uri(self, query, video=False):
        try:
            resolver = self._ctx.getContentResolver()
            if video:
                Media = autoclass("android.provider.MediaStore$Video$Media")
            else:
                Media = autoclass("android.provider.MediaStore$Audio$Media")
            collection = Media.EXTERNAL_CONTENT_URI
            cursor = resolver.query(collection, None, "_display_name LIKE ?",
                                    ["%" + query + "%"], None)
            if cursor is None or not cursor.moveToFirst():
                if cursor is not None:
                    cursor.close()
                return None, ""
            idx_id = cursor.getColumnIndex("_id")
            idx_title = cursor.getColumnIndex("_display_name")
            media_id = cursor.getLong(idx_id) if idx_id >= 0 else 0
            title = str(cursor.getString(idx_title)) if idx_title >= 0 else query
            cursor.close()
            ContentUris = autoclass("android.content.ContentUris")
            return ContentUris.withAppendedId(collection, media_id), title
        except Exception as exc:
            self._emit("media", exc)
            return None, ""

    def play_media(self, query="", video=False):
        uri = None
        title = ""
        if query:
            uri, title = self._media_uri(query, video)
        if uri is not None:
            try:
                Intent = autoclass("android.content.Intent")
                intent = Intent(Intent.ACTION_VIEW)
                intent.setDataAndType(uri, "video/*" if video else "audio/*")
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                self._start(intent)
                return Res(True, "включаю", {"source": "local", "title": title})
            except Exception as exc:
                self._emit("play_media", exc)

        # в памяти не нашлось — открываем ютуб (или ютуб мьюзик для музыки)
        search = "https://m.youtube.com/results?search_query=" + query.replace(" ", "+")
        if not query:
            search = "https://m.youtube.com"
        if video or not query:
            if self.app_installed("com.google.android.youtube"):
                if self.launch_package("com.google.android.youtube").ok:
                    return Res(True, "открываю ютуб", {"source": "youtube"})
        if not query:
            yt = "com.google.android.apps.youtube.music"
            if self.app_installed(yt) and yt:
                if self.launch_package(yt).ok:
                    return Res(True, "открываю ютуб мьюзик", {"source": "youtube-music"})
        opened = self.open_url(search)
        if opened.ok:
            return Res(True, "ищу в ютубе", {"source": "web", "query": query})
        return Res(False, "не нашла «%s» ни в памяти, ни в ютубе." % query)

    # ------------------------------------------------------------------
    #  Будильник, фонарик, батарея, звук, настройки
    # ------------------------------------------------------------------
    def set_alarm(self, hour, minute, label=""):
        try:
            AlarmClock = autoclass("android.provider.AlarmClock")
            intent = self._intent(AlarmClock.ACTION_SET_ALARM)
            intent.putExtra(AlarmClock.EXTRA_HOUR, int(hour))
            intent.putExtra(AlarmClock.EXTRA_MINUTES, int(minute))
            intent.putExtra(AlarmClock.EXTRA_SKIP_UI, False)
            if label:
                intent.putExtra(AlarmClock.EXTRA_MESSAGE, label)
            self._start(intent)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть будильник: %s" % exc)

    def torch(self, on):
        try:
            Context = autoclass("android.content.Context")
            CameraManager = autoclass("android.hardware.camera2.CameraManager")
            manager = self._ctx.getSystemService(Context.CAMERA_SERVICE)
            if self._torch_id is None:
                ids = manager.getCameraIdList()
                self._torch_id = ids[0] if ids is not None and len(ids) else None
            if not self._torch_id:
                return Res(False, "не нашла вспышку.")
            manager.setTorchMode(self._torch_id, bool(on))
            self._torch_on = bool(on)
            return Res(True, "")
        except Exception as exc:
            return Res(False, "фонарик не поддался: %s" % exc)

    def battery(self):
        try:
            Intent = autoclass("android.content.Intent")
            IntentFilter = autoclass("android.content.IntentFilter")
            sticky = self._ctx.registerReceiver(None, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
            if sticky is None:
                return {}
            level = sticky.getIntExtra("level", -1)
            scale = sticky.getIntExtra("scale", 100)
            status = sticky.getIntExtra("status", -1)
            plugged = sticky.getIntExtra("plugged", -1)
            if level < 0:
                return {}
            percent = int(round(level * 100.0 / (scale or 100)))
            return {"percent": percent,
                    "charging": status == 2 or plugged > 0}
        except Exception:
            return {}

    def volume(self, direction):
        try:
            Context = autoclass("android.content.Context")
            AudioManager = autoclass("android.media.AudioManager")
            am = self._ctx.getSystemService(Context.AUDIO_SERVICE)
            if am is None:
                return Res(False, "не нашла регулятор звука.")
            stream = AudioManager.STREAM_MUSIC
            if direction == "up":
                am.adjustStreamVolume(stream, AudioManager.ADJUST_RAISE, AudioManager.FLAG_SHOW_UI)
            elif direction == "down":
                am.adjustStreamVolume(stream, AudioManager.ADJUST_LOWER, AudioManager.FLAG_SHOW_UI)
            elif direction == "mute":
                am.setStreamVolume(stream, 0, AudioManager.FLAG_SHOW_UI)
            elif direction == "max":
                am.setStreamVolume(stream, am.getStreamMaxVolume(stream), AudioManager.FLAG_SHOW_UI)
            level = int(am.getStreamVolume(stream))
            top = int(am.getStreamMaxVolume(stream)) or 1
            return Res(True, "%d%%" % int(round(level * 100.0 / top)))
        except Exception as exc:
            return Res(False, "звук не поддался: %s" % exc)

    def open_settings(self, page=""):
        try:
            Settings = autoclass("android.provider.Settings")
            actions = {
                "wifi": "ACTION_WIFI_SETTINGS",
                "apps": "ACTION_APPLICATION_SETTINGS",
                "bluetooth": "ACTION_BLUETOOTH_SETTINGS",
                "display": "ACTION_DISPLAY_SETTINGS",
                "sound": "ACTION_SOUND_SETTINGS",
                "battery": "ACTION_BATTERY_SAVER_SETTINGS",
                "location": "ACTION_LOCATION_SOURCE_SETTINGS",
                "data": "ACTION_DATA_ROAMING_SETTINGS",
                "notification": "ACTION_NOTIFICATION_SETTINGS",
            }
            name = actions.get(page or "", "ACTION_SETTINGS")
            action = getattr(Settings, name, Settings.ACTION_SETTINGS)
            Intent = autoclass("android.content.Intent")
            self._start(Intent(action))
            return Res(True, "")
        except Exception as exc:
            return Res(False, "не смогла открыть настройки: %s" % exc)

    # ------------------------------------------------------------------
    #  Уведомления и вибрация
    # ------------------------------------------------------------------
    def _notification_manager(self):
        Context = autoclass("android.content.Context")
        return self._ctx.getSystemService(Context.NOTIFICATION_SERVICE)

    def notify(self, title, text):
        try:
            Build = autoclass("android.os.Build$VERSION")
            sdk = int(Build.SDK_INT)
            Context = autoclass("android.content.Context")
            manager = self._notification_manager()
            if manager is None:
                return Res(False, "")
            if sdk >= 33 and not self.has_permission("POST_NOTIFICATIONS"):
                return Res(False, "нет разрешения на уведомления")

            NotificationBuilder = autoclass("android.app.Notification$Builder")
            if sdk >= 26:
                Channel = autoclass("android.app.NotificationChannel")
                channel = Channel(self.NOTIF_CHANNEL, "Nika", 3)
                manager.createNotificationChannel(channel)
                builder = NotificationBuilder(self._ctx, self.NOTIF_CHANNEL)
            else:
                builder = NotificationBuilder(self._ctx)

            icon = autoclass("android.R$drawable").ic_dialog_info
            builder.setContentTitle(str(title))
            builder.setContentText(str(text))
            builder.setSmallIcon(icon)
            builder.setAutoCancel(True)
            try:
                builder.setShowWhen(True)
            except Exception:
                pass
            manager.notify(self.NOTIF_ID, builder.build())
            return Res(True, "")
        except Exception as exc:
            self._emit("notify", exc)
            return Res(False, str(exc))

    def vibrate(self, ms=40):
        try:
            Context = autoclass("android.content.Context")
            Vibrator = autoclass("android.os.Vibrator")
            vibrator = self._ctx.getSystemService(Context.VIBRATOR_SERVICE)
            if vibrator is None:
                return Res(False, "")
            Build = autoclass("android.os.Build$VERSION")
            if int(Build.SDK_INT) >= 26:
                VibrationEffect = autoclass("android.os.VibrationEffect")
                vibrator.vibrate(VibrationEffect.createOneShot(int(ms), -1))
            else:
                vibrator.vibrate(int(ms))
            return Res(True, "")
        except Exception:
            return Res(False, "")

    # ------------------------------------------------------------------
    #  Голос
    # ------------------------------------------------------------------
    def _init_tts(self):
        try:
            TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
            self._tts = TextToSpeech(self._ctx, _TTSListener(self._on_tts_ready))
        except Exception as exc:
            self._emit("tts", exc)
            self._tts = None

    def _on_tts_ready(self, ok):
        self._tts_ready = bool(ok)
        if not ok or self._tts is None:
            return
        try:
            Locale = autoclass("java.util.Locale")
            self._tts.setLanguage(Locale("ru", "RU"))
            self._tts.setSpeechRate(0.97)
            self._tts.setPitch(1.04)
        except Exception as exc:
            self._emit("tts_lang", exc)

    def speak(self, text):
        if not text:
            return Res(False, "")
        if self._tts is None or not self._tts_ready:
            return Res(False, "")
        try:
            Bundle = autoclass("android.os.Bundle")
            self._tts.speak(text, 0, Bundle(), "nika-%d" % int(time.time() * 1000))
            return Res(True, "")
        except Exception:
            try:
                self._tts.speak(text, 0, None)
                return Res(True, "")
            except Exception as exc:
                self._emit("speak", exc)
                return Res(False, "")

    def stop_speak(self):
        try:
            if self._tts is not None:
                self._tts.stop()
            return Res(True, "")
        except Exception:
            return Res(False, "")

    def _bind_activity_result(self):
        try:
            from android import activity
            activity.bind(on_activity_result=self._on_activity_result)
            self._bound = True
        except Exception as exc:
            self._emit("activity_bind", exc)
            self._bound = False

    def _on_activity_result(self, request_code, result_code, intent):
        try:
            if int(request_code) != REQ_SPEECH:
                return
            text = None
            if int(result_code) == -1 and intent is not None:
                try:
                    results = intent.getStringArrayListExtra("android.speech.extra.RESULTS")
                    if results is not None and results.size() > 0:
                        text = str(results.get(0))
                except Exception:
                    text = None
            callback = self._listen_cb
            self._listen_cb = None
            if callback:
                callback(text)
        except Exception as exc:
            self._emit("activity_result", exc)

    def listen(self, callback):
        if not self.has_permission("RECORD_AUDIO"):
            def after_grant(ok):
                if ok:
                    self.listen(callback)
                else:
                    callback(None)
            self.request_permissions(["RECORD_AUDIO"], after_grant)
            return Res(True, "")
        try:
            RecognizerIntent = autoclass("android.speech.RecognizerIntent")
            Intent = autoclass("android.content.Intent")
            intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                            RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ru-RU")
            intent.putExtra(RecognizerIntent.EXTRA_PROMPT, "Говори, я слушаю")
            intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
            self._listen_cb = callback
            self._ctx.startActivityForResult(intent, REQ_SPEECH)
            return Res(True, "")
        except Exception as exc:
            self._emit("listen", exc)
            self._listen_cb = None
            return Res(False, "не смогла включить микрофон: %s" % exc)

    # ------------------------------------------------------------------
    #  Wi-Fi
    # ------------------------------------------------------------------
    def _wifi_manager(self):
        try:
            Context = autoclass("android.content.Context")
            return self._ctx.getApplicationContext().getSystemService(Context.WIFI_SERVICE)
        except Exception:
            return None

    def wifi_saved(self):
        manager = self._wifi_manager()
        if manager is None:
            return []
        names = []
        try:
            networks = manager.getConfiguredNetworks()
            if networks is None:
                return []
            count = networks.size()
            for i in range(count):
                network = networks.get(i)
                ssid = str(network.SSID or "").strip().strip('"')
                if ssid and ssid not in names:
                    names.append(ssid)
        except Exception as exc:
            self._emit("wifi_saved", exc)
        return names

    def wifi_info(self):
        manager = self._wifi_manager()
        info = {}
        if manager is None:
            return info
        try:
            current = manager.getConnectionInfo()
            if current is not None:
                ssid = str(current.getSSID() or "").strip().strip('"')
                if ssid and ssid not in ("<unknown ssid>", "0x", "unknown"):
                    info["ssid"] = ssid
                rssi = int(current.getRssi())
                if rssi < 0:
                    info["rssi"] = rssi
                ip_int = int(current.getIpAddress())
                if ip_int:
                    info["ip"] = "%d.%d.%d.%d" % (
                        ip_int & 0xFF, (ip_int >> 8) & 0xFF,
                        (ip_int >> 16) & 0xFF, (ip_int >> 24) & 0xFF)
        except Exception as exc:
            self._emit("wifi_info", exc)
        info["connected"] = bool(info.get("ssid"))
        saved = self.wifi_saved()
        if saved:
            info["saved"] = saved
        return info

    def _root_cat(self, path):
        commands = [
            ["su", "-c", "cat '%s'" % path],
            ["su", "-c", "cat %s" % path],
        ]
        for command in commands:
            try:
                proc = subprocess.run(command, capture_output=True, timeout=8)
                if proc.returncode == 0 and proc.stdout:
                    return proc.stdout.decode("utf-8", errors="replace")
            except Exception:
                continue
        try:
            with os.popen("su -c 'cat %s' 2>/dev/null" % path) as handle:
                data = handle.read()
            if data and "No such file" not in data:
                return data
        except Exception:
            pass
        return ""

    def _read_wifi_config(self):
        for path in WIFI_CONFIG_PATHS:
            text = self._root_cat(path)
            if text and ("<Network>" in text or "network={" in text or "network = {" in text):
                return text, path
        return "", ""

    def wifi_password(self, ssid):
        text, path = self._read_wifi_config()
        if not text:
            return None, ""
        try:
            if path.endswith(".xml"):
                mapping = parse_wifi_config(text)
            else:
                mapping = parse_wpa_supplicant(text)
        except Exception:
            return None, ""
        password = find_password(mapping, ssid)
        if password:
            return password, "root"
        return None, ""

    # ------------------------------------------------------------------
    #  Права
    # ------------------------------------------------------------------
    def has_permission(self, name):
        try:
            from android.permissions import Permission, check_permission
            value = getattr(Permission, name, None)
            if value is None:
                return False
            return bool(check_permission(value))
        except Exception:
            return False

    def request_permissions(self, names, callback):
        try:
            from android.permissions import Permission, request_permissions
            values = [getattr(Permission, n) for n in names if hasattr(Permission, n)]
            if not values:
                callback(False)
                return Res(False, "таких прав нет")

            def _done(permissions, grants):
                try:
                    callback(bool(grants) and all(bool(g) for g in grants))
                except Exception:
                    pass

            request_permissions(values, _done)
            return Res(True, "")
        except Exception as exc:
            try:
                callback(False)
            except Exception:
                pass
            return Res(False, str(exc))
