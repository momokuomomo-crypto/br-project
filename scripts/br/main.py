"""コマンド入口。実行ディレクトリは scripts/。

python -m br.main collect  --from YYYY-MM-DD --to YYYY-MM-DD   # 期間指定の収集（取得済みの日は飛ばす）
python -m br.main backfill --from YYYY-MM-DD --to YYYY-MM-DD   # 過去分を1か月ずつ取り込み、月ごとに push
python -m br.main yesterday                                     # 直近7日分
python -m br.main predict                                       # 締切が近いレースの予想
python -m br.main backtest                                      # 学習・選定・確認の検証
python -m br.main dashboard <出力先>                            # ダッシュボード生成
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
    for name in ("collect", "backfill"):
        c = sub.add_parser(name)
        c.add_argument("--from", dest="start", type=_date, required=True)
        c.add_argument("--to", dest="end", type=_date, required=True)
        c.add_argument("--budget-min", type=float)
    sub.add_parser("yesterday")
    sub.add_parser("predict")
    sub.add_parser("backtest")
    d = sub.add_parser("dashboard")
    d.add_argument("out")
    a = ap.parse_args(argv)

    if a.cmd == "yesterday":
        from br.collect.collector import collect
        today = dt.datetime.now(JST).date()
        stats = collect(today - dt.timedelta(days=7), today - dt.timedelta(days=1), newest_first=True, refetch_recent=True)
        status.record("yesterday", stats)
        return 0
    if a.cmd == "collect":
        from br.collect.collector import collect
        stats = collect(a.start, a.end, time_budget_min=a.budget_min)
        status.record("collect", stats)
        return 0
    if a.cmd == "backfill":
        from br.collect.backfill import backfill
        backfill(a.start, a.end, budget_min=a.budget_min)
        return 0
    if a.cmd == "predict":
        from br.analysis.predictor import predict
        status.record("predict", [{"races": predict()}])
        return 0
    if a.cmd == "backtest":
        from br.analysis.backtest import run
        rep = run()
        print(json.dumps({k: rep.get(k) for k in ("periods", "log_loss", "selected", "test", "test_top_prob")}, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "dashboard":
        from br.dashboard.render import build
        build(a.out)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
