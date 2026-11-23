"""公式サイトのオッズページ解析（02_01 4章）。

* odds3t : 3連単 120通り
* odds2tf: 2連単 30通り（・2連複 15通り。2連複は使わない）
* oddstf : 単勝 6通り（・複勝。複勝は使わない）

いずれも `td.oddsPoint` に値が入る。欠場艇を含む組合せや発売前は
数値以外（"欠場"、"-" 等）になるため空欄として扱う。
"""
from __future__ import annotations

import itertools
import re

from bs4 import BeautifulSoup

BOATS = range(1, 7)
TRIFECTA_KEYS = [f"{a}-{b}-{c}" for a, b, c in itertools.permutations(BOATS, 3)]
EXACTA_KEYS = [f"{a}-{b}" for a, b in itertools.permutations(BOATS, 2)]
WIN_KEYS = [str(a) for a in BOATS]

_NUM = re.compile(r"^\d+(?:\.\d+)?$")


def _value(text: str) -> float | None:
    t = text.strip().replace(",", "")
    return float(t) if _NUM.match(t) else None


def _odds_tables(html: str):
    soup = BeautifulSoup(html, "html.parser")
    return [t for t in soup.find_all("table") if t.select_one("td.oddsPoint")]


def _grid(table, n_cols: int = 6) -> list[list]:
    """表の oddsPoint を [行][列] に並べる（行は tbody の tr 順）。"""
    rows = []
    for tr in table.select("tbody tr"):
        cells = tr.select("td.oddsPoint")
        if cells:
            rows.append(cells)
    for r in rows:
        if len(r) != n_cols:
            raise ValueError(f"オッズ表の列数が想定外です: {len(r)}")
    return rows


def parse_trifecta(html: str) -> dict[str, float | None] | None:
    """3連単。列 = 1着艇（1〜6）、行 = (2着, 3着) を2着昇順・3着昇順に20行。"""
    tables = _odds_tables(html)
    if not tables:
        return None
    rows = _grid(tables[0])
    if len(rows) != 20:
        raise ValueError(f"3連単の行数が想定外です: {len(rows)}")
    out: dict[str, float | None] = {}
    for col, first in enumerate(BOATS):
        others = [b for b in BOATS if b != first]
        for row in range(20):
            second = others[row // 4]
            thirds = [b for b in others if b != second]
            third = thirds[row % 4]
            cell = rows[row][col]
            # 直前のtdに3着艇番が入っている。並びの想定と照合する。
            prev = cell.find_previous_sibling("td")
            if prev is not None and prev.get_text(strip=True) not in ("", str(third)):
                raise ValueError("3連単の並びが想定と異なります")
            out[f"{first}-{second}-{third}"] = _value(cell.get_text())
    return out


def parse_exacta(html: str) -> dict[str, float | None] | None:
    """2連単（ページ内の最初のオッズ表）。列 = 1着艇、行 = 2着艇昇順の5行。"""
    tables = _odds_tables(html)
    if not tables:
        return None
    rows = _grid(tables[0])
    if len(rows) != 5:
        raise ValueError(f"2連単の行数が想定外です: {len(rows)}")
    out: dict[str, float | None] = {}
    for col, first in enumerate(BOATS):
        others = [b for b in BOATS if b != first]
        for row in range(5):
            out[f"{first}-{others[row]}"] = _value(rows[row][col].get_text())
    return out


def parse_win(html: str) -> dict[str, float | None] | None:
    """単勝（ページ内の最初のオッズ表、艇番順の6行）。"""
    tables = _odds_tables(html)
    if not tables:
        return None
    cells = tables[0].select("td.oddsPoint")
    if len(cells) != 6:
        raise ValueError(f"単勝の数が想定外です: {len(cells)}")
    return {str(b): _value(c.get_text()) for b, c in zip(BOATS, cells)}


def parse_deadlines(html: str) -> dict[int, str]:
    """オッズ・出走表ページ上部の「締切予定時刻」行から {R: "HH:MM"} を返す。"""
    soup = BeautifulSoup(html, "html.parser")
    for tr in soup.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
        if cells and cells[0] == "締切予定時刻":
            times = [c for c in cells[1:] if re.match(r"^\d{1,2}:\d{2}$", c)]
            return {i + 1: t for i, t in enumerate(times)}
    return {}


_GRADE = re.compile(r"\bis-(SG|PG1|G1|G2|G3|ippan)[ab]?\b")
GRADE_LABEL = {"SG": "SG", "PG1": "PG1", "G1": "G1", "G2": "G2", "G3": "G3", "ippan": "一般"}


def parse_index(html: str) -> dict[str, dict]:
    """開催一覧（race/index）から {jcd: {"grade", "meet_title"}} を返す。"""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, dict] = {}
    for tbody in soup.select("table tbody"):
        link = tbody.find("a", href=re.compile(r"raceindex\?.*jcd=\d\d"))
        if link is None:
            continue
        jcd = re.search(r"jcd=(\d\d)", link["href"]).group(1)
        grade = ""
        for td in tbody.find_all("td"):
            m = _GRADE.search(" ".join(td.get("class", [])))
            if m:
                grade = GRADE_LABEL[m.group(1)]
                break
        out[jcd] = {"grade": grade, "meet_title": link.get_text(strip=True)}
    return out
