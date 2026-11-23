"""入力フォルダ（data/input/）の読み書き（01_01 2章）。

data/input/{jcd}_{場名}/{YYYY-MM}/ に、場・月ごとに次のCSVを置く。

* program.csv : 出走表
* preview.csv : 直前情報（展示タイム・進入・気象）
* result.csv  : 結果（着順・進入・ST）
* payout.csv  : 払戻金

同じキー（date, jcd, rno[, lane / bet_type, combo]）の行は上書きする（再取得しても重複しない）。
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from br.collect.openapi import PAYOUT_COLUMNS, PREVIEW_COLUMNS, PROGRAM_COLUMNS, RESULT_COLUMNS
from br.venues import VENUES

ROOT = Path(__file__).resolve().parents[3]
INPUT_DIR = ROOT / "data" / "input"

FILES = {
    "program": (PROGRAM_COLUMNS, ("date", "jcd", "rno", "lane")),
    "result": (RESULT_COLUMNS, ("date", "jcd", "rno", "lane")),
    "payout": (PAYOUT_COLUMNS, ("date", "jcd", "rno", "bet_type", "combo")),
    "preview": (PREVIEW_COLUMNS, ("date", "jcd", "rno", "lane")),
}


def month_dir(jcd: str, hd: str, root: Path = INPUT_DIR) -> Path:
    return root / f"{jcd}_{VENUES[jcd]}" / f"{hd[:4]}-{hd[4:6]}"


def _key(row: dict, keys) -> tuple:
    return tuple(str(row[k]) for k in keys)


def read(kind: str, path: Path) -> list[dict]:
    f = path / f"{kind}.csv"
    if not f.exists():
        return []
    with f.open(encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def upsert(kind: str, rows: list[dict], root: Path = INPUT_DIR) -> int:
    """rowsを場・月ごとのCSVへ書き込む。書き込んだ行数を返す。"""
    columns, keys = FILES[kind]
    by_dir: dict[Path, list[dict]] = {}
    for r in rows:
        by_dir.setdefault(month_dir(str(r["jcd"]), str(r["date"]), root), []).append(r)
    for d, new in by_dir.items():
        d.mkdir(parents=True, exist_ok=True)
        merged = {_key(r, keys): r for r in read(kind, d)}
        for r in new:
            merged[_key(r, keys)] = {c: r.get(c, "") for c in columns}
        out = sorted(merged.values(), key=lambda r: (r["date"], int(r["rno"]), *[str(r[k]) for k in keys[3:]]))
        tmp = d / f".{kind}.csv.tmp"
        with tmp.open("w", encoding="utf-8", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=columns, lineterminator="\n")
            w.writeheader()
            w.writerows(out)
        os.replace(tmp, d / f"{kind}.csv")
    return len(rows)


def existing_keys(kind: str, jcd: str, hd: str, root: Path = INPUT_DIR) -> set[tuple]:
    _, keys = FILES[kind]
    return {_key(r, keys) for r in read(kind, month_dir(jcd, hd, root)) if r["date"] == hd}


def iter_all(kind: str, root: Path = INPUT_DIR):
    for f in sorted(root.glob(f"*/*/{kind}.csv")):
        with f.open(encoding="utf-8", newline="") as fp:
            yield from csv.DictReader(fp)
