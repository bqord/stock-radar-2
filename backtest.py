"""
backtest.py - "이 점수가 실제로 쓸모가 있었나"를 확인하는 스크립트.

비교 대상은 세 가지입니다.
  1. 점수 상위 N종목 (거래비용 반영)
  2. 유니버스 전체 동일비중  <- 점수의 실력을 보는 핵심 기준
  3. 벤치마크 (SPY)

1번이 2번을 이겨야 "점수가 종목을 잘 골랐다"고 말할 수 있습니다.
유니버스가 지금 잘나가는 종목들로 짜여 있어서 생기는 부풀림은
1번과 2번에 똑같이 들어가므로, 둘의 차이에서는 대부분 상쇄됩니다.

거래비용:
  매달 새로 바꾼 종목 비중만큼 왕복 비용(config.BACKTEST_COST, 기본 0.3%)을
  수익률에서 뺍니다. 유니버스 동일비중에는 비용을 빼지 않습니다.

중요한 한계:
  yfinance는 재무 지표의 "지금 값"만 줍니다. 그래서 이 백테스트는
  가격 팩터(모멘텀, 추세, 변동성)만으로 돌아갑니다.

  python backtest.py            (data/prices.csv.gz 사용)
  python backtest.py --download (긴 기간을 새로 받아서 검증)
"""
from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd

import config
import radar

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "backtest.csv")

DEFAULT_COST = 0.003


def price_score_at(p: pd.DataFrame, i: int) -> pd.Series:
    """i번째 행 시점의 가격 팩터 종합 z점수."""
    window = p.iloc[: i + 1]
    if len(window) < 260:
        return pd.Series(dtype=float)

    f = pd.DataFrame(index=window.columns)
    f["mom_12_1"] = window.iloc[-21] / window.iloc[-252] - 1.0
    f["mom_3"] = window.iloc[-1] / window.iloc[-63] - 1.0
    ma200 = window.rolling(200, min_periods=150).mean().iloc[-1]
    f["trend_200"] = window.iloc[-1] / ma200 - 1.0
    f["vol_126"] = window.pct_change().tail(126).std() * np.sqrt(252)

    specs = {k: v for k, v in config.FACTORS.items() if v["kind"] == "price"}
    wsum = sum(s["weight"] for s in specs.values())
    total = pd.Series(0.0, index=window.columns)
    den = pd.Series(0.0, index=window.columns)
    for name, spec in specs.items():
        z = radar.zscore(f[name], spec["higher_is_better"], config.WINSOR)
        w = spec["weight"] / wsum
        total = total.add((z * w).fillna(0.0), fill_value=0.0)
        den = den.add(z.notna().astype(float) * w, fill_value=0.0)
    return (total / den.replace(0, np.nan)).dropna()


def run(prices: pd.DataFrame, benchmark: str) -> pd.DataFrame:
    cost = getattr(config, "BACKTEST_COST", DEFAULT_COST)
    top_n = config.BACKTEST_TOP_N

    bench = prices[benchmark].ffill() if benchmark in prices.columns else None
    p = prices[[c for c in prices.columns if c != benchmark]].ffill()

    month_ends = p.resample(config.REBALANCE).last().index
    positions = [p.index.get_indexer([d], method="ffill")[0] for d in month_ends]
    positions = sorted(set(i for i in positions if i > 260))

    rows = []
    eq_net = eq_gross = eq_uni = eq_bench = 1.0
    prev_picks: set[str] = set()

    for a, b in zip(positions[:-1], positions[1:]):
        score = price_score_at(p, a)
        if score.empty:
            continue
        picks = list(score.nlargest(top_n).index)

        held = p.iloc[b][picks] / p.iloc[a][picks] - 1.0
        gross = float(held.dropna().mean())

        # 새로 바꾼 종목 비중 (첫 달은 전부 새로 산 것)
        turnover = (len(set(picks) - prev_picks) / len(picks)) if prev_picks else 1.0
        net = gross - turnover * cost
        prev_picks = set(picks)

        # 유니버스 전체 동일비중: 시작과 끝 가격이 둘 다 있는 종목만
        start, end = p.iloc[a], p.iloc[b]
        ok = start.notna() & end.notna()
        uni = float((end[ok] / start[ok] - 1.0).mean()) if ok.any() else np.nan

        if bench is not None:
            br = float(bench.iloc[b] / bench.iloc[a] - 1.0)
        else:
            br = np.nan

        eq_net *= (1 + net)
        eq_gross *= (1 + gross)
        if not np.isnan(uni):
            eq_uni *= (1 + uni)
        if not np.isnan(br):
            eq_bench *= (1 + br)

        rows.append({
            "date": p.index[b].date(),
            "strategy_return": net,
            "strategy_gross_return": gross,
            "universe_return": uni,
            "benchmark_return": br,
            "turnover": turnover,
            "strategy_equity": eq_net,
            "strategy_gross_equity": eq_gross,
            "universe_equity": eq_uni,
            "benchmark_equity": eq_bench if bench is not None else np.nan,
            "picks": " ".join(picks[:10]),
        })

    return pd.DataFrame(rows)


def _line(label, eq, rets, years):
    cagr = eq.iloc[-1] ** (1 / years) - 1
    mdd = (eq / eq.cummax() - 1).min()
    vol = rets.std() * np.sqrt(12)
    print(f"  {label:<12} 누적 {eq.iloc[-1]:.2f}배  CAGR {cagr * 100:+.1f}%  "
          f"최대낙폭 {mdd * 100:.1f}%  변동성 {vol * 100:.1f}%")
    return cagr


def summarize(df: pd.DataFrame) -> None:
    if df.empty:
        print("기간이 짧아 백테스트를 할 수 없습니다. --download 로 더 긴 데이터를 받으세요.")
        return
    months = len(df)
    years = months / 12
    cost = getattr(config, "BACKTEST_COST", DEFAULT_COST)
    print(f"  기간 {years:.1f}년 ({months}개월), 거래비용 왕복 {cost * 100:.2f}%, "
          f"평균 월 회전율 {df['turnover'].mean() * 100:.0f}%\n")

    c_net = _line("점수 상위(순)", df["strategy_equity"], df["strategy_return"], years)
    _line("점수 상위(총)", df["strategy_gross_equity"], df["strategy_gross_return"], years)
    c_uni = None
    if df["universe_equity"].notna().any():
        c_uni = _line("유니버스 평균", df["universe_equity"], df["universe_return"], years)
    if df["benchmark_equity"].notna().any():
        _line("벤치마크", df["benchmark_equity"], df["benchmark_return"], years)

    if c_uni is not None:
        diff = (c_net - c_uni) * 100
        win = (df["strategy_return"] > df["universe_return"]).mean()
        print(f"\n  점수 효과(점수 상위 - 유니버스 평균): 연 {diff:+.1f}%p, "
              f"월간 승률 {win * 100:.0f}%")
        if diff <= 0:
            print("  유니버스 평균을 못 이겼습니다. 이 기간에는 점수가 한 일이 없습니다.")

    print("\n  주의: 생존 편향은 세 선 모두에 들어 있습니다. 점수 효과(차이)는"
          "\n        절대 수익률보다 믿을 만하지만, 한 기간의 결과일 뿐입니다.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    args = ap.parse_args()

    if args.download:
        tickers = radar.load_universe() + [config.BENCHMARK]
        prices = radar.fetch_prices(tickers, period=f"{config.BACKTEST_YEARS}y")
    else:
        prices = pd.read_csv(radar.PRICES_PATH, index_col=0, parse_dates=True)

    df = run(prices, config.BENCHMARK)
    df.to_csv(OUT, index=False)
    print(f"\n{OUT} 저장")
    summarize(df)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
