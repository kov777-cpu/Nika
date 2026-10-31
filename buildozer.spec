[app]

# ---------- имя и пакет ----------
title = Nika
package.name = nika
package.domain = org.nikaassistant

# ---------- исходники ----------
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt
source.exclude_dirs = tests,docs,tools,.github,__pycache__,.venv,venv,build,bin
source.exclude_patterns = *.pyc,*.md,*.spec

version = 2.0.0

# ---------- зависимости ----------
# pyjnius — мост к Android (Intent'ы, контакты, TTS, wi-fi)
# android — права, activity, запуск
# certifi — чтобы https-погода работала с проверкой сертификата
requirements = python3==3.13.9, hostpython3==3.13.9, kivy==2.3.1, pyjnius, android, certifi, charset_normalizer==3.3.2

# ---------- иконки ----------
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #0d0d0f

orientation = portrait
fullscreen = 0

# ---------- Android ----------
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True
android.enable_androidx = True
# Ограничивает количество параллельных задач при сборке
android.num_jobs = 1
# Зачем каждое право:
#   INTERNET, ACCESS_NETWORK_STATE   — поиск, погода
#   ACCESS_WIFI_STATE, CHANGE_WIFI_STATE, ACCESS_FINE_LOCATION/COARSE
#                                    — имя текущей сети и сигнал (Android 8+ требует геолокацию)
#   CALL_PHONE                       — прямой звонок, если включить «звонить сразу»
#   READ_CONTACTS                    — «позвони маме»
#   SEND_SMS                         — «напиши смс»
#   RECORD_AUDIO                     — голосовой ввод
#   CAMERA                           — вспышка-фонарик на части прошивок
#   POST_NOTIFICATIONS, VIBRATE      — таймеры и напоминания
#   QUERY_ALL_PACKAGES               — «открой <приложение>» по названию
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_STATE,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,CALL_PHONE,READ_CONTACTS,SEND_SMS,RECORD_AUDIO,CAMERA,POST_NOTIFICATIONS,VIBRATE,QUERY_ALL_PACKAGES,FOREGROUND_SERVICE

android.allow_python3 = True

[buildozer]
log_level = 2
warn_on_root = 1
android.minapi = 24
p4a.bootstrap = sdl2
