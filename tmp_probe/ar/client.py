"""autorace.jp の JSON API クライアント（ページ表示と同じ手順: GETでセッション/XSRF取得 → POST）。"""
import time
import urllib.parse

import requests

BASE = "https://autorace.jp"
PLACES = {2: "kawaguchi", 3: "isesaki", 4: "hamamatsu", 5: "iizuka", 6: "sanyou", 1: "funabashi"}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"


class Client:
    def __init__(self, interval=1.0):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ja"})
        self.interval = interval
        self._last = 0.0
        self._ready = False

    def _wait(self):
        d = time.time() - self._last
        if d < self.interval:
            time.sleep(self.interval - d)
        self._last = time.time()

    def _init_session(self):
        self._wait()
        r = self.s.get(f"{BASE}/race_info/RaceResult/kawaguchi/2025-11-04_1", timeout=30)
        r.raise_for_status()
        self._ready = True

    def _xsrf(self):
        return urllib.parse.unquote(self.s.cookies.get("XSRF-TOKEN", domain="autorace.jp") or self.s.cookies.get("XSRF-TOKEN") or "")

    def calendar(self, ym):
        """ym='YYYY-MM' → 開催日程 JSON"""
        self._wait()
        r = self.s.get(f"{BASE}/race_info/XML/Calendar", params={"date": ym}, timeout=30)
        r.raise_for_status()
        return r.json()

    def post(self, endpoint, place_code, race_date, race_no, retries=3):
        """endpoint: RaceResult / Odds / Program / OtherRaceInfo"""
        for attempt in range(retries):
            if not self._ready:
                self._init_session()
            self._wait()
            r = self.s.post(
                f"{BASE}/race_info/{endpoint}",
                json={"placeCode": place_code, "raceDate": race_date, "raceNo": race_no},
                headers={"X-XSRF-TOKEN": self._xsrf(), "X-Requested-With": "XMLHttpRequest",
                         "Referer": f"{BASE}/race_info/{endpoint}/{PLACES.get(place_code,'kawaguchi')}/{race_date}_{race_no}"},
                timeout=30,
            )
            if r.status_code == 419:  # CSRF 切れ → セッション取り直し
                self._ready = False
                continue
            if r.status_code >= 500 or r.status_code == 429:
                time.sleep(10 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"{endpoint} {place_code} {race_date} {race_no}: 取得失敗 status={r.status_code}")
