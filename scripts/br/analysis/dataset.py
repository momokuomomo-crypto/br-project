"""分析用データセットの組み立て（04_01 3章）。

1レース = 6艇の特徴量（6×F）、的中組合せ、券種ごとの払戻金。
6艇がすべて1〜6着に入り（失格・欠場なし）、3連単の払戻が1通りだけのレースを対象とする。
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from br.collect import store

PERMS = list(itertools.permutations(range(6), 3))  # 0始まりの艇番
TRI_KEYS = [f"{a+1}-{b+1}-{c+1}" for a, b, c in PERMS]
EX_PAIRS = list(itertools.permutations(range(6), 2))
EX_KEYS = [f"{a+1}-{b+1}" for a, b in EX_PAIRS]
WIN_KEYS = [str(i) for i in range(1, 7)]
TRI_INDEX = {k: i for i, k in enumerate(TRI_KEYS)}
EX_INDEX = {k: i for i, k in enumerate(EX_KEYS)}
WIN_INDEX = {k: i for i, k in enumerate(WIN_KEYS)}
EX_FROM_TRI = np.zeros((30, 120))
WIN_FROM_TRI = np.zeros((6, 120))
for ci, (a, b, c) in enumerate(PERMS):
    EX_FROM_TRI[EX_PAIRS.index((a, b)), ci] = 1
    WIN_FROM_TRI[a, ci] = 1

CLASS_CODE = {"A1": 3, "A2": 2, "B1": 1, "B2": 0}
# レース内で標準化する数値特徴（符号はそのまま。小さいほど良い項目もモデルが係数で扱う）
NUMERIC = ["class", "nat_win", "nat_2r", "loc_win", "loc_2r", "motor_2r", "boat_2r",
           "avg_st", "flying", "weight", "ex_time", "ex_st", "course"]
LANES = [f"lane{i}" for i in range(1, 6)]  # 6号艇を基準とするダミー
# 場ごとの号艇の強さ（イン有利の度合いは場によって大きく違う。例：戸田は1号艇が弱い）。
# 各艇に「その場のその号艇の過去の1着率・2着以内率・3着以内率」が全国平均からどれだけずれているか
# （ロジットの差）を持たせる。率はそのレースの月より前の結果だけで数える（未来の結果は使わない）。
# 開催が少ないうちは全国平均に寄せる（VL_PRIOR レース分の全国平均を足して数える）。
VENUE_LANE = ["vl_1st", "vl_top2", "vl_top3"]
# 全国平均（5年分の結果から。1着・2着・3着になる割合、号艇順）
LANE_PRIOR = np.array([[0.5467, 0.1739, 0.0893], [0.1396, 0.2477, 0.1858], [0.1256, 0.2142, 0.1983],
                       [0.0998, 0.1651, 0.1970], [0.0574, 0.1200, 0.1749], [0.0308, 0.0792, 0.1546]])
VL_PRIOR = 300
# 天気（直前情報の風速・波高）。レース全体で同じ値なので、号艇との掛け算で「荒れるとインが弱い」
# などの効き方を表す。1号艇だけ（in）と、号艇の外側ほど大きい値（lane）の2通り。
WEATHER = ["wind_in", "wave_in", "wind_lane", "wave_lane"]
FEATURES = LANES + VENUE_LANE + WEATHER + NUMERIC
# 直前情報（展示タイム・展示ST・進入コース・天気）を使うか。当日予想は約10分間隔で更新される
# api/v1 から締切前に取得する（直前情報が出ていないレースは予想しない）。
USE_PREVIEW = True


@dataclass
class Races:
    keys: list = field(default_factory=list)       # (date, jcd, rno)
    grade: list = field(default_factory=list)
    x: np.ndarray | None = None                    # (N, 6, F)
    venue_lane: dict = field(default_factory=dict)  # jcd -> (6, 4) 1着・2着・3着・出走の数（全期間）
    winner: np.ndarray | None = None               # (N,) 的中3連単のindex（不明は-1）
    pay: dict = field(default_factory=dict)        # bet_type -> (N, n_combo) 100円あたり払戻

    def subset(self, idx) -> "Races":
        idx = np.asarray(idx)
        if idx.dtype == bool:
            idx = np.flatnonzero(idx)
        return Races(keys=[self.keys[i] for i in idx], grade=[self.grade[i] for i in idx],
                     x=self.x[idx], winner=self.winner[idx], pay={k: v[idx] for k, v in self.pay.items()})

    def __len__(self) -> int:
        return len(self.keys)

    @property
    def dates(self) -> np.ndarray:
        return np.array([k[0] for k in self.keys])


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def venue_lane_features(counts: np.ndarray | None) -> np.ndarray:
    """(6, 4) の数 → (6, 3) 全国平均とのロジット差。"""
    c = np.zeros((6, 4)) if counts is None else np.asarray(counts, dtype=float)
    n = c[:, 3:4] + VL_PRIOR
    rate = (np.cumsum(c[:, :3], axis=1) + VL_PRIOR * np.cumsum(LANE_PRIOR, axis=1)) / n
    return _logit(rate) - _logit(np.cumsum(LANE_PRIOR, axis=1))


def boat_features(entries: list[dict], previews: dict[int, dict], jcd: str | None = None,
                  vl_counts: np.ndarray | None = None) -> np.ndarray:
    """6艇（枠番順）の特徴量。数値はレース内で標準化し、欠損はレース内平均（=0）。"""
    num = []
    for e in entries:
        pv = previews.get(int(e["lane"]), {})
        row = {"class": CLASS_CODE.get(e.get("racer_class", ""), np.nan)}
        for k in ("nat_win", "nat_2r", "loc_win", "loc_2r", "motor_2r", "boat_2r", "avg_st", "flying", "weight"):
            row[k] = _f(e.get(k))
        row["ex_time"] = _f(pv.get("ex_time"))
        row["ex_st"] = _f(pv.get("ex_st"))
        row["course"] = _f(pv.get("course"))
        if row["ex_time"] == 0:
            row["ex_time"] = np.nan
        num.append([row[k] for k in NUMERIC])
    a = np.array(num, dtype=float)
    with np.errstate(all="ignore"):
        mean = np.nanmean(a, axis=0, keepdims=True)
        a = np.where(np.isnan(a), mean, a)
        a = np.nan_to_num(a - a.mean(axis=0, keepdims=True))
        sd = a.std(axis=0, keepdims=True)
        a = a / np.where(sd > 0, sd, 1)
    lanes = np.zeros((6, len(LANES)))
    for i in range(5):
        lanes[i, i] = 1
    wind = wave = 0.0
    for pv in previews.values():
        w, v = _f(pv.get("wind")), _f(pv.get("wave"))
        wind = w if np.isfinite(w) else 0.0
        wave = v if np.isfinite(v) else 0.0
        break
    pos = (np.arange(6) - 2.5) / 2.5          # 1号艇 -1 〜 6号艇 +1
    is1 = (np.arange(6) == 0).astype(float)
    weather = np.stack([is1 * wind / 5, is1 * wave / 5, pos * wind / 5, pos * wave / 5], axis=1)
    return np.concatenate([lanes, venue_lane_features(vl_counts), weather, a], axis=1)


def _group(rows):
    out: dict[tuple, list] = {}
    for r in rows:
        out.setdefault((r["date"], r["jcd"], int(r["rno"])), []).append(r)
    return out


def load(root=None) -> Races:
    """場・月フォルダごとに読み、必要な配列だけを残す（全期間を一度に辞書で持たない）。"""
    root = root or store.INPUT_DIR
    keys, grades, xs, wn, p_tri, p_ex, p_win = [], [], [], [], [], [], []
    vl: dict[str, np.ndarray] = {}
    # 場フォルダの中は月の古い順に並ぶので、月ごとに「それより前の月まで」の数を使える
    for mdir in sorted(p for p in root.glob("*/*") if p.is_dir()):
        jcd = mdir.parent.name[:2]
        cnt = vl.setdefault(jcd, np.zeros((6, 4)))
        snap = cnt.copy()
        prog = _group(store.read("program", mdir))
        prev = _group(store.read("preview", mdir))
        res = _group(store.read("result", mdir))
        pays: dict[tuple, dict] = {}
        for r in store.read("payout", mdir):
            pays.setdefault((r["date"], r["jcd"], int(r["rno"])), {}).setdefault(r["bet_type"], {})[r["combo"]] = int(r["payout"])
        for rr in res.values():
            if len(rr) == 6 and all(r["place"].isdigit() for r in rr):
                for r in rr:
                    ln, pl = int(r["lane"]) - 1, int(r["place"])
                    if 0 <= ln < 6:
                        cnt[ln, 3] += 1
                        if pl <= 3:
                            cnt[ln, pl - 1] += 1
        for k in sorted(res):
            rr = res[k]
            entries = sorted(prog.get(k, []), key=lambda e: int(e["lane"]))
            if len(entries) != 6 or len(rr) != 6:
                continue
            if not all(r["place"].isdigit() and 1 <= int(r["place"]) <= 6 for r in rr):
                continue
            pay = pays.get(k, {})
            tri = pay.get("trifecta", {})
            if len(tri) != 1:
                continue
            combo = next(iter(tri))
            if combo not in TRI_INDEX:
                continue
            pv = {int(p["lane"]): p for p in prev.get(k, [])} if USE_PREVIEW else {}
            xs.append(boat_features(entries, pv, k[1], snap).astype(np.float32))
            wn.append(TRI_INDEX[combo])
            ti = np.zeros(120, dtype=np.float32); ti[TRI_INDEX[combo]] = tri[combo]
            ei = np.zeros(30, dtype=np.float32)
            for c, v in pay.get("exacta", {}).items():
                if c in EX_INDEX:
                    ei[EX_INDEX[c]] = v
            wi = np.zeros(6, dtype=np.float32)
            for c, v in pay.get("win", {}).items():
                if c in WIN_INDEX:
                    wi[WIN_INDEX[c]] = v
            p_tri.append(ti); p_ex.append(ei); p_win.append(wi)
            keys.append(k)
            grades.append(entries[0].get("grade", ""))
    n = len(keys)
    order = sorted(range(n), key=lambda i: (keys[i][0], keys[i][1], keys[i][2]))
    out = Races(keys=[keys[i] for i in order], grade=[grades[i] for i in order],
                venue_lane={j: c.tolist() for j, c in vl.items()})
    out.x = (np.stack(xs)[order] if n else np.zeros((0, 6, len(FEATURES)))).astype(np.float64)
    out.winner = np.array(wn, dtype=int)[order] if n else np.zeros(0, dtype=int)
    out.pay = {"trifecta": np.stack(p_tri)[order] if n else np.zeros((0, 120)),
               "exacta": np.stack(p_ex)[order] if n else np.zeros((0, 30)),
               "win": np.stack(p_win)[order] if n else np.zeros((0, 6))}
    return out


def single_race(key: tuple, grade: str, entries: list[dict], previews: list[dict],
                venue_lane: dict | None = None) -> Races | None:
    """当日予想用：1レース分の Races を作る（結果・払戻は無し）。"""
    entries = sorted(entries, key=lambda e: int(e["lane"]))
    if len(entries) != 6:
        return None
    pv = {int(p["lane"]): p for p in previews} if USE_PREVIEW else {}
    return Races(keys=[key], grade=[grade], x=boat_features(entries, pv, key[1], (venue_lane or {}).get(key[1]))[None], winner=np.array([-1]),
                 pay={"trifecta": np.zeros((1, 120)), "exacta": np.zeros((1, 30)), "win": np.zeros((1, 6))})
