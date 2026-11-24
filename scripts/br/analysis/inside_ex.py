"""試走1位の1号艇（04_03）。

1号艇の展示タイムが、場・号艇ごとの平均タイムとの差で比べて6艇中いちばん速い
（同タイムを含む）レースで、1号艇の単勝・複勝を1点100円ずつ買ったとして記録する。
号艇ごとの平均は START より前のデータだけで計算し、START 以降は固定する
（記録期間の成績が平均の計算に混ざらないようにするため）。
"""
from __future__ import annotations

from collections import defaultdict

from br.collect import store
from br.venues import VENUES

# 注目条件（04_03 6章）：尼崎で、1号艇がB1級のとき
FOCUS = {"jcd": "13", "racer_class": "B1", "label": "尼崎・1号艇がB1級"}
START = "20261125"  # 記録開始日（この日より前のデータで号艇ごとの平均を決める）
STAKE = 100


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def lane_means(previews: dict, before: str = START) -> dict:
    s = defaultdict(lambda: [0.0, 0])
    for (d, j, _), lanes in previews.items():
        if d >= before:
            continue
        for lane, t in lanes.items():
            s[(j, lane)][0] += t
            s[(j, lane)][1] += 1
    return {k: v[0] / v[1] for k, v in s.items() if v[1]}


def picks(root=None, start: str = START) -> list[dict]:
    """対象レースごとに {date, jcd, rno, win, place}（100円あたり払戻）を返す。払戻が確定したレースだけ。"""
    root = root or store.INPUT_DIR
    previews: dict[tuple, dict[int, float]] = defaultdict(dict)
    for r in store.iter_all("preview", root):
        t = _f(r.get("ex_time"))
        if t > 0:
            previews[(r["date"], r["jcd"], int(r["rno"]))][int(r["lane"])] = t
    pays: dict[tuple, dict] = {}
    for r in store.iter_all("payout", root):
        k = (r["date"], r["jcd"], int(r["rno"]))
        p = pays.setdefault(k, {"win": 0, "place": 0})
        if r["combo"] == "1" and r["bet_type"] in ("win", "place"):
            p[r["bet_type"]] = int(r["payout"])
    cls = {(r["date"], r["jcd"], int(r["rno"])): r.get("racer_class", "")
           for r in store.iter_all("program", root) if str(r["lane"]) == "1"}
    means = lane_means(previews, start)
    out = []
    for k, lanes in previews.items():
        if len(lanes) != 6 or k not in pays:
            continue
        dev = {l: t - means.get((k[1], l), t) for l, t in lanes.items()}
        if (k[1], 1) not in means or dev[1] > min(dev.values()):
            continue
        out.append({"date": k[0], "jcd": k[1], "rno": k[2], "racer_class": cls.get(k, ""), **pays[k]})
    return sorted(out, key=lambda r: (r["date"], r["jcd"], r["rno"]))


def stats(rows: list[dict], bet: str) -> dict:
    n = len(rows)
    ret = sum(r[bet] for r in rows)
    return {"bets": n, "hits": sum(1 for r in rows if r[bet] > 0), "stake": n * STAKE, "return": ret,
            "profit": ret - n * STAKE, "roi": ret / (n * STAKE) if n else None}


def summary(rows: list[dict], start: str = START) -> dict:
    """全期間と記録開始以降の、全体・場ごとの単勝・複勝の成績。"""
    since = [r for r in rows if r["date"] >= start]
    venues = []
    for j, name in VENUES.items():
        a = [r for r in rows if r["jcd"] == j]
        s = [r for r in since if r["jcd"] == j]
        venues.append({"jcd": j, "name": name, "all_win": stats(a, "win"), "all_place": stats(a, "place"),
                       "since_win": stats(s, "win"), "since_place": stats(s, "place")})
    return {"start": start, "first": rows[0]["date"] if rows else None, "last": rows[-1]["date"] if rows else None,
            "all_win": stats(rows, "win"), "all_place": stats(rows, "place"),
            "since_win": stats(since, "win"), "since_place": stats(since, "place"),
            "since_rows": since, "venues": venues, "focus": focus(rows, start)}


def is_focus(r: dict) -> bool:
    return r["jcd"] == FOCUS["jcd"] and r.get("racer_class") == FOCUS["racer_class"]


def focus(rows: list[dict], start: str = START) -> dict:
    a = [r for r in rows if is_focus(r)]
    s = [r for r in a if r["date"] >= start]
    return {"label": FOCUS["label"], "all_win": stats(a, "win"), "all_place": stats(a, "place"),
            "since_win": stats(s, "win"), "since_place": stats(s, "place"),
            "recent": [{k: r[k] for k in ("date", "rno", "place")} for r in s[-10:]][::-1]}
