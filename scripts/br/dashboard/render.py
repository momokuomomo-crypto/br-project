"""ダッシュボードのHTML生成（06_02 5章）。1ファイルの index.html を出力する。"""
from __future__ import annotations

import html
from pathlib import Path

from br.analysis.ev import LABEL
from br.dashboard.data import collect_all
from br.venues import VENUES

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--accent:#1f6feb;--pos:#1a7f37;--neg:#cf222e}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1d1d20;--fg:#ececef;--muted:#9a9aa2;--line:#2e2e33;--accent:#4c8dff;--pos:#3fb950;--neg:#ff7b72}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Hiragino Sans","Noto Sans JP",sans-serif}
main{max-width:1040px;margin:0 auto;padding:16px}h1{font-size:22px;margin:8px 0 4px}h2{font-size:17px;margin:0 0 10px}
.sub{color:var(--muted);font-size:13px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:14px 0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.kpi{border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.kpi b{display:block;font-size:19px}.kpi span{color:var(--muted);font-size:12px}.pos{color:var(--pos)}.neg{color:var(--neg)}
.tbl{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th:first-child,td:first-child,td.l,th.l{text-align:left}th{color:var(--muted);font-weight:600}svg{width:100%;height:auto}
.note{color:var(--muted);font-size:12px;margin-top:8px}.bar{height:6px;background:var(--line);border-radius:3px;overflow:hidden}.bar i{display:block;height:100%;background:var(--accent)}
"""


def pct(v) -> str:
    return "—" if v is None else f"{v * 100:.1f}%"


def signed(v) -> str:
    cls = "pos" if v > 0 else "neg" if v < 0 else ""
    return f'<b class="{cls}">{v:+,.0f}円</b>'


def esc(s) -> str:
    return html.escape(str(s))


def sparkline(series: list[float]) -> str:
    if len(series) < 2:
        return ""
    w, h = 1000, 180
    lo, hi = min(0, min(series)), max(0, max(series))
    span = (hi - lo) or 1
    pts = " ".join(f"{i * w / (len(series) - 1):.1f},{h - (v - lo) * h / span:.1f}" for i, v in enumerate(series))
    zero = h - (0 - lo) * h / span
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="累積収支の推移">'
            f'<line x1="0" x2="{w}" y1="{zero:.1f}" y2="{zero:.1f}" stroke="var(--line)" stroke-width="2"/>'
            f'<polyline fill="none" stroke="var(--accent)" stroke-width="2.5" points="{pts}"/></svg>')


def kpis(s: dict) -> str:
    return ('<div class="kpis">'
            f'<div class="kpi"><span>収支</span>{signed(s["profit"])}</div>'
            f'<div class="kpi"><span>回収率</span><b>{pct(s["roi"])}</b></div>'
            f'<div class="kpi"><span>購入</span><b>{s["bets"]:,}点</b></div>'
            f'<div class="kpi"><span>買ったレース</span><b>{s["races"]:,}</b></div>'
            f'<div class="kpi"><span>的中</span><b>{s["hits"]:,}</b></div>'
            f'<div class="kpi"><span>購入額 / 払戻額</span><b style="font-size:14px">{s["stake"]:,} / {s["return"]:,.0f}</b></div></div>')


def monthly(s: dict) -> str:
    if not s["monthly"]:
        return ""
    rows = "".join(f'<tr><td>{m["month"][:4]}-{m["month"][4:]}</td><td>{m["bets"]:,}</td><td>{m["stake"]:,}</td>'
                   f'<td>{m["return"]:,.0f}</td><td>{signed(m["return"] - m["stake"])}</td><td>{pct(m["return"] / m["stake"] if m["stake"] else None)}</td></tr>'
                   for m in s["monthly"])
    return f'<div class="tbl"><table><tr><th>月</th><th>点数</th><th>購入額</th><th>払戻額</th><th>収支</th><th>回収率</th></tr>{rows}</table></div>'


def _r(st: dict) -> str:
    return f'{pct(st["roi"])}<span class="sub"> ({st["bets"]:,})</span>' if st["bets"] else "—"


def inside_section(ix: dict) -> str:
    st = ix["start"]
    sw, sp = ix["since_win"], ix["since_place"]
    k = ('<div class="kpis">'
         f'<div class="kpi"><span>単勝 回収率</span><b>{pct(sw["roi"])}</b></div>'
         f'<div class="kpi"><span>単勝 収支</span>{signed(sw["profit"])}</div>'
         f'<div class="kpi"><span>複勝 回収率</span><b>{pct(sp["roi"])}</b></div>'
         f'<div class="kpi"><span>複勝 収支</span>{signed(sp["profit"])}</div>'
         f'<div class="kpi"><span>対象レース</span><b>{sw["bets"]:,}</b></div>'
         f'<div class="kpi"><span>的中（単勝 / 複勝）</span><b>{sw["hits"]:,} / {sp["hits"]:,}</b></div></div>')
    rows = "".join(
        f'<tr><td>{esc(v["name"])}</td><td>{_r(v["since_win"])}</td><td>{pct(v["since_place"]["roi"]) if v["since_place"]["bets"] else "—"}</td>'
        f'<td>{_r(v["all_win"])}</td><td>{pct(v["all_place"]["roi"]) if v["all_place"]["bets"] else "—"}</td></tr>'
        for v in ix["venues"])
    aw, ap = ix["all_win"], ix["all_place"]
    rows += (f'<tr><td><b>全場</b></td><td>{_r(sw)}</td><td>{pct(sp["roi"])}</td><td>{_r(aw)}</td><td>{pct(ap["roi"])}</td></tr>')
    s = f'{st[:4]}/{int(st[4:6])}/{int(st[6:])}'
    fc = ix["focus"]
    rows += (f'<tr><td class="l"><b>注目：{esc(fc["label"])}</b></td><td>{_r(fc["since_win"])}</td><td><b>{pct(fc["since_place"]["roi"]) if fc["since_place"]["bets"] else "—"}</b></td>'
             f'<td>{_r(fc["all_win"])}</td><td><b>{pct(fc["all_place"]["roi"]) if fc["all_place"]["bets"] else "—"}</b></td></tr>')
    return (f'<section class="card"><h2>試走1位の1号艇（全場・全レースの記録）</h2>'
            f'<div class="sub">1号艇の展示タイムが、場・号艇ごとの平均との差で6艇中いちばん速いレースで、1号艇の単勝と複勝を100円ずつ買った場合。記録開始 {s}</div>'
            f'{k}{sparkline(ix["since_series"]["series"])}'
            f'<div class="tbl"><table><tr><th>場</th><th>記録開始から 単勝（点数）</th><th>複勝</th><th>全期間 {esc(ix["first"] or "")}〜 単勝（点数）</th><th>複勝</th></tr>{rows}</table></div>'
            f'<div class="note">号艇ごとの平均タイムは記録開始より前のデータで計算し、以後は固定しています。全期間の欄は平均の計算に使ったデータも含むので、少し甘めの参考値です。'
            f'注目条件（尼崎・1号艇がB1級）は、場×級別の約90通りから過去の複勝の成績で選んだもので、本命は複勝です。記録開始からの成績で本物かを確かめます。場を後から選ぶと運で100%を超える場も出るため、場ごとの差は記録開始からの成績で確かめます。グラフは単勝・複勝を合わせた累積収支。実際の購入記録ではなくシミュレーションです。</div></section>')


def build(out_dir: str) -> Path:
    d = collect_all()
    parts = [f'<main><h1>競艇 期待値派ダッシュボード</h1><div class="sub">更新 {esc(d["generated_at"])}（日本時間）・全24場・全グレード</div>']

    # 次のレースのおすすめ
    preds = d["predictions"]
    buys = [p for p in preds if p["decision"] == "購入"]
    rule = (d["model"] or {}).get("rule")
    body = ""
    if buys:
        rows = "".join(
            f'<tr><td>{esc(p["deadline"])}</td><td class="l">{esc(VENUES.get(p["jcd"], p["jcd"]))} {int(p["rno"])}R</td><td class="l">{esc(p["grade"])}</td>'
            f'<td class="l">{esc(LABEL.get(p["bet_type"], p["bet_type"]))} {esc(p["combo"])}</td><td>{float(p["odds"]):.1f}</td><td>{float(p["prob"]) * 100:.1f}%</td><td>{float(p["ev"]):.2f}</td>'
            f'<td>{"" if p.get("return") is None else ("的中 " + format(p["return"], ",") + "円" if p["return"] else "不的中")}</td></tr>'
            for p in sorted(buys, key=lambda p: (p["date"], p["deadline"])))
        body = f'<div class="tbl"><table><tr><th>締切</th><th class="l">レース</th><th class="l">グレード</th><th class="l">買い目</th><th>オッズ</th><th>推定確率</th><th>期待値</th><th>結果</th></tr>{rows}</table></div>'
    else:
        body = '<p>現在、おすすめはありません（割安な買い目が無いレースは見送ります）。</p>'
    seen = len({(p["jcd"], p["rno"]) for p in preds})
    rtxt = f'ルール：{esc(LABEL.get(rule["bet_type"]))}、期待値 {rule["min_ev"]} 以上、想定オッズ {rule["max_odds"]} 倍以下、1レース{rule["max_per_race"]}点まで、1点100円。' if rule else "運用モデルはまだありません。"
    parts.append(f'<section class="card"><h2>次のレースのおすすめ</h2>{body}<div class="note">{seen}レースを判定し、購入{len(buys)}点。{rtxt}想定オッズは過去の払戻実績から推定した値で、実際のオッズではありません（オッズの履歴を自動で取れる正規の入手先が無いため）。収支は実際の払戻金で計算します。</div></section>')

    # 収支
    live, bt, rep = d["live"], d["backtest"], d["report"]
    parts.append(f'<section class="card"><h2>運用開始からの収支（予想記録どおりに買った場合）</h2>{kpis(live)}'
                 f'{sparkline(live["series"])}{monthly(live)}<div class="note">未確定 {d["live_pending"]}点。実際の購入記録ではなくシミュレーションです。</div></section>')
    parts.append(inside_section(d["inside"]))
    if rep and rep.get("test"):
        per = rep["periods"]
        mk = rep.get("test_top_prob") or {}
        parts.append(
            f'<section class="card"><h2>検証：学習に使っていない期間の成績</h2>'
            f'<div class="sub">学習 {esc(per["train"][0])}〜（{per["train"][2]:,}R） / ルール選定 {esc(per["valid"][0])}〜（{per["valid"][2]:,}R） / 確認 {esc(per["test"][0])}〜{esc(per["test"][1])}（{per["test"][2]:,}R）</div>'
            f'{kpis(bt)}{sparkline(bt["series"])}{monthly(bt)}'
            f'<div class="note">確認期間の成績は、モデルの学習にもルール選びにも使っていません。参考：期待値を見ずに、確率の高い買い目を毎レース同じ点数買った場合の回収率 {pct(mk.get("roi"))}。収支は実際の払戻金で計算しています。</div></section>')

    # 収集状況
    col = d["collection"]
    total, with_pv = sum(c["races"] for c in col), sum(c["preview"] for c in col)
    rows = "".join(
        f'<tr><td>{esc(c["name"])}</td><td>{esc(c["first"])}</td><td>{esc(c["last"])}</td><td>{c["days"]:,}</td><td>{c["races"]:,}</td><td>{c["preview"]:,}</td>'
        f'<td style="min-width:90px"><div class="bar"><i style="width:{min(100, c["days"] / 18.26):.0f}%"></i></div></td></tr>' for c in col)
    parts.append(f'<section class="card"><h2>データ収集状況</h2><div class="sub">結果 {total:,}レース・うち直前情報あり {with_pv:,}レース（データ元：Boatrace Open API、非公式）。バーは5年分（約1,826日）に対する開催日数の目安</div>'
                 f'<div class="tbl"><table><tr><th>場</th><th>最初</th><th>最新</th><th>開催日</th><th>レース</th><th>直前情報あり</th><th>5年分の進み具合</th></tr>{rows}</table></div></section>')

    runs = "".join(f'<tr><td>{esc(r["at"])}</td><td class="l">{esc(r["kind"])}</td><td>{r["days"]}</td><td>{r["races"]}</td><td>{r["errors"]}</td></tr>' for r in d["runs"])
    parts.append(f'<section class="card"><h2>自動実行の履歴</h2><div class="tbl"><table><tr><th>日時</th><th class="l">処理</th><th>日数</th><th>レース</th><th>失敗</th></tr>{runs}</table></div></section></main>')

    page = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>競艇 期待値派</title><style>{CSS}</style></head><body>{"".join(parts)}</body></html>')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return out / "index.html"
