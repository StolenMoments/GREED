# Daily Rally 화면 해석 가이드

## 목적

Daily Rally 분석은 `D`일 이후 20거래일 안에 종가 기준 `+40%` 이상 급등한 과거 사례를 찾고, 급등 전 `D`일까지 이미 확인할 수 있었던 조건을 채굴한다.

이 화면에서 봐야 하는 질문은 하나다.

> 과거 급등 직전에 반복된 조건 조합이 무엇이고, 지금 그 조건에 가까운 종목은 무엇인가?

## 메뉴

프론트 상단 메뉴의 `Daily Rally`에서 확인한다. 기존 `Backtest` 화면은 전체 백테스트 실행과 원자료 확인용이고, Daily Rally 메뉴는 급등 패턴 해석용이다.

## 화면에서 보는 순서

1. `pattern briefing`

   가장 먼저 봐야 하는 영역이다. 상위 3개 룰을 사람이 읽을 수 있는 문장으로 보여준다.

   예:

   - 최근 20거래일 수익률 +20% 이상 + 거래량 20일 평균 대비 3배 이상
   - 주봉 종가가 구름대 위 + 20일선이 60일선 위

2. `candidate briefing`

   현재 후보 종목이 왜 후보로 잡혔는지 보여준다. 단순히 룰 키를 나열하지 않고, 매칭된 조건을 한국어 설명으로 변환한다.

3. `forward return`

   positive events, controls, all samples를 비교한다.

   - `Positive Events`: 실제로 20거래일 안에 +40% 급등한 과거 샘플
   - `Controls`: 급등하지 않은 비교 샘플
   - `All Samples`: 전체 샘플

4. 상세 테이블

   원자료 검증용이다. 패턴을 빠르게 이해하려면 먼저 briefing을 보고, 세부 수치 확인이 필요할 때만 상세 테이블을 본다.

## 주요 지표

- `Support`: 해당 룰에 걸린 positive event 수
- `Precision`: 해당 룰에 걸린 전체 샘플 중 positive event 비율
- `Base Rate`: 전체 샘플의 positive event 비율
- `Lift`: precision이 base rate보다 몇 배 높은지
- `Score`: support, precision, lift를 합친 정렬 점수

## 해석 기준

- `Lift >= 3`: 강한 반복 패턴
- `Lift >= 2`: 의미 있는 반복 패턴
- `Lift >= 1.2`: 약한 반복 패턴
- 그 미만: 전체 평균과 큰 차이가 작다

높은 lift만 보면 안 된다. support가 너무 작으면 우연일 수 있다. 우선순위는 보통 `support가 충분하면서 lift가 높은 룰`이다.

## 현재 한계

최근 생성된 구현 계획 문서 3개는 한글 인코딩이 깨져 있어 그대로 읽기 어렵다.

- `docs/daily-rally-01-core-analysis-engine.md`
- `docs/daily-rally-02-backend-api-persistence.md`
- `docs/daily-rally-03-frontend-e2e.md`

현재 사람이 읽는 기준 문서는 이 파일을 우선 사용한다.
