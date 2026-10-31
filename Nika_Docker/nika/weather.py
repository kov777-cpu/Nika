# -*- coding: utf-8 -*-
"""Погода через open-meteo: без ключей и регистрации.

Модуль чистый: http_get можно подменить в тестах.
"""

import json
import urllib.parse
import urllib.request

GEO_URL = ("https://geocoding-api.open-meteo.com/v1/search"
           "?name=%s&count=1&language=ru&format=json")
FORECAST_URL = ("https://api.open-meteo.com/v1/forecast"
                "?latitude=%s&longitude=%s"
                "&current=temperature_2m,apparent_temperature,relative_humidity_2m,"
                "weather_code,wind_speed_10m,is_day,precipitation"
                "&daily=temperature_2m_max,temperature_2m_min,weather_code"
                "&timezone=auto&forecast_days=2")

WEATHER_CODES = {
    0: "ясно",
    1: "почти ясно",
    2: "переменная облачность",
    3: "пасмурно",
    45: "туман",
    48: "изморозь",
    51: "слабая морось",
    53: "морось",
    55: "сильная морось",
    56: "ледяная морось",
    57: "ледяная морось",
    61: "небольшой дождь",
    63: "дождь",
    65: "сильный дождь",
    66: "ледяной дождь",
    67: "ледяной дождь",
    71: "небольшой снег",
    73: "снег",
    75: "сильный снег",
    77: "снежная крупа",
    80: "небольшой ливень",
    81: "ливень",
    82: "сильный ливень",
    85: "снегопад",
    86: "сильный снегопад",
    95: "гроза",
    96: "гроза с градом",
    99: "сильная гроза с градом",
}


def _default_http(url):
    context = None
    try:
        import ssl

        context = ssl.create_default_context()
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    except Exception:
        context = None
    request = urllib.request.Request(url, headers={
        "User-Agent": "Nika/1.0 (Android; +https://example.invalid)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=9, context=context) as response:
        return response.read().decode("utf-8", "replace")


class Weather:
    def __init__(self, http_get=None, timeout=9):
        self.http_get = http_get or _default_http
        self.timeout = timeout
        self._cache = {}

    # ---------- сеть ----------
    def _get_json(self, url):
        raw = self.http_get(url)
        return json.loads(raw)

    def geocode(self, city):
        city = (city or "").strip()
        if not city:
            return None
        key = "geo:" + city.lower()
        if key in self._cache:
            return self._cache[key]
        try:
            data = self._get_json(GEO_URL % urllib.parse.quote(city))
        except Exception:
            return None
        results = (data or {}).get("results") or []
        if not results:
            return None
        first = results[0]
        place = {
            "name": first.get("name") or city,
            "country": first.get("country") or "",
            "lat": first.get("latitude"),
            "lon": first.get("longitude"),
        }
        self._cache[key] = place
        return place

    def report(self, city):
        """Возвращает словарь с погодой или None."""
        place = self.geocode(city)
        if not place or place.get("lat") is None:
            return None
        key = "fc:%s:%s" % (place["lat"], place["lon"])
        if key in self._cache:
            return self._cache[key]
        try:
            data = self._get_json(FORECAST_URL % (place["lat"], place["lon"]))
        except Exception:
            return None
        current = (data or {}).get("current") or {}
        daily = (data or {}).get("daily") or {}
        if not current:
            return None
        code = int(current.get("weather_code") or 0)
        result = {
            "city": place["name"],
            "temp": current.get("temperature_2m"),
            "feels": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "wind": current.get("wind_speed_10m"),
            "desc": WEATHER_CODES.get(code, "непонятная погода"),
            "precip": current.get("precipitation") or 0,
            "is_day": bool(current.get("is_day", 1)),
        }
        try:
            highs = daily.get("temperature_2m_max") or []
            lows = daily.get("temperature_2m_min") or []
            codes = daily.get("weather_code") or []
            if highs:
                result["tmax"] = highs[0]
            if lows:
                result["tmin"] = lows[0]
            if len(highs) > 1:
                result["tomorrow_max"] = highs[1]
            if len(lows) > 1:
                result["tomorrow_min"] = lows[1]
            if len(codes) > 1:
                result["tomorrow_desc"] = WEATHER_CODES.get(int(codes[1]), "")
        except Exception:
            pass
        self._cache[key] = result
        return result

    # ---------- текст ----------
    @staticmethod
    def _round(value):
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None

    def format_report(self, data):
        """Короткий человеческий ответ."""
        if not data:
            return ""
        temp = self._round(data.get("temp"))
        feels = self._round(data.get("feels"))
        wind = self._round(data.get("wind"))
        lines = []
        head = "%s — сейчас %s°C, %s" % (data.get("city", ""), temp, data.get("desc", ""))
        lines.append(head)
        if feels is not None and temp is not None and abs(feels - temp) >= 2:
            lines.append("ощущается как %d°" % feels)
        if wind is not None:
            if wind >= 10:
                lines.append("ветер %d м/с — держи шапку" % wind)
            elif wind >= 5:
                lines.append("ветер %d м/с" % wind)
        high, low = self._round(data.get("tmax")), self._round(data.get("tmin"))
        if high is not None and low is not None:
            lines.append("днём %d°, ночью %d°" % (high, low))
        tomorrow_high = self._round(data.get("tomorrow_max"))
        if tomorrow_high is not None:
            tomorrow_low = self._round(data.get("tomorrow_min"))
            tail = "завтра %d°" % tomorrow_high
            if tomorrow_low is not None:
                tail += "…%d°" % tomorrow_low
            if data.get("tomorrow_desc"):
                tail += ", " + data["tomorrow_desc"]
            lines.append(tail)
        return "\n".join(lines)
