"""Boatrace Open API（非公式、GitHub Pages の静的JSON）からの取得と変換（02_01 3章）。

https://boatraceopenapi.github.io/{kind}/v2/{YYYY}/{YYYYMMDD}.json
kind = programs（出走表）/ previews（直前情報）/ results（結果・払戻）
当日分は {kind}/v2/today.json（約10分間隔で更新）。
"""
from __future__ import annotations

import time

import requests

BASE = "https://boatraceopenapi.github.io"
MIN_INTERVAL = 1.0
RETRIES = 4

GRADE = {1: "SG", 2: "G1", 3: "G2", 4: "G3", 5: "一般", 6: "PG1"}
CLASS = {1: "A1", 2: "A2", 3: "B1", 4: "B2"}
PAYOUT_KEYS = {"win": "win", "place": "place", "exacta": "exacta", "quinella": "quinella",
               "quinella_place": "wide", "trifecta": "trifecta", "trio": "trio"}

PROGRAM_COLUMNS = [
    "date", "jcd", "rno", "deadline", "grade", "title", "race_type", "distance", "lane",
    "racer_id", "racer_name", "racer_class", "age", "weight", "branch",
    "flying", "late", "avg_st", "nat_win", "nat_2r", "nat_3r", "loc_win", "loc_2r", "loc_3r",
    "motor_no", "motor_2r", "motor_3r", "boat_no", "boat_2r", "boat_3r",
]
PREVIEW_COLUMNS = ["date", "jcd", "rno", "wind", "wind_dir", "wave", "weather", "temp", "water_temp",
                   "lane", "course", "ex_st", "ex_time", "weight", "weight_adj", "tilt"]
RESULT_COLUMNS = ["date", "jcd", "rno", "technique", "lane", "course", "st", "place", "racer_id"]
PAYOUT_COLUMNS = ["date", "jcd", "rno", "bet_type", "combo", "payout"]


class Client:
    def __init__(self, min_interval: float = MIN_INTERVAL):
        self.s = requests.Session()
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, kind: str, hd: str | None) -> list[dict] | None:
        """hd=None は当日分（today.json）。データが無ければ None。"""
        path = f"{kind}/v2/today.json" if hd is None else f"{kind}/v2/{hd[:4]}/{hd}.json"
        err = None
        for i in range(RETRIES + 1):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(f"{BASE}/{path}", timeout=60)
                if r.status_code == 404:
                    return None
                if r.status_code == 200:
                    return r.json().get(kind, [])
                err = f"HTTP {r.status_code}"
            except (requests.RequestException, ValueError) as e:
                err = str(e)
            time.sleep(min(60, 5 * 2 ** i))
        raise RuntimeError(f"取得に失敗しました: {path}: {err}")


def _date(s: str) -> str:
    return s.replace("-", "")[:8]


def _key(race: dict) -> dict:
    return {"date": _date(race["race_date"]), "jcd": f"{int(race['race_stadium_number']):02d}", "rno": int(race["race_number"])}


def _v(x):
    return "" if x is None else x


def program_rows(races: list[dict]) -> list[dict]:
    rows = []
    for r in races:
        k = _key(r)
        closed = str(r.get("race_closed_at") or "")
        base = {**k, "deadline": closed[11:16], "grade": GRADE.get(r.get("race_grade_number"), ""),
                "title": _v(r.get("race_title")), "race_type": _v(r.get("race_subtitle")),
                "distance": _v(r.get("race_distance"))}
        for b in r.get("boats") or []:
            rows.append({**base, "lane": b["racer_boat_number"], "racer_id": _v(b.get("racer_number")),
                         "racer_name": _v(b.get("racer_name")), "racer_class": CLASS.get(b.get("racer_class_number"), ""),
                         "age": _v(b.get("racer_age")), "weight": _v(b.get("racer_weight")),
                         "branch": _v(b.get("racer_branch_number")), "flying": _v(b.get("racer_flying_count")),
                         "late": _v(b.get("racer_late_count")), "avg_st": _v(b.get("racer_average_start_timing")),
                         "nat_win": _v(b.get("racer_national_top_1_percent")), "nat_2r": _v(b.get("racer_national_top_2_percent")),
                         "nat_3r": _v(b.get("racer_national_top_3_percent")), "loc_win": _v(b.get("racer_local_top_1_percent")),
                         "loc_2r": _v(b.get("racer_local_top_2_percent")), "loc_3r": _v(b.get("racer_local_top_3_percent")),
                         "motor_no": _v(b.get("racer_assigned_motor_number")), "motor_2r": _v(b.get("racer_assigned_motor_top_2_percent")),
                         "motor_3r": _v(b.get("racer_assigned_motor_top_3_percent")), "boat_no": _v(b.get("racer_assigned_boat_number")),
                         "boat_2r": _v(b.get("racer_assigned_boat_top_2_percent")), "boat_3r": _v(b.get("racer_assigned_boat_top_3_percent"))})
    return rows


def preview_rows(races: list[dict]) -> list[dict]:
    rows = []
    for r in races:
        base = {**_key(r), "wind": _v(r.get("race_wind")), "wind_dir": _v(r.get("race_wind_direction_number")),
                "wave": _v(r.get("race_wave")), "weather": _v(r.get("race_weather_number")),
                "temp": _v(r.get("race_temperature")), "water_temp": _v(r.get("race_water_temperature"))}
        for b in r.get("boats") or []:
            if b.get("racer_exhibition_time") in (None, 0) and b.get("racer_course_number") is None:
                continue
            rows.append({**base, "lane": b["racer_boat_number"], "course": _v(b.get("racer_course_number")),
                         "ex_st": _v(b.get("racer_start_timing")), "ex_time": _v(b.get("racer_exhibition_time")),
                         "weight": _v(b.get("racer_weight")), "weight_adj": _v(b.get("racer_weight_adjustment")),
                         "tilt": _v(b.get("racer_tilt_adjustment"))})
    return rows


def result_rows(races: list[dict]) -> tuple[list[dict], list[dict]]:
    res, pay = [], []
    for r in races:
        k = _key(r)
        for b in r.get("boats") or []:
            res.append({**k, "technique": _v(r.get("race_technique_number")), "lane": b["racer_boat_number"],
                        "course": _v(b.get("racer_course_number")), "st": _v(b.get("racer_start_timing")),
                        "place": _v(b.get("racer_place_number")), "racer_id": _v(b.get("racer_number"))})
        for src, bt in PAYOUT_KEYS.items():
            for p in (r.get("payouts") or {}).get(src) or []:
                if p.get("payout") is None:
                    continue
                pay.append({**k, "bet_type": bt, "combo": str(p.get("combination", "")).replace("=", "-"),
                            "payout": int(p["payout"])})
    return res, pay


# ---- 当日予想用：新しい統合API（api/v1、約10分間隔で更新、2026-01以降） ----
# https://boatraceopenapi.github.io/api/v1/{YYYY}/{YYYYMMDD}.json
# 旧 {kind}/v2 の当日分は直前情報が1日2〜3回しか更新されないため、当日予想はこちらを使う。
LIVE_PATH = "api/v1/{y}/{hd}.json"


def get_live(hd: str, session: requests.Session | None = None) -> tuple[list[dict], list[dict]]:
    """当日の (出走表の行, 直前情報の行) を旧形式と同じ列で返す。"""
    s = session or requests.Session()
    url = f"{BASE}/{LIVE_PATH.format(y=hd[:4], hd=hd)}"
    err = None
    for i in range(RETRIES + 1):
        try:
            r = s.get(url, timeout=60)
            if r.status_code == 404:
                return [], []
            if r.status_code == 200:
                return live_rows(r.json())
            err = f"HTTP {r.status_code}"
        except (requests.RequestException, ValueError) as e:
            err = str(e)
        time.sleep(min(60, 5 * 2 ** i))
    raise RuntimeError(f"取得に失敗しました: {url}: {err}")


def live_rows(d: dict) -> tuple[list[dict], list[dict]]:
    progs, prevs = [], []
    for st in ((d.get("programs") or {}).get("stadiums") or {}).values():
        for race in (st.get("races") or {}).values():
            k = {"date": _date(race["date"]), "jcd": f"{int(race['stadium_number']):02d}", "rno": int(race["race_number"])}
            closed = str(race.get("closed_at") or "")
            base = {**k, "deadline": closed[11:16], "grade": GRADE.get(race.get("grade_number"), ""),
                    "title": _v(race.get("title")), "race_type": _v(race.get("subtitle")), "distance": _v(race.get("distance"))}
            for lane, b in (race.get("racers") or {}).items():
                progs.append({**base, "lane": int(lane), "racer_id": _v(b.get("number")), "racer_name": _v(b.get("name")),
                              "racer_class": CLASS.get(b.get("rank_number"), ""), "age": _v(b.get("age")),
                              "weight": _v(b.get("weight")), "branch": _v(b.get("branch_number")),
                              "flying": _v(b.get("flying_count")), "late": _v(b.get("late_count")),
                              "avg_st": _v(b.get("average_start_timing")),
                              "nat_win": _v(b.get("national_win_rate")), "nat_2r": _v(b.get("national_top_2_percent")),
                              "nat_3r": _v(b.get("national_top_3_percent")), "loc_win": _v(b.get("local_win_rate")),
                              "loc_2r": _v(b.get("local_top_2_percent")), "loc_3r": _v(b.get("local_top_3_percent")),
                              "motor_no": _v(b.get("motor_number")), "motor_2r": _v(b.get("motor_top_2_percent")),
                              "motor_3r": _v(b.get("motor_top_3_percent")), "boat_no": _v(b.get("boat_number")),
                              "boat_2r": _v(b.get("boat_top_2_percent")), "boat_3r": _v(b.get("boat_top_3_percent"))})
            pv = race.get("preview") or {}
            pbase = {**k, "wind": _v(pv.get("wind_speed")), "wind_dir": _v(pv.get("wind_direction_number")),
                     "wave": _v(pv.get("wave_height")), "weather": _v(pv.get("weather_number")),
                     "temp": _v(pv.get("air_temperature")), "water_temp": _v(pv.get("water_temperature"))}
            for lane, b in (pv.get("racers") or {}).items():
                if b.get("exhibition_time") in (None, 0) and b.get("course_number") is None:
                    continue
                prevs.append({**pbase, "lane": int(lane), "course": _v(b.get("course_number")),
                              "ex_st": _v(b.get("start_timing")), "ex_time": _v(b.get("exhibition_time")),
                              "weight": _v(b.get("weight")), "weight_adj": _v(b.get("weight_adjustment")),
                              "tilt": _v(b.get("tilt_adjustment"))})
    return progs, prevs
