"""期待値の計算と購入ルール（04_01 5章）。

期待値 EV = 推定確率 × 想定払戻 ÷ 100。EV が基準以上の組合せだけを買う。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from br.analysis.dataset import EX_KEYS, TRI_KEYS, WIN_KEYS, Races
from br.analysis.model import PayoutModel, marginals

STAKE = 100
BET_TYPES = ("win", "exacta", "trifecta")
LABEL = {"win": "単勝", "exacta": "2連単", "trifecta": "3連単"}
COMBO_KEYS = {"win": WIN_KEYS, "exacta": EX_KEYS, "trifecta": TRI_KEYS}


@dataclass(frozen=True)
class Rule:
    bet_type: str
    min_ev: float
    max_odds: float
    max_per_race: int = 2

    def to_dict(self) -> dict:
        return asdict(self)


def ev_table(r: Races, p_tri: np.ndarray, payout: PayoutModel, bet_type: str):
    p = marginals(p_tri)[bet_type]
    odds = payout.predict(r, bet_type) / 100
    return p, odds, p * odds


def select(p: np.ndarray, odds: np.ndarray, ev: np.ndarray, rule: Rule) -> np.ndarray:
    ok = (ev >= rule.min_ev) & (odds <= rule.max_odds)
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
    stake = n_bets * STAKE
    return {"races": int(mask.any(axis=1).sum()), "bets": n_bets, "hits": hits, "stake": stake,
            "return": ret, "profit": ret - stake, "roi": (ret / stake) if stake else None,
            "hit_rate": (hits / n_bets) if n_bets else None}


def ledger(r: Races, p, odds, ev, mask, rule: Rule) -> list[dict]:
    keys = COMBO_KEYS[rule.bet_type]
    pay = r.pay[rule.bet_type] * (STAKE / 100)
    rows = []
    for n, c in zip(*np.nonzero(mask)):
        d, j, rno = r.keys[n]
        rows.append({"date": d, "jcd": j, "rno": rno, "grade": r.grade[n], "bet_type": rule.bet_type,
                     "combo": keys[c], "prob": round(float(p[n, c]), 5), "odds": round(float(odds[n, c]), 1),
                     "ev": round(float(ev[n, c]), 3), "stake": STAKE, "return": float(pay[n, c])})
    return rows
