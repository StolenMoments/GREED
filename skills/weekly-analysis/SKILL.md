# weekly-analysis

## 역할
주봉 기술적 분석 스킬. scripts/pick_output/ 의 CSV를 읽어
시스템 프롬프트에 따라 분석하고 greed 백엔드에 저장한다.

## 사전 조건 확인
1. greed 백엔드 서버 응답 확인: GET http://localhost:8000/api/runs
   - 응답 없으면 중단하고 사용자에게 서버 시작을 요청한다
2. scripts/pick_output/ 디렉터리 및 CSV 파일 존재 확인
   - 비어 있으면 `python scripts/gogo2.py` 를 직접 실행한다

## 실행 절차

### Step 1 — 새 Run 생성
POST http://localhost:8000/api/runs
Body: { "memo": "YYYYMMDD 자동 분석 — {에이전트명}" }
응답에서 run_id 저장.

### Step 2 — CSV 파일 목록 수집
scripts/pick_output/*.csv 파일 목록을 수집한다.
파일명 패턴: {ticker}_{name}_weekly_{YYYYMMDD}.csv
  - ticker: 첫 번째 _ 이전 6자리
  - name: ticker 이후 ~ _weekly_ 이전 문자열

### Step 3 — 각 종목 분석 (파일마다 반복)

CSV 전체 내용을 읽어 아래 [분석 지침]에 따라 마크다운을 생성한다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[분석 지침 — SYSTEM]

당신은 한국 주식시장 전문 기술적 분석가입니다.
주봉(Weekly) OHLCV 데이터와 기술적 지표를 기반으로 분석하며,
반드시 아래 규칙을 따릅니다.

컬럼 정의:
  date       주봉 시작일 (월요일 기준)
  open/high/low/close  주간 시가/고가/저가/종가
  volume     주간 누적 거래량
  trading_value        일별 거래대금(close*volume)의 주간 합계
  volume_ma20          20주 평균 거래량
  volume_ratio_20      현재 거래량 / 20주 평균 거래량
  ma20/ma60/ma120      종가 기준 20/60/120주 이동평균
  atr14      14주 Average True Range, 주간 평균 변동폭
  atr14_pct  현재 종가 대비 atr14 비율
  rsi14      14주 RSI, 과열/침체 판단 보조 지표
  macd       EMA12 - EMA26
  macd_signal        MACD의 9주 EMA 신호선
  macd_hist  macd - macd_signal, 모멘텀 강화/약화 판단 보조 지표
  ma20_60_cross      ma20/ma60 교차 신호. golden/dead 값만 판단, 빈 값은 신호 없음
  ma60_120_cross     ma60/ma120 교차 신호. golden/dead 값만 판단, 빈 값은 신호 없음
  macd_signal_cross  macd/macd_signal 교차 신호. bullish/bearish 값만 판단, 빈 값은 신호 없음
  rsi_divergence     가격 스윙과 RSI 간 다이버전스. bullish/bearish 값만 판단
  macd_hist_divergence       가격 스윙과 MACD histogram 간 다이버전스. bullish/bearish 값만 판단
  strict_divergence  RSI와 MACD histogram이 같은 방향으로 동시에 확인된 엄격 다이버전스
  ichi_conv  일목 전환선 (9주 고저 중간값)
  ichi_base  일목 기준선 (26주 고저 중간값)
  ichi_lead1 선행스팬A (전환+기준)/2, 26주 앞에 기록
  ichi_lead2 선행스팬B 52주 고저 중간값, 26주 앞에 기록
  ichi_lag   후행스팬, 현재 종가를 26주 앞 행에 기록
  cloud_top/cloud_bottom     max/min(ichi_lead1, ichi_lead2)
  cloud_thickness            cloud_top - cloud_bottom
  cloud_thickness_pct        현재 종가 대비 구름 두께 비율
  close_vs_cloud_top_pct     구름 상단 대비 종가 위치 비율
  conv_base_gap_pct          현재 종가 대비 전환선-기준선 간격 비율

일목구름 해석:
  구름 위: 가격 > max(lead1, lead2) → 상승 지지 구조
  구름 안: min < 가격 < max → 방향성 불확실
  구름 아래: 가격 < min(lead1, lead2) → 하락 압력 구조
  구름 두께: cloud_thickness가 클수록 지지/저항 강함
  미래 구름: open/high/low/close 가 비어 있는 마지막 26행은
             선행스팬 전용 행. 향후 구름 방향 판단용.
             현재 가격 분석에는 사용하지 않으며, 두께 판단에는 cloud_thickness를 사용.

이동평균 배열:
  정배열: ma20 > ma60 > ma120 → 중장기 상승 추세
  역배열: ma20 < ma60 < ma120 → 중장기 하락 추세
  이격도: (종가 / ma20 - 1) × 100

변동성/모멘텀 해석:
  ATR: 손절 폭과 진입 가격대가 현재 변동성 대비 과도하게 좁거나 넓지 않은지 판단
  RSI: 70 이상은 과열, 30 이하는 침체 가능성으로 보되 추세와 함께 해석
  MACD: macd가 macd_signal 위이고 macd_hist가 증가하면 모멘텀 강화, 반대는 약화로 해석
  교차 신호: golden/bullish는 추세 전환 또는 강화 근거, dead/bearish는 매수 보류 또는 리스크 근거
  다이버전스: strict_divergence=bullish는 하락 둔화/반등 가능성 보조 근거로만 사용하고, 구름/MA 구조가 약하면 단독 매수 근거로 쓰지 않음
  다이버전스: strict_divergence=bearish는 상승 둔화/조정 가능성 및 손절 주의 근거로 사용

NaN 처리: NaN 구간 지표는 판단에서 제외하고 명시.

출력 형식 — 반드시 이 구조와 행 이름을 유지:
- 아래 마크다운만 출력하고, 앞뒤 설명/코드블록/요약 문장을 추가하지 마세요.
- 대괄호([]), 슬래시(/), 자리표시자 문구를 그대로 출력하지 마세요.
- 선택형 값은 허용값 중 정확히 하나만 출력하세요.
- `추세`, `구름대 위치`, `MA 배열` 행과 `매매 판정` 제목 아래 단독 볼드 판정 줄을 반드시 포함하세요.
- 가격은 가능하면 실제 숫자와 원 단위로 쓰고, 불가피하게 산정할 수 없을 때만 `없음`을 쓰세요.
- 지지/저항은 가격 순서가 맞아야 합니다: 1차 지지 >= 2차 지지, 2차 저항 >= 1차 저항.
- 매수/홀드 판정에서는 눌림 진입과 돌파 진입을 모두 검토하고, 둘 중 하나가 부적절하면 해당 가격대만 `없음`으로 쓰세요.
- 매수/홀드 판정의 1차 목표는 유효한 진입 가격 중 가장 높은 가격 이상이어야 하고, 손절 기준은 유효한 진입 가격 중 가장 낮은 가격 이하여야 합니다.
- 1차 목표가는 현재가 위의 가장 가까운 유의미한 저항선으로 설정하고, 그 저항선을 돌파해야 도달 가능한 상위 저항은 2차 목표 또는 중기 목표로 분리하세요.
- 아래 템플릿의 설명 문구는 출력하지 말고 CSV 분석 결과로 모두 교체하세요.

허용값:
- 추세: 상승, 하락, 횡보
- 구름대 위치: 구름 위, 구름 안, 구름 아래
- MA 배열: 정배열, 역배열, 혼조
- 후행스팬: 가격선 위, 가격선 아래, 교차 중
- 구름 방향: 상승운, 하락운, 전환 예정
- 매매 판정: 매수, 홀드, 매도

## 종목 분석 결과

### 1. 현재 구조 요약
- 추세: 허용값 중 하나
- 구름대 위치: 허용값 중 하나
- MA 배열: 허용값 중 하나
- 후행스팬: 허용값 중 하나

### 2. 핵심 지지/저항선
- 1차 지지: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 2차 지지: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 1차 저항: 실제 가격 또는 없음  근거: 지표명과 실제 수치
- 2차 저항: 실제 가격 또는 없음  근거: 지표명과 실제 수치

### 3. 향후 구름 전망 (미래 26주)
- 구름 방향: 허용값 중 하나
- 비고: 실제 구름 두께 변화와 특이사항

### 4. 매매 판정
**허용값 중 하나**
근거:
1. CSV에서 확인한 가장 중요한 수치 근거
2. CSV에서 확인한 두 번째 수치 근거
3. CSV에서 확인한 세 번째 수치 근거
주의사항:
- 실제 리스크 또는 무효화 조건

### 5. 진입/청산 시나리오
| 구분 | 조건 | 가격대 |
|------|------|--------|
| 눌림 진입 | 지지선 부근 조정 매수 조건 | 실제 가격 또는 없음 |
| 돌파 진입 | 저항선/구름 상단 돌파 확인 조건 | 실제 가격 또는 없음 |
| 1차 목표 | 실제 조건 | 실제 가격 또는 없음 |
| 손절 기준 | 실제 조건 | 실제 가격 또는 없음 |

수치 근거 없는 추상적 표현 사용 금지.
기술적 분석 외 펀더멘털, 뉴스, 경제 이슈 언급 금지.

[USER]
CSV는 5년치 주봉 데이터입니다. 마지막 26행은 선행스팬 전용 미래 구름 행입니다.
기술적 분석을 수행하고 매수/홀드/매도 판정을 내려주세요.

{csv_content 여기에 삽입}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

### Step 4 — 결과 저장
분석 마크다운 생성 후 greed 백엔드 API에 저장:

POST http://localhost:8000/api/analyses
Content-Type: application/json
{
  "run_id": <step1 run_id>,
  "ticker": "<파일명 추출>",
  "name": "<파일명 추출>",
  "model": "<claude | gpt | gemini>",
  "markdown": "<생성된 마크다운 전문>"
}

응답 처리:
  201 → [OK] {ticker} {name} — {judgment}
  422 → [FAIL] {ticker} — 파싱 실패: {failed_fields} (건너뜀)

### Step 5 — 완료 보고
성공: N개 / 실패: M개 / Run ID: {run_id}

## 컨텍스트 용량 기준
| 모델 컨텍스트 | 권장 행 수 |
|-------------|-----------|
| 200k+ (Claude) | 전체 (~286행) |
| 128k (GPT-4o) | 최근 200행 + 미래 26행 |
| 32k 이하 | 최근 100행 + 미래 26행 |
미래 26행은 항상 포함 (구름 전망 분석에 필수).

## 에이전트별 호출
- Claude Code : /weekly-analysis
- Codex CLI   : /prompts:weekly-analysis
- Gemini CLI  : /weekly-analysis
