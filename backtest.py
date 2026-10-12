"""
backtest.py - "이 점수가 실제로 쓸모가 있었나"를 확인하는 스크립트.

중요한 한계:
  yfinance는 재무 지표의 "지금 값"만 줍니다. 3년 전의 ROE가 얼마였는지는
  주지 않습니다. 그래서 이 백테스트는 가격 팩터(모멘텀, 추세, 변동성)만으로
  돌아갑니다. 사이트의 종합 점수와 완전히 같은 계산이 아닙니다.
  즉 "가격 팩터 부분이 과거에 통했는지"까지만 검증됩니다.

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
    bench = prices[benchmark].ffill() if benchmark in prices.columns else None
    p = prices[[c for c in prices.columns if c != benchmark]].ffill()

    month_ends = p.resample(config.REBALANCE).last().index
    positions = [p.index.get_indexer([d], method="ffill")[0] for d in month_ends]
    positions = sorted(set(i for i in positions if i > 260))

    rows, equity, bench_equity = [], 1.0, 1.0
    for a, b in zip(positions[:-1], positions[1:]):
        score = price_score_at(p, a)
        if score.empty:
            continue
        picks = score.nlargest(config.BACKTEST_TOP_N).index
        held = p.iloc[b][picks] / p.iloc[a][picks] - 1.0
        r = float(held.dropna().mean())
        equity *= (1 + r)

        if bench is not None:
            br = float(bench.iloc[b] / bench.iloc[a] - 1.0)
            bench_equity *= (1 + br)
        else:
            br = np.nan

        rows.append({
            "date": p.index[b].date(),
            "strategy_return": r,
            "benchmark_return": br,
            "strategy_equity": equity,
            "benchmark_equity": bench_equity,
            "picks": " ".join(picks[:10]),
        })

    return pd.DataFrame(rows)


def summarize(df: pd.DataFrame) -> None:
    if df.empty:
        print("기간이 짧아 백테스트를 할 수 없습니다. --download 로 더 긴 데이터를 받으세요.")
        return
    months = len(df)
    years = months / 12
    for label, eq, ret in (("전략", "strategy_equity", "strategy_return"),
                           ("벤치마크", "benchmark_equity", "benchmark_return")):
        series = df[eq]
        if series.isna().all():
            continue
        cagr = series.iloc[-1] ** (1 / years) - 1
        peak = series.cummax()
        mdd = (series / peak - 1).min()
        vol = df[ret].std() * np.sqrt(12)
        print(f"  {label:<6} 누적 {series.iloc[-1]:.2f}배  "
              f"CAGR {cagr * 100:+.1f}%  최대낙폭 {mdd * 100:.1f}%  "
              f"변동성 {vol * 100:.1f}%")
    if df["benchmark_return"].notna().any():
        cmp = df.dropna(subset=["benchmark_return"])
        win = (cmp["strategy_return"] > cmp["benchmark_return"]).mean()
        print(f"  월간 승률 {win * 100:.0f}%  ({months}개월, 약 {years:.1f}년)")
    else:
        print(f"  벤치마크 데이터가 없어 승률은 계산하지 못했습니다. "
              f"({months}개월)")
    print("\n  주의: 거래비용, 세금, 상장폐지 종목 제외로 인한 생존 편향이"
          "\n        반영되지 않았습니다. 실제 성과는 이보다 낮습니다.")


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
