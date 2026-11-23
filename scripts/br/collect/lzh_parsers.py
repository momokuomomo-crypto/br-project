"""番組表（B）・競走成績（K）テキストの解析（02_01 3章）。

公式の一括ダウンロード（LZH、Shift_JIS、固定長テキスト）を行単位で
NFKC正規化（全角数字・英字・空白を半角へ）してから正規表現で読む。
"""
from __future__ import annotations

import re
import unicodedata

from br.venues import NAME_TO_JCD


def _norm(line: str) -> str:
    return unicodedata.normalize("NFKC", line).rstrip()


_BLOCK = re.compile(r"^(\d{2})([BK])BGN")
_DATE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")

# ---------------------------------------------------------------- 番組表（B）

_B_RACE = re.compile(
    r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d{3,4})m.*?(\d{1,2}):(\d{2})"
)
_B_ENTRY = re.compile(
    r"^([1-6])\s(\d{4})(.+?)(\d{2})(\D+?)(\d{2})([AB][12])\s+"
    r"(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+"
    r"(\d+)\s+(\d+\.\d+)\s+(\d+)\s+(\d+\.\d+)"
)

PROGRAM_COLUMNS = [
    "date", "jcd", "rno", "grade", "meet_title", "race_type", "distance", "deadline", "lane",
    "racer_id", "racer_name", "age", "branch", "weight", "racer_class",
    "nat_win", "nat_2r", "loc_win", "loc_2r",
    "motor_no", "motor_2r", "boat_no", "boat_2r",
]


def parse_program(text: str, hd: str) -> list[dict]:
    rows: list[dict] = []
    jcd = None
    race = None
    for raw in text.split("\n"):
        line = _norm(raw)
        m = _BLOCK.match(line)
        if m:
            jcd, race = m.group(1), None
            continue
        if jcd is None:
            continue
        if line.startswith(f"{jcd}BEND"):
            jcd, race = None, None
            continue
        m = _B_RACE.match(line)
        if m:
            race = {
                "rno": int(m.group(1)),
                "race_type": re.sub(r"\s+", "", m.group(2)),
                "distance": int(m.group(3)),
                "deadline": f"{int(m.group(4)):02d}:{m.group(5)}",
            }
            continue
        m = _B_ENTRY.match(line)
        if m and race is not None:
            g = m.groups()
            rows.append({
                "date": hd, "jcd": jcd, "rno": race["rno"],
                "race_type": race["race_type"], "distance": race["distance"],
                "deadline": race["deadline"], "lane": int(g[0]),
                "racer_id": g[1], "racer_name": re.sub(r"\s+", "", g[2]),
                "age": int(g[3]), "branch": re.sub(r"\s+", "", g[4]),
                "weight": int(g[5]), "racer_class": g[6],
                "nat_win": float(g[7]), "nat_2r": float(g[8]),
                "loc_win": float(g[9]), "loc_2r": float(g[10]),
                "motor_no": int(g[11]), "motor_2r": float(g[12]),
                "boat_no": int(g[13]), "boat_2r": float(g[14]),
            })
    return rows


# ---------------------------------------------------------------- 競走成績（K）

_K_RACE = re.compile(
    r"^\s*(\d{1,2})R\s+(.+?)\s+H(\d{3,4})m\s+(\S+)\s+風\s+(\S+)\s+(\d+)m\s+波\s+(\d+)cm"
)
_K_ENTRY = re.compile(r"^\s*(\S{1,2})\s+([1-6])\s+(\d{4})\s+(.*)$")
_BET = re.compile(r"^\s*(単勝|複勝|2連単|2連複|拡連複|3連単|3連複)\s+(.*)$")
_PAIR = re.compile(r"(\d(?:-\d){0,2})\s+(\d+)(?:\s+人気\s+(\d+))?")

RESULT_COLUMNS = [
    "date", "jcd", "rno", "race_type", "distance", "weather", "wind_dir",
    "wind_m", "wave_cm", "lane", "racer_id", "finish", "motor_no", "boat_no",
    "exhibition", "course", "st", "race_time",
]
PAYOUT_COLUMNS = ["date", "jcd", "rno", "bet_type", "combo", "payout", "popularity"]

BET_TYPE_CODE = {
    "単勝": "win", "複勝": "place", "2連単": "exacta", "2連複": "quinella",
    "拡連複": "wide", "3連単": "trifecta", "3連複": "trio",
}


def _parse_entry_rest(rest: str) -> dict | None:
    toks = rest.split()
    i = 0
    while i < len(toks) and not re.match(r"^\d+$", toks[i]):
        i += 1  # 選手名（空白区切りの可能性あり）
    nums = toks[i:]
    if len(nums) < 2:
        return None
    out = {"motor_no": nums[0], "boat_no": nums[1], "exhibition": "", "course": "", "st": "", "race_time": ""}
    tail = nums[2:]
    keys = ["exhibition", "course", "st", "race_time"]
    for k, v in zip(keys, tail):
        out[k] = v
    return out


def parse_result(text: str, hd: str) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    payouts: list[dict] = []
    jcd = None
    race = None
    last_bet = None
    for raw in text.split("\n"):
        line = _norm(raw)
        m = _BLOCK.match(line)
        if m:
            jcd, race, last_bet = m.group(1), None, None
            continue
        if jcd is None:
            continue
        if line.startswith(f"{jcd}KEND"):
            jcd, race, last_bet = None, None, None
            continue
        m = _K_RACE.match(line)
        if m:
            race = {
                "date": hd, "jcd": jcd, "rno": int(m.group(1)),
                "race_type": re.sub(r"\s+", "", m.group(2)),
                "distance": int(m.group(3)), "weather": m.group(4),
                "wind_dir": m.group(5), "wind_m": int(m.group(6)),
                "wave_cm": int(m.group(7)),
            }
            last_bet = None
            continue
        if race is None:
            continue
        m = _BET.match(line)
        if m:
            last_bet = BET_TYPE_CODE[m.group(1)]
            _add_payouts(payouts, race, last_bet, m.group(2))
            continue
        if last_bet and re.match(r"^\s+\d(?:-\d){1,2}\s+\d+", line):
            _add_payouts(payouts, race, last_bet, line)
            continue
        m = _K_ENTRY.match(line)
        if m and re.match(r"^(0[1-6]|[A-Z]\d?|F|L|S\d|K\d)$", m.group(1)):
            rest = _parse_entry_rest(m.group(4))
            if rest is None:
                continue
            fin = m.group(1)
            results.append({
                **{k: race[k] for k in ("date", "jcd", "rno", "race_type", "distance", "weather", "wind_dir", "wind_m", "wave_cm")},
                "lane": int(m.group(2)), "racer_id": m.group(3),
                "finish": str(int(fin)) if fin.isdigit() else fin,
                **rest,
            })
            last_bet = None
    return results, payouts


def _add_payouts(payouts: list[dict], race: dict, bet: str, s: str) -> None:
    for combo, pay, pop in _PAIR.findall(s):
        payouts.append({
            "date": race["date"], "jcd": race["jcd"], "rno": race["rno"],
            "bet_type": bet, "combo": combo, "payout": int(pay),
            "popularity": int(pop) if pop else "",
        })
