"""合成データでの通し確認：入力CSV → データセット → 学習 → 検証。"""
import datetime as dt

import numpy as np

from br.analysis import backtest, dataset, model as M
from br.collect import store


def make_data(root, n_days=240, seed=0):
    rng = np.random.default_rng(seed)
    prog, prev, res, pay = [], [], [], []
    start = dt.date(2025, 1, 1)
    for d in range(n_days):
        hd = (start + dt.timedelta(days=d)).strftime("%Y%m%d")
        for rno in range(1, 7):
            skill = rng.normal(size=6) + np.array([1.5, .5, .3, 0, -.2, -.4])
            nat = 5 + skill + rng.normal(scale=.4, size=6)
            ext = 6.8 - 0.05 * skill + rng.normal(scale=.03, size=6)
            s = np.exp(skill)
            left, order = list(range(6)), []
            for _ in range(6):
                w = s[left] / s[left].sum()
                order.append(left.pop(rng.choice(len(left), p=w)))
            win = "-".join(str(o + 1) for o in order[:3])
            # 払戻：世間の見立て（全国勝率だけで判断）から決まる。展示タイムに表れる本当の強さは反映されない
            pub = np.exp(1.0 * (nat - 5))
            a, b, c = order[:3]
            q3 = pub[a] / pub.sum() * pub[b] / (pub.sum() - pub[a]) * pub[c] / (pub.sum() - pub[a] - pub[b])
            q1 = pub[a] / pub.sum()
            pay.append({"date": hd, "jcd": "02", "rno": rno, "bet_type": "trifecta", "combo": win,
                        "payout": int(75 / q3 * np.exp(rng.normal(scale=.2)) // 10 * 10)})
            pay.append({"date": hd, "jcd": "02", "rno": rno, "bet_type": "win", "combo": str(a + 1),
                        "payout": max(100, int(75 / q1 * np.exp(rng.normal(scale=.1)) // 10 * 10))})
            for lane in range(1, 7):
                prog.append({"date": hd, "jcd": "02", "rno": rno, "lane": lane, "grade": "一般", "deadline": "12:00",
                             "racer_class": "A1" if nat[lane-1] > 6 else "B1", "nat_win": round(nat[lane-1], 2)})
                prev.append({"date": hd, "jcd": "02", "rno": rno, "lane": lane, "ex_time": round(ext[lane-1], 2), "course": lane})
                res.append({"date": hd, "jcd": "02", "rno": rno, "lane": lane, "place": str(order.index(lane - 1) + 1)})
    for k, rows in (("program", prog), ("preview", prev), ("result", res), ("payout", pay)):
        store.upsert(k, rows, root)


def test_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(backtest, "MIN_BETS", 30)
    root = tmp_path / "input"
    make_data(root)
    races = dataset.load(root)
    assert len(races) == 240 * 6
    m = M.fit(races)
    assert M.log_loss(m.proba(races), races) < np.log(120) - 0.3
    pm = M.fit_payout(races)
    assert "trifecta" in pm.coef and "win" in pm.coef
    rep = backtest.run(out_dir=tmp_path / "out", valid_start="20250501", test_start="20250701", races=races)
    assert rep["periods"]["test"][2] > 0
    assert rep["selected"] is not None and "test" in rep
    assert (tmp_path / "out" / "model.json").exists()
    assert (tmp_path / "out" / "backtest_report.json").exists()
