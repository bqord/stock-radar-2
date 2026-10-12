"""
설정 파일. 대부분의 튜닝은 여기서만 하면 됩니다.
"""

# ---------------------------------------------------------------------------
# 1. 유니버스 (분석 대상 종목)
#    yfinance 티커 형식입니다.
#      미국: AAPL   한국: 005930.KS   일본: 7203.T
#      대만: 2330.TW  독일: SAP.DE   네덜란드: ASML.AS
#    universe.txt 파일이 있으면 그 파일이 아래 목록을 대체합니다.
#    S&P500 전체를 자동으로 채우려면:  python radar.py --refresh-universe
# ---------------------------------------------------------------------------
SEED_UNIVERSE = [
    # 미국 대형 기술
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "AMD", "TSM",
    "ORCL", "CRM", "ADBE", "NOW", "PLTR", "SNOW", "ANET", "MU", "QCOM",
    # 미국 산업·항공우주·방산
    "BA", "LMT", "RTX", "GE", "HON", "CAT", "DE", "ETN", "PH", "RKLB",
    # 미국 헬스케어·소비·금융·에너지
    "LLY", "UNH", "JNJ", "ABBV", "NVO", "COST", "WMT", "PG", "KO",
    "JPM", "BRK-B", "V", "MA", "XOM", "CVX", "NEE",
    # 한국
    "005930.KS", "000660.KS", "373220.KS", "005380.KS", "207940.KS",
    "012450.KS", "042700.KS", "086520.KQ",
    # 일본
    "7203.T", "6758.T", "8035.T", "6501.T", "6902.T", "7011.T",
    # 대만·유럽
    "2330.TW", "2454.TW", "ASML.AS", "SAP.DE", "SIE.DE", "AIR.PA",
    "MC.PA", "NESN.SW", "SHEL.L", "AZN.L",
]

# 백테스트·비교용 벤치마크
BENCHMARK = "SPY"

# ---------------------------------------------------------------------------
# 2. 팩터 정의
#    weight  : 종합 점수에서의 비중 (합이 1이 아니어도 됩니다. 자동 정규화)
#    higher_is_better : True면 값이 클수록 가점, False면 작을수록 가점
#
#    가격 팩터는 매일 계산 가능하고 백테스트도 됩니다.
#    재무 팩터는 yfinance가 "현재 값"만 주기 때문에 백테스트에는 못 씁니다.
#    (이 한계는 README에 자세히 적어 뒀습니다)
# ---------------------------------------------------------------------------
FACTORS = {
    # --- 가격 팩터 ---
    "mom_12_1":  {"weight": 0.20, "higher_is_better": True,  "label": "12개월 모멘텀",
                  "kind": "price"},
    "mom_3":     {"weight": 0.10, "higher_is_better": True,  "label": "3개월 모멘텀",
                  "kind": "price"},
    "trend_200": {"weight": 0.10, "higher_is_better": True,  "label": "200일선 대비",
                  "kind": "price"},
    "vol_126":   {"weight": 0.10, "higher_is_better": False, "label": "변동성",
                  "kind": "price"},
    # --- 재무 팩터 ---
    "roe":            {"weight": 0.15, "higher_is_better": True,  "label": "ROE",
                       "kind": "fundamental"},
    "revenue_growth": {"weight": 0.15, "higher_is_better": True,  "label": "매출성장률",
                       "kind": "fundamental"},
    "profit_margin":  {"weight": 0.10, "higher_is_better": True,  "label": "영업이익률",
                       "kind": "fundamental"},
    "debt_to_equity": {"weight": 0.05, "higher_is_better": False, "label": "부채비율",
                       "kind": "fundamental"},
    "earnings_yield": {"weight": 0.05, "higher_is_better": True,  "label": "이익수익률",
                       "kind": "fundamental"},
}

# ---------------------------------------------------------------------------
# 3. 계산 옵션
# ---------------------------------------------------------------------------
TOP_N = 10           # 사이트에 보여줄 상위 종목 수
BOTTOM_N = 10        # 하위 종목 수
MIN_COVERAGE = 0.6   # 팩터 중 최소 몇 %가 계산되어야 순위에 넣을지
WINSOR = 0.05        # 이상치를 상하위 5%에서 자릅니다
HISTORY_DAYS = 30    # 사이트의 "점수 추세"에 쓸 일수
PRICE_CHART_DAYS = 120

# ---------------------------------------------------------------------------
# 4. 백테스트 옵션
# ---------------------------------------------------------------------------
BACKTEST_YEARS = 8
BACKTEST_TOP_N = 10
REBALANCE = "ME"     # 월말 리밸런싱
