# 백테스트 Task 실행 프롬프트 모음

> 새 세션에서 컨텍스트를 비운 뒤, 아래 프롬프트를 하나씩 복사해 지시한다.
> 구현 계획: `docs/superpowers/plans/2026-05-24-backtest.md`
> 설계 스펙: `docs/superpowers/specs/2026-05-24-backtest-design.md`
> 각 Task는 선행 Task가 커밋돼 있어야 한다(의존 관계는 각 프롬프트에 명시).

---

## Task 1 — 공용 지표 모듈 추출

```
greed 프로젝트에서 백테스트 기능을 구현 중이야. 구현 계획은
docs/superpowers/plans/2026-05-24-backtest.md 에 있어.
이 계획의 "Task 1: 공용 지표 모듈 추출"만 TDD 단계대로 실행해줘.

핵심: scripts/pick.py의 지표 함수들을 scripts/weekly_indicators.py로 본문 변경 없이
옮기고, pick.py는 그 모듈에서 import(재export)하게 만든다.
회귀 게이트는 backend/tests/test_pick_indicators.py 가 수정 없이 통과하는 것.
테스트는 .venv/Scripts/python.exe -m pytest 로 실행.
계획에 적힌 Step 순서대로 진행하고 마지막에 커밋까지 해줘. 다른 Task는 건드리지 마.
```

---

## Task 2 — 누수 없는 as-of 피처 재구성

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 2: as-of 피처 재구성"만 TDD 단계대로 실행해줘. (Task 1이 이미 커밋돼 있어야 함)

핵심: scripts/rule_scorer/features.py에 extract_features_asof를 추가하고
extract_features를 그 위로 재구성한다. 다이버전스(_add_divergence_signals의 wing=2)가
유일한 미래 누수원이므로 _apply_confirmation_shift로 +wing 확정 시프트를 적용한다.
테스트 backend/tests/test_features_asof.py 의 골든 테스트와 truncation 누수 테스트가
모두 통과해야 하고, 기존 backend/tests/test_rule_scorer.py 도 통과해야 한다(시프트로
깨지면 계획 Step 4 지침대로 합성 데이터를 보정).
.venv/Scripts/python.exe -m pytest 로 실행하고 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 3 — DB 모델 + 마이그레이션 + 스키마

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 3: DB 모델 + 마이그레이션 + 스키마"만 실행해줘.

핵심: backend/models.py에 BacktestRun/BacktestSignal/BacktestStat 추가,
backend/database.py의 _migrate_mariadb()에 세 테이블 CREATE TABLE IF NOT EXISTS 추가,
backend/schemas.py에 백테스트 Pydantic 스키마 추가. (DB는 MariaDB임)
검증: .venv/Scripts/python.exe -c "import backend.models, backend.schemas; print('ok')"
계획 Step대로 진행하고 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 4 — 유니버스 로더 + 주봉 데이터 적재

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 4: 유니버스 로더 + 주봉 데이터 적재"만 TDD 단계대로 실행해줘.
(Task 1이 커밋돼 있어야 함 — weekly_indicators.resample_weekly 사용)

핵심: scripts/backtest/ 패키지 생성, universe.py(kospi200.csv 로더),
data.py(기존 backend/price_bars의 price_bars interval "1w" 캐시 재사용 + FDR 폴백).
universe만 단위 테스트(backend/tests/test_backtest_universe.py)로 검증하고
data.py는 Task 5 엔진 테스트에서 간접 검증된다.
.venv/Scripts/python.exe -m pytest 로 실행, 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 5 — 이벤트 스터디 엔진 + 집계

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 5: 이벤트 스터디 엔진 + 집계"만 TDD 단계대로 실행해줘.
(Task 1·2·4가 커밋돼 있어야 함)

핵심: scripts/backtest/engine.py — build_combined(지표+미래구름+식별컬럼, 다이버전스
확정 시프트 1회 적용), run_ticker(매수 신호마다 진입가=open[i+1], 청산=close[i+N],
i+N이 끝을 넘으면 우측 절단), score_bucket(4-5/6-7/8+), aggregate(승률+분포).
HORIZONS=(4,8,12,26). 테스트 backend/tests/test_backtest_engine.py 통과 필수.
.venv/Scripts/python.exe -m pytest 로 실행, 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 6 — 영속화 + CLI

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 6: 영속화 + CLI 엔트리포인트"만 실행해줘. (Task 3·5가 커밋돼 있어야 함)

핵심: scripts/backtest/persistence.py(persist_run)와 scripts/backtest/run.py(CLI).
구문 점검은 ast.parse(계획 Step 3)로 하고 커밋한다.
Step 4의 실제 스모크(python -m scripts.backtest.run --limit 3)는 DATABASE_URL(MariaDB)과
scripts/backtest/kospi200.csv(내가 따로 제공)가 있어야 하니, 없으면 생략하고 알려줘.
계획 Step대로 진행하고 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 7 — 백엔드 읽기 전용 API

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 7: 백엔드 읽기 전용 API"만 TDD 단계대로 실행해줘. (Task 3이 커밋돼 있어야 함)

핵심: backend/routers/backtest.py(runs/run detail/signals/histogram 4개 엔드포인트),
backend/routers/__init__.py와 backend/main.py에 backtest_router 등록.
테스트 backend/tests/test_backtest_router.py 는 계획에 적힌 SQLite 인메모리 client/
db_session 픽스처를 파일 안에 직접 정의하므로 MariaDB 연결 불필요.
.venv/Scripts/python.exe -m pytest 로 실행, 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 8 — 프론트엔드 /backtest 페이지

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 8: 프론트엔드 /backtest 페이지"만 실행해줘. (Task 7이 커밋돼 있어야 함)

핵심: frontend/src/api/backtest.ts, frontend/src/pages/BacktestPage.tsx 생성,
frontend/src/App.tsx에 /backtest 라우트와 내비 추가. StatsPage의 톤을 따른다.
검증: cd frontend && npm run build 가 타입에러 없이 성공해야 한다.
계획 Step대로 진행하고 마지막에 커밋. 다른 Task는 건드리지 마.
```

---

## Task 9 — 통합 점검 + 문서

```
greed 백테스트 구현 계획(docs/superpowers/plans/2026-05-24-backtest.md)의
"Task 9: 통합 점검 + 문서"만 실행해줘. (Task 1~8이 커밋돼 있어야 함)

핵심: 신규 테스트 5개 파일(test_weekly_indicators, test_features_asof,
test_backtest_universe, test_backtest_engine, test_backtest_router)을
.venv/Scripts/python.exe -m pytest 로 한꺼번에 돌려 전부 PASS 확인.
그 다음 docs/기능정의.md에 "14. 룰 신호 백테스트" 절을 계획대로 추가하고 커밋.
```
