# Daily 20d +40% Rally Backend Persistence And API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 문서 1의 `daily_20d_40pct_rally` 엔진을 기존 백테스트 strategy job 흐름에 연결하고, rule insight와 현재 후보를 DB/API로 조회 가능하게 만든다.

**Architecture:** 기존 `backtest_runs`, `backtest_signals`, `backtest_stats`는 실행 메타데이터와 forward return 통계 저장에 재사용한다. 신규 분석 전용 결과는 `daily_rally_rule_stats`, `daily_rally_current_candidates` 두 테이블에 저장한다. API는 기존 `/api/backtest` 라우터에 추가해 프론트가 같은 query/polling 흐름을 사용할 수 있게 한다.

**Tech Stack:** FastAPI, SQLAlchemy, MariaDB migration in `backend/database.py`, Pydantic v2, pytest.

---

## 목표

- `BacktestStrategyJobCreate`에 `daily_20d_40pct_rally`를 허용한다.
- `run_backtest_strategy_pipeline`에 신규 전략 분기를 추가한다.
- 문서 1 엔진 결과를 저장하고 조회하는 persistence 함수를 만든다.
- 새 API:
  - `GET /api/backtest/runs/{run_id}/daily-rally-insights`
  - `GET /api/backtest/runs/{run_id}/daily-rally-candidates`
- 기존 run 목록/상세 API는 그대로 동작해야 한다.

## 변경 파일

- Modify: `backend/models.py`
- Modify: `backend/database.py`
- Modify: `backend/schemas.py`
- Modify: `backend/routers/backtest.py`
- Modify: `scripts/backtest/persistence.py`
- Test: `backend/tests/test_daily_rally_persistence.py`
- Test: `backend/tests/test_backtest_router.py`

## DB 모델

`backend/models.py`에 추가한다.

```python
class DailyRallyRuleStat(Base):
    __tablename__ = "daily_rally_rule_stats"
    __table_args__ = (
        Index("ix_daily_rally_rule_stats_run_score", "run_id", "score"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_key: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_label: Mapped[str] = mapped_column(String(500), nullable=False)
    support: Mapped[int] = mapped_column(Integer, nullable=False)
    positives: Mapped[int] = mapped_column(Integer, nullable=False)
    total_matches: Mapped[int] = mapped_column(Integer, nullable=False)
    precision: Mapped[float] = mapped_column(Float, nullable=False)
    base_rate: Mapped[float] = mapped_column(Float, nullable=False)
    lift: Mapped[float] = mapped_column(Float, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)


class DailyRallyCurrentCandidate(Base):
    __tablename__ = "daily_rally_current_candidates"
    __table_args__ = (
        Index("ix_daily_rally_current_candidates_run_score", "run_id", "max_rule_score"),
        Index("ix_daily_rally_current_candidates_run_ticker", "run_id", "ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
    matched_rules_json: Mapped[str] = mapped_column(Text, nullable=False)
    matched_rule_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_rule_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    features_json: Mapped[str] = mapped_column(Text, nullable=False)
```

## Migration

`backend/database.py:_migrate_mariadb()`에 `CREATE TABLE IF NOT EXISTS`를 추가한다.

```sql
CREATE TABLE IF NOT EXISTS daily_rally_rule_stats (
    id INTEGER NOT NULL AUTO_INCREMENT,
    run_id INTEGER NOT NULL,
    rule_key VARCHAR(255) NOT NULL,
    rule_label VARCHAR(500) NOT NULL,
    support INTEGER NOT NULL,
    positives INTEGER NOT NULL,
    total_matches INTEGER NOT NULL,
    precision FLOAT NOT NULL,
    base_rate FLOAT NOT NULL,
    lift FLOAT NOT NULL,
    score FLOAT NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_daily_rally_rule_stats_run_score (run_id, score)
)
```

```sql
CREATE TABLE IF NOT EXISTS daily_rally_current_candidates (
    id INTEGER NOT NULL AUTO_INCREMENT,
    run_id INTEGER NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    signal_date DATE NOT NULL,
    close_price FLOAT NOT NULL,
    matched_rules_json TEXT NOT NULL,
    matched_rule_count INTEGER NOT NULL,
    max_rule_score FLOAT NULL,
    mean_rule_score FLOAT NULL,
    features_json TEXT NOT NULL,
    PRIMARY KEY (id),
    INDEX ix_daily_rally_current_candidates_run_score (run_id, max_rule_score),
    INDEX ix_daily_rally_current_candidates_run_ticker (run_id, ticker)
)
```

## API 스키마

`backend/schemas.py`에 추가한다.

```python
class DailyRallyRuleStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    rule_key: str
    rule_label: str
    support: int
    positives: int
    total_matches: int
    precision: float
    base_rate: float
    lift: float
    score: float


class DailyRallyInsightsRead(BaseModel):
    run_id: int
    rule_count: int
    rules: list[DailyRallyRuleStatRead]


class DailyRallyCandidateRead(BaseModel):
    id: int
    run_id: int
    ticker: str
    name: str
    signal_date: date
    close_price: float
    matched_rules: list[str]
    matched_rule_count: int
    max_rule_score: float | None
    mean_rule_score: float | None
    features: dict[str, bool | int | float | str | None]


class DailyRallyCandidatesRead(BaseModel):
    run_id: int
    candidate_count: int
    candidates: list[DailyRallyCandidateRead]
```

그리고 `BacktestStrategyJobCreate`를 다음처럼 확장한다.

```python
class BacktestStrategyJobCreate(BaseModel):
    strategy_kind: Literal["ichimoku_span2_breakout", "daily_20d_40pct_rally"]
```

## 구현 단계

### Task 1: 모델과 migration

- [ ] `backend/models.py`에 `DailyRallyRuleStat`, `DailyRallyCurrentCandidate`를 추가한다.
- [ ] `backend/database.py`의 table 목록에 `daily_rally_rule_stats`, `daily_rally_current_candidates`를 포함한다.
- [ ] `_migrate_mariadb()`에 두 `CREATE TABLE IF NOT EXISTS` 블록을 추가한다.
- [ ] SQLite 테스트 DB는 `Base.metadata.create_all()`로 생성되므로 별도 SQLite DDL은 추가하지 않는다.
- [ ] 테스트 `backend/tests/test_daily_rally_persistence.py::test_daily_rally_tables_are_created`를 추가한다. `DailyRallyRuleStat.__table__.name`과 `DailyRallyCurrentCandidate.__table__.name`이 metadata에 있는지 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_persistence.py -v`

### Task 2: persistence 함수

- [ ] `scripts/backtest/persistence.py`에 `persist_daily_rally_run(db, result)`를 추가한다.
- [ ] 내부에서 기존 `persist_run`을 호출해 `BacktestRun`, `BacktestSignal`, `BacktestStat`을 저장한다.
- [ ] `BacktestSignal` 변환 규칙:
  - `signal_date = sample.signal_date`
  - `entry_date = sample.signal_date`
  - `entry_price = sample.close_price`
  - `score = int(sample.label)`
  - `score_bucket = "positive"` if label 1 else `"control"`
  - `ret_4w = sample.forward_returns[20]`
  - `ret_8w = sample.forward_returns[40]`
  - `ret_12w = sample.forward_returns[60]`
  - `ret_26w = sample.forward_returns[120]`
- [ ] `BacktestStat`은 horizon `20`, `40`, `60`, `120`과 bucket `positive`, `control`, `ALL`로 집계한다. 기존 컬럼명은 주 단위처럼 보이지만 이 run은 `backtest_runs.horizons = "20d,40d,60d,120d"`로 해석을 구분한다.
- [ ] `BacktestRun` 메타데이터:
  - `buy_threshold = 0`
  - `warmup_weeks = 0`
  - `strategy_kind = "daily_20d_40pct_rally"`
  - `horizons = "20d,40d,60d,120d"`
  - `universe = "KOSPI200-DB"`
  - `notes = "daily 20 trading day +40% rally rule mining"`
- [ ] `DailyRallyRuleStat`과 `DailyRallyCurrentCandidate`를 같은 transaction 안에 저장한다.
- [ ] JSON 저장은 `json.dumps(..., ensure_ascii=False, sort_keys=True)`를 사용한다.
- [ ] 테스트 `test_persist_daily_rally_run_writes_run_rules_and_candidates`를 추가한다. synthetic `DailyRallyBacktestResult`로 run 1개, rule 1개, candidate 1개가 저장되는지 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_persistence.py -v`

### Task 3: strategy job 분기

- [ ] `backend/routers/backtest.py`에 `_DAILY_RALLY_STRATEGY_KIND = "daily_20d_40pct_rally"`를 추가한다.
- [ ] import에 `run_daily_rally_backtest`와 `persist_daily_rally_run`을 추가한다.
- [ ] `run_backtest_strategy_pipeline`의 기존 span2 분기를 유지하고, 신규 분기를 추가한다.

```python
if job.strategy_kind == _SPAN2_STRATEGY_KIND:
    result = run_span2_breakout_backtest(db)
    run_id = persist_run(...)
elif job.strategy_kind == _DAILY_RALLY_STRATEGY_KIND:
    result = run_daily_rally_backtest(db)
    run_id = persist_daily_rally_run(db, result)
else:
    raise ValueError(f"Unsupported strategy_kind: {job.strategy_kind}")
```

- [ ] 완료/실패 상태 처리 로직은 기존 함수를 그대로 재사용한다.
- [ ] `backend/tests/test_backtest_router.py`에 `test_create_strategy_job_accepts_daily_rally_kind`를 추가한다.
- [ ] `test_run_backtest_strategy_pipeline_daily_rally_marks_done_with_run_id`를 추가한다. `monkeypatch`로 엔진과 persistence를 대체해 job 상태와 `backtest_run_id`를 검증한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_router.py -v`

### Task 4: 조회 API

- [ ] `backend/schemas.py`에 Daily Rally read schema를 추가한다.
- [ ] `backend/routers/backtest.py` import에 신규 모델과 schema를 추가한다.
- [ ] `_daily_rally_run_or_404(db, run_id)` helper를 추가한다. run이 없으면 404, `strategy_kind != "daily_20d_40pct_rally"`이면 404로 응답한다.
- [ ] `GET /api/backtest/runs/{run_id}/daily-rally-insights`를 추가한다.
  - 정렬: `score desc`, `precision desc`, `support desc`
  - 기본 limit: 100
  - 응답: `DailyRallyInsightsRead`
- [ ] `GET /api/backtest/runs/{run_id}/daily-rally-candidates`를 추가한다.
  - 정렬: `max_rule_score desc`, `matched_rule_count desc`, `ticker asc`
  - 기본 limit: 200
  - `matched_rules_json`, `features_json`은 `json.loads`로 변환한다.
  - 응답: `DailyRallyCandidatesRead`
- [ ] 테스트 `test_get_daily_rally_insights_returns_rules_for_run`을 추가한다.
- [ ] 테스트 `test_get_daily_rally_candidates_decodes_json`을 추가한다.
- [ ] 테스트 `test_get_daily_rally_insights_rejects_non_daily_rally_run`을 추가한다.
- [ ] 실행: `.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_router.py backend/tests/test_daily_rally_persistence.py -v`

## 테스트

필수 실행:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_daily_rally_persistence.py backend/tests/test_backtest_router.py -v
```

백테스트 회귀:

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_backtest_engine.py backend/tests/test_analysis_similarity_backtest.py backend/tests/test_analysis_backtest_jobs_router.py -v
```

완료 기준:

- 신규 strategy kind가 job 생성 schema를 통과한다.
- strategy pipeline이 daily rally 엔진과 persistence를 호출한다.
- `backtest_runs`, `backtest_signals`, `backtest_stats`에 기존 run 조회와 호환되는 데이터가 저장된다.
- 두 신규 테이블에 rule/candidate 결과가 저장된다.
- 두 신규 API가 daily rally run만 대상으로 JSON을 decoding해 응답한다.
