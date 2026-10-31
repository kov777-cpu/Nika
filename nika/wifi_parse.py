# -*- coding: utf-8 -*-
"""Разбор сохранённых wi-fi конфигов Android (нужен root).

Файлы, где Android хранит сети:
    /data/misc/apexdata/com.android.wifi/WifiConfigStore.xml   (Android 11+)
    /data/misc/wifi/WifiConfigStore.xml                        (Android 9-10)
    /data/misc/wifi/wpa_supplicant.conf                        (старые версии)

Модуль чистый: его можно тестировать на компьютере на образцах файлов.
"""

import html
import re

# <string name="SSID">&quot;MyNet&quot;</string>
_XML_SSID = re.compile(r'<string name="SSID">(.*?)</string>', re.DOTALL)
_XML_PSK = re.compile(r'<string name="PreSharedKey">(.*?)</string>', re.DOTALL)
_XML_NETWORK = re.compile(r"<Network>(.*?)</Network>", re.DOTALL)


def _unquote(value):
    """Раскодирует &quot;...&quot; и снимает кавычки."""
    if value is None:
        return ""
    text = html.unescape(value).strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1]
    return text


def _decode_psk(text):
    """PreSharedKey может быть открытым текстом или hex-строкой."""
    text = _unquote(text)
    if not text:
        return ""
    if text.startswith("0x") or (len(text) >= 32 and re.fullmatch(r"[0-9a-fA-F]+", text)):
        raw = text[2:] if text.startswith("0x") else text
        try:
            decoded = bytes.fromhex(raw).decode("utf-8", errors="replace")
            if decoded and all(32 <= ord(ch) < 127 or ord(ch) > 0x400 for ch in decoded):
                return decoded
        except ValueError:
            pass
    return text


def parse_wifi_config(text):
    """Возвращает {ssid: пароль} из WifiConfigStore.xml."""
    result = {}
    if not text:
        return result
    for block in _XML_NETWORK.findall(text):
        ssid_match = _XML_SSID.search(block)
        if not ssid_match:
            continue
        ssid = _unquote(ssid_match.group(1))
        if not ssid or ssid.startswith("<") and ssid.endswith(">"):
            continue
        psk_match = _XML_PSK.search(block)
        psk = _decode_psk(psk_match.group(1)) if psk_match else ""
        if ssid not in result or (not result[ssid] and psk):
            result[ssid] = psk
    return result


def parse_wpa_supplicant(text):
    """Возвращает {ssid: пароль} из wpa_supplicant.conf."""
    result = {}
    if not text:
        return result
    for block in re.findall(r"network\s*=\s*\{(.*?)\}", text, re.DOTALL):
        ssid_match = re.search(r'ssid\s*=\s*"((?:[^"\\]|\\.)*)"', block)
        if not ssid_match:
            ssid_match = re.search(r"ssid\s*=\s*([^\s]+)", block)
        if not ssid_match:
            continue
        ssid = ssid_match.group(1).replace('\\"', '"')
        psk_match = re.search(r'psk\s*=\s*"((?:[^"\\]|\\.)*)"', block)
        if not psk_match:
            psk_match = re.search(r"psk\s*=\s*([0-9a-fA-F]{32,})", block)
        psk = psk_match.group(1).replace('\\"', '"') if psk_match else ""
        result[ssid] = psk
    return result


def find_password(mapping, ssid):
    """Ищет сеть без учёта регистра, снимая кавычки с обоих сторон."""
    if not mapping or not ssid:
        return None
    target = ssid.strip().strip('"').lower()
    for name, psk in mapping.items():
        if name.strip().strip('"').lower() == target:
            return psk or None
    return None
