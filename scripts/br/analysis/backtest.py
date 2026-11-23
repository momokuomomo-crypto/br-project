"""学習に使っていない期間での検証（04_02）。

期間は日付で3つに分ける（既定：最後の6か月が「確認」、その前の6か月が「選定」、
それより前が「学習」）。

1. 学習期間だけでモデルを学習する。
2. 選定期間で、購入ルールの候補（券種×EV基準×オッズ上限）を試し、
   購入点数が MIN_BETS 以上の中で回収率が最も高いものを選ぶ。
3. 学習＋選定期間でモデルを学習し直し、2. のルールで確認期間を評価する。
   確認期間の成績は、モデル・ルールのどちらの決定にも使っていない。
4. 運用用に、全期間でモデルを学習し直して保存する（ルールは2.のもの）。
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path

import numpy as np

from br.analysis import dataset, ev, model as M
from br.collect.store import ROOT

OUT_DIR = ROOT / "data" / "output"
MIN_BETS = 300
GRID_EV = (1.0, 1.1, 1.2, 1.3, 1.5)
GRID_ODDS = {"win": (10, 30, 100), "exacta": (30, 100, 300), "trifecta": (100, 300, 1000)}


def shift_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    y = d.year + m // 12
    return dt.date(y, m % 12 + 1, min(d.day, 28))


def split_dates(last: str, test_months=6, valid_months=6) -> tuple[str, str]:
    end = dt.datetime.strptime(last, "%Y%m%d").date()
    test_start = shift_months(end, -test_months) + dt.timedelta(days=1)
    valid_start = shift_months(test_start, -valid_months)
    return valid_start.strftime("%Y%m%d"), test_start.strftime("%Y%m%d")


def run(out_dir: Path = OUT_DIR, valid_start: str | None = None, test_start: str | None = None) -> dict:
    races = dataset.load()
    if len(races.keys) == 0:
        raise SystemExit("分析できるレースがありません（odds.csv と成績が必要です）")
    dates = races.dates
    if not (valid_start and test_start):
        valid_start, test_start = split_dates(max(dates))
    tr, va, te = dates < valid_start, (dates >= valid_start) & (dates < test_start), dates >= test_start
    R_tr, R_va, R_te = races.subset(tr), races.subset(va), races.subset(te)

    m1 = M.fit(R_tr)
    p_va = m1.proba(R_va)
    candidates = []
    for bt in ev.BET_TYPES:
        if bt != "trifecta" and np.isnan(getattr(R_va, {"win": "win_odds", "exacta": "ex_odds"}[bt])).all():
            continue
        for th in GRID_EV:
            for mo in GRID_ODDS[bt]:
                rule = ev.Rule(bt, th, mo)
                res = ev.settle(R_va, ev.select(R_va, p_va, rule), bt)
                candidates.append({"rule": rule.to_dict(), **res})
    ok = [c for c in candidates if c["bets"] >= MIN_BETS]
    best = max(ok, key=lambda c: c["roi"]) if ok else None

    m2 = M.fit(races.subset(tr | va))
    p_te = m2.proba(R_te)
    report = {
        "generated_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
        "periods": {
            "train": [min(dates[tr]) if tr.any() else None, max(dates[tr]) if tr.any() else None, int(tr.sum())],
            "valid": [valid_start, max(dates[va]) if va.any() else None, int(va.sum())],
            "test": [test_start, max(dates[te]) if te.any() else None, int(te.sum())],
        },
        "model_train": m1.to_json(), "model_final_test": m2.to_json(),
        "log_loss": {"market_valid": M.log_loss(M.market_only(), R_va) if va.any() else None,
                     "model_valid": M.log_loss(m1, R_va) if va.any() else None,
                     "market_test": M.log_loss(M.market_only(), R_te) if te.any() else None,
                     "model_test": M.log_loss(m2, R_te) if te.any() else None},
        "candidates": candidates, "selected": best,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    if best:
        rule = ev.Rule(**best["rule"])
        mask = ev.select(R_te, p_te, rule)
        report["test"] = ev.settle(R_te, mask, rule.bet_type)
        # 参考：同じルールを市場の見立てのまま使った場合
        report["test_market_only"] = ev.settle(R_te, ev.select(R_te, M.market_only().proba(R_te), rule), rule.bet_type)
        rows = ev.ledger(R_te, p_te, mask, rule)
        m3 = M.fit(races)
        M.save(m3, out_dir / "model.json", {"rule": rule.to_dict(), "trained_until": max(dates),
                                             "n_races": len(races.keys)})
    with (out_dir / "backtest_ledger.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "jcd", "rno", "grade", "bet_type", "combo", "prob", "odds", "ev", "stake", "return"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (out_dir / "backtest_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="期待値派の検証（学習・選定・確認の3期間）")
    ap.add_argument("--valid-start")
    ap.add_argument("--test-start")
    a = ap.parse_args(argv)
    rep = run(valid_start=a.valid_start, test_start=a.test_start)
    print(json.dumps({k: rep.get(k) for k in ("periods", "log_loss", "selected", "test", "test_market_only")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
