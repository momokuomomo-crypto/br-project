"""当日の予想（04_01 6章）。

当日の出走表・直前情報（Open API の today.json）を取得し、締切まで LEAD_MIN〜WINDOW_MIN 分で
直前情報（展示タイム）がそろったレースについて、運用モデル（data/output/model.json）と
購入ルールで期待値を計算し、data/predictions/YYYYMMDD.csv に追記する。
購入対象が無いレースも「見送り」として1行記録する（毎レース買わない）。
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import numpy as np

from br.analysis import dataset, ev
from br.analysis.model import load_saved
from br.collect import openapi as A
from br.collect import store

JST = dt.timezone(dt.timedelta(hours=9))
PRED_DIR = store.ROOT / "data" / "predictions"
MODEL_PATH = store.ROOT / "data" / "output" / "model.json"
WINDOW_MIN = 30
LEAD_MIN = 1
COLUMNS = ["date", "jcd", "rno", "grade", "deadline", "predicted_at", "bet_type", "combo", "prob", "odds", "ev", "decision"]


def _existing(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        return {(r["jcd"], int(r["rno"])) for r in csv.DictReader(f)}


def _group(rows):
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault((r["jcd"], int(r["rno"])), []).append({k: str(v) for k, v in r.items()})
    return out


def predict(now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(JST)
    hd = now.strftime("%Y%m%d")
    if not MODEL_PATH.exists():
        print("運用モデル（data/output/model.json）がまだ無いため予想しません")
        return 0
    model, payout, meta = load_saved(MODEL_PATH)
    rule = ev.Rule(**meta["rule"])
    client = A.Client()
    progs = [r for r in A.program_rows(client.get("programs", None) or []) if r["date"] == hd]
    prevs = [r for r in A.preview_rows(client.get("previews", None) or []) if r["date"] == hd]
    prog, prev = _group(progs), _group(prevs)
    path = PRED_DIR / f"{hd}.csv"
    done = _existing(path)
    out = []
    for key, entries in sorted(prog.items()):
        if key in done or not entries[0]["deadline"]:
            continue
        dl = dt.datetime.strptime(f"{hd} {entries[0]['deadline']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
        mins = (dl - now).total_seconds() / 60
        pv = prev.get(key, [])
        ready = len(pv) == 6 and all(p.get("ex_time") not in ("", "0", "0.0") for p in pv)
        if not (LEAD_MIN <= mins <= WINDOW_MIN) or not ready:
            continue
        base = {"date": hd, "jcd": key[0], "rno": key[1], "grade": entries[0]["grade"],
                "deadline": entries[0]["deadline"], "predicted_at": now.strftime("%H:%M")}
        r = dataset.single_race((hd, *key), base["grade"], entries, pv)
        if r is None:
            out.append({**base, "decision": "対象外（欠場）"})
            continue
        p, odds, e = ev.ev_table(r, model.proba(r), payout, rule.bet_type)
        mask = ev.select(p, odds, e, rule)
        keys = ev.COMBO_KEYS[rule.bet_type]
        picks = np.flatnonzero(mask[0]) if mask.any() else [int(np.argmax(e[0]))]
        for c in picks:
            out.append({**base, "bet_type": rule.bet_type, "combo": keys[c], "prob": round(float(p[0, c]), 4),
                        "odds": round(float(odds[0, c]), 1), "ev": round(float(e[0, c]), 3),
                        "decision": "購入" if mask.any() else "見送り"})
    if out:
        PRED_DIR.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            if new:
                w.writeheader()
            w.writerows(out)
    print(f"{hd} {now:%H:%M}: {len({(o['jcd'], o['rno']) for o in out})}レースを判定、購入{sum(o['decision'] == '購入' for o in out)}点")
    return len(out)
