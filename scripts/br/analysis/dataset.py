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
FEATURES = LANES + NUMERIC


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


def boat_features(entries: list[dict], previews: dict[int, dict]) -> np.ndarray:
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
    return np.concatenate([lanes, a], axis=1)


def _group(kind, root):
    out: dict[tuple, list] = {}
    for r in store.iter_all(kind, root):
        out.setdefault((r["date"], r["jcd"], int(r["rno"])), []).append(r)
    return out


def load(root=None) -> Races:
    root = root or store.INPUT_DIR
    prog = _group("program", root)
    prev = _group("preview", root)
    res = _group("result", root)
    pays: dict[tuple, dict] = {}
    for r in store.iter_all("payout", root):
        pays.setdefault((r["date"], r["jcd"], int(r["rno"])), {}).setdefault(r["bet_type"], {})[r["combo"]] = int(r["payout"])
    out = Races()
    xs, wn, p_tri, p_ex, p_win = [], [], [], [], []
    for k in sorted(res):
        rr = res[k]
        entries = sorted(prog.get(k, []), key=lambda e: int(e["lane"]))
        if len(entries) != 6 or len(rr) != 6:
            continue
        places = [r["place"] for r in rr]
        if not all(p.isdigit() and 1 <= int(p) <= 6 for p in places):
            continue
        tri = pays.get(k, {}).get("trifecta", {})
        if len(tri) != 1:
            continue
        combo = next(iter(tri))
        if combo not in TRI_KEYS:
            continue
        pv = {int(p["lane"]): p for p in prev.get(k, [])}
        xs.append(boat_features(entries, pv))
        wn.append(TRI_KEYS.index(combo))
        pay = pays.get(k, {})
        p_tri.append([tri.get(c, 0) for c in TRI_KEYS])
        p_ex.append([pay.get("exacta", {}).get(c, 0) for c in EX_KEYS])
        p_win.append([pay.get("win", {}).get(c, 0) for c in WIN_KEYS])
        out.keys.append(k)
        out.grade.append(entries[0].get("grade", ""))
    n = len(out.keys)
    out.x = np.array(xs, dtype=float).reshape(n, 6, len(FEATURES))
    out.winner = np.array(wn, dtype=int)
    out.pay = {"trifecta": np.array(p_tri, dtype=float).reshape(n, 120),
               "exacta": np.array(p_ex, dtype=float).reshape(n, 30),
               "win": np.array(p_win, dtype=float).reshape(n, 6)}
    return out


def single_race(key: tuple, grade: str, entries: list[dict], previews: list[dict]) -> Races | None:
    """当日予想用：1レース分の Races を作る（結果・払戻は無し）。"""
    entries = sorted(entries, key=lambda e: int(e["lane"]))
    if len(entries) != 6:
        return None
    pv = {int(p["lane"]): p for p in previews}
    return Races(keys=[key], grade=[grade], x=boat_features(entries, pv)[None], winner=np.array([-1]),
                 pay={"trifecta": np.zeros((1, 120)), "exacta": np.zeros((1, 30)), "win": np.zeros((1, 6))})
