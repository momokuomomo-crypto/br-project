"""確定済みレースの収集（02_01 4章）。

1日ごとに出走表・直前情報・結果（払戻を含む）を取得し、data/input/ に保存する。
"""
from __future__ import annotations

import datetime as dt
import sys
import time

from br.collect import openapi as A
from br.collect import store

DONE_PATH = store.ROOT / "data" / "dashboard" / "fetched_days.txt"


def _done() -> set[str]:
    return set(DONE_PATH.read_text().split()) if DONE_PATH.exists() else set()


def _mark(hd: str) -> None:
    DONE_PATH.parent.mkdir(parents=True, exist_ok=True)
    days = _done() | {hd}
    DONE_PATH.write_text("\n".join(sorted(days)) + "\n")


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def collect_day(client: A.Client, day: dt.date, log=print) -> dict:
    hd = day.strftime("%Y%m%d")
    stat = {"date": hd, "races": 0, "errors": 0}
    prog = client.get("programs", hd)
    if prog:
        store.upsert("program", A.program_rows(prog))
    prev = client.get("previews", hd)
    if prev:
        store.upsert("preview", A.preview_rows(prev))
    res = client.get("results", hd)
    if res:
        r, p = A.result_rows(res)
        store.upsert("result", r)
        store.upsert("payout", p)
        stat["races"] = len(res)
    log(f"{hd}: 出走表{len(prog or [])}R 直前{len(prev or [])}R 結果{len(res or [])}R")
    return stat


def collect(start: dt.date, end: dt.date, newest_first=False, time_budget_min=None, min_interval=1.0,
            refetch_recent=False) -> list[dict]:
    """取得済み（結果まで取れた日）の日は飛ばす。refetch_recent=True なら期間内すべて取り直す。"""
    client = A.Client(min_interval)
    t0 = time.monotonic()
    done = set() if refetch_recent else _done()
    days = [d for d in daterange(start, end) if d.strftime("%Y%m%d") not in done]
    if newest_first:
        days.reverse()
    stats = []
    for d in days:
        if time_budget_min and (time.monotonic() - t0) / 60 > time_budget_min:
            print(f"時間上限（{time_budget_min}分）に達したため中断します。")
            break
        try:
            st = collect_day(client, d)
            stats.append(st)
            if st["races"] or d < dt.date.today() - dt.timedelta(days=3):
                _mark(st["date"])  # 結果が取れた日・非開催が確定した過去日は次回から飛ばす
        except Exception as e:
            print(f"{d}: 失敗 {e}", file=sys.stderr)
            stats.append({"date": d.strftime("%Y%m%d"), "error": str(e)})
    return stats
