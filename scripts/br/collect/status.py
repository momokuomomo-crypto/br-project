"""自動実行の履歴（data/dashboard/run_status.json、直近50件）。"""
from __future__ import annotations

import datetime as dt
import json

from br.collect.store import ROOT

PATH = ROOT / "data" / "dashboard" / "run_status.json"


def record(kind: str, stats: list[dict]) -> None:
    PATH.parent.mkdir(parents=True, exist_ok=True)
    hist = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else []
    hist.append({
        "at": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M"),
        "kind": kind,
        "days": len(stats),
        "races": sum(s.get("races", 0) for s in stats),
        "errors": sum(s.get("errors", 0) + (1 if "error" in s else 0) for s in stats),
    })
    PATH.write_text(json.dumps(hist[-50:], ensure_ascii=False, indent=1), encoding="utf-8")
