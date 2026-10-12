"""
build_site.py - data/ 의 CSV들을 읽어 docs/index.html 을 만듭니다.

차트는 전부 인라인 SVG로 직접 그립니다. 차트 라이브러리를 안 쓰기 때문에
설치할 것도 없고 깨질 것도 없습니다. GitHub Pages에 그대로 올라갑니다.
"""
from __future__ import annotations

import html
import os
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

import config

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DOCS = os.path.join(HERE, "docs")
os.makedirs(DOCS, exist_ok=True)

KST = timezone(timedelta(hours=9))

INK = "#0E1F1D"
PANEL = "#152C29"
RULE = "#2A4A46"
TEXT = "#D6E0DA"
DIM = "#7E948E"
BRASS = "#E0B341"
UP = "#6FA76A"
DOWN = "#C0644A"


# ---------------------------------------------------------------------------
# SVG 그리기
# ---------------------------------------------------------------------------
def _pts(vals, w, h, pad=1.5):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if len(vals) < 2:
        return None, None
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = pad + i * (w - 2 * pad) / (n - 1)
        y = h - pad - (v - lo) * (h - 2 * pad) / span
        pts.append((x, y))
    return pts, vals


def sparkline(vals, w=96, h=26, color=BRASS, fill=True):
    pts, vals = _pts(vals, w, h)
    if not pts:
        return f'<svg width="{w}" height="{h}" role="img" aria-hidden="true"></svg>'
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = ""
    if fill:
        area = (f'<polygon points="{pts[0][0]:.1f},{h} {line} {pts[-1][0]:.1f},{h}" '
                f'fill="{color}" opacity="0.12"/>')
    return (f'<svg class="spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'preserveAspectRatio="none" role="img" aria-hidden="true">{area}'
            f'<polyline points="{line}" fill="none" stroke="{color}" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2" fill="{color}"/></svg>')


def dual_chart(series: dict, w=680, h=240):
    """여러 시계열을 하나의 좌표계에 겹쳐 그립니다. {이름: (values, color)}"""
    allvals = [v for vals, _ in series.values()
               for v in vals if v is not None and not np.isnan(v)]
    if len(allvals) < 2:
        return "<p class='empty'>표시할 데이터가 아직 없습니다.</p>"
    lo, hi = min(allvals), max(allvals)
    span = (hi - lo) or 1.0
    pad = 8

    grid, labels = [], []
    for frac in (0, 0.5, 1.0):
        y = h - pad - frac * (h - 2 * pad)
        val = lo + frac * span
        grid.append(f'<line x1="0" y1="{y:.1f}" x2="{w}" y2="{y:.1f}" '
                    f'stroke="{RULE}" stroke-width="1"/>')
        labels.append(f'<text x="4" y="{y - 4:.1f}" fill="{DIM}" '
                      f'font-size="10">{val:.2f}</text>')

    paths, legend = [], []
    for name, (vals, color) in series.items():
        clean = [v for v in vals if v is not None and not np.isnan(v)]
        n = len(clean)
        if n < 2:
            continue
        pts = []
        for i, v in enumerate(clean):
            x = i * w / (n - 1)
            y = h - pad - (v - lo) * (h - 2 * pad) / span
            pts.append(f"{x:.1f},{y:.1f}")
        paths.append(f'<polyline points="{" ".join(pts)}" fill="none" '
                     f'stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        legend.append(f'<span class="key"><i style="background:{color}"></i>'
                      f'{html.escape(name)}</span>')

    return (f'<div class="chartwrap"><svg viewBox="0 0 {w} {h}" width="100%" '
            f'height="{h}" preserveAspectRatio="none" role="img">'
            f'{"".join(grid)}{"".join(paths)}{"".join(labels)}</svg>'
            f'<div class="legend">{"".join(legend)}</div></div>')


# ---------------------------------------------------------------------------
# 데이터 읽기
# ---------------------------------------------------------------------------
def read_all():
    latest = pd.read_csv(os.path.join(DATA, "latest.csv"), index_col="ticker")
    prices = pd.read_csv(os.path.join(DATA, "prices.csv.gz"),
                         index_col=0, parse_dates=True)
    hist_path = os.path.join(DATA, "history.csv")
    hist = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
    bt_path = os.path.join(DATA, "backtest.csv")
    bt = pd.read_csv(bt_path) if os.path.exists(bt_path) else pd.DataFrame()
    return latest, prices, hist, bt


def score_trend(hist: pd.DataFrame, ticker: str) -> list[float]:
    if hist.empty or "ticker" not in hist.columns:
        return []
    s = hist[hist["ticker"] == ticker].sort_values("date")["score"]
    return s.tail(config.HISTORY_DAYS).tolist()


def price_trend(prices: pd.DataFrame, ticker: str) -> list[float]:
    if ticker not in prices.columns:
        return []
    return prices[ticker].ffill().tail(config.PRICE_CHART_DAYS).dropna().tolist()


# ---------------------------------------------------------------------------
# HTML 조립
# ---------------------------------------------------------------------------
def fmt_pct(v, digits=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "&mdash;"
    return f"{v * 100:+.{digits}f}%"


def factor_chips(row) -> str:
    chips = []
    for name, spec in config.FACTORS.items():
        col = "z_" + name
        if col not in row.index:
            continue
        z = row[col]
        if pd.isna(z):
            continue
        cls = "pos" if z >= 0 else "neg"
        chips.append(f'<span class="chip {cls}">{html.escape(spec["label"])}'
                     f'<b>{z:+.1f}</b></span>')
    return "".join(chips)


def hero(row, ticker, prices, hist) -> str:
    trend = score_trend(hist, ticker)
    spark = sparkline(trend, w=150, h=40) if len(trend) > 1 else ""
    note = (f'<span class="sub">최근 {len(trend)}일 점수</span>' if len(trend) > 1
            else '<span class="sub">점수 추세는 며칠 쌓이면 나타납니다</span>')
    return f"""
    <section class="hero">
      <div class="rank">01</div>
      <div class="heroname">
        <h2>{html.escape(str(row.get("name", ticker)))}</h2>
        <p class="tick">{html.escape(ticker)}
           {("&middot; " + html.escape(str(row["sector"]))) if str(row.get("sector", "")) else ""}</p>
      </div>
      <div class="heroscore">
        <span class="big">{row["score"]:+.2f}</span>
        <span class="sub">종합 점수</span>
      </div>
      <div class="herospark">{spark}{note}</div>
      <div class="chips">{factor_chips(row)}</div>
      <div class="heroprice">
        {sparkline(price_trend(prices, ticker), w=680, h=64,
                   color=UP if row.get("chg_1d", 0) >= 0 else DOWN)}
        <span class="sub">최근 {config.PRICE_CHART_DAYS}거래일 주가 &middot;
          당일 {fmt_pct(row.get("chg_1d"), 2)}</span>
      </div>
    </section>"""


def table(df, prices, hist, title, subtitle, accent) -> str:
    rows = []
    for i, (ticker, row) in enumerate(df.iterrows(), 1):
        st = score_trend(hist, ticker)
        rows.append(f"""
        <li>
          <span class="n">{int(row["rank"]):02d}</span>
          <span class="who">
            <b>{html.escape(str(row.get("name", ticker))[:34])}</b>
            <em>{html.escape(ticker)}</em>
          </span>
          <span class="sc" style="color:{accent}">{row["score"]:+.2f}</span>
          <span class="sp">{sparkline(price_trend(prices, ticker), 78, 24,
                                      color=DIM, fill=False)}</span>
          <span class="sp">{sparkline(st, 60, 24, color=accent, fill=False)}</span>
          <span class="d">{fmt_pct(row.get("mom_12_1"), 0)}</span>
        </li>""")
    return f"""
    <section class="block">
      <h3>{title}</h3>
      <p class="blocksub">{subtitle}</p>
      <ol class="ranktable">
        <li class="head">
          <span class="n">#</span><span class="who">종목</span>
          <span class="sc">점수</span><span class="sp">주가 120일</span>
          <span class="sp">점수추세</span><span class="d">12개월</span>
        </li>
        {"".join(rows)}
      </ol>
    </section>"""


def backtest_section(bt: pd.DataFrame) -> str:
    if bt.empty:
        return """
    <section class="block">
      <h3>검증</h3>
      <p class="blocksub">아직 백테스트를 돌리지 않았습니다.
         <code>python backtest.py --download</code> 을 한 번 실행하면 이 자리에 결과가 들어갑니다.</p>
    </section>"""

    series = {"이 점수 상위 10종목": (bt["strategy_equity"].tolist(), BRASS)}
    if bt["benchmark_equity"].notna().any():
        series[f"{config.BENCHMARK} (벤치마크)"] = (bt["benchmark_equity"].tolist(), DIM)

    years = max(len(bt) / 12, 0.1)
    final = bt["strategy_equity"].iloc[-1]
    cagr = final ** (1 / years) - 1
    mdd = (bt["strategy_equity"] / bt["strategy_equity"].cummax() - 1).min()

    bench_line = ""
    if bt["benchmark_equity"].notna().any():
        bfinal = bt["benchmark_equity"].iloc[-1]
        bcagr = bfinal ** (1 / years) - 1
        bench_line = (f'<div><span class="lab">벤치마크 CAGR</span>'
                      f'<span class="val">{bcagr * 100:+.1f}%</span></div>')

    return f"""
    <section class="block">
      <h3>검증</h3>
      <p class="blocksub">이 점수의 가격 팩터 부분만 과거에 적용해 월말마다 상위 10종목을
        같은 비중으로 담았다면 어땠는지 계산한 결과입니다.
        재무 팩터는 과거 값을 구할 수 없어 제외했습니다.</p>
      {dual_chart(series)}
      <div class="stats">
        <div><span class="lab">기간</span><span class="val">{years:.1f}년</span></div>
        <div><span class="lab">누적</span><span class="val">{final:.2f}배</span></div>
        <div><span class="lab">CAGR</span><span class="val">{cagr * 100:+.1f}%</span></div>
        {bench_line}
        <div><span class="lab">최대낙폭</span><span class="val">{mdd * 100:.1f}%</span></div>
      </div>
      <p class="warn">거래비용, 세금, 그리고 지금 상장돼 있는 종목만 대상으로 했다는
        생존 편향이 반영되지 않았습니다. 실제로는 이 수치보다 낮게 나옵니다.</p>
    </section>"""


CSS = f"""
:root {{
  --ink:{INK}; --panel:{PANEL}; --rule:{RULE};
  --text:{TEXT}; --dim:{DIM}; --brass:{BRASS}; --up:{UP}; --down:{DOWN};
}}
* {{ box-sizing:border-box; }}
html {{ -webkit-text-size-adjust:100%; }}
body {{
  margin:0; background:var(--ink); color:var(--text);
  font-family:Pretendard,-apple-system,BlinkMacSystemFont,"Segoe UI",
    "Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-variant-numeric:tabular-nums;
  line-height:1.55; font-size:15px;
}}
.wrap {{ max-width:760px; margin:0 auto; padding:28px 18px 72px; }}
a {{ color:var(--brass); }}
h1 {{ font-size:23px; font-weight:650; letter-spacing:-.02em; margin:0; }}
h2 {{ font-size:26px; font-weight:650; letter-spacing:-.02em; margin:0; }}
h3 {{ font-size:16px; font-weight:650; margin:0 0 2px; }}
.masthead {{ display:flex; justify-content:space-between; align-items:flex-end;
  gap:14px; padding-bottom:14px; border-bottom:1px solid var(--rule); }}
.masthead .meta {{ text-align:right; color:var(--dim); font-size:12.5px;
  line-height:1.45; white-space:nowrap; }}
.sub {{ color:var(--dim); font-size:12px; display:block; }}

.hero {{ margin:22px 0 30px; padding:18px; background:var(--panel);
  border-radius:3px; display:grid; gap:12px;
  grid-template-columns:auto 1fr auto; align-items:start; }}
.hero .rank {{ font-size:34px; font-weight:700; color:var(--brass);
  line-height:1; letter-spacing:-.04em; }}
.hero .heroname p.tick {{ margin:2px 0 0; color:var(--dim); font-size:12.5px; }}
.hero .heroscore {{ text-align:right; }}
.hero .big {{ font-size:30px; font-weight:700; color:var(--brass);
  letter-spacing:-.03em; line-height:1; }}
.hero .herospark, .hero .chips, .hero .heroprice {{ grid-column:1/-1; }}
.hero .herospark {{ display:flex; align-items:center; gap:10px; }}
.hero .heroprice svg {{ display:block; width:100%; }}

.chips {{ display:flex; flex-wrap:wrap; gap:5px; }}
.chip {{ font-size:11.5px; padding:2px 7px; border:1px solid var(--rule);
  border-radius:2px; color:var(--dim); }}
.chip b {{ margin-left:5px; font-weight:600; }}
.chip.pos b {{ color:var(--up); }}
.chip.neg b {{ color:var(--down); }}

.block {{ margin:34px 0; }}
.blocksub {{ color:var(--dim); font-size:12.5px; margin:0 0 12px; max-width:68ch; }}
.ranktable {{ list-style:none; margin:0; padding:0; }}
.ranktable li {{ display:grid; align-items:center; gap:9px;
  grid-template-columns:26px minmax(0,1fr) 52px 78px 60px 52px;
  padding:9px 0; border-bottom:1px solid var(--rule); }}
.ranktable li.head {{ color:var(--dim); font-size:11.5px; padding-bottom:6px;
  border-bottom:1px solid var(--rule); }}
.ranktable .n {{ color:var(--dim); font-size:12.5px; }}
.ranktable .who {{ min-width:0; }}
.ranktable .who b {{ display:block; font-weight:550; font-size:13.5px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.ranktable .who em {{ font-style:normal; color:var(--dim); font-size:11.5px;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
.ranktable .sc {{ text-align:right; font-weight:650; font-size:14px; }}
.ranktable .d {{ text-align:right; color:var(--dim); font-size:12px; }}
.ranktable .sp svg {{ display:block; }}

.chartwrap svg {{ display:block; background:var(--panel); border-radius:3px; }}
.legend {{ display:flex; gap:16px; margin-top:8px; font-size:12px; color:var(--dim); }}
.key i {{ display:inline-block; width:10px; height:2px; vertical-align:middle;
  margin-right:6px; }}
.stats {{ display:flex; flex-wrap:wrap; gap:20px; margin:16px 0 10px; }}
.stats .lab {{ display:block; color:var(--dim); font-size:11.5px; }}
.stats .val {{ font-size:17px; font-weight:650; }}
.warn {{ color:var(--dim); font-size:12px; max-width:68ch; }}
.empty {{ color:var(--dim); font-size:12.5px; }}

footer {{ margin-top:46px; padding-top:16px; border-top:1px solid var(--rule);
  color:var(--dim); font-size:12px; }}
footer h4 {{ color:var(--text); font-size:13px; margin:0 0 6px; }}
footer ul {{ margin:0 0 14px; padding-left:18px; }}
footer li {{ margin-bottom:4px; max-width:66ch; }}
code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em;
  background:var(--panel); padding:1px 5px; border-radius:2px; }}

@media (max-width:560px) {{
  .ranktable li {{ grid-template-columns:24px minmax(0,1fr) 48px 56px; }}
  .ranktable li > :nth-child(5), .ranktable li > :nth-child(6) {{ display:none; }}
  .hero {{ grid-template-columns:auto 1fr; }}
  .hero .heroscore {{ grid-column:1/-1; text-align:left; }}
  .masthead {{ flex-direction:column; align-items:flex-start; }}
  .masthead .meta {{ text-align:left; }}
}}
@media (prefers-reduced-motion:no-preference) {{
  .hero {{ animation:rise .5s ease-out both; }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(6px); }} }}
}}
"""


def build() -> str:
    latest, prices, hist, bt = read_all()
    latest = latest.sort_values("score", ascending=False)
    asof = str(latest["date"].iloc[0]) if "date" in latest.columns else "-"
    built = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    top = latest.head(config.TOP_N)
    bottom = latest.tail(config.BOTTOM_N).sort_values("score")
    first_ticker = top.index[0]
    days_of_history = hist["date"].nunique() if not hist.empty else 1

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>종목 레이더 &middot; {html.escape(asof)}</title>
<meta name="description" content="전 세계 주식을 매일 팩터 점수로 줄 세운 기록">
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<link rel="stylesheet"
  href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard-dynamic-subset.min.css">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">

  <header class="masthead">
    <div>
      <h1>종목 레이더</h1>
      <span class="sub">전 세계 주식을 매일 같은 규칙으로 줄 세운 기록</span>
    </div>
    <div class="meta">
      기준일 {html.escape(asof)}<br>
      {len(latest)}종목 &middot; 관측 {days_of_history}일차<br>
      생성 {built}
    </div>
  </header>

  {hero(top.iloc[0], first_ticker, prices, hist)}

  {table(top, prices, hist, "상위 " + str(len(top)),
         "종합 점수가 가장 높은 종목입니다. 점수는 같은 날 다른 종목들과 비교한 상대값입니다.",
         BRASS)}

  {table(bottom, prices, hist, "하위 " + str(len(bottom)),
         "점수가 가장 낮은 종목입니다. 나쁜 회사라는 뜻이 아니라, 이 규칙이 보는 지표에서 뒤처져 있다는 뜻입니다.",
         DOWN)}

  {backtest_section(bt)}

  <footer>
    <h4>이 점수가 무엇인지</h4>
    <ul>
      <li>매일 각 종목의 팩터 값을 구하고, 그날 유니버스 안에서 z점수로 바꿔
        가중 평균한 값입니다. 절대적인 가치 평가가 아니라 같은 날 다른 종목과의 비교입니다.</li>
      <li>쓰는 팩터: {html.escape(", ".join(s["label"] for s in config.FACTORS.values()))}.
        비중은 <code>config.py</code>에서 바꿉니다.</li>
      <li>이상치는 상하위 {int(config.WINSOR * 100)}%에서 자르고, 팩터가
        {int(config.MIN_COVERAGE * 100)}% 미만만 계산된 종목은 순위에서 제외합니다.</li>
    </ul>
    <h4>이 점수가 못 하는 것</h4>
    <ul>
      <li>미래 주가를 예측하지 않습니다. 예상 주가 그래프를 일부러 넣지 않았습니다.
        이 정도 데이터로 그린 예측선은 근거 없는 선이고, 있으면 오히려 판단을 망칩니다.</li>
      <li>실적 발표, 소송, 규제, 경영진 같은 숫자로 안 잡히는 것들을 전혀 보지 않습니다.</li>
      <li>데이터는 Yahoo Finance 비공식 경로에서 옵니다. 값이 틀리거나 비어 있을 수 있습니다.</li>
      <li>투자 판단이나 권유가 아닙니다. 후보를 좁히는 도구입니다.</li>
    </ul>
  </footer>

</div>
</body>
</html>
"""


if __name__ == "__main__":
    out = os.path.join(DOCS, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(build())
    print(f"{out} 생성 ({os.path.getsize(out) / 1024:.0f} KB)")
