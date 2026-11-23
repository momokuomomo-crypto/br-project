"""分析用データセットの組み立て（04_01 3章）。

1レース = 6艇の特徴量（6×F）、3連単120通りの市場確率、的中組合せ、
2連単・単勝オッズ、払戻金。全艇が出走し、3連単オッズ120通りが
揃っているレースだけを対象とする（欠場・不成立・特払いのレースは除く）。
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
# 3連単120通り → 2連単30通り・単勝6通りへの集約行列
EX_FROM_TRI = np.zeros((30, 120))
WIN_FROM_TRI = np.zeros((6, 120))
for ci, (a, b, c) in enumerate(PERMS):
    EX_FROM_TRI[EX_PAIRS.index((a, b)), ci] = 1
    WIN_FROM_TRI[a, ci] = 1

FEATURES = ["class", "nat_win", "loc_win", "motor_2r", "boat_2r"]
CLASS_CODE = {"A1": 3, "A2": 2, "B1": 1, "B2": 0}


@dataclass
class Races:
    keys: list = field(default_factory=list)       # (date, jcd, rno)
    grade: list = field(default_factory=list)
    x: np.ndarray | None = None                    # (N, 6, F)
    log_q: np.ndarray | None = None                # (N, 120) 3連単の市場確率（対数）
    tri_odds: np.ndarray | None = None             # (N, 120)
    ex_odds: np.ndarray | None = None              # (N, 30)  無い場合 nan
    win_odds: np.ndarray | None = None             # (N, 6)   無い場合 nan
    winner: np.ndarray | None = None               # (N,) 的中3連単のindex
    pay: dict = field(default_factory=dict)        # bet_type -> (N, n_combo) 100円あたり払戻

    def subset(self, mask) -> "Races":
        mask = np.asarray(mask)
        idx = np.flatnonzero(mask) if mask.dtype == bool else mask
        return Races(
            keys=[self.keys[i] for i in idx], grade=[self.grade[i] for i in idx],
            x=self.x[idx], log_q=self.log_q[idx], tri_odds=self.tri_odds[idx],
            ex_odds=self.ex_odds[idx], win_odds=self.win_odds[idx], winner=self.winner[idx],
            pay={k: v[idx] for k, v in self.pay.items()},
        )

    @property
    def dates(self) -> np.ndarray:
        return np.array([k[0] for k in self.keys])


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def boat_features(entries: list[dict]) -> np.ndarray:
    """6艇の特徴量（レース内で標準化）。"""
    raw = np.array([[CLASS_CODE.get(e.get("racer_class", ""), 1), _f(e.get("nat_win")), _f(e.get("loc_win")),
                     _f(e.get("motor_2r")), _f(e.get("boat_2r"))] for e in entries], dtype=float)
    raw = np.where(np.isnan(raw), np.nanmean(raw, axis=0, keepdims=True), raw)
    raw = np.nan_to_num(raw)
    sd = raw.std(axis=0, keepdims=True)
    return (raw - raw.mean(axis=0, keepdims=True)) / np.where(sd > 0, sd, 1)


def market_log_q(tri: np.ndarray) -> np.ndarray:
    inv = 1.0 / tri
    return np.log(inv / inv.sum())


def load(root=store.INPUT_DIR, require_result=True) -> Races:
    prog: dict[tuple, list] = {}
    grade: dict[tuple, str] = {}
    for r in store.iter_all("program", root):
        k = (r["date"], r["jcd"], int(r["rno"]))
        prog.setdefault(k, []).append(r)
        grade[k] = r.get("grade", "")
    starters: dict[tuple, int] = {}
    for r in store.iter_all("result", root):
        k = (r["date"], r["jcd"], int(r["rno"]))
        starters[k] = starters.get(k, 0) + (1 if r["finish"].isdigit() else 0)
    pays: dict[tuple, dict] = {}
    for r in store.iter_all("payout", root):
        k = (r["date"], r["jcd"], int(r["rno"]))
        pays.setdefault(k, {}).setdefault(r["bet_type"], {})[r["combo"]] = int(r["payout"])
    out = Races()
    xs, lq, tri_l, ex_l, win_l, wn, p_tri, p_ex, p_win = [], [], [], [], [], [], [], [], []
    for r in store.iter_all("odds", root):
        k = (r["date"], r["jcd"], int(r["rno"]))
        entries = sorted(prog.get(k, []), key=lambda e: int(e["lane"]))
        if len(entries) != 6:
            continue
        tri = np.array([_f(r.get(f"tri_{c}")) for c in TRI_KEYS])
        if np.isnan(tri).any() or (tri <= 0).any():
            continue
        pay = pays.get(k, {})
        tri_pay = pay.get("trifecta", {})
        if require_result:
            if starters.get(k, 0) != 6 or len(tri_pay) != 1:
                continue
            combo = next(iter(tri_pay))
            if combo not in TRI_KEYS:
                continue
            wn.append(TRI_KEYS.index(combo))
        else:
            wn.append(-1)
        xs.append(boat_features(entries))
        lq.append(market_log_q(tri))
        tri_l.append(tri)
        ex_l.append([_f(r.get(f"ex_{c}")) for c in EX_KEYS])
        win_l.append([_f(r.get(f"win_{i}")) for i in range(1, 7)])
        p_tri.append([tri_pay.get(c, 0) for c in TRI_KEYS])
        p_ex.append([pay.get("exacta", {}).get(c, 0) for c in EX_KEYS])
        p_win.append([pay.get("win", {}).get(str(i), 0) for i in range(1, 7)])
        out.keys.append(k)
        out.grade.append(grade.get(k, ""))
    n = len(out.keys)
    out.x = np.array(xs).reshape(n, 6, len(FEATURES))
    out.log_q = np.array(lq).reshape(n, 120)
    out.tri_odds = np.array(tri_l).reshape(n, 120)
    out.ex_odds = np.array(ex_l, dtype=float).reshape(n, 30)
    out.win_odds = np.array(win_l, dtype=float).reshape(n, 6)
    out.winner = np.array(wn, dtype=int)
    out.pay = {"trifecta": np.array(p_tri).reshape(n, 120), "exacta": np.array(p_ex).reshape(n, 30),
               "win": np.array(p_win).reshape(n, 6)}
    order = np.argsort([f"{d}{j}{r:02d}" for d, j, r in out.keys], kind="stable")
    return out.subset(order) if n else out


def single_race(key: tuple, grade: str, entries: list[dict], odds_row: dict) -> Races | None:
    """当日予想用：1レース分の Races を作る（結果・払戻は無し）。"""
    entries = sorted(entries, key=lambda e: int(e["lane"]))
    tri = np.array([_f(odds_row.get(f"tri_{c}")) for c in TRI_KEYS])
    if len(entries) != 6 or np.isnan(tri).any() or (tri <= 0).any():
        return None
    return Races(
        keys=[key], grade=[grade], x=boat_features(entries)[None], log_q=market_log_q(tri)[None],
        tri_odds=tri[None], ex_odds=np.array([[_f(odds_row.get(f"ex_{c}")) for c in EX_KEYS]]),
        win_odds=np.array([[_f(odds_row.get(f"win_{i}")) for i in range(1, 7)]]),
        winner=np.array([-1]), pay={"trifecta": np.zeros((1, 120)), "exacta": np.zeros((1, 30)), "win": np.zeros((1, 6))},
    )
