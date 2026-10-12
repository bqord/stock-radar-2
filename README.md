# 종목 레이더

전 세계 주식을 매일 같은 규칙으로 채점해서 순위와 추세를 정적 웹사이트로 뿌려주는 프로젝트.
서버 없이 GitHub Actions가 매일 돌려주고, GitHub Pages가 사이트를 서빙합니다. 전부 무료.

```
radar.py        데이터 수집 -> 팩터 계산 -> 점수/순위 -> data/ 저장
build_site.py   data/ 를 읽어 docs/index.html 생성 (차트는 인라인 SVG)
backtest.py     이 점수가 과거에 통했는지 검증
config.py       유니버스, 팩터, 비중. 튜닝은 여기서만
```

## 처음 세팅 (10분)

**1. 내 컴퓨터에서 먼저 확인**

```bash
pip install -r requirements.txt
python radar.py --demo      # 인터넷 없이 파이프라인만 확인
python build_site.py
```

`docs/index.html`을 브라우저로 열어 보세요. 데모 데이터라 종목명이 가짜입니다.
잘 나오면 진짜 데이터로:

```bash
python radar.py             # 처음엔 3~10분 걸립니다
python backtest.py --download
python build_site.py
```

**2. GitHub에 올리기**

```bash
git init && git add . && git commit -m "init"
gh repo create stock-radar --public --source=. --push
```

**3. Pages 켜기**

리포지토리 → Settings → Pages → Source를 `Deploy from a branch`,
Branch를 `main` / `/docs` 로 설정. 1분 뒤
`https://<내아이디>.github.io/stock-radar/` 에서 사이트가 열립니다.

**4. 자동 실행 확인**

Actions 탭 → `daily radar` → `Run workflow` 로 한 번 손으로 돌려 보세요.
성공하면 그 다음부터는 평일 아침 7시(KST)에 알아서 돌아갑니다.

## 튜닝

`config.py`만 고치면 됩니다.

- `SEED_UNIVERSE` : 보고 싶은 종목. 티커 형식은 `AAPL`, `005930.KS`, `7203.T`, `2330.TW`, `ASML.AS`
- `FACTORS` : 각 팩터의 `weight`를 바꾸면 순위가 바뀝니다
- `TOP_N` / `BOTTOM_N` : 사이트에 보여줄 개수

S&P500 전체를 유니버스에 넣으려면:

```bash
python radar.py --refresh-universe   # universe.txt 생성
```

500종목이면 재무 수집이 20분 넘게 걸립니다. 빠르게 돌리려면 `--no-fundamentals`.

**비중을 바꿨으면 반드시 백테스트를 다시 돌리세요.** 이게 이 프로젝트에서 제일 중요한 습관입니다.
비중을 감으로 만지면 과거에 우연히 잘 맞는 조합이 나오고, 그건 미래에 안 통합니다.

## 점수 계산 방식

1. 팩터별 원값을 구합니다 (12개월 모멘텀, ROE, 매출성장률, 부채비율 등)
2. 그날 유니버스 안에서 상하위 5%를 자르고 z점수로 변환
3. `higher_is_better`가 False인 팩터는 부호를 뒤집습니다
4. 비중대로 가중 평균 → 종합 점수
5. 팩터가 60% 미만만 계산된 종목은 순위에서 제외

점수는 **절대 평가가 아니라 그날 다른 종목들과의 상대 비교**입니다.
점수 2.0은 "좋은 회사"가 아니라 "이 지표들에서 오늘 상위권"이라는 뜻입니다.

## 알고 있어야 하는 한계

- **미래 주가 예측선은 넣지 않았습니다.** 이 정도 데이터로 그린 예측 그래프는 근거가 없고,
  화면에 있으면 오히려 판단을 망칩니다. 대신 점수 추세와 백테스트를 넣었습니다.
- **백테스트는 가격 팩터만 검증합니다.** yfinance는 재무 지표의 "현재 값"만 주고
  3년 전 ROE는 주지 않습니다. 그래서 재무 팩터는 과거 검증이 불가능합니다.
  제대로 하려면 유료 데이터(예: Financial Modeling Prep, Sharadar)가 필요합니다.
- **생존 편향.** 지금 상장돼 있는 종목만 대상이라 과거에 망한 회사가 빠져 있습니다.
  백테스트 성과가 실제보다 좋게 나옵니다.
- **yfinance는 비공식 경로**입니다. 야후가 구조를 바꾸면 갑자기 깨집니다.
  깨지면 `pip install -U yfinance` 먼저 해 보세요.
- **GitHub Actions는 리포가 60일간 아무 활동이 없으면 크론을 자동으로 멈춥니다.**
  메일이 오면 Actions 탭에서 다시 켜면 됩니다.
- 투자 판단이나 권유가 아닙니다. 후보를 좁히는 도구입니다.

## 다음에 붙일 만한 것

- 텔레그램 봇으로 매일 아침 상위 10종목 전송 (`requests` + Bot API, 30줄)
- 뉴스 헤드라인 감성 점수를 팩터로 추가
- 섹터별 중립화 (지금은 특정 섹터가 순위를 독식할 수 있습니다)
- 점수가 급등한 종목만 따로 보여주는 "변화" 섹션

---

리포에 포함된 `docs/index.html`은 데모 데이터로 만든 미리보기입니다.
`python radar.py`를 한 번 돌리면 진짜 데이터로 덮어써집니다.
