"""確定済みレースの収集（02_01 5章）。

1日ごとに
1. 開催一覧（グレード・節名）
2. 番組表LZH → program.csv
3. 競走成績LZH → result.csv / payout.csv
4. 成績のある各レースの確定オッズ（3連単・2連単・単勝）→ odds.csv
を取得する。既に odds.csv にあるレースは取得しない（中断しても再開できる）。
"""
from __future__ import annotations

import datetime as dt
import sys
import time

from br.collect import odds as O
from br.collect import store
from br.collect.client import Client
from br.collect.lzh_parsers import parse_program, parse_result

ODDS_PAGES = ("odds3t", "odds2tf", "oddstf")


def daterange(start: dt.date, end: dt.date):
    d = start
    while d <= end:
        yield d
        d += dt.timedelta(days=1)


def fetch_race_odds(client: Client, hd: str, jcd: str, rno: int, pages=ODDS_PAGES) -> dict | None:
    row = {"date": hd, "jcd": jcd, "rno": rno,
           "fetched_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")}
    got = False
    if "odds3t" in pages:
        tri = O.parse_trifecta(client.page("odds3t", hd, jcd, rno) or "")
        if tri:
            got = True
            row.update({f"tri_{k}": ("" if v is None else v) for k, v in tri.items()})
    if "odds2tf" in pages:
        ex = O.parse_exacta(client.page("odds2tf", hd, jcd, rno) or "")
        if ex:
            got = True
            row.update({f"ex_{k}": ("" if v is None else v) for k, v in ex.items()})
    if "oddstf" in pages:
        win = O.parse_win(client.page("oddstf", hd, jcd, rno) or "")
        if win:
            got = True
            row.update({f"win_{k}": ("" if v is None else v) for k, v in win.items()})
    return row if got else None


def collect_day(client: Client, day: dt.date, pages=ODDS_PAGES, with_odds: bool = True, log=print) -> dict:
    hd = day.strftime("%Y%m%d")
    stat = {"date": hd, "races": 0, "odds_new": 0, "errors": 0}
    meets = O.parse_index(client.page("index", hd) or "")
    btxt = client.lzh_text("B", hd)
    if btxt:
        prog = parse_program(btxt, hd)
        for r in prog:
            m = meets.get(r["jcd"], {})
            r["grade"], r["meet_title"] = m.get("grade", ""), m.get("meet_title", "")
        store.upsert("program", prog)
    ktxt = client.lzh_text("K", hd)
    if not ktxt:
        log(f"{hd}: 競走成績なし（非開催または未公開）")
        return stat
    results, payouts = parse_result(ktxt, hd)
    store.upsert("result", results)
    store.upsert("payout", payouts)
    races = sorted({(r["jcd"], int(r["rno"])) for r in results})
    stat["races"] = len(races)
    if not with_odds:
        return stat
    rows = []
    for jcd in sorted({j for j, _ in races}):
        have = {int(k[2]) for k in store.existing_keys("odds", jcd, hd)}
        for j, rno in races:
            if j != jcd or rno in have:
                continue
            try:
                row = fetch_race_odds(client, hd, jcd, rno, pages)
            except Exception as e:  # 1レースの失敗で全体を止めない
                stat["errors"] += 1
                log(f"{hd} {jcd} {rno}R オッズ取得失敗: {e}")
                continue
            if row:
                rows.append(row)
    store.upsert("odds", rows)
    stat["odds_new"] = len(rows)
    log(f"{hd}: {len(races)}レース、オッズ新規{len(rows)}件、失敗{stat['errors']}件")
    return stat


def collect(start: dt.date, end: dt.date, pages=ODDS_PAGES, with_odds=True,
            time_budget_min: float | None = None, newest_first=False, min_interval=1.0) -> list[dict]:
    client = Client(min_interval=min_interval)
    t0 = time.monotonic()
    days = list(daterange(start, end))
    if newest_first:
        days.reverse()
    stats = []
    for d in days:
        if time_budget_min and (time.monotonic() - t0) / 60 > time_budget_min:
            print(f"時間上限（{time_budget_min}分）に達したため中断します。次回は続きから取得します。")
            break
        try:
            stats.append(collect_day(client, d, pages, with_odds))
        except Exception as e:
            print(f"{d}: 失敗 {e}", file=sys.stderr)
            stats.append({"date": d.strftime("%Y%m%d"), "error": str(e)})
    return stats
