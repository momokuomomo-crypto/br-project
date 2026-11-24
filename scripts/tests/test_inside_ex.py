"""試走1位の1号艇（04_03）の選び方と集計。"""
from br.analysis import inside_ex
from br.collect import store


def _race(d, rno, times, win_lane, place_pay):
    prev = [{"date": d, "jcd": "18", "rno": rno, "lane": l, "ex_time": t} for l, t in enumerate(times, 1)]
    pay = [{"date": d, "jcd": "18", "rno": rno, "bet_type": "win", "combo": str(win_lane), "payout": 150}]
    pay += [{"date": d, "jcd": "18", "rno": rno, "bet_type": "place", "combo": c, "payout": v} for c, v in place_pay.items()]
    return prev, pay


def test_picks_and_summary(tmp_path):
    prev, pay = [], []
    # 記録開始前：1号艇の平均 6.80、ほかは 6.70（1号艇は遅く出やすい場）
    for rno in range(1, 5):
        p, y = _race("20261101", rno, [6.80, 6.70, 6.70, 6.70, 6.70, 6.70], 2, {"2": 110})
        prev += p; pay += y
    # 記録開始後 R1：1号艇 6.78 は平均より0.02速く、他は平均どおり → 対象、単勝的中
    p, y = _race("20261126", 1, [6.78, 6.70, 6.70, 6.70, 6.70, 6.70], 1, {"1": 120, "3": 130})
    prev += p; pay += y
    # R2：生のタイムは1号艇が最速だが、補正後は2号艇がもっと速い → 対象外
    p, y = _race("20261126", 2, [6.69, 6.55, 6.70, 6.70, 6.70, 6.70], 1, {"1": 120})
    prev += p; pay += y
    # R3：展示タイムが欠けている → 対象外
    p, y = _race("20261126", 3, [6.70, 6.70, 6.70, 6.70, 6.70, 0], 1, {"1": 120})
    prev += p; pay += y
    store.upsert("preview", prev, tmp_path)
    store.upsert("payout", pay, tmp_path)

    rows = inside_ex.picks(tmp_path, start="20261125")
    since = [r for r in rows if r["date"] >= "20261125"]
    assert [(r["date"], r["rno"]) for r in since] == [("20261126", 1)]
    s = inside_ex.summary(rows, start="20261125")
    assert s["since_win"]["return"] == 150 and s["since_place"]["return"] == 120
    tok = next(v for v in s["venues"] if v["jcd"] == "18")
    assert tok["since_win"]["bets"] == 1
