# Analysis Similarity Backtest Task 실행 프롬프트 모음

> 새 세션에서 컨텍스트를 비운 뒤 아래 프롬프트를 하나씩 복사해 지시한다.
> 구현 계획: `docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md`
> 설계 스펙: `docs/superpowers/specs/2026-05-24-analysis-similarity-backtest-design.md`
> 각 Task는 선행 Task가 커밋되어 있어야 한다. 의존 관계는 각 프롬프트에 명시한다.

---

## Task 1 - Data Model, Migration, and Schemas

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 1: Data Model, Migration, and Schemas"만 TDD 단계대로 실행해줘.

핵심: backend/models.py에 AnalysisBacktestJob 모델을 추가하고 BacktestRun에
source_analysis_id, strategy_kind, similarity_threshold nullable 컬럼을 추가해.
backend/database.py의 MariaDB migration에 analysis_backtest_jobs CREATE TABLE과
backtest_runs ALTER TABLE을 추가하고, backend/schemas.py에 AnalysisBacktestJobCreate/
AnalysisBacktestJobRead 및 BacktestRunSummary 확장 필드를 추가해.

테스트는 backend/tests/test_analysis_backtest_jobs_router.py를 먼저 만들고 실패를 확인한 뒤
모델/스키마/마이그레이션을 구현해. 이 Task에서는 CRUD/router endpoint가 아직 없어서
최종 테스트가 endpoint 미구현으로 실패하는 상태여도 괜찮지만, 모델/스키마 import 오류는 없어야 해.
.venv/Scripts/python.exe -m pytest 로 실행하고 마지막에 커밋까지 해줘.
다른 Task는 건드리지 마.
```

---

## Task 2 - Similarity Profile and Engine

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 2: Similarity Profile and Engine"만 TDD 단계대로 실행해줘.
(Task 1은 이미 커밋되어 있어야 해.)

핵심: scripts/backtest/analysis_similarity.py를 새로 만들고 SimilarityProfile,
bucket_macd_hist, bucket_rsi, bucket_volume, profile_from_features, similarity_score,
analysis_score_bucket, analysis_asof_index, run_similarity_ticker를 구현해.
유사도 가중치는 cloud_position 3, ma_alignment 3, trend 2, macd_hist_direction 2,
rsi_bucket 1, volume_bucket 1, strict_divergence 1, future_cloud_direction 1이야.
unknown끼리는 점수를 주지 마.

또 scripts/backtest/persistence.py의 persist_run이 source_analysis_id,
strategy_kind, similarity_threshold optional metadata를 받을 수 있게 확장해.
기존 scripts.backtest.run CLI는 기본값 None으로 계속 동작해야 해.

테스트는 backend/tests/test_analysis_similarity_backtest.py를 만들고
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py -q 로 검증해.
마지막에 커밋까지 해줘. 다른 Task는 건드리지 마.
```

---

## Task 3 - CRUD Helpers and Background Job Endpoints

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 3: CRUD Helpers and Background Pipeline" 중 CRUD helper와 endpoint 부분만 실행해줘.
(Task 1, Task 2는 이미 커밋되어 있어야 해.)

핵심: backend/crud.py에 create_analysis_backtest_job, get_analysis_backtest_job,
get_analysis_backtest_jobs, update_analysis_backtest_job_done,
update_analysis_backtest_job_failed를 추가해.
backend/routers/analyses.py에 아래 endpoint를 추가해:
- POST /api/analyses/{analysis_id}/backtest-jobs
- GET /api/analyses/{analysis_id}/backtest-jobs

이 Task에서는 run_analysis_backtest_pipeline은 임시 failure stub으로 둬도 돼.
테스트는 backend/tests/test_analysis_backtest_jobs_router.py에 create/list endpoint 테스트를 추가하고,
BackgroundTasks는 monkeypatch로 실제 실행을 막아.
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py -q 가 통과해야 해.
마지막에 커밋까지 해줘. 다른 Task는 건드리지 마.
```

---

## Task 4 - End-to-End Pipeline Persistence

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 4: End-to-End Pipeline Persistence"만 TDD 단계대로 실행해줘.
(Task 1~3은 이미 커밋되어 있어야 해.)

핵심: backend/routers/analyses.py의 run_analysis_backtest_pipeline 임시 stub을 실제 wrapper로 교체해.
job과 analysis를 조회하고, _execute_analysis_backtest를 호출한 뒤 성공하면 done + backtest_run_id,
실패하면 failed + error_message로 저장해야 해.

scripts/backtest/analysis_similarity.py에는 run_analysis_similarity_backtest entrypoint를 추가해.
이 함수는 기준 analysis의 ticker/created_at으로 기준 profile을 만들고,
scripts/backtest/kospi200.csv universe 전체에 run_similarity_ticker를 돌린 뒤,
aggregate와 persist_run으로 기존 backtest_runs/backtest_signals/backtest_stats에 저장해야 해.
persist_run에는 source_analysis_id, strategy_kind="analysis_similarity",
similarity_threshold를 넘겨.

테스트는 backend/tests/test_analysis_backtest_jobs_router.py에 pipeline 완료 테스트를 추가하고,
_execute_analysis_backtest는 monkeypatch로 fake runner를 써서 빠르게 검증해.
.venv/Scripts/python.exe -m pytest backend/tests/test_analysis_backtest_jobs_router.py backend/tests/test_analysis_similarity_backtest.py -q
가 통과해야 해. 마지막에 커밋까지 해줘. 다른 Task는 건드리지 마.
```

---

## Task 5 - Backtest Run Metadata and Deep Link

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 5: Backtest Run Metadata and Query Parameter Selection"만 실행해줘.
(Task 1~4는 이미 커밋되어 있어야 해.)

핵심: 기존 /api/backtest/runs, /api/backtest/runs/{id} 응답에
source_analysis_id, strategy_kind, similarity_threshold가 포함되게 유지/검증해.
backend/tests/test_backtest_router.py의 seed run에 analysis_similarity metadata를 넣고
detail 응답에서 확인하는 assertion을 추가해.

프론트는 frontend/src/api/backtest.ts의 BacktestRunSummary 타입에 세 필드를 추가하고,
frontend/src/pages/BacktestPage.tsx가 /backtest?runId=123 query parameter를 읽어
해당 run을 기본 선택하게 만들어. analysis_similarity run이면 source analysis와 similarity threshold도
메타데이터로 표시해.

검증:
- .venv/Scripts/python.exe -m pytest backend/tests/test_backtest_router.py -q
- cd frontend && npm run build
마지막에 커밋까지 해줘. 다른 Task는 건드리지 마.
```

---

## Task 6 - Frontend API Client and Hooks

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 6: Analysis Backtest API Client and Hooks"만 실행해줘.
(Task 1~5는 이미 커밋되어 있어야 해.)

핵심: frontend/src/types/index.ts에 AnalysisBacktestJobStatus,
AnalysisBacktestJob, AnalysisBacktestJobCreate 타입을 추가해.
frontend/src/api/analysisBacktests.ts를 만들고:
- triggerAnalysisBacktest(analysisId, payload)
- fetchAnalysisBacktestJobs(analysisId)
를 구현해.

frontend/src/hooks/useAnalysisBacktests.ts를 만들고:
- analysisBacktestKeys
- useAnalysisBacktestJobs
- useTriggerAnalysisBacktest
를 구현해. pending job이 있으면 2초 polling하고, mutation 성공 시 해당 analysis job list와
backtest query를 invalidate해.

검증은 cd frontend && npm run build 로 하고, 마지막에 커밋까지 해줘.
다른 Task는 건드리지 마.
```

---

## Task 7 - Analysis Detail UI Panel

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 7: Analysis Detail UI Panel"만 실행해줘.
(Task 1~6은 이미 커밋되어 있어야 해.)

핵심: frontend/src/components/AnalysisBacktestPanel.tsx를 만들고 분석 상세 오른쪽 패널에
KOSPI200 유사도 백테스트 실행 UI를 추가해.
임계값은 8/9/10/11 segmented control로 선택하고 기본값은 9야.
실행 버튼은 pending 중 disabled 처리하고, latest job 상태 pending/done/failed를 보여줘.
done이면 /backtest?runId={backtest_run_id} 링크를 표시하고, failed면 error_message를 표시해.
여러 job이 있으면 최근 과거 job 링크 일부도 보여줘.

frontend/src/pages/AnalysisDetailPage.tsx에 AnalysisBacktestPanel을 import해서
오른쪽 컬럼 OutcomePanel 근처에 렌더링해.

검증은 cd frontend && npm run build 로 하고, 마지막에 커밋까지 해줘.
다른 Task는 건드리지 마.
```

---

## Task 8 - Integration Verification and Documentation

```
greed 프로젝트에서 Analysis Similarity Backtest 기능을 구현 중이야.
구현 계획은 docs/superpowers/plans/2026-05-24-analysis-similarity-backtest.md 에 있어.
그 계획의 "Task 8: Integration Verification and Documentation"만 실행해줘.
(Task 1~7은 이미 커밋되어 있어야 해.)

핵심: 영향 범위 테스트와 프론트 빌드를 한 번에 확인하고, docs/기능정의.md에
Analysis Similarity Backtest 설명을 짧게 추가해.

검증:
- .venv/Scripts/python.exe -m pytest backend/tests/test_analysis_similarity_backtest.py backend/tests/test_analysis_backtest_jobs_router.py backend/tests/test_backtest_router.py -q
- .venv/Scripts/python.exe -m pytest backend/tests/test_main.py backend/tests/test_jobs_router.py -q
- cd frontend && npm run build

가능하면 수동 smoke도 확인해:
분석 상세 -> threshold 9 선택 -> 백테스트 실행 -> pending 표시 -> 완료 후 Backtest Run 링크 ->
/backtest?runId=...에서 해당 run 선택.

문서 변경 후 커밋까지 해줘. 다른 Task는 건드리지 마.
```
