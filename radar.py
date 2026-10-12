"""
radar.py - 매일 한 번 실행되는 스크리너.

  python radar.py                    평소 실행
  python radar.py --no-fundamentals  가격 팩터만 (빠름)
  python radar.py --refresh-universe S&P500 종목을 유니버스에 채워넣기
  python radar.py --demo             인터넷 없이 가짜 데이터로 동작 확인

출력:
  data/prices.csv.gz        최근 주가
  data/latest.csv           오늘 순위표
  data/history.csv          날짜별 점수 누적 (사이트의 점수 추세용)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import warnings

import numpy as np
import pandas as pd

import config

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

PRICES_PATH = os.path.join(DATA, "prices.csv.gz")
LATEST_PATH = os.path.join(DATA, "latest.csv")
HISTORY_PATH = os.path.join(DATA, "history.csv")
UNIVERSE_PATH = os.path.join(HERE, "universe.txt")


# ---------------------------------------------------------------------------
# 유니버스
# ---------------------------------------------------------------------------
def load_universe() -> list[str]:
    if os.path.exists(UNIVERSE_PATH):
        with open(UNIVERSE_PATH, encoding="utf-8") as f:
            tickers = [ln.strip() for ln in f
                       if ln.strip() and not ln.startswith("#")]
        if tickers:
            return sorted(set(tickers))
    return sorted(set(config.SEED_UNIVERSE))


def refresh_universe() -> None:
    """위키백과에서 S&P500 종목을 읽어 universe.txt에 병합합니다."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    tables = pd.read_html(url)
    symbols = [str(s).replace(".", "-") for s in tables[0]["Symbol"]]
    merged = sorted(set(symbols) | set(load_universe()))
    with open(UNIVERSE_PATH, "w", encoding="utf-8") as f:
        f.write("# radar.py --refresh-universe 로 자동 생성됩니다.\n")
        f.write("# 직접 종목을 추가하거나 지워도 됩니다.\n")
        f.write("\n".join(merged) + "\n")
    print(f"universe.txt 갱신 완료: {len(merged)}종목")


# ---------------------------------------------------------------------------
# 데이터 수집
# ---------------------------------------------------------------------------
def fetch_prices(tickers: list[str], period: str = "2y") -> pd.DataFrame:
    """종가 데이터프레임 (index=날짜, columns=티커)."""
    import yfinance as yf

    frames = []
    chunk = 60
    for i in range(0, len(tickers), chunk):
        batch = tickers[i:i + chunk]
        print(f"  주가 {i + 1}-{i + len(batch)} / {len(tickers)}", flush=True)
        raw = yf.download(batch, period=period, interval="1d",
                          auto_adjust=True, progress=False, threads=True)
        if raw is None or raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw["Close"] if "Close" in raw.columns.levels[0] else raw.xs(
                "Close", axis=1, level=-1)
        else:
            close = raw[["Close"]].rename(columns={"Close": batch[0]})
        frames.append(close)
        time.sleep(1)

    if not frames:
        raise RuntimeError("주가를 하나도 받지 못했습니다. 네트워크나 티커를 확인하세요.")

    prices = pd.concat(frames, axis=1).sort_index()
    prices = prices.loc[:, ~prices.columns.duplicated()]
    # 데이터가 거의 없는 종목은 버립니다
    keep = prices.notna().sum() > 250
    return prices.loc[:, keep]


def fetch_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """yfinance .info에서 재무 지표를 긁어옵니다. 실패한 종목은 NaN."""
    import yfinance as yf

    rows = []
    for n, t in enumerate(tickers, 1):
        if n % 25 == 0:
            print(f"  재무 {n} / {len(tickers)}", flush=True)
        info = {}
        try:
            info = yf.Ticker(t).get_info() or {}
        except Exception:
            pass

        pe = info.get("trailingPE")
        rows.append({
            "ticker": t,
            "name": info.get("shortName") or t,
            "sector": info.get("sector") or "",
            "currency": info.get("currency") or "",
            "market_cap": info.get("marketCap"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "earnings_yield": (1.0 / pe) if isinstance(pe, (int, float)) and pe and pe > 0 else np.nan,
        })
    return pd.DataFrame(rows).set_index("ticker")


# ---------------------------------------------------------------------------
# 팩터 계산
# ---------------------------------------------------------------------------
def price_factors(prices: pd.DataFrame) -> pd.DataFrame:
    """가격에서 나오는 팩터. 마지막 날 기준."""
    p = prices.ffill()
    out = pd.DataFrame(index=p.columns)

    def ret(days_ago_from: int, days_ago_to: int = 0):
        a = p.shift(days_ago_from).iloc[-1]
        b = p.shift(days_ago_to).iloc[-1]
        return b / a - 1.0

    if len(p) > 252:
        # 최근 1개월을 제외한 12개월 모멘텀 (단기 반전 효과를 피하기 위함)
        out["mom_12_1"] = p.shift(21).iloc[-1] / p.shift(252).iloc[-1] - 1.0
    else:
        out["mom_12_1"] = np.nan
    out["mom_3"] = ret(63) if len(p) > 63 else np.nan

    ma200 = p.rolling(200, min_periods=150).mean().iloc[-1]
    out["trend_200"] = p.iloc[-1] / ma200 - 1.0

    daily = p.pct_change()
    out["vol_126"] = daily.tail(126).std() * np.sqrt(252)

    out["last_price"] = p.iloc[-1]
    out["chg_1d"] = p.pct_change().iloc[-1]
    return out


def zscore(s: pd.Series, higher_is_better: bool, winsor: float) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    if s.notna().sum() < 5:
        return pd.Series(np.nan, index=s.index)
    lo, hi = s.quantile(winsor), s.quantile(1 - winsor)
    s = s.clip(lo, hi)
    sd = s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    z = (s - s.mean()) / sd
    return z if higher_is_better else -z


def build_scores(raw: pd.DataFrame, factors: dict) -> pd.DataFrame:
    """팩터 원값 -> z점수 -> 가중합 -> 순위."""
    zs = pd.DataFrame(index=raw.index)
    weights = {}
    for name, spec in factors.items():
        if name not in raw.columns:
            continue
        zs["z_" + name] = zscore(raw[name], spec["higher_is_better"], config.WINSOR)
        weights[name] = spec["weight"]

    if not weights:
        raise RuntimeError("계산된 팩터가 없습니다.")

    wsum = sum(weights.values())
    weights = {k: v / wsum for k, v in weights.items()}

    # 결측 팩터는 그 종목의 남은 팩터 비중을 키워 계산합니다
    num = pd.Series(0.0, index=raw.index)
    den = pd.Series(0.0, index=raw.index)
    for name, w in weights.items():
        col = zs["z_" + name]
        num = num.add((col * w).fillna(0.0), fill_value=0.0)
        den = den.add(col.notna().astype(float) * w, fill_value=0.0)

    coverage = den
    score = num / den.replace(0, np.nan)
    score[coverage < config.MIN_COVERAGE] = np.nan

    out = raw.join(zs)
    out["coverage"] = coverage
    out["score"] = score
    out = out.sort_values("score", ascending=False)
    out["rank"] = out["score"].rank(ascending=False, method="first")
    return out


# ---------------------------------------------------------------------------
# 데모용 가짜 데이터 (인터넷 없이 파이프라인 확인)
# ---------------------------------------------------------------------------
def demo_data(tickers: list[str]):
    rng = np.random.default_rng(7)
    days = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=520)
    drift = rng.normal(0.0004, 0.0006, len(tickers))
    vol = rng.uniform(0.010, 0.030, len(tickers))
    steps = rng.normal(drift, vol, size=(len(days), len(tickers)))
    prices = pd.DataFrame(100 * np.exp(np.cumsum(steps, axis=0)),
                          index=days, columns=tickers)
    fund = pd.DataFrame({
        "name": [t + " (데모)" for t in tickers],
        "sector": rng.choice(["Technology", "Industrials", "Healthcare",
                              "Financials", "Energy"], len(tickers)),
        "currency": "USD",
        "market_cap": rng.uniform(5e9, 3e12, len(tickers)),
        "roe": rng.normal(0.15, 0.10, len(tickers)),
        "revenue_growth": rng.normal(0.10, 0.15, len(tickers)),
        "profit_margin": rng.normal(0.14, 0.09, len(tickers)),
        "debt_to_equity": rng.uniform(5, 220, len(tickers)),
        "earnings_yield": rng.uniform(0.01, 0.09, len(tickers)),
    }, index=pd.Index(tickers, name="ticker"))
    return prices, fund


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fundamentals", action="store_true")
    ap.add_argument("--refresh-universe", action="store_true")
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()

    if args.refresh_universe:
        refresh_universe()
        return 0

    tickers = load_universe()
    print(f"유니버스 {len(tickers)}종목")

    if args.demo:
        prices, fund = demo_data(tickers + [config.BENCHMARK])
        fund = fund.drop(index=config.BENCHMARK, errors="ignore")
    else:
        prices = fetch_prices(tickers + [config.BENCHMARK])
        fund = (pd.DataFrame(index=pd.Index([], name="ticker"))
                if args.no_fundamentals
                else fetch_fundamentals([t for t in prices.columns
                                         if t != config.BENCHMARK]))

    prices.tail(600).to_csv(PRICES_PATH)

    universe_cols = [c for c in prices.columns if c != config.BENCHMARK]
    raw = price_factors(prices[universe_cols])
    if not fund.empty:
        raw = raw.join(fund)
    for col in ("name", "sector", "currency"):
        if col not in raw.columns:
            raw[col] = ""
    names = raw["name"].astype("string").fillna("")
    raw["name"] = [t if not str(v).strip() else v
                   for t, v in zip(raw.index, names)]

    table = build_scores(raw, config.FACTORS)
    ranked = table[table["score"].notna()]
    print(f"점수 계산 완료: {len(ranked)}종목")

    asof = str(prices.index[-1].date())
    ranked = ranked.copy()
    ranked.insert(0, "date", asof)
    ranked.index.name = "ticker"
    ranked.to_csv(LATEST_PATH)

    # 점수 이력 누적 (같은 날짜를 다시 돌리면 덮어씁니다)
    hist_cols = ["date", "score", "rank"]
    today = ranked[hist_cols].reset_index()
    if os.path.exists(HISTORY_PATH):
        old = pd.read_csv(HISTORY_PATH)
        old = old[old["date"] != asof]
        today = pd.concat([old, today], ignore_index=True)
    today.sort_values(["date", "rank"]).to_csv(HISTORY_PATH, index=False)

    print("\n상위 5")
    for t, r in ranked.head(5).iterrows():
        print(f"  {int(r['rank']):>3}  {t:<12} {r['score']:+.2f}  {str(r['name'])[:28]}")
    print("하위 5")
    for t, r in ranked.tail(5).iterrows():
        print(f"  {int(r['rank']):>3}  {t:<12} {r['score']:+.2f}  {str(r['name'])[:28]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
