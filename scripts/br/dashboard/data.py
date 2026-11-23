"""ダッシュボードの集計（06_02 4章）。"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict

from br.collect import store
from br.venues import VENUES

OUT = store.ROOT / "data" / "output"
PRED = store.ROOT / "data" / "predictions"
STATUS = store.ROOT / "data" / "dashboard" / "run_status.json"
JST = dt.timezone(dt.timedelta(hours=9))


def _csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def collection_status() -> list[dict]:
    rows = []
    for jcd, name in VENUES.items():
        vdir = store.INPUT_DIR / f"{jcd}_{name}"
        res, odd = set(), set()
        for m in sorted(vdir.glob("*")) if vdir.exists() else []:
            res |= {(r["date"], r["rno"]) for r in store.read("result", m)}
            odd |= {(r["date"], r["rno"]) for r in store.read("odds", m)}
        days = sorted({d for d, _ in res})
        rows.append({"jcd": jcd, "name": name, "first": days[0] if days else "", "last": days[-1] if days else "",
                     "days": len(days), "races": len(res), "odds": len(res & odd)})
    return rows


def payouts_index() -> dict:
    idx = {}
    for r in store.iter_all("payout"):
        idx[(r["date"], r["jcd"], int(r["rno"]), r["bet_type"], r["combo"])] = int(r["payout"])
    return idx


def settled_races() -> set:
    return {(r["date"], r["jcd"], int(r["rno"])) for r in store.iter_all("payout")}


def live_ledger(pay_idx: dict, done: set) -> list[dict]:
    rows = []
    for f in sorted(PRED.glob("*.csv")) if PRED.exists() else []:
        for r in _csv(f):
            if r["decision"] != "購入":
                continue
            k = (r["date"], r["jcd"], int(r["rno"]))
            r["settled"] = k in done
            r["return"] = pay_idx.get((*k, r["bet_type"], r["combo"]), 0) if r["settled"] else None
            rows.append(r)
    return rows


def summarize(rows: list[dict], stake=100) -> dict:
    s = [r for r in rows if r.get("settled", True) and r.get("return") is not None]
    bets = len(s)
    ret = sum(float(r["return"]) for r in s)
    hits = sum(1 for r in s if float(r["return"]) > 0)
    cum, series = 0.0, []
    monthly = defaultdict(lambda: [0, 0.0, 0])
    for r in sorted(s, key=lambda r: (r["date"], r["jcd"], int(r["rno"]))):
        cum += float(r["return"]) - stake
        series.append(cum)
        m = monthly[r["date"][:6]]
        m[0] += stake; m[1] += float(r["return"]); m[2] += 1
    return {"bets": bets, "races": len({(r["date"], r["jcd"], r["rno"]) for r in s}), "hits": hits,
            "stake": bets * stake, "return": ret, "profit": ret - bets * stake,
            "roi": ret / (bets * stake) if bets else None, "series": series,
            "monthly": [{"month": k, "stake": v[0], "return": v[1], "bets": v[2]} for k, v in sorted(monthly.items())]}


def collect_all() -> dict:
    pay_idx = payouts_index()
    done = settled_races()
    report = json.loads((OUT / "backtest_report.json").read_text(encoding="utf-8")) if (OUT / "backtest_report.json").exists() else None
    model = json.loads((OUT / "model.json").read_text(encoding="utf-8")) if (OUT / "model.json").exists() else None
    bt_rows = [{**r, "settled": True} for r in _csv(OUT / "backtest_ledger.csv")]
    live = live_ledger(pay_idx, done)
    today = dt.datetime.now(JST).strftime("%Y%m%d")
    pred_files = sorted(PRED.glob("*.csv")) if PRED.exists() else []
    latest = [f for f in pred_files if f.stem >= today] or pred_files[-1:]
    upcoming = []
    for f in latest:
        for r in _csv(f):
            k = (r["date"], r["jcd"], int(r["rno"]))
            if r["decision"] == "購入" and k in done:
                r["return"] = pay_idx.get((*k, r["bet_type"], r["combo"]), 0)
            upcoming.append(r)
    return {
        "generated_at": dt.datetime.now(JST).strftime("%Y-%m-%d %H:%M"),
        "collection": collection_status(), "report": report, "model": model,
        "backtest": summarize(bt_rows), "live": summarize(live), "live_pending": sum(1 for r in live if not r["settled"]),
        "predictions": upcoming,
        "runs": (json.loads(STATUS.read_text(encoding="utf-8"))[-10:][::-1] if STATUS.exists() else []),
    }
