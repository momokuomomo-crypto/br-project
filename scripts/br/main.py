"""コマンド入口。実行ディレクトリは scripts/。

python -m br.main collect  --from YYYY-MM-DD --to YYYY-MM-DD [--no-odds] [--pages odds3t,odds2tf] [--budget-min N] [--newest-first]
python -m br.main yesterday                       # 昨日分（＋取りこぼし直近7日）
python -m br.main predict                         # 締切が近いレースの予想
python -m br.main backtest                        # 学習・選定・確認の検証
python -m br.main dashboard <出力先>              # ダッシュボード生成
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from br.collect import status

JST = dt.timezone(dt.timedelta(hours=9))


def _date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%Y-%m-%d").date()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--from", dest="start", type=_date, required=True)
    c.add_argument("--to", dest="end", type=_date, required=True)
    c.add_argument("--no-odds", action="store_true")
    c.add_argument("--pages", default="odds3t,odds2tf,oddstf")
    c.add_argument("--budget-min", type=float)
    c.add_argument("--newest-first", action="store_true")
    c.add_argument("--interval", type=float, default=1.0)
    b = sub.add_parser("backfill")
    b.add_argument("--from", dest="start", type=_date, required=True)
    b.add_argument("--to", dest="end", type=_date, required=True)
    b.add_argument("--no-odds", action="store_true")
    b.add_argument("--pages", default="odds3t,odds2tf,oddstf")
    b.add_argument("--interval", type=float, default=1.0)
    b.add_argument("--budget-min", type=float)
    sm = sub.add_parser("sample")
    sm.add_argument("--date", required=True, help="YYYYMMDD")
    sub.add_parser("yesterday")
    sub.add_parser("predict")
    sub.add_parser("backtest")
    d = sub.add_parser("dashboard")
    d.add_argument("out")
    a = ap.parse_args(argv)

    if a.cmd in ("collect", "yesterday"):
        from br.collect.collector import collect
        if a.cmd == "yesterday":
            today = dt.datetime.now(JST).date()
            stats = collect(today - dt.timedelta(days=7), today - dt.timedelta(days=1), newest_first=True)
        else:
            stats = collect(a.start, a.end, pages=tuple(a.pages.split(",")), with_odds=not a.no_odds,
                            time_budget_min=a.budget_min, newest_first=a.newest_first, min_interval=a.interval)
        status.record(a.cmd, stats)
        failed = [s for s in stats if "error" in s or s.get("errors")]
        return 1 if failed and len(failed) == len(stats) else 0
    if a.cmd == "backfill":
        from br.collect.backfill import backfill
        backfill(a.start, a.end, pages=tuple(a.pages.split(",")), with_odds=not a.no_odds,
                 min_interval=a.interval, budget_min=a.budget_min)
        return 0
    if a.cmd == "sample":
        from br.collect.client import Client
        from br.collect.store import ROOT
        out = ROOT / "samples"
        out.mkdir(exist_ok=True)
        cl = Client()
        for k in ("B", "K"):
            t = cl.lzh_text(k, a.date)
            if t:
                (out / f"{k}{a.date}.txt").write_text(t, encoding="utf-8")
        idx = cl.page("index", a.date) or ""
        (out / f"index_{a.date}.html").write_text(idx, encoding="utf-8")
        import re
        jcd = (re.findall(r"jcd=(\d\d)", idx) or ["02"])[0]
        for p in ("odds3t", "odds2tf", "oddstf"):
            (out / f"{p}_{a.date}_{jcd}_12.html").write_text(cl.page(p, a.date, jcd, 12) or "", encoding="utf-8")
        return 0
    if a.cmd == "predict":
        from br.analysis.predictor import predict
        n = predict()
        status.record("predict", [{"rows": n}])
        return 0
    if a.cmd == "backtest":
        from br.analysis.backtest import run
        rep = run()
        print(json.dumps({k: rep.get(k) for k in ("periods", "log_loss", "selected", "test")}, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "dashboard":
        from br.dashboard.render import build
        build(a.out)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
