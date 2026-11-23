"""期待値の計算と購入ルール（04_01 5章）。

期待値 EV = 推定確率 × オッズ。EV が基準以上の組合せだけを買う。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from br.analysis.dataset import EX_KEYS, TRI_KEYS, Races
from br.analysis.model import marginals

STAKE = 100  # 1点100円
BET_TYPES = ("win", "exacta", "trifecta")
LABEL = {"win": "単勝", "exacta": "2連単", "trifecta": "3連単"}
COMBO_KEYS = {"win": [str(i) for i in range(1, 7)], "exacta": EX_KEYS, "trifecta": TRI_KEYS}


@dataclass(frozen=True)
class Rule:
    bet_type: str
    min_ev: float
    max_odds: float
    max_per_race: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


def probs_and_odds(r: Races, p_tri: np.ndarray, bet_type: str) -> tuple[np.ndarray, np.ndarray]:
    if bet_type == "trifecta":
        return p_tri, r.tri_odds
    p_ex, p_win = marginals(p_tri)
    if bet_type == "exacta":
        return p_ex, r.ex_odds
    return p_win, r.win_odds


def select(r: Races, p_tri: np.ndarray, rule: Rule) -> np.ndarray:
    """買う組合せのマスク (N, n_combo)。"""
    p, odds = probs_and_odds(r, p_tri, rule.bet_type)
    ev = np.where(np.isnan(odds), -np.inf, p * np.nan_to_num(odds))
    ok = (ev >= rule.min_ev) & (np.nan_to_num(odds, nan=np.inf) <= rule.max_odds)
    ev_ok = np.where(ok, ev, -np.inf)
    order = np.argsort(-ev_ok, axis=1)[:, : rule.max_per_race]
    mask = np.zeros_like(ok)
    np.put_along_axis(mask, order, True, axis=1)
    return mask & ok


def settle(r: Races, mask: np.ndarray, bet_type: str) -> dict:
    pay = r.pay[bet_type] * (STAKE / 100)
    n_bets = int(mask.sum())
    ret = float((pay * mask).sum())
    hits = int(((pay > 0) & mask).sum())
    races = int(mask.any(axis=1).sum())
    stake = n_bets * STAKE
    return {"races": races, "bets": n_bets, "hits": hits, "stake": stake, "return": ret,
            "profit": ret - stake, "roi": (ret / stake) if stake else None,
            "hit_rate": (hits / n_bets) if n_bets else None}


def ledger(r: Races, p_tri: np.ndarray, mask: np.ndarray, rule: Rule) -> list[dict]:
    p, odds = probs_and_odds(r, p_tri, rule.bet_type)
    keys = COMBO_KEYS[rule.bet_type]
    pay = r.pay[rule.bet_type] * (STAKE / 100)
    rows = []
    for n, c in zip(*np.nonzero(mask)):
        d, j, rno = r.keys[n]
        rows.append({"date": d, "jcd": j, "rno": rno, "grade": r.grade[n], "bet_type": rule.bet_type,
                     "combo": keys[c], "prob": round(float(p[n, c]), 5), "odds": float(odds[n, c]),
                     "ev": round(float(p[n, c] * odds[n, c]), 3), "stake": STAKE, "return": float(pay[n, c])})
    return rows
