"""分析用データセットの組み立て（04_01 3章）。

1レース = 6艇の特徴量（6×F）、的中組合せ、券種ごとの払戻金。
6艇がすべて1〜6着に入り（失格・欠場なし）、3連単の払戻が1通りだけのレースを対象とする。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from br.collect import store

PERMS = list(itertools.permutations(range(6), 3))  # 0始まりの艇番
TRI_KEYS = [f"{a+1}-{b+1}-{c+1}" for a, b, c in PERMS]
EX_PAIRS = list(itertools.permutations(range(6), 2))
EX_KEYS = [f"{a+1}-{b+1}" for a, b in EX_PAIRS]
WIN_KEYS = [str(i) for i in range(1, 7)]
TRI_INDEX = {k: i for i, k in enumerate(TRI_KEYS)}
EX_INDEX = {k: i for i, k in enumerate(EX_KEYS)}
WIN_INDEX = {k: i for i, k in enumerate(WIN_KEYS)}
EX_FROM_TRI = np.zeros((30, 120))
WIN_FROM_TRI = np.zeros((6, 120))
for ci, (a, b, c) in enumerate(PERMS):
    EX_FROM_TRI[EX_PAIRS.index((a, b)), ci] = 1
    WIN_FROM_TRI[a, ci] = 1

CLASS_CODE = {"A1": 3, "A2": 2, "B1": 1, "B2": 0}
# レース内で標準化する数値特徴（符号はそのまま。小さいほど良い項目もモデルが係数で扱う）
NUMERIC = ["class", "nat_win", "nat_2r", "loc_win", "loc_2r", "motor_2r", "boat_2r",
           "avg_st", "flying", "weight", "ex_time", "ex_st", "course"]
LANES = [f"lane{i}" for i in range(1, 6)]  # 6号艇を基準とするダミー
# 場ごとの1号艇の強さ（イン有利の度合いは場によって大きく違う）。jcd=01 を基準とする
VENUE_IN = [f"in_{j:02d}" for j in range(2, 25)]
FEATURES = LANES + VENUE_IN + NUMERIC


@dataclass
class Races:
    keys: list = field(default_factory=list)       # (date, jcd, rno)
    grade: list = field(default_factory=list)
    x: np.ndarray | None = None                    # (N, 6, F)
    winner: np.ndarray | None = None               # (N,) 的中3連単のindex（不明は-1）
    pay: dict = field(default_factory=dict)        # bet_type -> (N, n_combo) 100円あたり払戻

    def subset(self, idx) -> "Races":
        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.flatnonzero(idx)
        return Races(keys=[self.keys[i] for i in idx], grade=[self.grade[i] for i in idx],
                     x=self.x[idx], winner=self.winner[idx], pay={k: v[idx] for k, v in self.pay.items()})

    def __len__(self) -> int:
        return len(self.keys)

    @property
    def dates(self) -> np.ndarray:
        return np.array([k[0] for k in self.keys])


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def boat_features(entries: list[dict], previews: dict[int, dict], jcd: str | None = None) -> np.ndarray:
    """6艇（枠番順）の特徴量。数値はレース内で標準化し、欠損はレース内平均（=0）。"""
    num = []
    for e in entries:
        pv = previews.get(int(e["lane"]), {})
        row = {"class": CLASS_CODE.get(e.get("racer_class", ""), np.nan)}
        for k in ("nat_win", "nat_2r", "loc_win", "loc_2r", "motor_2r", "boat_2r", "avg_st", "flying", "weight"):
            row[k] = _f(e.get(k))
        row["ex_time"] = _f(pv.get("ex_time"))
        row["ex_st"] = _f(pv.get("ex_st"))
        row["course"] = _f(pv.get("course"))
        if row["ex_time"] == 0:
            row["ex_time"] = np.nan
        num.append([row[k] for k in NUMERIC])
    a = np.array(num, dtype=float)
    with np.errstate(all="ignore"):
        mean = np.nanmean(a, axis=0, keepdims=True)
        a = np.where(np.isnan(a), mean, a)
        a = np.nan_to_num(a - a.mean(axis=0, keepdims=True))
        sd = a.std(axis=0, keepdims=True)
        a = a / np.where(sd > 0, sd, 1)
    lanes = np.zeros((6, len(LANES)))
    for i in range(5):
        lanes[i, i] = 1
    venue = np.zeros((6, len(VENUE_IN)))
    j = int(jcd or entries[0].get("jcd", 1) or 1)
    if j >= 2:
        venue[0, j - 2] = 1
    return np.concatenate([lanes, venue, a], axis=1)


def _group(rows):
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault((r["date"], r["jcd"], int(r["rno"])), []).append(r)
    return out


def load(root=None) -> Races:
    """場・月フォルダごとに読み、必要な配列だけを残す（全期間を一度に辞書で持たない）。"""
    root = root or store.INPUT_DIR
    keys, grades, xs, wn, p_tri, p_ex, p_win = [], [], [], [], [], [], []
    for mdir in sorted(p for p in root.glob("*/*") if p.is_dir()):
        prog = _group(store.read("program", mdir))
        prev = _group(store.read("preview", mdir))
        res = _group(store.read("result", mdir))
        pays: dict[tuple, dict] = {}
        for r in store.read("payout", mdir):
            pays.setdefault((r["date"], r["jcd"], int(r["rno"])), {}).setdefault(r["bet_type"], {})[r["combo"]] = int(r["payout"])
        for k in sorted(res):
            rr = res[k]
            entries = sorted(prog.get(k, []), key=lambda e: int(e["lane"]))
            if len(entries) != 6 or len(rr) != 6:
                continue
            if not all(r["place"].isdigit() and 1 <= int(r["place"]) <= 6 for r in rr):
                continue
            pay = pays.get(k, {})
            tri = pay.get("trifecta", {})
            if len(tri) != 1:
                continue
            combo = next(iter(tri))
            if combo not in TRI_INDEX:
                continue
            pv = {int(p["lane"]): p for p in prev.get(k, [])}
            xs.append(boat_features(entries, pv, k[1]).astype(np.float32))
            wn.append(TRI_INDEX[combo])
            ti = np.zeros(120, dtype=np.float32); ti[TRI_INDEX[combo]] = tri[combo]
            ei = np.zeros(30, dtype=np.float32)
            for c, v in pay.get("exacta", {}).items():
                if c in EX_INDEX:
                    ei[EX_INDEX[c]] = v
            wi = np.zeros(6, dtype=np.float32)
            for c, v in pay.get("win", {}).items():
                if c in WIN_INDEX:
                    wi[WIN_INDEX[c]] = v
            p_tri.append(ti); p_ex.append(ei); p_win.append(wi)
            keys.append(k)
            grades.append(entries[0].get("grade", ""))
    n = len(keys)
    order = sorted(range(n), key=lambda i: (keys[i][0], keys[i][1], keys[i][2]))
    out = Races(keys=[keys[i] for i in order], grade=[grades[i] for i in order])
    out.x = (np.stack(xs)[order] if n else np.zeros((0, 6, len(FEATURES)))).astype(np.float64)
    out.winner = np.array(wn, dtype=int)[order] if n else np.zeros(0, dtype=int)
    out.pay = {"trifecta": np.stack(p_tri)[order] if n else np.zeros((0, 120)),
               "exacta": np.stack(p_ex)[order] if n else np.zeros((0, 30)),
               "win": np.stack(p_win)[order] if n else np.zeros((0, 6))}
    return out


def single_race(key: tuple, grade: str, entries: list[dict], previews: list[dict]) -> Races | None:
    """当日予想用：1レース分の Races を作る（結果・払戻は無し）。"""
    entries = sorted(entries, key=lambda e: int(e["lane"]))
    if len(entries) != 6:
        return None
    pv = {int(p["lane"]): p for p in previews}
    return Races(keys=[key], grade=[grade], x=boat_features(entries, pv, key[1])[None], winner=np.array([-1]),
                 pay={"trifecta": np.zeros((1, 120)), "exacta": np.zeros((1, 30)), "win": np.zeros((1, 6))})
