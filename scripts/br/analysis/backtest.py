"""学習に使っていない期間での検証（04_02）。

期間は日付で3つに分ける（既定：最後の6か月が「確認」、その前の6か月が「選定」、
それより前が「学習」）。

1. 学習期間だけで確率モデルと想定オッズモデルを学習する。
2. 選定期間で、購入ルールの候補（券種×EV基準×想定オッズ上限）を試し、
   購入点数が MIN_BETS 以上の中で回収率が最も高いものを選ぶ。
3. 学習＋選定期間で学習し直し、2. のルールで確認期間を評価する（実際の払戻で計算）。
   確認期間の成績は、モデル・ルールのどちらの決定にも使っていない。
4. 運用用に、全期間で学習し直して保存する（ルールは2.のもの）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import numpy as np

from br.analysis import dataset, ev, model as M
from br.collect.store import ROOT

OUT_DIR = ROOT / "data" / "output"
MIN_BETS = 300
GRID_EV = (1.0, 1.1, 1.2, 1.3, 1.5, 2.0)
GRID_ODDS = {"win": (5, 10, 30), "exacta": (20, 50, 150), "trifecta": (50, 200, 1000)}


def shift_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    return dt.date(d.year + m // 12, m % 12 + 1, min(d.day, 28))


def split_dates(last: str, test_months=6, valid_months=6) -> tuple[str, str]:
    end = dt.datetime.strptime(last, "%Y%m%d").date()
    test_start = shift_months(end, -test_months) + dt.timedelta(days=1)
    valid_start = shift_months(test_start, -valid_months)
    return valid_start.strftime("%Y%m%d"), test_start.strftime("%Y%m%d")


def _span(dates, mask):
    return [min(dates[mask]) if mask.any() else None, max(dates[mask]) if mask.any() else None, int(mask.sum())]


def run(out_dir: Path = OUT_DIR, valid_start: str | None = None, test_start: str | None = None, races=None) -> dict:
    races = races if races is not None else dataset.load()
    if len(races) == 0:
        raise SystemExit("分析できるレースがありません")
    dates = races.dates
    if not (valid_start and test_start):
        valid_start, test_start = split_dates(max(dates))
    tr, va, te = dates < valid_start, (dates >= valid_start) & (dates < test_start), dates >= test_start
    R_tr, R_va, R_te = races.subset(tr), races.subset(va), races.subset(te)

    m1, pm1 = M.fit(R_tr), M.fit_payout(R_tr)
    p_va = m1.proba(R_va)
    candidates = []
    for bt in ev.BET_TYPES:
        if bt not in pm1.coef:
            continue
        p, odds, e = ev.ev_table(R_va, p_va, pm1, bt)
        for th in GRID_EV:
            for mo in GRID_ODDS[bt]:
                rule = ev.Rule(bt, th, mo)
                candidates.append({"rule": rule.to_dict(), **ev.settle(R_va, ev.select(p, odds, e, rule), bt)})
    ok = [c for c in candidates if c["bets"] >= MIN_BETS]
    best = max(ok, key=lambda c: c["roi"]) if ok else None

    trva = tr | va
    m2, pm2 = M.fit(races.subset(trva)), M.fit_payout(races.subset(trva))
    p_te = m2.proba(R_te)
    report = {
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
        "periods": {"train": _span(dates, tr), "valid": _span(dates, va), "test": _span(dates, te)},
        "log_loss": {"uniform": float(np.log(120)),
                     "model_valid": M.log_loss(p_va, R_va) if va.any() else None,
                     "model_test": M.log_loss(p_te, R_te) if te.any() else None},
        "candidates": candidates, "selected": best,
    }
    rows = []
    out_dir.mkdir(parents=True, exist_ok=True)
    if best and te.any():
        rule = ev.Rule(**best["rule"])
        p, odds, e = ev.ev_table(R_te, p_te, pm2, rule.bet_type)
        mask = ev.select(p, odds, e, rule)
        report["test"] = ev.settle(R_te, mask, rule.bet_type)
        # 参考：同じ券種を、モデルの確率が最も高い組合せから順に同じ点数だけ毎レース買った場合
        k = rule.max_per_race
        top = np.zeros_like(mask)
        np.put_along_axis(top, np.argsort(-p, axis=1)[:, :k], True, axis=1)
        report["test_top_prob"] = ev.settle(R_te, top, rule.bet_type)
        rows = ev.ledger(R_te, p, odds, e, mask, rule)
        m3, pm3 = M.fit(races), M.fit_payout(races)
        M.save(out_dir / "model.json", m3, pm3, {"rule": rule.to_dict(), "trained_until": max(dates), "n_races": len(races)})
    with (out_dir / "backtest_ledger.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "jcd", "rno", "grade", "bet_type", "combo", "prob", "odds", "ev", "stake", "return"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (out_dir / "backtest_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report
