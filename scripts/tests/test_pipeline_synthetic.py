"""合成データでの通し確認：収集形式のCSV → データセット → 学習 → 検証。"""
import datetime as dt
import itertools

import numpy as np

from br.analysis import backtest, dataset, model as M
from br.collect import store


def make_data(root, n_days=200, seed=0):
    rng = np.random.default_rng(seed)
    perms = list(itertools.permutations(range(1, 7), 3))
    prog, res, pay, odds = [], [], [], []
    start = dt.date(2025, 1, 1)
    for d in range(n_days):
        hd = (start + dt.timedelta(days=d)).strftime("%Y%m%d")
        for rno in range(1, 7):
            skill = rng.normal(size=6) + np.array([1.2, .4, .2, 0, -.2, -.4])
            nat = 5 + skill + rng.normal(scale=.3, size=6)
            # 真の強さ：市場は skill の一部しか見ていない（モデルが補正できる余地）
            s = np.exp(skill)
            order = []
            left = list(range(6))
            for _ in range(3):
                w = s[left] / s[left].sum()
                order.append(left.pop(rng.choice(len(left), p=w)))
            mkt = np.exp(0.6 * skill)
            p = {}
            for a, b, c in perms:
                pa = mkt[a-1] / mkt.sum(); pb = mkt[b-1] / (mkt.sum() - mkt[a-1]); pc = mkt[c-1] / (mkt.sum() - mkt[a-1] - mkt[b-1])
                p[(a, b, c)] = pa * pb * pc
            row = {"date": hd, "jcd": "02", "rno": rno, "fetched_at": ""}
            for (a, b, c), v in p.items():
                row[f"tri_{a}-{b}-{c}"] = round(max(1.0, 0.75 / v), 1)
            odds.append(row)
            win = "-".join(str(o + 1) for o in order)
            pay.append({"date": hd, "jcd": "02", "rno": rno, "bet_type": "trifecta", "combo": win, "payout": int(row[f"tri_{win}"] * 100), "popularity": ""})
            for lane in range(1, 7):
                prog.append({"date": hd, "jcd": "02", "rno": rno, "lane": lane, "racer_class": "A1" if skill[lane-1] > 1 else "B1",
                             "nat_win": round(nat[lane-1], 2), "loc_win": round(nat[lane-1], 2), "motor_2r": 30, "boat_2r": 30})
                fin = order.index(lane - 1) + 1 if lane - 1 in order else 4 + lane % 3
                res.append({"date": hd, "jcd": "02", "rno": rno, "lane": lane, "finish": str(fin)})
    store.upsert("program", prog, root); store.upsert("result", res, root)
    store.upsert("payout", pay, root); store.upsert("odds", odds, root)


def test_end_to_end(tmp_path, monkeypatch):
    root = tmp_path / "input"
    make_data(root)
    monkeypatch.setattr(store, "INPUT_DIR", root)
    monkeypatch.setattr(dataset.store, "INPUT_DIR", root)
    races = dataset.load(root)
    assert len(races.keys) == 1200
    m = M.fit(races)
    assert M.log_loss(m, races) < M.log_loss(M.market_only(), races)
    assert m.w[1] > 0  # class / skill 補正が正
    monkeypatch.setattr(backtest.dataset, "load", lambda: races)
    monkeypatch.setattr(backtest, "MIN_BETS", 20)
    rep = backtest.run(out_dir=tmp_path / "out", valid_start="20250401", test_start="20250601")
    assert rep["selected"] is not None
    assert (tmp_path / "out" / "model.json").exists()
