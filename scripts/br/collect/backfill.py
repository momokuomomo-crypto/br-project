"""過去データの一括取り込み（02_01 6章）。

新しい月から古い月へ1か月ずつ取得し、1か月ごとに git commit・push する
（長時間の実行が途中で止まっても、それまでの分は残り、次回は続きから取る）。
"""
from __future__ import annotations

import datetime as dt
import subprocess
import time

from br.collect import status
from br.collect.collector import collect
from br.collect.store import ROOT


def months_desc(start: dt.date, end: dt.date):
    y, m = end.year, end.month
    while (y, m) >= (start.year, start.month):
        first = dt.date(y, m, 1)
        nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
        yield max(first, start), min(nxt - dt.timedelta(days=1), end)
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)


def git_push(message: str) -> None:
    def run(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, capture_output=True, text=True)
    run("add", "data")
    if run("diff", "--cached", "--quiet", check=False).returncode == 0:
        return
    run("commit", "-m", message)
    for i in range(4):
        run("pull", "--rebase", "-X", "theirs", "origin", "main", check=False)
        if run("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
        time.sleep(10 * (i + 1))
    raise RuntimeError("git push に失敗しました")


def backfill(start: dt.date, end: dt.date, min_interval=1.0, budget_min=None) -> None:
    t0 = time.monotonic()
    for a, b in months_desc(start, end):
        left = None if budget_min is None else budget_min - (time.monotonic() - t0) / 60
        if left is not None and left <= 0:
            print("時間上限に達したため終了します（次回は続きから）")
            break
        stats = collect(a, b, min_interval=min_interval,
                        newest_first=True, time_budget_min=left)
        status.record(f"backfill {a:%Y-%m}", stats)
        git_push(f"data: 過去データ取り込み {a:%Y-%m} [skip ci]")
