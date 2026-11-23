"""当日の予想（04_01 6章）。

締切が近いレース（既定：今から WINDOW_MIN 分以内、LEAD_MIN 分以上先）について
発売中のオッズを取得し、運用モデル（data/output/model.json）と購入ルールで
期待値を計算して data/predictions/YYYYMMDD.csv に追記する。
購入対象が無いレースも「見送り」として1行記録する（毎レース買わない）。
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from pathlib import Path

import numpy as np

from br.analysis import dataset, ev
from br.analysis.model import Model
from br.collect import store
from br.collect.client import Client
from br.collect.collector import fetch_race_odds
from br.collect.lzh_parsers import parse_program

JST = dt.timezone(dt.timedelta(hours=9))
PRED_DIR = store.ROOT / "data" / "predictions"
MODEL_PATH = store.ROOT / "data" / "output" / "model.json"
WINDOW_MIN = 25
LEAD_MIN = 2
COLUMNS = ["date", "jcd", "rno", "grade", "deadline", "odds_at", "bet_type", "combo", "prob", "odds", "ev", "decision"]


def _existing(path: Path) -> set[tuple]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        return {(r["jcd"], int(r["rno"])) for r in csv.DictReader(f)}


def ensure_program(client: Client, hd: str) -> list[dict]:
    rows = [r for r in store.iter_all("program") if r["date"] == hd]
    if rows:
        return rows
    from br.collect import odds as O
    txt = client.lzh_text("B", hd)
    if not txt:
        return []
    prog = parse_program(txt, hd)
    meets = O.parse_index(client.page("index", hd) or "")
    for r in prog:
        m = meets.get(r["jcd"], {})
        r["grade"], r["meet_title"] = m.get("grade", ""), m.get("meet_title", "")
    store.upsert("program", prog)
    return [{k: str(v) for k, v in r.items()} for r in prog]


def predict(now: dt.datetime | None = None, window_min: int = WINDOW_MIN) -> int:
    now = now or dt.datetime.now(JST)
    hd = now.strftime("%Y%m%d")
    if not MODEL_PATH.exists():
        print("運用モデル（data/output/model.json）がまだ無いため予想しません")
        return 0
    meta = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    model, rule = Model.from_json(meta), ev.Rule(**meta["rule"])
    client = Client()
    prog = ensure_program(client, hd)
    races: dict[tuple, list] = {}
    for r in prog:
        races.setdefault((r["jcd"], int(r["rno"])), []).append(r)
    path = PRED_DIR / f"{hd}.csv"
    done = _existing(path)
    out = []
    for (jcd, rno), entries in sorted(races.items()):
        if (jcd, rno) in done:
            continue
        dl = dt.datetime.strptime(f"{hd} {entries[0]['deadline']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
        mins = (dl - now).total_seconds() / 60
        if not (LEAD_MIN <= mins <= window_min):
            continue
        odds_row = fetch_race_odds(client, hd, jcd, rno)
        base = {"date": hd, "jcd": jcd, "rno": rno, "grade": entries[0].get("grade", ""),
                "deadline": entries[0]["deadline"], "odds_at": now.strftime("%H:%M")}
        r = dataset.single_race((hd, jcd, rno), base["grade"], entries, odds_row or {})
        if r is None:
            out.append({**base, "decision": "対象外（欠場・オッズ無し）"})
            continue
        p_tri = model.proba(r)
        mask = ev.select(r, p_tri, rule)
        p, odds = ev.probs_and_odds(r, p_tri, rule.bet_type)
        if not mask.any():
            if np.isnan(odds).all():
                out.append({**base, "decision": "対象外（オッズ無し）"})
                continue
            c = int(np.argmax(np.where(np.isnan(odds), -np.inf, p * np.nan_to_num(odds))[0]))
            out.append({**base, "bet_type": rule.bet_type, "combo": ev.COMBO_KEYS[rule.bet_type][c],
                        "prob": round(float(p[0, c]), 4), "odds": float(odds[0, c]),
                        "ev": round(float(p[0, c] * odds[0, c]), 3), "decision": "見送り"})
            continue
        for c in np.flatnonzero(mask[0]):
            out.append({**base, "bet_type": rule.bet_type, "combo": ev.COMBO_KEYS[rule.bet_type][c],
                        "prob": round(float(p[0, c]), 4), "odds": float(odds[0, c]),
                        "ev": round(float(p[0, c] * odds[0, c]), 3), "decision": "購入"})
    if out:
        PRED_DIR.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
            if new:
                w.writeheader()
            w.writerows(out)
    print(f"{hd} {now:%H:%M}: {len({(o['jcd'], o['rno']) for o in out})}レースを予想、購入{sum(o['decision'] == '購入' for o in out)}点")
    return len(out)
